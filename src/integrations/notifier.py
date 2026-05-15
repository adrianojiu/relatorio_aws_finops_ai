"""
Notificação via SNS com upload de arquivos para S3.

Fluxo:
  1. Faz upload dos arquivos para S3 em path organizado por YYYY/MM/DD/HHmm/
  2. Gera presigned URLs válidas por 30 dias (2592000 segundos)
  3. Publica mensagem no tópico SNS com resumo + links de download

Diário : envia apenas o HTML interativo do relatório
Mensal : envia apenas os dois CSVs (todos os serviços + somente PDP)
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Optional

import boto3
from botocore.config import Config as BotoConfig

PRESIGNED_URL_EXPIRY_SECONDS = 30 * 24 * 3600  # 30 dias


def _s3_client(aws_profile: Optional[str], region: str):
    session = boto3.Session(profile_name=aws_profile or None, region_name=region)
    return session.client("s3", config=BotoConfig(connect_timeout=30, read_timeout=120))


def _sns_client(aws_profile: Optional[str], region: str):
    session = boto3.Session(profile_name=aws_profile or None, region_name=region)
    return session.client("sns")


def _s3_key(prefix: str, filename: str, ts: datetime) -> str:
    """Monta o caminho S3 organizado por ano/mes/dia/hora-minuto."""
    time_path = ts.strftime("%Y/%m/%d/%H%M")
    clean_prefix = prefix.rstrip("/")
    return f"{clean_prefix}/{time_path}/{filename}"


def upload_file(
    local_path: str,
    bucket: str,
    s3_key: str,
    aws_profile: Optional[str],
    region: str,
) -> str:
    """Faz upload do arquivo e retorna a presigned URL válida por 30 dias."""
    client = _s3_client(aws_profile, region)
    client.upload_file(local_path, bucket, s3_key)
    url = client.generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": s3_key},
        ExpiresIn=PRESIGNED_URL_EXPIRY_SECONDS,
    )
    return url


def _publish_sns(
    topic_arn: str,
    subject: str,
    message: str,
    aws_profile: Optional[str],
    region: str,
) -> None:
    client = _sns_client(aws_profile, region)
    client.publish(TopicArn=topic_arn, Subject=subject, Message=message)


def notify_daily_report(
    topic_arn: str,
    bucket: str,
    s3_prefix: str,
    html_path: str,
    aws_profile: Optional[str],
    aws_region: str,
    reference_day: str,
    avg_cost: float,
    variation_pct: float,
) -> None:
    """Envia notificação do relatório diário com link para o HTML interativo."""
    ts = datetime.now()

    html_key = _s3_key(s3_prefix, Path(html_path).name, ts)
    html_url = upload_file(html_path, bucket, html_key, aws_profile, aws_region)

    variation_sign = "+" if variation_pct >= 0 else ""
    subject = f"[FinOps CIAM] Relatório Diário — {reference_day}"
    message = (
        f"Relatório diário de custos AWS — {reference_day}\n"
        f"{'=' * 60}\n\n"
        f"  Média diária  : USD {avg_cost:,.2f}\n"
        f"  Variação média: {variation_sign}{variation_pct:.1f}%\n\n"
        f"Relatório HTML (link válido por 30 dias):\n"
        f"  {html_url}\n\n"
        f"Caminho S3: s3://{bucket}/{_s3_key(s3_prefix, '', ts).rstrip('/')}/\n"
    )
    _publish_sns(topic_arn, subject, message, aws_profile, aws_region)
    print(f"[notifier] SNS publicado: {subject}")


def notify_monthly_report(
    topic_arn: str,
    bucket: str,
    s3_prefix: str,
    csv_all_path: str,
    csv_pdp_path: str,
    aws_profile: Optional[str],
    aws_region: str,
    month: str,
    total_cost: float,
    pdp_cost: float,
    avg_daily: float,
) -> None:
    """Envia notificação do relatório mensal com links para os dois CSVs."""
    ts = datetime.now()
    links: list[str] = []

    for label, path in [
        ("CSV todos os serviços", csv_all_path),
        ("CSV somente PDP     ", csv_pdp_path),
    ]:
        key = _s3_key(s3_prefix, Path(path).name, ts)
        url = upload_file(path, bucket, key, aws_profile, aws_region)
        links.append(f"  {label}: {url}")

    subject = f"[FinOps CIAM] Relatório Mensal — {month}"
    message = (
        f"Relatório mensal de custos AWS — {month}\n"
        f"{'=' * 60}\n\n"
        f"  Custo total   : USD {total_cost:,.2f}\n"
        f"  Custo PDP     : USD {pdp_cost:,.2f} ({pdp_cost / total_cost * 100:.1f}% do total)\n"
        f"  Média diária  : USD {avg_daily:,.2f}\n\n"
        f"Arquivos disponíveis (links válidos por 30 dias):\n"
        + "\n".join(links)
        + "\n\n"
        f"Caminho S3: s3://{bucket}/{_s3_key(s3_prefix, '', ts).rstrip('/')}/\n"
    )
    _publish_sns(topic_arn, subject, message, aws_profile, aws_region)
    print(f"[notifier] SNS publicado: {subject}")
