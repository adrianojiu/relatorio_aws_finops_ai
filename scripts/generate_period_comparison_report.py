#!/usr/bin/env python3
"""
Generate an HTML report comparing AWS cost between two arbitrary date periods.
The output is written to output/period_comparison/<period_a>_vs_<period_b>/.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date, datetime
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parents[1] / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

import config
from collectors import cost_explorer
from renderers import period_comparison_report
from utils import get_aws_account_label


def parse_date(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"Data inválida: '{value}'. Use o formato YYYY-MM-DD."
        ) from exc


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Gera relatório HTML comparando custo AWS entre dois períodos arbitrários."
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
        "--workload-region",
        default=config.WORKLOAD_REGION,
        help=f"Região usada para resolver conta/alias no cabeçalho. Padrão: {config.WORKLOAD_REGION}",
    )
    parser.add_argument(
        "--period-a-start", required=True, type=parse_date,
        help="Data inicial do período A (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--period-a-end", required=True, type=parse_date,
        help="Data final do período A (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--period-b-start", required=True, type=parse_date,
        help="Data inicial do período B (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--period-b-end", required=True, type=parse_date,
        help="Data final do período B (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--output-dir",
        default=str(config.OUTPUT_DIR),
        help=f"Diretório base de saída. Padrão: {config.OUTPUT_DIR}",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.period_a_start > args.period_a_end:
        raise SystemExit("--period-a-start deve ser anterior ou igual a --period-a-end.")
    if args.period_b_start > args.period_b_end:
        raise SystemExit("--period-b-start deve ser anterior ou igual a --period-b-end.")

    period_a_start = args.period_a_start.isoformat()
    period_a_end = args.period_a_end.isoformat()
    period_b_start = args.period_b_start.isoformat()
    period_b_end = args.period_b_end.isoformat()

    config.AWS_PROFILE = args.aws_profile or None
    config.COST_EXPLORER_REGION = args.cost_explorer_region
    config.WORKLOAD_REGION = args.workload_region

    output_dir = (
        Path(args.output_dir)
        / config.PERIOD_COMPARISON_OUTPUT_SUBDIR
        / f"{period_a_start}_{period_a_end}_vs_{period_b_start}_{period_b_end}"
    )

    print(f"Coletando período A: {period_a_start} a {period_a_end}")
    df_a = cost_explorer.fetch_cost_drivers_from_cost_explorer(period_a_start, period_a_end)
    print(f"Coletando período B: {period_b_start} a {period_b_end}")
    df_b = cost_explorer.fetch_cost_drivers_from_cost_explorer(period_b_start, period_b_end)

    account_label = get_aws_account_label()

    html_file = period_comparison_report.write_period_comparison_html(
        output_dir=str(output_dir),
        period_a_start=period_a_start,
        period_a_end=period_a_end,
        period_b_start=period_b_start,
        period_b_end=period_b_end,
        df_a=df_a,
        df_b=df_b,
        account_label=account_label,
        region_label=config.WORKLOAD_REGION,
        period_a_label=f"{period_a_start} a {period_a_end}",
        period_b_label=f"{period_b_start} a {period_b_end}",
    )

    print("Relatório comparativo gerado com sucesso.")
    print(f"HTML: {html_file}")


if __name__ == "__main__":
    main()
