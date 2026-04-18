"""
Main entry point for AWS Cost Report
"""

import sys
import argparse
import json
import os
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
        self.execution_id = self.started_at.strftime("%Y-%m-%dT%H-%M-%S")
        self.steps = []
        self.status = "running"
        self.error = None
        # The runtime files are created before the report exists to preserve failure traces.
        self.output_dir = utils.ensure_output_dir()
        self.runtime_log_file = os.path.join(self.output_dir, f"execucao_{self.execution_id}.log")
        self.summary_file = os.path.join(self.output_dir, f"execucao_{self.execution_id}.json")
        self._emit_runtime_log("INFO", "execution_start", "Execution started.")

    def _emit_runtime_log(self, level, step_name, message):
        timestamp = datetime.now(timezone.utc).isoformat()
        line = f"{timestamp} | {level} | {step_name} | {message}"
        print(line)
        with open(self.runtime_log_file, "a", encoding="utf-8") as file_handle:
            file_handle.write(line + "\n")

    def run_step(self, step_name, fn):
        started_at = datetime.now(timezone.utc)
        perf_started_at = time.perf_counter()
        status = "ok"
        error = None
        self._emit_runtime_log("INFO", step_name, "started")
        try:
            return fn()
        except Exception as exc:
            status = "error"
            error = str(exc)
            self._emit_runtime_log("ERROR", step_name, f"failed: {error}")
            raise
        finally:
            duration_seconds = round(time.perf_counter() - perf_started_at, 4)
            finished_at = datetime.now(timezone.utc)
            self.steps.append(
                {
                    "name": step_name,
                    "started_at": started_at.isoformat(),
                    "finished_at": finished_at.isoformat(),
                    "duration_seconds": duration_seconds,
                    "status": status,
                    "error": error,
                }
            )
            if status == "ok":
                self._emit_runtime_log("INFO", step_name, f"finished in {duration_seconds:.4f}s")

    def build_summary(self, extra=None):
        finished_at = datetime.now(timezone.utc)
        summary = {
            "execution_id": self.execution_id,
            "started_at": self.started_at.isoformat(),
            "finished_at": finished_at.isoformat(),
            "total_duration_seconds": round((finished_at - self.started_at).total_seconds(), 4),
            "status": self.status,
            "error": self.error,
            "runtime_log_file": self.runtime_log_file,
            "steps": self.steps,
        }
        if extra:
            summary.update(extra)
        return summary

    def finalize(self, extra=None):
        with open(self.summary_file, "w", encoding="utf-8") as file_handle:
            json.dump(self.build_summary(extra=extra), file_handle, indent=2, ensure_ascii=False)
        self._emit_runtime_log(
            "INFO",
            "execution_finish",
            f"Execution {self.status}. Summary saved to {self.summary_file}",
        )

    def mark_execution_failed(self, error):
        self.status = "error"
        self.error = str(error)
        self._emit_runtime_log("ERROR", "execution_finish", f"Execution failed: {self.error}")

    def mark_execution_completed(self):
        self.status = "ok"


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


def _read_text_file(path):
    with open(path, "r", encoding="utf-8") as file_handle:
        return file_handle.read()


def _confirm_business_event_calendar_is_updated():
    """
    Fail closed when the operator cannot confirm that the business event calendar is current.
    """
    calendar_file = config.BUSINESS_EVENT_CALENDAR_FILE
    color_reset = "\033[0m"
    color_yellow = "\033[33m"
    color_cyan = "\033[36m"
    color_green = "\033[32m"
    color_bold = "\033[1m"
    color_underline = "\033[4m"
    prompt = (
        f"\n{color_bold}{color_yellow}Confirmacao obrigatoria antes da execucao:{color_reset}\n"
        f"{color_cyan}Voce esta com uma versao atualizada do arquivo "
        f"{color_green}{color_underline}'{calendar_file}'{color_reset}"
        f"{color_cyan}? [s/N]: {color_reset}"
    )

    try:
        answer = input(prompt).strip().lower()
    except EOFError as exc:
        raise RuntimeError(
            "Nao foi possivel confirmar a atualizacao da planilha de eventos/push em modo nao interativo."
        ) from exc

    if answer not in {"s", "sim", "y", "yes"}:
        raise RuntimeError(
            "Execucao cancelada: confirme a atualizacao da planilha de eventos/push antes de gerar o relatorio."
        )

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
        "--skip-calendar-confirmation",
        action="store_true",
        help="Skip the interactive confirmation about the business event calendar spreadsheet",
    )
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
    txt_file = None
    data_inicio = None
    data_fim = None
    ultimo_dia = None

    try:
        if args.skip_calendar_confirmation:
            execution_logger.run_step(
                "confirm_business_event_calendar",
                lambda: print(
                    "Skipping business event calendar confirmation because "
                    "--skip-calendar-confirmation was provided."
                ),
            )
        else:
            execution_logger.run_step(
                "confirm_business_event_calendar",
                _confirm_business_event_calendar_is_updated,
            )

        data_inicio, data_fim, ultimo_dia = execution_logger.run_step(
            "analysis_period",
            utils.get_analysis_period,
        )

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

        # The pivot is reused by the daily totals and service variation calculations.
        df_pivot = execution_logger.run_step(
            "build_daily_pivot",
            lambda: cost_analysis.build_daily_pivot(df_service),
        )

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

        custo_medio, custo_ultimo_dia, variacao_media, variacao_media_pct = execution_logger.run_step(
            "calculate_cost_metrics",
            lambda: cost_analysis.calculate_cost_metrics(df_periodo, ultimo_dia),
        )
        df_var, aumentaram, reduziram, top_costs = execution_logger.run_step(
            "calculate_service_variations",
            lambda: cost_analysis.calculate_service_variations(df_periodo, ultimo_dia),
        )

        sms_por_dia, total_sms_7d, media_sms_7d = execution_logger.run_step(
            "build_sms_last_7_days",
            lambda: cost_analysis.build_sms_last_7_days(df, ultimo_dia),
        )

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

        txt_file = execution_logger.run_step(
            "write_txt_report",
            lambda: txt_report.write_txt_report(
                data_inicio, data_fim, ultimo_dia, custo_medio, variacao_media,
                aumentaram, reduziram, top_costs, daily_costs, sms_por_dia, total_sms_7d,
                media_sms_7d, enriched_anomalies, daily_top_services, account_label
            ),
        )
        pdf_file = txt_file.replace(".txt", ".pdf")
        execution_logger.run_step(
            "write_main_pdf",
            lambda: pdf_report.write_cost_report_pdf(
                pdf_file,
                _read_text_file(txt_file),
                daily_costs=daily_costs,
                top_costs=top_costs,
                sms_por_dia=sms_por_dia,
                account_label=account_label,
            ),
        )
        print(f"Relatório PDF salvo em: {pdf_file}")
        execution_logger.run_step(
            "write_bedrock_context_txt",
            lambda: txt_report.write_bedrock_context_txt(txt_file, ultimo_dia, enriched_anomalies),
        )

        execution_logger.run_step(
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
                        lambda: pdf_report.write_ai_analysis_pdf(
                            ai_pdf_file,
                            f"AI Analysis\n\n{ai_analysis}",
                            report_data=report_data,
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

        execution_logger.mark_execution_completed()
    except Exception as exc:
        execution_logger.mark_execution_failed(exc)
        raise
    finally:
        summary_extra = {
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
        }
        execution_logger.finalize(extra=summary_extra)
        if txt_file:
            _write_execution_log(
                txt_file,
                execution_logger,
                extra=summary_extra,
            )

if __name__ == "__main__":
    main()
