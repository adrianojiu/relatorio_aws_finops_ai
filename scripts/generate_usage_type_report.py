#!/usr/bin/env python3
"""
Generate an independent UsageType variation report over a custom date range.
The output is written to output/usage_type_report/<start_date>_to_<end_date>/.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parents[1] / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

import config
from collectors import cost_explorer
from analyzers import cost_analysis
from integrations import bedrock
from renderers import usage_type_report


def parse_date(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"Data inválida: '{value}'. Use o formato YYYY-MM-DD."
        ) from exc


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Gera relatório independente de UsageType e variação de custo por janela de datas."
    )
    parser.add_argument(
        "--aws-profile",
        default=config.AWS_PROFILE,
        help=f"Perfil AWS CLI. Padrão: {config.AWS_PROFILE}",
    )
    parser.add_argument(
        "--cost-explorer-region",
        default=config.COST_EXPLORER_REGION,
        help=f"Região do Cost Explorer. Padrão: {config.COST_EXPLORER_REGION}",
    )
    parser.add_argument(
        "--start-date",
        type=parse_date,
        help="Data inicial da janela no formato YYYY-MM-DD. Se omitido, será calculado a partir de --end-date ou do padrão de 30 dias.",
    )
    parser.add_argument(
        "--end-date",
        type=parse_date,
        help="Data final da janela no formato YYYY-MM-DD. Se omitido, usa hoje menos OFFSET_DAYS.",
    )
    parser.add_argument(
        "--min-total-usd",
        type=float,
        default=config.USAGE_TYPE_REPORT_MIN_TOTAL_USD,
        help=f"Filtro mínimo de custo total do UsageType no período. Padrão: {config.USAGE_TYPE_REPORT_MIN_TOTAL_USD}",
    )
    parser.add_argument(
        "--output-dir",
        default=str(config.OUTPUT_DIR),
        help=f"Diretório base de saída. Padrão: {config.OUTPUT_DIR}",
    )
    parser.add_argument(
        "--enable-bedrock",
        action="store_true",
        help="Habilita a análise textual opcional do relatório.",
    )
    parser.add_argument(
        "--bedrock-region",
        default=config.BEDROCK_REGION,
        help=f"Região do Bedrock. Padrão: {config.BEDROCK_REGION}",
    )
    parser.add_argument(
        "--bedrock-model",
        default=config.BEDROCK_MODEL_ID,
        help=f"Modelo Bedrock. Padrão: {config.BEDROCK_MODEL_ID}",
    )
    return parser.parse_args()


def _load_usage_type_prompt() -> str:
    """Carrega um prompt próprio para manter o fluxo de UsageType isolado."""
    prompt_path = Path(__file__).resolve().parents[1] / "prompts" / "usage_type_analysis.txt"
    return prompt_path.read_text(encoding="utf-8").strip()


def _build_usage_type_analysis_prompt(report_payload: dict, context_operational: str) -> str:
    """Monta o prompt final usado apenas pela análise textual deste relatório."""
    return (
        f"{_load_usage_type_prompt()}\n\n"
        f"Contexto operacional consolidado:\n{context_operational}\n\n"
        f"{json.dumps(report_payload, indent=2, ensure_ascii=False)}"
    )


def build_date_window(start_date: date | None, end_date: date | None) -> tuple[str, str]:
    if end_date is None:
        end_date = date.today() - timedelta(days=config.OFFSET_DAYS)

    if start_date is None:
        start_date = end_date - timedelta(days=config.USAGE_TYPE_REPORT_DEFAULT_WINDOW_DAYS - 1)

    if start_date > end_date:
        raise ValueError("start_date must be before or equal to end_date")

    days = (end_date - start_date).days + 1
    # O limite é opcional porque o relatório foi projetado para janelas customizadas.
    if (
        config.USAGE_TYPE_REPORT_MAX_RANGE_DAYS is not None
        and days > config.USAGE_TYPE_REPORT_MAX_RANGE_DAYS
    ):
        raise ValueError(
            f"Date range cannot exceed {config.USAGE_TYPE_REPORT_MAX_RANGE_DAYS} days"
        )

    return start_date.isoformat(), end_date.isoformat()


def main() -> None:
    args = parse_args()

    if args.start_date and not args.end_date:
        raise SystemExit("--start-date requires --end-date when provided.")

    try:
        start_date, end_date = build_date_window(args.start_date, args.end_date)
    except ValueError as exc:
        raise SystemExit(str(exc))

    output_base = Path(args.output_dir) / config.USAGE_TYPE_REPORT_OUTPUT_SUBDIR / f"{start_date}_to_{end_date}"
    output_base.mkdir(parents=True, exist_ok=True)

    print(
        f"Gerando relatório UsageType de {start_date} até {end_date} "
        f"(min_total_usd={args.min_total_usd:.2f})"
    )

    config.AWS_PROFILE = args.aws_profile or None
    config.COST_EXPLORER_REGION = args.cost_explorer_region
    config.BEDROCK_REGION = args.bedrock_region
    config.BEDROCK_MODEL_ID = args.bedrock_model
    config.ENABLE_BEDROCK = args.enable_bedrock

    df = cost_explorer.fetch_cost_drivers_from_cost_explorer(start_date, end_date)
    df_report = cost_analysis.build_usage_type_variation_report(
        df=df,
        start_date=start_date,
        end_date=end_date,
        min_total_usd=args.min_total_usd,
    )

    report_labels, forecast_labels, usage_type_chart_data, total_daily_values = (
        cost_analysis.build_usage_type_daily_trend(df, start_date, end_date)
    )
    _, variation_pct_chart_data = cost_analysis.build_usage_type_daily_variation_pct_trend(
        df, start_date, end_date, df_report=df_report
    )
    variation_chart_data = cost_analysis.build_usage_type_variation_percent_chart_data(df_report)

    # Detecção de anomalias — injeta índices nos datasets do gráfico diário.
    anomaly_data = cost_analysis.build_anomaly_data(df, start_date, end_date)
    for item in usage_type_chart_data:
        item["anomaly_indices"] = anomaly_data["by_label"].get(item["UsageType"], [])

    # Padrão semanal de custo.
    weekly_labels, weekly_data = cost_analysis.build_weekly_pattern(df, start_date, end_date)

    analysis_payload = cost_analysis.build_usage_type_analysis_payload(
        df_report=df_report,
        start_date=start_date,
        end_date=end_date,
        min_total_usd=args.min_total_usd,
        top_anomalies=anomaly_data["top_anomalies"],
        weekly_pattern_data=weekly_data,
    )
    analysis_prompt = _build_usage_type_analysis_prompt(
        analysis_payload,
        config.BEDROCK_CONTEXT,
    )
    analysis_text = None

    analysis_payload_file = output_base / f"relatorio_usagetype_{end_date}_analysis_payload.json"
    analysis_prompt_file = output_base / f"relatorio_usagetype_{end_date}_analysis_prompt.txt"
    analysis_payload_file.write_text(
        json.dumps(analysis_payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    analysis_prompt_file.write_text(analysis_prompt, encoding="utf-8")

    if config.ENABLE_BEDROCK:
        print("Gerando análise textual do relatório...")
        analysis_result = bedrock.analyze_prompt_with_bedrock(analysis_prompt)
        analysis_text = (analysis_result or {}).get("text")
        analysis_meta = (analysis_result or {}).get("metadata") or {}
        (output_base / f"relatorio_usagetype_{end_date}_analysis.txt").write_text(
            analysis_text or "",
            encoding="utf-8",
        )
        (output_base / f"relatorio_usagetype_{end_date}_analysis_meta.json").write_text(
            json.dumps(analysis_meta, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    txt_file = usage_type_report.write_usage_type_txt_report(
        str(output_base), start_date, end_date, df_report, args.min_total_usd, analysis_text=analysis_text
    )
    html_file = usage_type_report.write_usage_type_html_report(
        str(output_base), start_date, end_date, df_report,
        report_labels, forecast_labels, usage_type_chart_data,
        total_daily_values, variation_chart_data, variation_pct_chart_data,
        anomaly_data["top_anomalies"], weekly_labels, weekly_data,
        analysis_text=analysis_text,
    )

    print("Relatório de UsageType gerado com sucesso.")
    print(f"TXT: {txt_file}")
    print(f"HTML: {html_file}")


if __name__ == "__main__":
    main()
