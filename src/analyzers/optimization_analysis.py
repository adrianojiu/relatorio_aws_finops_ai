"""
Optimization analysis: trends, opportunity mapping, ranking and unit economics.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

import numpy as np
import pandas as pd

import config


# ============================================================
# Tendência e comportamento por serviço
# ============================================================

def _slope_usd_per_day(series: pd.Series) -> float:
    """Regressão linear simples para calcular tendência (US$/dia)."""
    if len(series) < 2:
        return 0.0
    x = np.arange(len(series), dtype=float)
    y = series.values.astype(float)
    if np.all(y == 0):
        return 0.0
    coeffs = np.polyfit(x, y, 1)
    return float(coeffs[0])


def _classify_behavior(slope: float, mean: float, cv: float) -> str:
    """Classifica comportamento com base em slope e volatilidade."""
    if cv > 0.5:
        return "Volátil"
    if mean == 0:
        return "Estável"
    relative_slope = slope / mean if mean > 0 else 0.0
    if relative_slope > 0.01:
        return "Crescendo"
    if relative_slope < -0.01:
        return "Caindo"
    return "Estável"


def build_service_trends(df: pd.DataFrame, start_date: str, end_date: str) -> pd.DataFrame:
    """
    Calcula tendência de custo por serviço nos últimos 3 meses.

    Retorna DataFrame com uma linha por serviço, contendo métricas de evolução
    e o top UsageType por custo no período.
    """
    if df.empty:
        return pd.DataFrame()

    # Garante coluna de data como string YYYY-MM-DD
    df = df.copy()
    df["Data"] = df["Data"].astype(str)

    # Custo total por (data, serviço)
    daily_svc = (
        df.groupby(["Data", "Serviço"])["Custo($)"]
        .sum()
        .reset_index()
    )

    all_dates = sorted(daily_svc["Data"].unique())
    start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
    end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()
    total_days = (end_dt - start_dt).days + 1

    # Divide o período em 3 meses para comparação MoM
    month_size = total_days // 3
    month_boundaries = [
        start_date,
        (start_dt + timedelta(days=month_size)).isoformat(),
        (start_dt + timedelta(days=month_size * 2)).isoformat(),
        end_date,
    ]

    records = []
    for service, grp in daily_svc.groupby("Serviço"):
        total_3m = grp["Custo($)"].sum()
        if total_3m < config.OPTIMIZATION_MIN_SERVICE_USD_3M:
            continue

        pivot = grp.set_index("Data")["Custo($)"].reindex(all_dates, fill_value=0.0)
        mean_daily = pivot.mean()
        std_daily = pivot.std() if len(pivot) > 1 else 0.0
        cv = std_daily / mean_daily if mean_daily > 0 else 0.0
        slope = _slope_usd_per_day(pivot)
        behavior = _classify_behavior(slope, mean_daily, cv)

        # Custo por mês (aprox)
        def _month_total(mb_start: str, mb_end: str) -> float:
            mask = (grp["Data"] >= mb_start) & (grp["Data"] <= mb_end)
            return float(grp.loc[mask, "Custo($)"].sum())

        m1 = _month_total(month_boundaries[0], month_boundaries[1])
        m2 = _month_total(month_boundaries[1], month_boundaries[2])
        m3 = _month_total(month_boundaries[2], month_boundaries[3])

        mom_m2 = ((m2 - m1) / m1 * 100) if m1 > 0 else 0.0
        mom_m3 = ((m3 - m2) / m2 * 100) if m2 > 0 else 0.0

        # Top UsageType do período
        top_ut = (
            df[df["Serviço"] == service]
            .groupby("UsageType")["Custo($)"]
            .sum()
            .sort_values(ascending=False)
        )
        top_usage_type = top_ut.index[0] if not top_ut.empty else ""
        top_usage_type_usd = float(top_ut.iloc[0]) if not top_ut.empty else 0.0

        records.append({
            "Serviço": service,
            "Total 3M (US$)": round(total_3m, 2),
            "Média diária (US$)": round(mean_daily, 2),
            "Comportamento": behavior,
            "Tendência (US$/dia)": round(slope, 4),
            "CV": round(cv, 3),
            "Mês 1 (US$)": round(m1, 2),
            "Mês 2 (US$)": round(m2, 2),
            "Mês 3 (US$)": round(m3, 2),
            "Var MoM M2 (%)": round(mom_m2, 1),
            "Var MoM M3 (%)": round(mom_m3, 1),
            "Top UsageType": top_usage_type,
            "Top UsageType (US$)": round(top_usage_type_usd, 2),
        })

    df_out = pd.DataFrame(records)
    if not df_out.empty:
        df_out = df_out.sort_values("Total 3M (US$)", ascending=False).reset_index(drop=True)
    return df_out


# ============================================================
# Unit Economics
# ============================================================

def build_unit_economics(df: pd.DataFrame, start_date: str, end_date: str) -> dict:
    """
    Calcula custo diário total e tendência ao longo do período.

    Retorna dicionário com série temporal, médias mensais e projeção anual.
    """
    if df.empty:
        return {
            "daily_series": [],
            "daily_avg_usd": 0.0,
            "monthly_avg_usd": [],
            "trend_usd_per_day": 0.0,
            "projected_annual_usd": 0.0,
            "cost_growth_pct_mom": [],
        }

    df = df.copy()
    df["Data"] = df["Data"].astype(str)

    start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
    end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()
    total_days = (end_dt - start_dt).days + 1

    # Série diária total
    daily_total = (
        df.groupby("Data")["Custo($)"]
        .sum()
        .reindex(
            [(start_dt + timedelta(days=i)).isoformat() for i in range(total_days)],
            fill_value=0.0,
        )
    )

    slope = _slope_usd_per_day(daily_total)

    # Últimos 30 dias para projeção
    last_30_days = daily_total.iloc[-30:] if len(daily_total) >= 30 else daily_total
    projected_annual = float(last_30_days.mean()) * 365

    # Médias mensais aproximadas
    month_size = total_days // 3
    monthly_avgs = []
    for i in range(3):
        s = start_dt + timedelta(days=i * month_size)
        e = start_dt + timedelta(days=(i + 1) * month_size - 1) if i < 2 else end_dt
        mask = (daily_total.index >= s.isoformat()) & (daily_total.index <= e.isoformat())
        avg = float(daily_total[mask].mean()) if mask.any() else 0.0
        monthly_avgs.append(round(avg, 2))

    mom_growth = []
    for i in range(1, len(monthly_avgs)):
        prev = monthly_avgs[i - 1]
        curr = monthly_avgs[i]
        mom_growth.append(round(((curr - prev) / prev * 100) if prev > 0 else 0.0, 1))

    return {
        "daily_series": [
            {"date": d, "cost_usd": round(float(v), 4)}
            for d, v in daily_total.items()
        ],
        "daily_avg_usd": round(float(daily_total.mean()), 2),
        "monthly_avg_usd": monthly_avgs,
        "trend_usd_per_day": round(slope, 4),
        "projected_annual_usd": round(projected_annual, 2),
        "cost_growth_pct_mom": mom_growth,
    }


# ============================================================
# Identificação de oportunidades
# ============================================================

def _detect_opportunities_for_service(
    service: str,
    row: pd.Series,
    df_raw: pd.DataFrame,
    optimizer_recs: list[dict],
    utilization: Optional[dict] = None,
) -> list[dict]:
    """
    Aplica regras determinísticas para identificar oportunidades de otimização
    para um serviço com base em sua tendência, UsageTypes, recomendações externas
    e métricas reais de utilização (CPU, conexões RDS, tráfego ELB, EBS, EIP).
    """
    opportunities = []
    slope = row["Tendência (US$/dia)"]
    behavior = row["Comportamento"]
    total_3m = row["Total 3M (US$)"]
    mean_daily = row["Média diária (US$)"]
    util = utilization or {}

    # Usage types do serviço no período
    svc_df = df_raw[df_raw["Serviço"] == service]
    usage_type_totals = (
        svc_df.groupby("UsageType")["Custo($)"].sum().sort_values(ascending=False)
    )

    def _add(category: str, action: str, savings_usd: float, detail: str = ""):
        effort = config.OPTIMIZATION_EFFORT_SCORES.get(category, 5)
        # Estimativa de impacto: economia mensal estimada normalizada por 10
        impact_score = min(10, round(savings_usd / 100, 1)) if savings_usd > 0 else 1.0
        if impact_score < 0.5:
            impact_score = 0.5
        priority = (
            "Alta" if savings_usd >= config.OPTIMIZATION_HIGH_PRIORITY_SAVINGS_USD
            else "Média" if savings_usd >= config.OPTIMIZATION_MEDIUM_PRIORITY_SAVINGS_USD
            else "Baixa"
        )
        opportunities.append({
            "categoria": category,
            "tecnica_gartner": config.OPTIMIZATION_GARTNER_TECHNIQUE.get(category, ""),
            "servico": service,
            "acao": action,
            "detalhe": detail,
            "economia_estimada_usd_mes": round(savings_usd, 2),
            "impacto_score": impact_score,
            "esforco_score": effort,
            "prioridade": priority,
            "horizonte": (
                "Imediato" if effort >= 7 and savings_usd >= config.OPTIMIZATION_MEDIUM_PRIORITY_SAVINGS_USD
                else "30 dias" if effort >= 5
                else "90 dias"
            ),
        })

    # --- Compute Optimizer: EC2 e ASG
    svc_recs = [
        r for r in optimizer_recs
        if r["resource_type"] in ("ec2_instance", "asg")
        and r["finding"] in ("OVER_PROVISIONED", "VERY_OVER_PROVISIONED")
        and r["savings_usd_monthly"] > 0
    ]
    if svc_recs and service in (
        "Amazon Elastic Compute Cloud - Compute",
        "EC2 - Other",
        "Amazon Elastic Container Service for Kubernetes",
    ):
        total_savings = sum(r["savings_usd_monthly"] for r in svc_recs)
        recs_summary = ", ".join(
            f"{r['resource_name'] or r['resource_id']} ({r['current_type']}→{r['recommended_type']})"
            for r in svc_recs[:3]
        )
        _add(
            "rightsizing",
            "Redimensionar instâncias super-provisionadas",
            total_savings,
            f"Compute Optimizer: {recs_summary}{'...' if len(svc_recs) > 3 else ''}",
        )

    # --- Nova geração de instâncias (Compute Optimizer)
    newer_gen_recs = [
        r for r in optimizer_recs
        if r["resource_type"] in ("ec2_instance", "asg")
        and r["finding"] == "OPTIMIZED"
        and r["recommended_type"] and r["recommended_type"] != r["current_type"]
    ]
    if newer_gen_recs and service in (
        "Amazon Elastic Compute Cloud - Compute",
        "Amazon Elastic Container Service for Kubernetes",
    ):
        savings = sum(r["savings_usd_monthly"] for r in newer_gen_recs)
        if savings > 0:
            _add(
                "newer_generation",
                "Migrar para geração mais recente de instâncias",
                savings,
                f"{len(newer_gen_recs)} instância(s) com geração mais eficiente disponível",
            )

    # --- S3: Lifecycle policy
    for ut, usd in usage_type_totals.items():
        if "TimedStorage" in ut and "Standard" in ut and usd > 50:
            monthly = usd / 3  # média mensal estimada
            potential = monthly * 0.30  # estimativa conservadora de 30% com IA/Glacier
            if potential > config.OPTIMIZATION_MEDIUM_PRIORITY_SAVINGS_USD:
                _add(
                    "lifecycle_s3",
                    "Implementar/revisar lifecycle policy no S3",
                    potential,
                    f"Storage Standard alto ({ut}: US$ {usd:,.2f} em 3M) — avaliar migração para IA ou Glacier",
                )
                break

    # --- NAT Gateway: VPC Endpoints (Gateway gratuito para S3/DynamoDB; Interface pago para outros)
    for ut in usage_type_totals.index:
        if "NatGateway-Bytes" in ut:
            monthly_nat = usage_type_totals[ut] / 3
            nat_total_3m = usage_type_totals[ut]

            # Gateway Endpoints (S3 + DynamoDB): GRATUITOS — sem custo por hora nem por GB.
            # Eliminam tráfego NAT de instâncias EC2/EKS que acessam S3 ou DynamoDB via internet.
            # Estimativa conservadora: 20-30% do tráfego NAT é tipicamente S3/DynamoDB em ambientes CIAM.
            gateway_potential = monthly_nat * 0.25
            if gateway_potential > 0:
                _add(
                    "vpc_endpoints",
                    "Criar VPC Gateway Endpoints para S3 e DynamoDB (gratuitos)",
                    gateway_potential,
                    (
                        f"NatGateway-Bytes: US$ {nat_total_3m:,.2f} em 3M. "
                        f"Gateway Endpoints para S3 e DynamoDB são GRATUITOS (sem custo por hora ou GB). "
                        f"Eliminam tráfego NAT de workloads EC2/EKS que acessam esses serviços via internet. "
                        f"Ação: AWS Console → VPC → Endpoints → Create Endpoint → tipo 'Gateway' → "
                        f"selecionar S3 e DynamoDB → associar às route tables das subnets privadas. "
                        f"Economia estimada: redução de ~25% do custo NAT sem custo adicional."
                    ),
                )

            # Interface Endpoints (ECR, CloudWatch, SSM, etc.): têm custo por hora (~$7/mês cada).
            # Só valem quando o tráfego NAT evitado supera o custo do endpoint.
            # Estimativa: cada endpoint Interface custa ~$7/mês; compensa quando elimina mais do que isso em NAT.
            interface_potential = monthly_nat * 0.15  # parcela restante após Gateway Endpoints
            if interface_potential > config.OPTIMIZATION_MEDIUM_PRIORITY_SAVINGS_USD:
                _add(
                    "vpc_endpoints",
                    "Avaliar VPC Interface Endpoints para ECR, CloudWatch e SSM",
                    interface_potential,
                    (
                        f"NatGateway-Bytes: US$ {nat_total_3m:,.2f} em 3M. "
                        f"Interface Endpoints têm custo de ~US$ 7/mês por endpoint por AZ. "
                        f"Indicados para workloads com tráfego intenso para ECR (pull de imagens Docker), "
                        f"CloudWatch (envio de logs/métricas) ou SSM (acesso a instâncias). "
                        f"Verificar primeiro: criar Gateway Endpoints (S3/DynamoDB) antes de avaliar Interface Endpoints."
                    ),
                )
            break

    # --- CloudWatch: dois problemas distintos tratados separadamente
    if "AmazonCloudWatch" in service or "CloudWatch" in service:

        # DataScanned-Bytes = custo de QUERIES (CloudWatch Logs Insights escaneando dados)
        # Não é retenção — é volume de dados varridos por consultas ativas
        for ut, usd in usage_type_totals.items():
            if "DataScanned" in ut and usd > 30:
                monthly = usd / 3
                _add(
                    "log_retention",
                    "Reduzir volume de dados varridos por queries no CloudWatch Logs Insights",
                    monthly * 0.50,
                    (
                        f"DataScanned-Bytes: US$ {usd:,.2f} em 3M — custo gerado por queries que escaneiam "
                        f"grandes volumes de logs. Verificar: quais log groups são consultados, se há queries "
                        f"sem filtro de tempo ou com janelas muito amplas, e se é possível usar filtros mais "
                        f"específicos ou exportar logs antigos para S3 (consulta via Athena é mais barata)."
                    ),
                )
                break

        # TimedStorage = custo de ARMAZENAMENTO de logs (retenção indefinida ou muito longa)
        for ut, usd in usage_type_totals.items():
            if "TimedStorage" in ut and usd > 50:
                monthly = usd / 3
                _add(
                    "log_retention",
                    "Definir política de retenção em log groups sem expiração",
                    monthly * 0.40,
                    (
                        f"Storage de logs: US$ {usd:,.2f} em 3M — log groups sem política de retenção "
                        f"acumulam dados indefinidamente. Verificar no console CloudWatch → Log groups quais "
                        f"estão com retenção 'Never expire' e definir um período adequado (ex: 30, 60 ou 90 dias)."
                    ),
                )
                break

    # --- Backup/Snapshots: retenção — só sugere quando há tendência de crescimento
    if "AWS Backup" in service or "EC2 - Other" in service:
        for ut, usd in usage_type_totals.items():
            if any(k in ut for k in ("Snapshot", "BackupUsage", "EBS:SnapshotUsage")):
                monthly = usd / 3
                if monthly > config.OPTIMIZATION_MEDIUM_PRIORITY_SAVINGS_USD:
                    # Indica crescimento como critério se comportamento for Crescendo
                    growth_note = (
                        f"custo crescendo ({behavior})" if behavior == "Crescendo"
                        else f"custo acumulado relevante"
                    )
                    _add(
                        "backup_retention",
                        "Revisar janela de retenção e duplicidade de backups",
                        monthly * 0.25,
                        (
                            f"{ut}: US$ {usd:,.2f} em 3M ({growth_note}). Verificar: "
                            f"quantos dias de retenção estão configurados, se há planos de backup duplicados "
                            f"cobrindo os mesmos recursos, se instâncias efêmeras (ASG/EKS nodes) estão "
                            f"sendo backupeadas desnecessariamente, e se há replicação cross-region que pode "
                            f"ser eliminada."
                        ),
                    )
                break

    # --- EC2: análise combinada CPU + rede — apenas no serviço principal, evita duplicata com EC2-Other
    ec2_instances = util.get("ec2", [])
    if ec2_instances and service == "Amazon Elastic Compute Cloud - Compute":
        total_inst = len(ec2_instances)

        # Candidatas a investigação: CPU baixa em média E pico E rede baixa
        investigation = [i for i in ec2_instances if i.get("investigation_candidate")]
        # Uso periódico: CPU média baixa mas pico alto — não sugere ação, apenas informa
        periodic = [i for i in ec2_instances if i.get("periodic_use")]
        # I/O-bound: CPU baixa mas rede significativa — não candidata
        io_bound = [i for i in ec2_instances if i.get("io_bound")]
        # Candidatas a rightsize: CPU 10–40% sem pico extremo
        rightsize = [i for i in ec2_instances if i.get("rightsize_candidate")]
        # Nós EKS com evidência confirmada de uso (pods, scaling, LB)
        eks_active = [i for i in ec2_instances if i.get("eks_active")]
        # Nós EKS sem evidência conclusiva (Container Insights não habilitado)
        eks_low_load = [i for i in ec2_instances if i.get("eks_low_load")]

        def _inst_summary(i: dict) -> str:
            cpu_avg = f"{i['cpu_avg_pct']:.1f}%" if i.get("cpu_avg_pct") is not None else "n/d"
            cpu_peak = f"{i['cpu_peak_90d_pct']:.1f}%" if i.get("cpu_peak_90d_pct") is not None else "n/d"
            net = f"{i.get('net_total_mb_day', 0):.0f} MB/dia"
            return (
                f"{i['name']} ({i['instance_type']}, "
                f"CPU média 45d: {cpu_avg} / pico 90d: {cpu_peak}, rede: {net})"
            )

        # Proporção de instâncias com evidência real de subutilização vs. total
        investigation_pct = len(investigation) / total_inst if total_inst > 0 else 0
        # Instâncias com justificativa clara de uso: periódico + I/O-bound + EKS ativo
        justified_count = len(periodic) + len(io_bound) + len(eks_active)
        justified_pct = justified_count / total_inst if total_inst > 0 else 0

        # Nota sobre nós EKS com evidência de uso — sempre inclusa quando presente
        eks_active_note = ""
        if eks_active:
            clusters_used = list({i["eks_info"]["cluster"] for i in eks_active if i.get("eks_info")})
            cluster_list = ", ".join(clusters_used[:3])
            # Pega uma razão de exemplo para ilustrar qual evidência foi usada
            sample_reason = next(
                (i.get("eks_active_reason", "") for i in eks_active if i.get("eks_active_reason")), ""
            )
            eks_active_note = (
                f"{len(eks_active)} nó(s) EKS excluídos da análise por evidência de uso ativo "
                f"(cluster: {cluster_list}; ex: {sample_reason}). "
            )

        # Nota sobre nós EKS inconclusivos (Container Insights não habilitado)
        eks_gap_note = ""
        if eks_low_load:
            clusters_gap = list({i["eks_info"].get("cluster", "?") for i in eks_low_load if i.get("eks_info")})
            eks_gap_note = (
                f"{len(eks_low_load)} nó(s) EKS sem dados de pods (Container Insights não habilitado "
                f"em: {', '.join(clusters_gap[:3])}) — análise baseada apenas em CPU e rede. "
            )

        if investigation:
            fraction = investigation_pct
            savings = mean_daily * 30 * fraction

            names = ", ".join(_inst_summary(i) for i in investigation[:3])
            extra_notes = []
            if eks_active_note:
                extra_notes.append(eks_active_note.rstrip(". "))
            if eks_gap_note:
                extra_notes.append(eks_gap_note.rstrip(". "))
            if periodic:
                periodic_names = ", ".join(
                    f"{i['name']} (pico 90d: {i['cpu_peak_90d_pct']:.1f}%)"
                    if i.get("cpu_peak_90d_pct") is not None else i["name"]
                    for i in periodic[:3]
                )
                extra_notes.append(
                    f"{len(periodic)} instância(s) com uso periódico — CPU recente baixa "
                    f"mas pico nos 90 dias foi alto (provável uso sazonal, não remover): {periodic_names}"
                )
            if io_bound:
                io_names = ", ".join(
                    f"{i['name']} (rede: {i.get('net_total_mb_day', 0):.0f} MB/dia)"
                    for i in io_bound[:3]
                )
                extra_notes.append(
                    f"{len(io_bound)} instância(s) com rede significativa mas CPU baixa "
                    f"(I/O-bound — não são candidatas): {io_names}"
                )

            detail = (
                f"{len(investigation)} de {total_inst} instância(s) com baixa utilização "
                f"nos 45 dias recentes e sem pico relevante nos 90 dias: "
                f"{names}{'...' if len(investigation) > 3 else ''}. "
            )
            if extra_notes:
                detail += " | ".join(extra_notes) + ". "
            detail += (
                "Validar com o time responsável se há justificativa operacional "
                "(ex: standby, disponibilidade, agendamento futuro) antes de qualquer ação."
            )

            # Decide categoria e prioridade com base na proporção real de evidências
            # Se a maioria das instâncias tem justificativa clara de uso, o sinal é fraco:
            # usar "rightsizing" (verificar) em vez de "idle_cleanup" (remover),
            # e a prioridade será rebaixada automaticamente pela economia estimada baixa.
            if investigation_pct < 0.10 and justified_pct > 0.50:
                # Minoria candidata + maioria justificada → sinal fraco, rebaixa para "verificar"
                _add(
                    "rightsizing",
                    "Verificar instâncias EC2 com baixa utilização (evidência limitada)",
                    savings,
                    (
                        f"Apenas {len(investigation)} de {total_inst} instâncias ({investigation_pct*100:.0f}%) "
                        f"têm evidência combinada de baixa utilização — {justified_count} instâncias têm "
                        f"justificativa clara de uso (periódico ou I/O-bound). "
                        f"Investigar com cautela, sem ação imediata. "
                    ) + detail,
                )
            else:
                _add("idle_cleanup", "Investigar instâncias EC2 com baixa utilização (CPU e rede)", savings, detail)

        if rightsize and not any(o["categoria"] == "rightsizing" for o in opportunities):
            fraction = len(rightsize) / total_inst if total_inst > 0 else 0
            savings = mean_daily * 30 * fraction * 0.30
            names = ", ".join(
                f"{i['name']} ({i['instance_type']}, CPU média 45d: {i['cpu_avg_pct']:.1f}% / "
                f"pico 90d: {i['cpu_peak_90d_pct']:.1f}%)"
                if i.get("cpu_peak_90d_pct") is not None
                else f"{i['name']} ({i['instance_type']}, CPU média 45d: {i['cpu_avg_pct']:.1f}%)"
                for i in rightsize[:3]
            )
            _add(
                "rightsizing",
                "Avaliar redução de tipo de instância EC2 com CPU 10–40%",
                savings,
                (
                    f"{len(rightsize)} instância(s) com CPU média (45d) entre 10–40% "
                    f"sem pico extremo nos 90 dias: {names}{'...' if len(rightsize) > 3 else ''}. "
                    f"Para nodegroups EKS do Ping Identity, validar fora de janelas de evento."
                ),
            )

    # --- RDS: instâncias ociosas (conexões ≈ 0)
    rds_instances = util.get("rds", [])
    if rds_instances and "Relational Database" in service:
        idle_rds = [db for db in rds_instances if db.get("idle")]
        if idle_rds:
            # Custo estimado: proporção de instâncias idle × custo total RDS
            total_rds = len(rds_instances)
            idle_fraction = len(idle_rds) / total_rds if total_rds > 0 else 0
            savings = mean_daily * 30 * idle_fraction
            names = ", ".join(
                f"{db['db_id']} ({db['db_class']}, {db['connections_avg']:.1f} conn)"
                for db in idle_rds[:3]
            )
            _add(
                "idle_cleanup",
                "Revisar instâncias RDS sem conexões ativas com DBA ou owner do serviço",
                savings,
                (
                    f"{len(idle_rds)} instância(s) RDS com média de conexões próxima de zero: "
                    f"{names}{'...' if len(idle_rds) > 3 else ''}. "
                    f"Confirmar com DBA ou owner se a instância pode ser desligada ou removida — "
                    f"RDS contém dados e qualquer remoção deve ser precedida de snapshot final."
                ),
            )

    # --- ELB: load balancers sem tráfego
    elb_instances = util.get("elb", [])
    if elb_instances and "Elastic Load Balancing" in service:
        idle_elb = [lb for lb in elb_instances if lb.get("idle") or lb.get("no_data")]
        if idle_elb:
            # ALB/NLB: ~$16–22/mês cada mesmo sem tráfego
            cost_per_lb = 18.0
            savings = len(idle_elb) * cost_per_lb
            names = ", ".join(f"{lb['lb_name']} ({lb['lb_type']})" for lb in idle_elb[:4])
            _add(
                "idle_cleanup",
                "Remover load balancers sem tráfego mensurável",
                savings,
                f"{len(idle_elb)} LB(s) sem tráfego: {names}{'...' if len(idle_elb) > 4 else ''}",
            )

    # --- EBS: volumes não atachados e migração GP2→GP3
    # IMPORTANTE: volumes armazenam dados — nunca recomendar remoção direta.
    # A recomendação é sempre "verificar com owner", graduada pelo nível de evidência.
    ebs_volumes = util.get("ebs", [])
    if ebs_volumes and service in (
        "Amazon Elastic Compute Cloud - Compute",
        "EC2 - Other",
        "Amazon Elastic Block Store",
    ):
        unattached = [v for v in ebs_volumes if v.get("unattached")]
        already_emitted_ebs = any(o["categoria"] == "idle_cleanup" and "EBS" in o.get("acao", "") for o in opportunities)
        if unattached and not already_emitted_ebs:
            total_gb = sum(v.get("size_gb", 0) for v in unattached)
            # EBS GP2/GP3: ~$0.08–0.10/GB-mês; volume desatachado ainda gera cobrança
            savings = total_gb * 0.08

            # Separa por nível de evidência para construir detalhe graduado
            pvc_vols = [v for v in unattached if v.get("is_kubernetes_pvc")]
            recent_io_vols = [v for v in unattached if v.get("has_recent_io") and not v.get("is_kubernetes_pvc")]
            zero_io_vols = [v for v in unattached if not v.get("has_recent_io") and not v.get("is_kubernetes_pvc") and (v.get("read_ops_45d") is not None or v.get("write_ops_45d") is not None)]
            no_data_vols = [v for v in unattached if v.get("read_ops_45d") is None and v.get("write_ops_45d") is None and not v.get("is_kubernetes_pvc")]

            detail_parts = []

            # PVCs: maior cautela — requer confirmação via kubectl
            if pvc_vols:
                pvc_gb = sum(v.get("size_gb", 0) for v in pvc_vols)
                pvc_names = ", ".join(
                    f"{v.get('pvc_name', v['volume_id'])} ({v['size_gb']} GB, ns: {v.get('pvc_namespace', '?')})"
                    for v in pvc_vols[:3]
                )
                detail_parts.append(
                    f"{len(pvc_vols)} PVC(s) Kubernetes desatachado(s) — {pvc_gb} GB: {pvc_names}"
                    f"{'...' if len(pvc_vols) > 3 else ''}. "
                    f"Verificar via `kubectl get pvc -A` se o PVC ainda está Bound antes de qualquer ação."
                )

            # Com I/O recente: dado foi acessado nos últimos 45d — cuidado redobrado
            if recent_io_vols:
                rio_gb = sum(v.get("size_gb", 0) for v in recent_io_vols)
                rio_names = ", ".join(
                    f"{v['name']} ({v['size_gb']} GB, "
                    f"leituras: {int(v.get('read_ops_45d') or 0):,}, "
                    f"escritas: {int(v.get('write_ops_45d') or 0):,})"
                    for v in recent_io_vols[:3]
                )
                detail_parts.append(
                    f"{len(recent_io_vols)} volume(s) desatachado(s) com I/O recente (45d) — {rio_gb} GB: "
                    f"{rio_names}{'...' if len(recent_io_vols) > 3 else ''}. "
                    f"Dado foi acessado recentemente — verificar com owner do serviço antes de qualquer ação."
                )

            # Zero I/O nos 45d: sem evidência de acesso recente, mas ainda é dado
            if zero_io_vols:
                zio_gb = sum(v.get("size_gb", 0) for v in zero_io_vols)
                zio_names = ", ".join(
                    f"{v['name']} ({v['size_gb']} GB)"
                    for v in zero_io_vols[:3]
                )
                detail_parts.append(
                    f"{len(zero_io_vols)} volume(s) desatachado(s) sem I/O nos últimos 45 dias — {zio_gb} GB: "
                    f"{zio_names}{'...' if len(zero_io_vols) > 3 else ''}. "
                    f"Sem acesso recente detectado — confirmar com owner se o dado pode ser descartado."
                )

            # Sem dados de métrica: inconclusivo
            if no_data_vols:
                nd_gb = sum(v.get("size_gb", 0) for v in no_data_vols)
                detail_parts.append(
                    f"{len(no_data_vols)} volume(s) desatachado(s) sem dados de I/O disponíveis — {nd_gb} GB. "
                    f"Verificar com owner antes de qualquer ação."
                )

            if detail_parts:
                _add(
                    "idle_cleanup",
                    "Revisar volumes EBS desatachados com owner de cada serviço",
                    savings,
                    " | ".join(detail_parts),
                )

        gp2_vols = [v for v in ebs_volumes if v.get("gp2_eligible_for_gp3")]
        already_emitted_gp3 = any(o["categoria"] == "newer_generation" and "GP3" in o.get("acao", "") for o in opportunities)
        if gp2_vols and not already_emitted_gp3:
            # GP3 é ~20% mais barato que GP2 para mesmo tamanho/IOPS baseline
            # Migração é não-destrutiva: sem perda de dados, pode ser revertida
            total_gb = sum(v.get("size_gb", 0) for v in gp2_vols)
            savings = total_gb * 0.08 * 0.20  # 20% de economia sobre custo de storage
            if savings > config.OPTIMIZATION_MEDIUM_PRIORITY_SAVINGS_USD:
                _add(
                    "newer_generation",
                    "Migrar volumes EBS de GP2 para GP3 (20% mais barato, sem impacto nos dados)",
                    savings,
                    (
                        f"{len(gp2_vols)} volume(s) GP2 elegíveis — {total_gb} GB total. "
                        f"Migração é não-destrutiva: sem perda de dados e pode ser revertida. "
                        f"AWS Console → EC2 → Volumes → selecionar → Modify Volume → GP3."
                    ),
                )

    # --- EIP: Elastic IPs ociosos
    eip_list = util.get("eip", [])
    if eip_list and service in (
        "Amazon Elastic Compute Cloud - Compute",
        "EC2 - Other",
        "Amazon Virtual Private Cloud",
    ):
        savings = sum(e.get("estimated_cost_usd_month", 3.60) for e in eip_list)
        ips = ", ".join(e.get("public_ip", "") for e in eip_list[:5])
        if savings > 0:
            _add(
                "idle_cleanup",
                "Liberar Elastic IPs não associados a nenhuma instância",
                savings,
                f"{len(eip_list)} EIP(s) ocioso(s): {ips}{'...' if len(eip_list) > 5 else ''}",
            )

    # --- Savings Plans: serviços de compute estáveis
    if (
        service in (
            "Amazon Elastic Compute Cloud - Compute",
            "Amazon Elastic Container Service for Kubernetes",
        )
        and behavior == "Estável"
        and mean_daily > 10
    ):
        # Compute Savings Plans oferece ~17% de desconto sobre On-Demand sem fixar tipo/região
        potential = mean_daily * 30 * 0.17
        _add(
            "savings_plans",
            "Avaliar Compute Savings Plans para carga estável de compute",
            potential,
            (
                f"Custo estável por 3 meses (média US$ {mean_daily:.2f}/dia) indica padrão previsível "
                f"— candidato a commitment de 1 ano. "
                f"Como configurar: AWS Console → Cost Management → Savings Plans → "
                f"'Purchase Savings Plans' → escolher 'Compute Savings Plans' (cobre EC2 + EKS + Fargate "
                f"sem fixar região ou tipo de instância). Recomendado apenas se o custo permanecer "
                f"estável nos próximos meses."
            ),
        )

    # --- Recursos ociosos
    if behavior == "Caindo" and mean_daily < 5 and total_3m > config.OPTIMIZATION_MIN_SERVICE_USD_3M:
        _add(
            "idle_cleanup",
            "Investigar recursos ociosos ou subutilizados",
            mean_daily * 30,
            f"Serviço em queda contínua com custo baixo — pode indicar recursos não removidos após depreciação",
        )

    return opportunities


def build_optimization_opportunities(
    df_raw: pd.DataFrame,
    df_service_trends: pd.DataFrame,
    optimizer_recs: list[dict],
    utilization: Optional[dict] = None,
) -> list[dict]:
    """
    Gera lista priorizada de oportunidades de otimização para todos os serviços relevantes.

    Cada oportunidade inclui: categoria, ação, serviço, economia estimada, scores de
    impacto e esforço, prioridade e horizonte temporal sugerido.

    O parâmetro opcional `utilization` recebe o resultado de
    `utilization_metrics.collect_all_utilization()` e permite usar métricas reais
    de CPU, conexões RDS, tráfego ELB, EBS e EIP como evidência nas regras.
    """
    if df_service_trends.empty:
        return []

    all_opportunities = []
    for _, row in df_service_trends.iterrows():
        service = row["Serviço"]
        ops = _detect_opportunities_for_service(
            service, row, df_raw, optimizer_recs, utilization=utilization
        )
        all_opportunities.extend(ops)

    # Deduplica oportunidades muito similares (mesmo serviço + categoria)
    seen = set()
    deduped = []
    for op in all_opportunities:
        key = (op["servico"], op["categoria"])
        if key not in seen:
            seen.add(key)
            deduped.append(op)

    # Ordena: prioridade Alta→Média→Baixa, depois por economia estimada desc
    priority_order = {"Alta": 0, "Média": 1, "Baixa": 2}
    deduped.sort(
        key=lambda x: (priority_order.get(x["prioridade"], 9), -x["economia_estimada_usd_mes"])
    )
    return deduped


# ============================================================
# Payload para Bedrock
# ============================================================

def build_unclassified_services(
    df_raw: pd.DataFrame,
    df_service_trends: pd.DataFrame,
    opportunities: list[dict],
) -> list[dict]:
    """
    Identifica serviços com custo relevante e comportamento de atenção que não geraram
    nenhuma oportunidade pelas regras determinísticas.

    Esses serviços são enviados ao Bedrock para análise investigativa — o modelo
    sugere o que pode estar causando o crescimento e o que vale examinar, sem
    estimativa de economia (evidência fraca, direção de investigação).

    Critérios de inclusão:
    - Nenhuma oportunidade mapeada pelo código
    - Comportamento "Crescendo" ou "Volátil"
    - Custo total no período >= threshold mínimo configurável
    """
    # Conjunto de serviços que já têm pelo menos uma oportunidade mapeada
    classified = {op["servico"] for op in opportunities}

    unclassified = []
    for _, row in df_service_trends.iterrows():
        service = row["Serviço"]
        if service in classified:
            continue
        behavior = row["Comportamento"]
        total_3m = row["Total 3M (US$)"]

        # Só inclui se o comportamento justifica atenção e o custo é relevante
        if behavior not in ("Crescendo", "Volátil"):
            continue
        if total_3m < config.OPTIMIZATION_MIN_SERVICE_USD_3M * 3:
            continue  # threshold mais alto para serviços sem regra (evita ruído)

        # Top 3 usage types para dar contexto ao Bedrock
        svc_df = df_raw[df_raw["Serviço"] == service]
        top_uts = (
            svc_df.groupby("UsageType")["Custo($)"]
            .sum()
            .sort_values(ascending=False)
            .head(3)
        )
        usage_types = [
            {"usage_type": ut, "total_3m_usd": round(float(usd), 2)}
            for ut, usd in top_uts.items()
        ]

        unclassified.append({
            "servico": service,
            "total_3m_usd": total_3m,
            "media_diaria_usd": row["Média diária (US$)"],
            "comportamento": behavior,
            "tendencia_usd_dia": row["Tendência (US$/dia)"],
            "var_mom_m2_pct": row["Var MoM M2 (%)"],
            "var_mom_m3_pct": row["Var MoM M3 (%)"],
            "top_usage_types": usage_types,
        })

    # Ordena por custo total descendente — os mais caros primeiro
    unclassified.sort(key=lambda x: -x["total_3m_usd"])
    return unclassified[:15]  # limita para não saturar o contexto do modelo


def build_optimization_payload(
    df_service_trends: pd.DataFrame,
    opportunities: list[dict],
    unit_economics: dict,
    start_date: str,
    end_date: str,
    df_raw: Optional[pd.DataFrame] = None,
) -> dict:
    """
    Monta payload compacto para análise textual via Bedrock.

    Inclui dois grupos distintos:
    - opportunities: oportunidades com evidência determinística (regras de código)
    - unclassified_services: serviços crescendo sem regra mapeada (para análise investigativa)
    """
    total_days = (
        datetime.strptime(end_date, "%Y-%m-%d").date()
        - datetime.strptime(start_date, "%Y-%m-%d").date()
    ).days + 1

    top_services = []
    if not df_service_trends.empty:
        top_services = (
            df_service_trends.head(15)
            [[
                "Serviço", "Total 3M (US$)", "Comportamento",
                "Tendência (US$/dia)", "Var MoM M2 (%)", "Var MoM M3 (%)",
            ]]
            .to_dict(orient="records")
        )

    high_priority = [o for o in opportunities if o["prioridade"] == "Alta"]
    medium_priority = [o for o in opportunities if o["prioridade"] == "Média"]
    total_savings_potential = sum(o["economia_estimada_usd_mes"] for o in opportunities)

    # Serviços sem regra determinística mas com comportamento relevante
    unclassified = []
    if df_raw is not None and not df_service_trends.empty:
        unclassified = build_unclassified_services(df_raw, df_service_trends, opportunities)

    return {
        "report_type": "optimization",
        "window": {
            "start_date": start_date,
            "end_date": end_date,
            "total_days": total_days,
        },
        "unit_economics": {
            "daily_avg_usd": unit_economics.get("daily_avg_usd", 0.0),
            "monthly_avg_usd": unit_economics.get("monthly_avg_usd", []),
            "trend_usd_per_day": unit_economics.get("trend_usd_per_day", 0.0),
            "projected_annual_usd": unit_economics.get("projected_annual_usd", 0.0),
            "cost_growth_pct_mom": unit_economics.get("cost_growth_pct_mom", []),
        },
        "top_services": top_services,
        "total_savings_potential_usd_month": round(total_savings_potential, 2),
        "high_priority_opportunities": high_priority[:10],
        "medium_priority_opportunities": medium_priority[:10],
        # Serviços sem regra — Bedrock analisa e sugere direção de investigação
        "unclassified_services_for_investigation": unclassified,
    }
