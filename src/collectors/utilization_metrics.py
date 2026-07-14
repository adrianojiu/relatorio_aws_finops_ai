"""
Coleta métricas de utilização real para o relatório de otimização de custos.

Diferente do metrics_cloudwatch.py (orientado a anomalias específicas), este módulo
varre a conta e retorna evidências de utilização por tipo de recurso — CPU de EC2,
conexões de RDS, RequestCount de ELB, VolumeIdleTime de EBS, etc.

As métricas são usadas para fortalecer ou enfraquecer as oportunidades detectadas
pela análise de custo (optimization_analysis.py).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

import boto3
import botocore.exceptions

import config

logger = logging.getLogger(__name__)


def _session() -> boto3.Session:
    return boto3.Session(
        profile_name=config.AWS_PROFILE,
        region_name=config.WORKLOAD_REGION,
    )


def _cw_client(session: boto3.Session) -> boto3.client:
    return session.client("cloudwatch", region_name=config.WORKLOAD_REGION)


def _metric_stats(
    cw,
    namespace: str,
    metric_name: str,
    dimensions: list[dict],
    start_date: str,
    end_date: str,
    stats: list[str],
) -> dict[str, Optional[float]]:
    """
    Coleta múltiplas estatísticas (Average, Maximum, Sum) de uma métrica no período.
    Retorna dicionário {stat: valor} — None para cada stat sem dados.
    Granularidade diária (Period=86400).
    """
    start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
    result: dict[str, Optional[float]] = {s: None for s in stats}
    try:
        resp = cw.get_metric_statistics(
            Namespace=namespace,
            MetricName=metric_name,
            Dimensions=dimensions,
            StartTime=start_dt,
            EndTime=end_dt,
            Period=86400,
            Statistics=stats,
        )
    except (botocore.exceptions.BotoCoreError, botocore.exceptions.ClientError):
        return result

    points = resp.get("Datapoints", [])
    if not points:
        return result

    for stat in stats:
        values = [float(p[stat]) for p in points if stat in p]
        if not values:
            continue
        if stat == "Maximum":
            result[stat] = round(max(values), 2)
        elif stat == "Sum":
            result[stat] = round(sum(values), 2)
        else:  # Average
            result[stat] = round(sum(values) / len(values), 2)

    # Percentual de dias com Average acima de 20% (só para CPU)
    if "Average" in stats:
        avg_values = [float(p["Average"]) for p in points if "Average" in p]
        result["_active_days_pct"] = round(
            100.0 * sum(1 for v in avg_values if v > 20.0) / len(avg_values), 1
        ) if avg_values else None

    return result


def _metric_avg(
    cw,
    namespace: str,
    metric_name: str,
    dimensions: list[dict],
    start_date: str,
    end_date: str,
    stat: str = "Average",
) -> Optional[float]:
    """Retorna média simples de uma métrica CloudWatch no período. None se sem dados."""
    result = _metric_stats(cw, namespace, metric_name, dimensions, start_date, end_date, [stat])
    return result.get(stat)


# ============================================================
# EC2 — CPU + Rede + EKS (análise combinada para evitar falsos positivos)
# ============================================================

# Thresholds para classificação de EC2
_CPU_LOW_AVG = 10.0        # CPU média abaixo disso = potencialmente subutilizada
_CPU_PEAK_IDLE = 30.0      # CPU pico abaixo disso = sem uso intenso no período
_CPU_ACTIVE_DAYS = 15.0    # % de dias com CPU > 20% — acima disso = uso periódico
_NET_IO_MB_DAY = 100.0     # bytes/dia → MB: acima disso = instância serve tráfego real


def _collect_eks_cluster_context(session: boto3.Session, cw, recent_start: str, end_date: str) -> dict:
    """
    Coleta contexto EKS a nível de cluster:
    - ASG: GroupDesiredCapacity, GroupMinSize por nodegroup (via autoscaling API)
    - Container Insights: node_number_of_running_pods por cluster (se habilitado)
    - LBs associados ao cluster: RequestCount / ActiveFlowCount (tag kubernetes.io/cluster/<name>)

    Retorna dicionário indexado por cluster_name:
    {
        "<cluster>": {
            "asg_desired": int,
            "asg_min": int,
            "pods_avg": float | None,     # None = Container Insights não habilitado
            "lb_requests_avg": float | None,
            "lb_names": [str],
        }
    }
    """
    result: dict[str, dict] = {}
    ec2_client = session.client("ec2", region_name=config.WORKLOAD_REGION)
    asg_client = session.client("autoscaling", region_name=config.WORKLOAD_REGION)
    elb_client = session.client("elbv2", region_name=config.WORKLOAD_REGION)

    # 1. Descobre clusters EKS existentes via tags nas instâncias EC2
    try:
        resp = ec2_client.describe_instances(
            Filters=[
                {"Name": "instance-state-name", "Values": ["running"]},
                {"Name": "tag-key", "Values": ["eks:cluster-name"]},
            ]
        )
        cluster_names = set()
        for reservation in resp.get("Reservations", []):
            for inst in reservation.get("Instances", []):
                for tag in inst.get("Tags", []):
                    if tag["Key"] == "eks:cluster-name":
                        cluster_names.add(tag["Value"])
    except Exception as exc:
        logger.warning("EKS: falha ao listar clusters via tags: %s", exc)
        return result

    for cluster in cluster_names:
        entry: dict = {
            "asg_desired": None,
            "asg_min": None,
            "pods_avg": None,
            "lb_requests_avg": None,
            "lb_names": [],
        }

        # 2. ASG: soma GroupDesiredCapacity e GroupMinSize de todos os nodegroups do cluster
        try:
            paginator = asg_client.get_paginator("describe_auto_scaling_groups")
            total_desired = 0
            total_min = 0
            found = False
            for page in paginator.paginate(
                Filters=[{"Name": "tag:eks:cluster-name", "Values": [cluster]}]
            ):
                for asg in page.get("AutoScalingGroups", []):
                    total_desired += asg.get("DesiredCapacity", 0)
                    total_min += asg.get("MinSize", 0)
                    found = True
            if found:
                entry["asg_desired"] = total_desired
                entry["asg_min"] = total_min
        except Exception as exc:
            logger.warning("EKS %s: falha ao coletar ASG: %s", cluster, exc)

        # 3. Container Insights: node_number_of_running_pods (média no período recente)
        # Só disponível se o cluster tiver Container Insights habilitado
        try:
            pods_stats = _metric_stats(
                cw,
                namespace="ContainerInsights",
                metric_name="node_number_of_running_pods",
                dimensions=[
                    {"Name": "ClusterName", "Value": cluster},
                ],
                start_date=recent_start,
                end_date=end_date,
                stats=["Average"],
            )
            entry["pods_avg"] = pods_stats.get("Average")  # None se não habilitado
        except Exception as exc:
            logger.warning("EKS %s: falha ao coletar pods via Container Insights: %s", cluster, exc)

        # 4. LBs associados ao cluster via tag kubernetes.io/cluster/<name>=owned|shared
        try:
            lb_requests = []
            lb_names = []
            paginator = elb_client.get_paginator("describe_load_balancers")
            for page in paginator.paginate():
                for lb in page.get("LoadBalancers", []):
                    lb_arn = lb.get("LoadBalancerArn", "")
                    lb_type = lb.get("Type", "")
                    # Busca tags do LB para verificar associação com o cluster
                    try:
                        tags_resp = elb_client.describe_tags(ResourceArns=[lb_arn])
                        lb_tags = {
                            t["Key"]: t["Value"]
                            for tl in tags_resp.get("TagDescriptions", [])
                            for t in tl.get("Tags", [])
                        }
                    except Exception:
                        continue

                    cluster_tag = lb_tags.get(f"kubernetes.io/cluster/{cluster}", "")
                    if cluster_tag not in ("owned", "shared"):
                        continue

                    lb_names.append(lb.get("LoadBalancerName", lb_arn))
                    arn_suffix = "/".join(lb_arn.split("loadbalancer/")[-1].split("/")) if "loadbalancer/" in lb_arn else ""
                    namespace = "AWS/ApplicationELB" if lb_type == "application" else "AWS/NetworkELB"
                    metric_name = "RequestCount" if lb_type == "application" else "ActiveFlowCount"
                    stat = "Sum" if metric_name == "RequestCount" else "Average"

                    req = _metric_avg(
                        cw, namespace, metric_name,
                        [{"Name": "LoadBalancer", "Value": arn_suffix}],
                        recent_start, end_date, stat,
                    )
                    if req is not None:
                        lb_requests.append(req)

            entry["lb_names"] = lb_names
            entry["lb_requests_avg"] = round(sum(lb_requests) / len(lb_requests), 2) if lb_requests else None
        except Exception as exc:
            logger.warning("EKS %s: falha ao coletar LBs: %s", cluster, exc)

        result[cluster] = entry

    return result


def collect_ec2_utilization(start_date: str, end_date: str) -> list[dict]:
    """
    Retorna lista de instâncias EC2 com métricas combinadas de CPU, rede e contexto EKS.

    Janelas temporais:
    - 45 dias (recentes): CPU média, % dias ativos, rede — classifica estado atual
    - 90 dias (histórico): pico de CPU — detecta uso periódico/sazonal

    Para instâncias EKS (tag eks:cluster-name), coleta contexto adicional por cluster:
    - ASG: DesiredCapacity vs MinSize — autoscaler adicionou nós por demanda real?
    - Container Insights: node_number_of_running_pods — há pods agendados?
    - LBs do cluster: RequestCount / ActiveFlowCount — cluster recebe tráfego real?

    Classificação resultante:
    - eks_active: nó EKS com evidência de uso (pods, scaling ou tráfego no LB) → não candidato
    - eks_low_load: nó EKS sem evidência de uso, mas Container Insights ausente → inconclusivo
    - investigation_candidate: CPU e rede baixas nos 45d, sem pico nos 90d, não EKS ativo
    - periodic_use: CPU recente baixa mas pico histórico alto → sazonal, não remover
    - io_bound: CPU baixa mas rede significativa → não candidata
    - rightsize_candidate: CPU 10–40% nos 45d sem pico extremo nos 90d
    """
    session = _session()
    ec2_client = session.client("ec2", region_name=config.WORKLOAD_REGION)
    cw = _cw_client(session)

    # Janela recente: 45 dias para classificação atual
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")
    recent_start = (end_dt - timedelta(days=45)).strftime("%Y-%m-%d")

    # Janela histórica: 90 dias para detecção de pico sazonal
    history_start = (end_dt - timedelta(days=90)).strftime("%Y-%m-%d")

    # Coleta contexto EKS antes de iterar instâncias (uma chamada por cluster, não por nó)
    eks_context = _collect_eks_cluster_context(session, cw, recent_start, end_date)

    instances = []
    try:
        paginator = ec2_client.get_paginator("describe_instances")
        for page in paginator.paginate(
            Filters=[{"Name": "instance-state-name", "Values": ["running"]}]
        ):
            for reservation in page.get("Reservations", []):
                for inst in reservation.get("Instances", []):
                    instance_id = inst.get("InstanceId", "")
                    instance_type = inst.get("InstanceType", "")
                    tags = {t["Key"]: t["Value"] for t in inst.get("Tags", [])}
                    name = tags.get("Name", instance_id)

                    # Detecta se é nó EKS e qual cluster/nodegroup
                    eks_cluster = tags.get("eks:cluster-name")
                    eks_nodegroup = tags.get("eks:nodegroup-name")
                    is_eks_node = eks_cluster is not None

                    dims = [{"Name": "InstanceId", "Value": instance_id}]

                    # --- Janela recente (45 dias): CPU + rede
                    cpu_recent = _metric_stats(
                        cw, "AWS/EC2", "CPUUtilization", dims,
                        recent_start, end_date, ["Average"],
                    )
                    cpu_avg = cpu_recent.get("Average")
                    cpu_active_days_pct = cpu_recent.get("_active_days_pct")

                    net_out_recent = _metric_stats(
                        cw, "AWS/EC2", "NetworkOut", dims, recent_start, end_date, ["Sum"],
                    )
                    net_in_recent = _metric_stats(
                        cw, "AWS/EC2", "NetworkIn", dims, recent_start, end_date, ["Sum"],
                    )
                    net_out_mb_day = round((net_out_recent.get("Sum") or 0.0) / 1_048_576 / 45, 2)
                    net_in_mb_day = round((net_in_recent.get("Sum") or 0.0) / 1_048_576 / 45, 2)
                    net_total_mb_day = net_out_mb_day + net_in_mb_day

                    # --- Janela histórica (90 dias): apenas pico de CPU
                    cpu_history = _metric_stats(
                        cw, "AWS/EC2", "CPUUtilization", dims,
                        history_start, end_date, ["Maximum"],
                    )
                    cpu_peak_90d = cpu_history.get("Maximum")

                    # --- Contexto EKS (a nível de cluster, não de nó individual)
                    eks_info: dict = {}
                    eks_active = False
                    eks_low_load = False
                    eks_active_reason = ""

                    if is_eks_node and eks_cluster in eks_context:
                        ctx = eks_context[eks_cluster]
                        eks_info = {
                            "cluster": eks_cluster,
                            "nodegroup": eks_nodegroup,
                            "asg_desired": ctx.get("asg_desired"),
                            "asg_min": ctx.get("asg_min"),
                            "pods_avg": ctx.get("pods_avg"),
                            "lb_requests_avg": ctx.get("lb_requests_avg"),
                            "lb_names": ctx.get("lb_names", []),
                            "container_insights_enabled": ctx.get("pods_avg") is not None,
                        }

                        reasons = []
                        # Evidência 1: autoscaler expandiu além do mínimo → demanda real
                        if (ctx.get("asg_desired") is not None
                                and ctx.get("asg_min") is not None
                                and ctx["asg_desired"] > ctx["asg_min"]):
                            reasons.append(
                                f"ASG desired ({ctx['asg_desired']}) > min ({ctx['asg_min']})"
                            )
                        # Evidência 2: pods em execução no cluster
                        if ctx.get("pods_avg") is not None and ctx["pods_avg"] > 0:
                            reasons.append(f"pods em execução: {ctx['pods_avg']:.1f} em média")
                        # Evidência 3: LB do cluster com tráfego real
                        if ctx.get("lb_requests_avg") is not None and ctx["lb_requests_avg"] > 1.0:
                            lb_list = ", ".join(ctx["lb_names"][:2])
                            reasons.append(
                                f"tráfego no LB ({lb_list}): {ctx['lb_requests_avg']:.0f} req/s avg"
                            )

                        if reasons:
                            eks_active = True
                            eks_active_reason = "; ".join(reasons)
                        elif ctx.get("pods_avg") is None:
                            # Container Insights não habilitado — não é possível confirmar uso por pods
                            eks_low_load = True
                        # else: pods_avg == 0 e sem LB e desired == min → nó realmente ocioso

                    elif is_eks_node:
                        # Cluster não encontrado no contexto (falha de coleta)
                        eks_low_load = True

                    # --- Classificação combinada
                    has_cpu_data = cpu_avg is not None
                    cpu_low_avg = has_cpu_data and cpu_avg < _CPU_LOW_AVG
                    cpu_low_peak_90d = cpu_peak_90d is not None and cpu_peak_90d < _CPU_PEAK_IDLE
                    net_low = net_total_mb_day < _NET_IO_MB_DAY
                    active_days_low = (
                        cpu_active_days_pct is None or cpu_active_days_pct < _CPU_ACTIVE_DAYS
                    )

                    # Nós EKS com evidência de uso nunca são candidatos
                    if eks_active:
                        investigation_candidate = False
                        periodic_use = False
                        io_bound = False
                        rightsize_candidate = False
                    else:
                        investigation_candidate = (
                            not is_eks_node  # nós EKS inconclusivos não entram aqui
                            and cpu_low_avg and cpu_low_peak_90d and net_low and active_days_low
                        )
                        periodic_use = (
                            cpu_low_avg and not cpu_low_peak_90d and not investigation_candidate
                        )
                        io_bound = cpu_low_avg and not net_low and not investigation_candidate
                        rightsize_candidate = (
                            has_cpu_data
                            and not cpu_low_avg
                            and cpu_avg < 40.0
                            and (cpu_peak_90d is None or cpu_peak_90d < 80.0)
                            and not investigation_candidate
                            and not eks_active
                        )

                    instances.append({
                        "instance_id": instance_id,
                        "instance_type": instance_type,
                        "name": name,
                        # Métricas recentes (45 dias)
                        "cpu_avg_pct": cpu_avg,
                        "cpu_active_days_pct": cpu_active_days_pct,
                        "net_out_mb_day": net_out_mb_day,
                        "net_in_mb_day": net_in_mb_day,
                        "net_total_mb_day": net_total_mb_day,
                        # Pico histórico (90 dias)
                        "cpu_peak_90d_pct": cpu_peak_90d,
                        # Contexto EKS (preenchido apenas para nós EKS)
                        "is_eks_node": is_eks_node,
                        "eks_active": eks_active,
                        "eks_active_reason": eks_active_reason,
                        "eks_low_load": eks_low_load,
                        "eks_info": eks_info,
                        # Classificação final
                        "investigation_candidate": investigation_candidate,
                        "periodic_use": periodic_use,
                        "io_bound": io_bound,
                        "rightsize_candidate": rightsize_candidate,
                    })
    except (botocore.exceptions.BotoCoreError, botocore.exceptions.ClientError) as exc:
        logger.warning("Falha ao coletar instâncias EC2: %s", exc)

    return instances


# ============================================================
# RDS — DatabaseConnections
# ============================================================

def collect_rds_utilization(start_date: str, end_date: str) -> list[dict]:
    """
    Retorna lista de instâncias RDS com média de conexões no período.
    Conexões próximas de zero indicam instância ociosa.
    """
    session = _session()
    rds = session.client("rds", region_name=config.WORKLOAD_REGION)
    cw = _cw_client(session)

    instances = []
    try:
        paginator = rds.get_paginator("describe_db_instances")
        for page in paginator.paginate():
            for db in page.get("DBInstances", []):
                db_id = db.get("DBInstanceIdentifier", "")
                db_class = db.get("DBInstanceClass", "")
                engine = db.get("Engine", "")
                multi_az = db.get("MultiAZ", False)
                status = db.get("DBInstanceStatus", "")

                connections_avg = _metric_avg(
                    cw,
                    namespace="AWS/RDS",
                    metric_name="DatabaseConnections",
                    dimensions=[{"Name": "DBInstanceIdentifier", "Value": db_id}],
                    start_date=start_date,
                    end_date=end_date,
                )
                instances.append({
                    "db_id": db_id,
                    "db_class": db_class,
                    "engine": engine,
                    "multi_az": multi_az,
                    "status": status,
                    "connections_avg": connections_avg,
                    # Média < 1 conexão no período = forte candidato a remoção
                    "idle": connections_avg is not None and connections_avg < 1.0,
                })
    except (botocore.exceptions.BotoCoreError, botocore.exceptions.ClientError) as exc:
        logger.warning("Falha ao coletar instâncias RDS: %s", exc)

    return instances


# ============================================================
# ELB — RequestCount
# ============================================================

def collect_elb_utilization(start_date: str, end_date: str) -> list[dict]:
    """
    Retorna lista de load balancers com RequestCount médio no período.
    RequestCount ≈ 0 indica LB sem tráfego real (candidato a remoção).
    """
    session = _session()
    elb = session.client("elbv2", region_name=config.WORKLOAD_REGION)
    cw = _cw_client(session)

    load_balancers = []
    try:
        paginator = elb.get_paginator("describe_load_balancers")
        for page in paginator.paginate():
            for lb in page.get("LoadBalancers", []):
                lb_arn = lb.get("LoadBalancerArn", "")
                lb_name = lb.get("LoadBalancerName", "")
                lb_type = lb.get("Type", "")  # application | network | gateway

                # Extrai sufixo do ARN para usar como dimensão CloudWatch
                # ARN: arn:aws:elasticloadbalancing:region:account:loadbalancer/app/name/id
                arn_suffix = "/".join(lb_arn.split("loadbalancer/")[-1].split("/")) if "loadbalancer/" in lb_arn else ""
                namespace = "AWS/ApplicationELB" if lb_type == "application" else "AWS/NetworkELB"
                metric_name = "RequestCount" if lb_type == "application" else "ActiveFlowCount"

                requests_avg = _metric_avg(
                    cw,
                    namespace=namespace,
                    metric_name=metric_name,
                    dimensions=[{"Name": "LoadBalancer", "Value": arn_suffix}],
                    start_date=start_date,
                    end_date=end_date,
                    stat="Sum" if metric_name == "RequestCount" else "Average",
                )
                load_balancers.append({
                    "lb_name": lb_name,
                    "lb_type": lb_type,
                    "lb_arn": lb_arn,
                    "metric": metric_name,
                    "metric_avg": requests_avg,
                    # Sem tráfego mensurável = candidato a remoção
                    "idle": requests_avg is not None and requests_avg < 1.0,
                    "no_data": requests_avg is None,
                })
    except (botocore.exceptions.BotoCoreError, botocore.exceptions.ClientError) as exc:
        logger.warning("Falha ao coletar load balancers: %s", exc)

    return load_balancers


# ============================================================
# EBS — volumes não atachados (com métricas de I/O e detecção de PVC)
# ============================================================

# Tags que o EBS CSI Driver do Kubernetes coloca em volumes criados como PVC
_K8S_PVC_TAGS = (
    "kubernetes.io/created-for/pvc/name",
    "kubernetes.io/created-for/pv/name",
    "CSIVolumeName",
)

# Janela para avaliar I/O de volumes não atachados (dias)
_EBS_IO_WINDOW_DAYS = 45


def collect_ebs_utilization(start_date: str, end_date: str) -> list[dict]:
    """
    Retorna volumes EBS não atachados e volumes GP2 (candidatos à migração GP3).

    Para volumes não atachados, coleta métricas de I/O (VolumeReadOps + VolumeWriteOps)
    nos últimos 45 dias para avaliar se o volume teve acesso recente.

    Detecta volumes gerenciados pelo Kubernetes (PVC) via tags do EBS CSI Driver.
    Esses volumes são classificados separadamente — nunca sugerir remoção direta.

    Classificação de volumes não atachados:
    - has_recent_io: teve I/O nos últimos 45d — verificar com owner antes de qualquer ação
    - is_kubernetes_pvc: gerenciado pelo K8s — verificar via kubectl antes de qualquer ação
    - zero_io: sem nenhum I/O nos 45d — candidato a avaliação, mas sempre com owner
    - no_io_data: sem dados de métrica — tratar com cautela
    """
    session = _session()
    ec2 = session.client("ec2", region_name=config.WORKLOAD_REGION)
    cw = _cw_client(session)

    # Janela de 45 dias para avaliação de I/O (independente da janela do relatório)
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")
    io_start = (end_dt - timedelta(days=_EBS_IO_WINDOW_DAYS)).strftime("%Y-%m-%d")

    volumes = []
    try:
        paginator = ec2.get_paginator("describe_volumes")
        for page in paginator.paginate():
            for vol in page.get("Volumes", []):
                vol_id = vol.get("VolumeId", "")
                vol_type = vol.get("VolumeType", "")
                size_gb = vol.get("Size", 0)
                state = vol.get("State", "")
                attachments = vol.get("Attachments", [])
                tags = {t["Key"]: t["Value"] for t in vol.get("Tags", [])}
                name = tags.get("Name", vol_id)

                is_unattached = state == "available" and len(attachments) == 0
                is_gp2 = vol_type == "gp2"

                # Só coleta métricas de I/O para volumes não atachados (evita chamadas desnecessárias)
                read_ops: Optional[float] = None
                write_ops: Optional[float] = None
                has_recent_io = False
                is_kubernetes_pvc = False
                pvc_name: Optional[str] = None
                pvc_namespace: Optional[str] = None

                if is_unattached:
                    # Detecta PVC Kubernetes pelas tags do EBS CSI Driver
                    for tag_key in _K8S_PVC_TAGS:
                        if tag_key in tags:
                            is_kubernetes_pvc = True
                            break
                    pvc_name = tags.get("kubernetes.io/created-for/pvc/name")
                    pvc_namespace = tags.get("kubernetes.io/created-for/pvc/namespace")

                    # Métricas de I/O nos últimos 45 dias (Sum = total de operações no período)
                    dims = [{"Name": "VolumeId", "Value": vol_id}]
                    read_stats = _metric_stats(
                        cw, "AWS/EBS", "VolumeReadOps", dims,
                        io_start, end_date, ["Sum"],
                    )
                    write_stats = _metric_stats(
                        cw, "AWS/EBS", "VolumeWriteOps", dims,
                        io_start, end_date, ["Sum"],
                    )
                    read_ops = read_stats.get("Sum")
                    write_ops = write_stats.get("Sum")

                    # Qualquer operação de leitura ou escrita = acesso recente
                    if read_ops is not None or write_ops is not None:
                        total_ops = (read_ops or 0.0) + (write_ops or 0.0)
                        has_recent_io = total_ops > 0

                volumes.append({
                    "volume_id": vol_id,
                    "volume_type": vol_type,
                    "size_gb": size_gb,
                    "state": state,
                    "name": name,
                    "unattached": is_unattached,
                    # GP2 → GP3: migração gratuita, ~20% mais barato, sem impacto operacional
                    "gp2_eligible_for_gp3": is_gp2,
                    # Métricas de I/O (apenas para volumes não atachados)
                    "read_ops_45d": read_ops,
                    "write_ops_45d": write_ops,
                    "has_recent_io": has_recent_io,
                    # Contexto Kubernetes
                    "is_kubernetes_pvc": is_kubernetes_pvc,
                    "pvc_name": pvc_name,
                    "pvc_namespace": pvc_namespace,
                })
    except (botocore.exceptions.BotoCoreError, botocore.exceptions.ClientError) as exc:
        logger.warning("Falha ao coletar volumes EBS: %s", exc)

    return volumes


# ============================================================
# EIP — Elastic IPs não atribuídos
# ============================================================

def collect_eip_utilization() -> list[dict]:
    """
    Retorna Elastic IPs alocados mas não associados a nenhuma instância ou ENI.
    Cada EIP idle gera custo fixo por hora (~$3,60/mês).
    """
    session = _session()
    ec2 = session.client("ec2", region_name=config.WORKLOAD_REGION)

    idle_eips = []
    try:
        resp = ec2.describe_addresses()
        for addr in resp.get("Addresses", []):
            # EIP ocioso = sem InstanceId e sem NetworkInterfaceId
            if not addr.get("InstanceId") and not addr.get("NetworkInterfaceId"):
                idle_eips.append({
                    "allocation_id": addr.get("AllocationId", ""),
                    "public_ip": addr.get("PublicIp", ""),
                    "domain": addr.get("Domain", ""),
                    # Custo estimado: ~$0.005/hora = ~$3.60/mês por EIP idle
                    "estimated_cost_usd_month": 3.60,
                })
    except (botocore.exceptions.BotoCoreError, botocore.exceptions.ClientError) as exc:
        logger.warning("Falha ao coletar Elastic IPs: %s", exc)

    return idle_eips


# ============================================================
# Ponto de entrada unificado
# ============================================================

def collect_all_utilization(start_date: str, end_date: str) -> dict:
    """
    Coleta todas as métricas de utilização disponíveis.

    Falhas individuais são silenciadas — o relatório continua com os dados
    que conseguiu coletar.

    Retorna dicionário com:
      - ec2: lista de instâncias com CPU média
      - rds: lista de instâncias RDS com conexões médias
      - elb: lista de load balancers com tráfego médio
      - ebs: lista de volumes com estado e tipo
      - eip: lista de Elastic IPs ociosos
    """
    logger.info("Coletando métricas de utilização (EC2, RDS, ELB, EBS, EIP)...")

    result = {
        "ec2": [],
        "rds": [],
        "elb": [],
        "ebs": [],
        "eip": [],
    }

    collectors = [
        ("ec2", lambda: collect_ec2_utilization(start_date, end_date)),
        ("rds", lambda: collect_rds_utilization(start_date, end_date)),
        ("elb", lambda: collect_elb_utilization(start_date, end_date)),
        ("ebs", lambda: collect_ebs_utilization(start_date, end_date)),
        ("eip", lambda: collect_eip_utilization()),
    ]

    for key, fn in collectors:
        try:
            result[key] = fn()
            logger.info("  %s: %d recursos coletados", key.upper(), len(result[key]))
        except Exception as exc:
            logger.warning("  %s: falha na coleta — %s", key.upper(), exc)

    return result
