#!/usr/bin/env python3
"""
Generate a 3-month AWS cost optimization report.

Coleta dados do Cost Explorer para todos os serviços, calcula tendências,
identifica oportunidades de otimização (com enriquecimento via AWS Compute Optimizer)
e gera relatório HTML, TXT e 3 CSVs. Suporta análise textual via Bedrock.
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
from collectors import compute_optimizer
from collectors import utilization_metrics
from analyzers import optimization_analysis
from integrations import bedrock
from renderers import optimization_report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Gera relatório de otimização de custos AWS com visão de 3 meses."
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
        help=f"Região dos workloads (usada pelo Compute Optimizer). Padrão: {config.WORKLOAD_REGION}",
    )
    parser.add_argument(
        "--months",
        type=int,
        default=config.OPTIMIZATION_REPORT_DEFAULT_MONTHS,
        help=f"Quantos meses analisar. Padrão: {config.OPTIMIZATION_REPORT_DEFAULT_MONTHS}",
    )
    parser.add_argument(
        "--end-date",
        default=None,
        help="Data final da análise (YYYY-MM-DD). Padrão: hoje menos OFFSET_DAYS.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(config.OUTPUT_DIR),
        help=f"Diretório base de saída. Padrão: {config.OUTPUT_DIR}",
    )
    parser.add_argument(
        "--enable-bedrock",
        action="store_true",
        help="Habilita análise textual via AWS Bedrock.",
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
    parser.add_argument(
        "--skip-compute-optimizer",
        action="store_true",
        help="Pula coleta do AWS Compute Optimizer (útil quando sem permissão).",
    )
    parser.add_argument(
        "--skip-utilization",
        action="store_true",
        help="Pula coleta de métricas de utilização (EC2 CPU, RDS conexões, ELB tráfego, EBS, EIP).",
    )
    return parser.parse_args()


def _build_date_window(months: int, end_date_str: str | None) -> tuple[str, str]:
    """Calcula janela de datas: end_date - months meses até end_date."""
    if end_date_str:
        end_dt = datetime.strptime(end_date_str, "%Y-%m-%d").date()
    else:
        end_dt = date.today() - timedelta(days=config.OFFSET_DAYS)

    # Aproximação: months × 30 dias
    start_dt = end_dt - timedelta(days=months * 30)
    return start_dt.isoformat(), end_dt.isoformat()


def _load_optimization_prompt() -> str:
    """Carrega prompt de otimização isolado do fluxo diário."""
    prompt_path = Path(__file__).resolve().parents[1] / "prompts" / "optimization_analysis.txt"
    return prompt_path.read_text(encoding="utf-8").strip()


def _build_optimization_bedrock_prompt(payload: dict) -> str:
    """Monta prompt final enviado ao Bedrock para análise de otimização."""
    template = _load_optimization_prompt()
    return (
        f"{template}\n\n"
        f"Contexto operacional consolidado:\n{config.BEDROCK_CONTEXT}\n\n"
        f"{json.dumps(payload, indent=2, ensure_ascii=False)}"
    )


def main() -> None:
    args = parse_args()

    # Aplica configurações ao módulo config (padrão do projeto)
    config.AWS_PROFILE = args.aws_profile or None
    config.COST_EXPLORER_REGION = args.cost_explorer_region
    config.WORKLOAD_REGION = args.workload_region
    config.BEDROCK_REGION = args.bedrock_region
    config.BEDROCK_MODEL_ID = args.bedrock_model
    config.ENABLE_BEDROCK = args.enable_bedrock

    start_date, end_date = _build_date_window(args.months, args.end_date)

    output_base = (
        Path(args.output_dir)
        / config.OPTIMIZATION_REPORT_OUTPUT_SUBDIR
        / f"{start_date}_to_{end_date}"
    )
    output_base.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("RELATÓRIO DE OTIMIZAÇÃO DE CUSTOS AWS")
    print(f"Período:  {start_date} a {end_date} (~{args.months} meses)")
    print(f"Saída:    {output_base}")
    print("=" * 60)

    # 1. Coleta de custos (Cost Explorer)
    print("\n[1/5] Coletando dados do Cost Explorer...")
    df = cost_explorer.fetch_cost_drivers_from_cost_explorer(start_date, end_date)
    if df.empty:
        print("Nenhum dado retornado pelo Cost Explorer. Encerrando.")
        return

    # 2. Compute Optimizer
    optimizer_recs = []
    if not args.skip_compute_optimizer:
        print("\n[2/5] Coletando recomendações do Compute Optimizer...")
        optimizer_recs = compute_optimizer.collect_all_recommendations()
    else:
        print("\n[2/5] Compute Optimizer: pulado (--skip-compute-optimizer).")

    # 2b. Métricas de utilização real (EC2 CPU, RDS conexões, ELB, EBS, EIP)
    utilization = {}
    if not args.skip_utilization:
        print("\n[2b] Coletando métricas de utilização real...")
        utilization = utilization_metrics.collect_all_utilization(start_date, end_date)
        print(f"  EC2: {len(utilization.get('ec2', []))} instâncias")
        print(f"  RDS: {len(utilization.get('rds', []))} instâncias")
        print(f"  ELB: {len(utilization.get('elb', []))} load balancers")
        print(f"  EBS: {len(utilization.get('ebs', []))} volumes")
        print(f"  EIP: {len(utilization.get('eip', []))} IPs ociosos")
    else:
        print("\n[2b] Métricas de utilização: puladas (--skip-utilization).")

    # 3. Análise
    print("\n[3/5] Calculando tendências e oportunidades de otimização...")
    df_service_trends = optimization_analysis.build_service_trends(df, start_date, end_date)
    print(f"  Serviços analisados: {len(df_service_trends)}")

    unit_economics = optimization_analysis.build_unit_economics(df, start_date, end_date)
    print(f"  Custo médio/dia: US$ {unit_economics['daily_avg_usd']:.2f}")

    opportunities = optimization_analysis.build_optimization_opportunities(
        df_raw=df,
        df_service_trends=df_service_trends,
        optimizer_recs=optimizer_recs,
        utilization=utilization,
    )
    total_savings = sum(o["economia_estimada_usd_mes"] for o in opportunities)
    print(f"  Oportunidades identificadas: {len(opportunities)}")
    print(f"  Economia potencial total: US$ {total_savings:,.2f}/mês")

    # 4. Payload e Bedrock
    print("\n[4/5] Montando payload e análise textual...")
    payload = optimization_analysis.build_optimization_payload(
        df_service_trends=df_service_trends,
        opportunities=opportunities,
        unit_economics=unit_economics,
        start_date=start_date,
        end_date=end_date,
        df_raw=df,
    )

    # Adiciona resumo de utilização ao payload para enriquecer a análise Bedrock
    if utilization:
        payload["utilization_summary"] = {
            "ec2_total": len(utilization.get("ec2", [])),
            "ec2_underutilized": len([i for i in utilization.get("ec2", []) if i.get("investigation_candidate")]),
            "ec2_rightsize_candidates": len([i for i in utilization.get("ec2", []) if i.get("rightsize_candidate")]),
            "rds_total": len(utilization.get("rds", [])),
            "rds_idle": len([db for db in utilization.get("rds", []) if db.get("idle")]),
            "elb_total": len(utilization.get("elb", [])),
            "elb_idle": len([lb for lb in utilization.get("elb", []) if lb.get("idle") or lb.get("no_data")]),
            "ebs_unattached": len([v for v in utilization.get("ebs", []) if v.get("unattached")]),
            "ebs_gp2_eligible": len([v for v in utilization.get("ebs", []) if v.get("gp2_eligible_for_gp3")]),
            "eip_idle": len(utilization.get("eip", [])),
        }

    payload_path = output_base / f"relatorio_otimizacao_{end_date}_analysis_payload.json"
    payload_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    prompt_text = _build_optimization_bedrock_prompt(payload)
    prompt_path = output_base / f"relatorio_otimizacao_{end_date}_analysis_prompt.txt"
    prompt_path.write_text(prompt_text, encoding="utf-8")

    analysis_text = None
    if config.ENABLE_BEDROCK:
        print("  Chamando Bedrock para análise textual...")
        try:
            result = bedrock.analyze_prompt_with_bedrock(prompt_text)
            analysis_text = result.get("text", "")
            meta = result.get("metadata", {})
            analysis_path = output_base / f"relatorio_otimizacao_{end_date}_analysis.txt"
            meta_path = output_base / f"relatorio_otimizacao_{end_date}_analysis_meta.json"
            analysis_path.write_text(analysis_text or "", encoding="utf-8")
            meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"  Análise textual gerada: {len(analysis_text or '')} caracteres")
        except Exception as exc:
            error_path = output_base / f"relatorio_otimizacao_{end_date}_analysis_error.txt"
            error_path.write_text(str(exc), encoding="utf-8")
            print(f"  Bedrock falhou: {exc}")
    else:
        print("  Bedrock desabilitado (use --enable-bedrock para ativar).")

    # 5. Renderização
    print("\n[5/5] Gerando artefatos...")
    optimization_report.write_optimization_html_report(
        output_dir=output_base,
        start_date=start_date,
        end_date=end_date,
        df_service_trends=df_service_trends,
        opportunities=opportunities,
        unit_economics=unit_economics,
        analysis_text=analysis_text,
    )
    optimization_report.write_optimization_txt_report(
        output_dir=output_base,
        start_date=start_date,
        end_date=end_date,
        df_service_trends=df_service_trends,
        opportunities=opportunities,
        unit_economics=unit_economics,
        analysis_text=analysis_text,
    )
    optimization_report.write_optimization_csvs(
        output_dir=output_base,
        end_date=end_date,
        df_service_trends=df_service_trends,
        opportunities=opportunities,
        unit_economics=unit_economics,
    )

    print("\n" + "=" * 60)
    print("CONCLUÍDO")
    print(f"Artefatos em: {output_base}")
    print("=" * 60)


if __name__ == "__main__":
    main()
