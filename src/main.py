"""
Main entry point for AWS Cost Report
"""

import sys
import argparse
import json
import time
import unicodedata
from datetime import datetime, timezone
import config
import utils
from collectors import business_events, cost_explorer, csv_input
from analyzers import cost_analysis, anomaly_detection, correlation_analysis
from renderers import txt_report, excel_report, pdf_report
from integrations import bedrock


def _normalize_completion_text(text):
    normalized = unicodedata.normalize("NFKD", text or "")
    return normalized.encode("ascii", "ignore").decode("ascii").upper()


def _ai_analysis_completed(ai_analysis):
    return "ANALISE CONCLUIDA" in _normalize_completion_text(ai_analysis)


def _build_ai_completion_warning(ai_analysis, ai_metadata):
    warning_lines = [
        "WARNING: AI report may be incomplete or truncated.",
        "The marker 'ANALISE CONCLUIDA' was not found in the generated analysis.",
    ]

    provider = ai_metadata.get("provider")
    if provider == "anthropic":
        stop_reason = ai_metadata.get("stop_reason")
        if stop_reason:
            warning_lines.append(f"Bedrock stop_reason: {stop_reason}")
        usage = ai_metadata.get("usage") or {}
        output_tokens = usage.get("output_tokens")
        if output_tokens is not None:
            warning_lines.append(f"Output tokens used: {output_tokens}")
    elif provider in {"amazon_nova", "meta_llama"}:
        stop_reason = ai_metadata.get("stop_reason")
        if stop_reason:
            warning_lines.append(f"Bedrock stop_reason: {stop_reason}")
    elif provider in {"openai", "deepseek"}:
        finish_reasons = ai_metadata.get("finish_reasons") or []
        if finish_reasons:
            warning_lines.append(f"Finish reasons: {', '.join(str(item) for item in finish_reasons)}")

    warning_lines.append(
        "Possible causes: insufficient max tokens, model interruption, or provider-side generation failure."
    )

    if ai_analysis:
        tail = ai_analysis.strip()[-160:]
        if tail:
            warning_lines.append(f"Analysis tail: {tail}")

    return "\n".join(warning_lines)


class ExecutionLogger:
    def __init__(self):
        self.started_at = datetime.now(timezone.utc)
        self.steps = []

    def run_step(self, step_name, fn):
        started_at = datetime.now(timezone.utc)
        perf_started_at = time.perf_counter()
        status = "ok"
        error = None
        try:
            return fn()
        except Exception as exc:
            status = "error"
            error = str(exc)
            raise
        finally:
            finished_at = datetime.now(timezone.utc)
            self.steps.append(
                {
                    "name": step_name,
                    "started_at": started_at.isoformat(),
                    "finished_at": finished_at.isoformat(),
                    "duration_seconds": round(time.perf_counter() - perf_started_at, 4),
                    "status": status,
                    "error": error,
                }
            )

    def build_summary(self, extra=None):
        finished_at = datetime.now(timezone.utc)
        summary = {
            "started_at": self.started_at.isoformat(),
            "finished_at": finished_at.isoformat(),
            "total_duration_seconds": round((finished_at - self.started_at).total_seconds(), 4),
            "steps": self.steps,
        }
        if extra:
            summary.update(extra)
        return summary


def _write_execution_log(base_txt_file, execution_logger, extra=None):
    execution_log_file = base_txt_file.replace(".txt", "_execution_log.json")
    with open(execution_log_file, "w", encoding="utf-8") as file_handle:
        json.dump(execution_logger.build_summary(extra=extra), file_handle, indent=2, ensure_ascii=False)
    print(f"Execution log saved to {execution_log_file}")


def _write_json_file(path, payload):
    with open(path, "w", encoding="utf-8") as file_handle:
        json.dump(payload, file_handle, indent=2, ensure_ascii=False)


def _write_text_file(path, content):
    with open(path, "w", encoding="utf-8") as file_handle:
        file_handle.write(content)

def main():
    parser = argparse.ArgumentParser(description="Generate AWS Cost Reports")
    parser.add_argument("--source", choices=["cost-explorer", "csv"], default="cost-explorer",
                       help="Data source: cost-explorer or csv")
    parser.add_argument("--csv-file", help="CSV file path (required if source is csv)")
    parser.add_argument("--aws-profile", help="Override the AWS profile for this execution")
    parser.add_argument("--aws-region", help="Override the workload AWS region for this execution")
    parser.add_argument("--cost-explorer-region", help="Override the AWS Cost Explorer region for this execution")
    parser.add_argument("--bedrock-region", help="Override the Bedrock region for this execution")
    parser.add_argument("--enable-bedrock", action="store_true", help="Enable Bedrock AI analysis")
    parser.add_argument(
        "--bedrock-model",
        help="Override the Bedrock model ID for this execution",
    )

    args = parser.parse_args()

    if args.enable_bedrock:
        config.ENABLE_BEDROCK = True
    if args.aws_profile:
        config.AWS_PROFILE = args.aws_profile
    if args.aws_region:
        config.AWS_REGION = args.aws_region
        config.WORKLOAD_REGION = args.aws_region
    if args.cost_explorer_region:
        config.COST_EXPLORER_REGION = args.cost_explorer_region
    if args.bedrock_region:
        config.BEDROCK_REGION = args.bedrock_region
    if args.bedrock_model:
        config.BEDROCK_MODEL_ID = args.bedrock_model

    execution_logger = ExecutionLogger()

    # Get analysis period
    data_inicio, data_fim, ultimo_dia = execution_logger.run_step(
        "analysis_period",
        utils.get_analysis_period,
    )

    # Collect data
    if args.source == "cost-explorer":
        print(
            "Using AWS profile: "
            f"{config.AWS_PROFILE} | "
            f"workload region: {config.WORKLOAD_REGION} | "
            f"cost explorer region: {config.COST_EXPLORER_REGION} | "
            f"bedrock region: {config.BEDROCK_REGION}"
        )
        df = execution_logger.run_step(
            "cost_explorer_fetch",
            lambda: cost_explorer.fetch_cost_drivers_from_cost_explorer(data_inicio, data_fim),
        )
    elif args.source == "csv":
        if not args.csv_file:
            print("Error: --csv-file is required when source is csv")
            sys.exit(1)
        df = execution_logger.run_step(
            "csv_load",
            lambda: csv_input.load_csv_data(args.csv_file),
        )
        data_inicio, data_fim, ultimo_dia = execution_logger.run_step(
            "align_period_to_available_data",
            lambda: utils.align_period_to_available_data(df, data_inicio, data_fim, ultimo_dia),
        )

    df_service = execution_logger.run_step(
        "build_service_dataframe",
        lambda: (
            df.groupby(["Data", "Serviço"], as_index=False)["Custo($)"]
            .sum()
            .sort_values(["Data", "Serviço"])
        ),
    )

    # Build pivot
    df_pivot = execution_logger.run_step(
        "build_daily_pivot",
        lambda: cost_analysis.build_daily_pivot(df_service),
    )

    # Filter period
    def _prepare_period_views():
        df_periodo_local = df_pivot[(df_pivot["Service"] >= data_inicio) & (df_pivot["Service"] <= data_fim)].copy()
        total_por_dia = df_periodo_local.drop(columns=["Service"]).sum(axis=1)
        df_periodo_local["Total costs($)"] = total_por_dia
        daily_costs_local = [
            (str(row["Service"]), float(row["Total costs($)"]))
            for _, row in df_periodo_local[["Service", "Total costs($)"]].iterrows()
        ]
        account_label_local = utils.get_aws_account_label() if args.source == "cost-explorer" else "fonte CSV"
        daily_top_services_local = {}
        df_service_period = df_service[(df_service["Data"] >= data_inicio) & (df_service["Data"] <= data_fim)].copy()
        for date_value, daily_group in df_service_period.groupby("Data"):
            top_services_for_day = (
                daily_group.sort_values("Custo($)", ascending=False)
                .head(config.TOP_N_DAILY_SERVICES)[["Serviço", "Custo($)"]]
                .values.tolist()
            )
            daily_top_services_local[str(date_value)] = [
                (str(service).replace("($)", ""), float(cost))
                for service, cost in top_services_for_day
            ]
        return df_periodo_local, daily_costs_local, account_label_local, daily_top_services_local

    df_periodo, daily_costs, account_label, daily_top_services = execution_logger.run_step(
        "prepare_period_views",
        _prepare_period_views,
    )

    # Calculate metrics
    custo_medio, custo_ultimo_dia, variacao_media, variacao_media_pct = execution_logger.run_step(
        "calculate_cost_metrics",
        lambda: cost_analysis.calculate_cost_metrics(df_periodo, ultimo_dia),
    )
    df_var, aumentaram, reduziram, top_costs = execution_logger.run_step(
        "calculate_service_variations",
        lambda: cost_analysis.calculate_service_variations(df_periodo, ultimo_dia),
    )

    # SMS analysis
    sms_por_dia, total_sms_7d, media_sms_7d = execution_logger.run_step(
        "build_sms_last_7_days",
        lambda: cost_analysis.build_sms_last_7_days(df, ultimo_dia),
    )

    # Usage type anomalies and resource correlation
    timeseries_df = execution_logger.run_step(
        "build_usage_type_timeseries",
        lambda: anomaly_detection.build_usage_type_timeseries(df),
    )
    anomalies = execution_logger.run_step(
        "calculate_anomalies",
        lambda: anomaly_detection.calculate_anomalies(timeseries_df, data_inicio, data_fim, ultimo_dia),
    )
    anomalies = execution_logger.run_step(
        "enrich_sms_complementary_usage_types",
        lambda: anomaly_detection.enrich_sms_complementary_usage_types(
            anomalies,
            timeseries_df,
            ultimo_dia,
        ),
    )
    relevant_anomalies = execution_logger.run_step(
        "filter_relevant_anomalies",
        lambda: anomaly_detection.filter_relevant_anomalies(anomalies),
    )
    enriched_anomalies = execution_logger.run_step(
        "resource_enrichment",
        lambda: correlation_analysis.enrich_anomalies(
            relevant_anomalies,
            start_date=data_inicio,
            end_date=data_fim,
            anchor_day=ultimo_dia,
            enable_aws_lookup=(args.source == "cost-explorer"),
        ),
    )
    business_event_calendar = execution_logger.run_step(
        "load_business_event_calendar",
        lambda: business_events.load_business_event_calendar(
            start_date=data_inicio,
            end_date=data_fim,
            reference_day=ultimo_dia,
        ),
    )

    # Generate reports
    txt_file = execution_logger.run_step(
        "write_txt_report",
        lambda: txt_report.write_txt_report(
            data_inicio, data_fim, ultimo_dia, custo_medio, variacao_media,
            aumentaram, reduziram, top_costs, daily_costs, sms_por_dia, total_sms_7d,
            media_sms_7d, enriched_anomalies, daily_top_services, account_label
        ),
    )
    bedrock_context_txt = execution_logger.run_step(
        "write_bedrock_context_txt",
        lambda: txt_report.write_bedrock_context_txt(txt_file, ultimo_dia, enriched_anomalies),
    )

    excel_file = execution_logger.run_step(
        "write_excel_report",
        lambda: excel_report.write_excel_report(
            data_inicio, data_fim, ultimo_dia, custo_medio, variacao_media,
            aumentaram, reduziram, top_costs, daily_costs, sms_por_dia, total_sms_7d,
            media_sms_7d, enriched_anomalies
        ),
    )

    report_data = execution_logger.run_step(
        "build_bedrock_payload",
        lambda: correlation_analysis.build_bedrock_payload(
            data_inicio=data_inicio,
            data_fim=data_fim,
            ultimo_dia=ultimo_dia,
            custo_medio=custo_medio,
            custo_ultimo_dia=custo_ultimo_dia,
            variacao_media=variacao_media,
            variacao_media_pct=variacao_media_pct,
            daily_costs=daily_costs,
            top_costs=top_costs,
            enriched_anomalies=enriched_anomalies,
            contexto_operacional=config.CONTEXT_OPERATIONAL,
            business_event_calendar=business_event_calendar,
        ),
    )
    payload_file = txt_file.replace(".txt", "_bedrock_payload.json")
    execution_logger.run_step(
        "write_bedrock_payload",
        lambda: _write_json_file(payload_file, report_data),
    )

    prompt_file = txt_file.replace(".txt", "_bedrock_prompt.txt")
    execution_logger.run_step(
        "write_bedrock_prompt",
        lambda: _write_text_file(
            prompt_file,
            bedrock.build_bedrock_prompt(report_data, config.CONTEXT_OPERATIONAL),
        ),
    )

    print(f"Bedrock payload saved to {payload_file}")
    print(f"Bedrock prompt saved to {prompt_file}")

    # Bedrock analysis
    if config.ENABLE_BEDROCK:
        print(f"Using Bedrock model: {config.BEDROCK_MODEL_ID}")
        try:
            ai_result = execution_logger.run_step(
                "bedrock_inference",
                lambda: bedrock.analyze_with_bedrock(report_data, config.CONTEXT_OPERATIONAL),
            )
            ai_analysis = ai_result.get("text")
            ai_metadata = ai_result.get("metadata", {})
            if ai_analysis:
                execution_logger.run_step(
                    "write_ai_text",
                    lambda: _write_text_file(
                        txt_file.replace(".txt", "_ai.txt"),
                        "AI Analysis:\n" + ai_analysis,
                    ),
                )
                print(f"AI analysis saved to {txt_file.replace('.txt', '_ai.txt')}")
                ai_pdf_file = txt_file.replace(".txt", "_ai.pdf")
                execution_logger.run_step(
                    "write_ai_pdf",
                    lambda: pdf_report.write_text_pdf(
                        ai_pdf_file,
                        f"AI Analysis\n\n{ai_analysis}",
                        account_label=utils.get_aws_account_label(),
                    ),
                )
                print(f"AI analysis PDF saved to {ai_pdf_file}")
            meta_file = txt_file.replace(".txt", "_ai_meta.json")
            execution_logger.run_step(
                "write_ai_metadata",
                lambda: _write_json_file(meta_file, ai_metadata),
            )
            print(f"AI metadata saved to {meta_file}")
            if not _ai_analysis_completed(ai_analysis):
                print(_build_ai_completion_warning(ai_analysis, ai_metadata))
        except Exception as exc:
            error_file = txt_file.replace(".txt", "_ai_error.txt")
            with open(error_file, "w", encoding="utf-8") as f:
                f.write("Bedrock invocation failed.\n")
                f.write(f"Model: {config.BEDROCK_MODEL_ID}\n")
                f.write(f"Error: {exc}\n")
            print(f"Bedrock invocation failed: {exc}")
            print(f"Bedrock error saved to {error_file}")

    _write_execution_log(
        txt_file,
        execution_logger,
        extra={
            "source": args.source,
            "aws_profile": config.AWS_PROFILE,
            "workload_region": config.WORKLOAD_REGION,
            "cost_explorer_region": config.COST_EXPLORER_REGION,
            "bedrock_region": config.BEDROCK_REGION,
            "bedrock_enabled": config.ENABLE_BEDROCK,
            "bedrock_model_id": config.BEDROCK_MODEL_ID if config.ENABLE_BEDROCK else None,
            "analysis_period": {
                "start": data_inicio,
                "end": data_fim,
                "reference_day": ultimo_dia,
            },
        },
    )

if __name__ == "__main__":
    main()
