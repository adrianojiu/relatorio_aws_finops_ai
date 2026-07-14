"""
AWS Compute Optimizer collector for rightsizing recommendations.
Retorna recomendações de EC2, ASG e ECS/EKS sem custo de API.
"""

import boto3
import config


def _build_client(service: str):
    session = boto3.Session(
        profile_name=config.AWS_PROFILE,
        region_name=config.WORKLOAD_REGION,
    )
    return session.client(service)


def _safe_savings(rec: dict) -> float:
    """Extrai economia mensal estimada em USD de uma recomendação do Compute Optimizer."""
    for option in rec.get("recommendationOptions", []):
        savings = option.get("savingsOpportunity", {})
        monthly = savings.get("estimatedMonthlySavings", {})
        value = monthly.get("value")
        if value is not None:
            try:
                return float(value)
            except (TypeError, ValueError):
                pass
    return 0.0


def _safe_finding(rec: dict) -> str:
    return rec.get("finding", "UNKNOWN")


def get_ec2_recommendations() -> list[dict]:
    """
    Retorna recomendações de rightsizing para instâncias EC2.
    Retorna lista vazia em caso de erro ou sem permissão.
    """
    try:
        client = _build_client("compute-optimizer")
        results = []
        paginator = client.get_paginator("get_ec2_instance_recommendations")
        for page in paginator.paginate():
            for rec in page.get("instanceRecommendations", []):
                current_type = rec.get("currentInstanceType", "")
                options = rec.get("recommendationOptions", [])
                recommended_type = options[0].get("instanceType", "") if options else ""
                utilization = rec.get("utilizationMetrics", [])
                cpu_avg = next(
                    (
                        m.get("value", 0.0)
                        for m in utilization
                        if m.get("name") == "CPU" and m.get("statistic") == "AVERAGE"
                    ),
                    None,
                )
                results.append({
                    "resource_type": "ec2_instance",
                    "resource_id": rec.get("instanceArn", ""),
                    "resource_name": rec.get("instanceName", ""),
                    "current_type": current_type,
                    "recommended_type": recommended_type,
                    "finding": _safe_finding(rec),
                    "cpu_utilization_avg_pct": cpu_avg,
                    "savings_usd_monthly": _safe_savings(rec),
                })
        print(f"  Compute Optimizer EC2: {len(results)} recomendações encontradas.")
        return results
    except Exception as exc:
        print(f"  Compute Optimizer EC2 indisponível ou sem permissão: {exc}")
        return []


def get_asg_recommendations() -> list[dict]:
    """
    Retorna recomendações de rightsizing para Auto Scaling Groups (inclui nodegroups EKS).
    Retorna lista vazia em caso de erro ou sem permissão.
    """
    try:
        client = _build_client("compute-optimizer")
        results = []
        paginator = client.get_paginator("get_auto_scaling_group_recommendations")
        for page in paginator.paginate():
            for rec in page.get("autoScalingGroupRecommendations", []):
                current = rec.get("currentConfiguration", {})
                options = rec.get("recommendationOptions", [])
                recommended = options[0].get("configuration", {}) if options else {}
                results.append({
                    "resource_type": "asg",
                    "resource_id": rec.get("autoScalingGroupArn", ""),
                    "resource_name": rec.get("autoScalingGroupName", ""),
                    "current_type": current.get("instanceType", ""),
                    "recommended_type": recommended.get("instanceType", ""),
                    "finding": _safe_finding(rec),
                    "cpu_utilization_avg_pct": None,
                    "savings_usd_monthly": _safe_savings(rec),
                })
        print(f"  Compute Optimizer ASG: {len(results)} recomendações encontradas.")
        return results
    except Exception as exc:
        print(f"  Compute Optimizer ASG indisponível ou sem permissão: {exc}")
        return []


def get_ecs_recommendations() -> list[dict]:
    """
    Retorna recomendações de rightsizing para serviços ECS (inclui workloads EKS via Fargate).
    Retorna lista vazia em caso de erro ou sem permissão.
    """
    try:
        client = _build_client("compute-optimizer")
        results = []
        paginator = client.get_paginator("get_ecs_service_recommendations")
        for page in paginator.paginate():
            for rec in page.get("ecsServiceRecommendations", []):
                current = rec.get("currentServiceConfiguration", {})
                options = rec.get("recommendationOptions", [])
                recommended = options[0].get("containerRecommendations", []) if options else []
                results.append({
                    "resource_type": "ecs_service",
                    "resource_id": rec.get("serviceArn", ""),
                    "resource_name": rec.get("serviceArn", "").split("/")[-1],
                    "current_type": f"cpu={current.get('cpu', '?')} mem={current.get('memory', '?')}",
                    "recommended_type": str(recommended[0]) if recommended else "",
                    "finding": _safe_finding(rec),
                    "cpu_utilization_avg_pct": None,
                    "savings_usd_monthly": _safe_savings(rec),
                })
        print(f"  Compute Optimizer ECS: {len(results)} recomendações encontradas.")
        return results
    except Exception as exc:
        print(f"  Compute Optimizer ECS indisponível ou sem permissão: {exc}")
        return []


def collect_all_recommendations() -> list[dict]:
    """
    Coleta recomendações de EC2, ASG e ECS e retorna lista unificada.
    Falhas individuais são silenciadas — o relatório continua sem aquele tipo.
    """
    print("Coletando recomendações do AWS Compute Optimizer...")
    recs = []
    recs.extend(get_ec2_recommendations())
    recs.extend(get_asg_recommendations())
    recs.extend(get_ecs_recommendations())
    total_savings = sum(r["savings_usd_monthly"] for r in recs)
    print(f"  Total: {len(recs)} recomendações | Economia potencial estimada: US$ {total_savings:,.2f}/mês")
    return recs
