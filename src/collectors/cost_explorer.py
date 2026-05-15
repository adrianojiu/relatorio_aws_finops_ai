"""
Cost Explorer data collector
"""

import config
import boto3
import botocore
import pandas as pd
from datetime import datetime, timedelta


def _build_cost_filter(included_services=None):
    filters = [
        {
            'Not': {
                'Dimensions': {
                    'Key': 'RECORD_TYPE',
                    'Values': config.EXCLUDED_RECORD_TYPES
                }
            }
        }
    ]

    if config.EXCLUDED_SERVICES:
        filters.insert(0, {
            'Not': {
                'Dimensions': {
                    'Key': 'SERVICE',
                    'Values': config.EXCLUDED_SERVICES
                }
            }
        })

    if included_services:
        filters.append({
            'Dimensions': {
                'Key': 'SERVICE',
                'Values': included_services
            }
        })

    return filters[0] if len(filters) == 1 else {'And': filters}


def _build_cost_explorer_client():
    """
    Create a Cost Explorer client using the configured profile and region.
    """
    session = boto3.Session(profile_name=config.AWS_PROFILE, region_name=config.COST_EXPLORER_REGION)
    return session.client("ce")


def _iter_cost_and_usage_results(ce, request_params):
    """
    Iterate through Cost Explorer pages so grouped rows are not truncated.
    """
    next_token = None
    while True:
        paged_params = dict(request_params)
        if next_token:
            paged_params["NextPageToken"] = next_token
        response = ce.get_cost_and_usage(**paged_params)
        for day in response.get("ResultsByTime", []):
            yield day
        next_token = response.get("NextPageToken")
        if not next_token:
            break


def fetch_cost_drivers_from_cost_explorer(data_inicio, data_fim):
    """
    Fetch daily cost drivers grouped by service and usage type.
    Returns: DataFrame with columns ['Data', 'Serviço', 'UsageType', 'Custo($)']
    """
    ce = _build_cost_explorer_client()

    print(f"Coletando custos de {data_inicio} até {data_fim} (sem TAX)...")

    data_fim_exclusiva = (
        datetime.strptime(data_fim, "%Y-%m-%d") + timedelta(days=1)
    ).strftime("%Y-%m-%d")

    request_params = {
        "TimePeriod": {
            "Start": data_inicio,
            "End": data_fim_exclusiva
        },
        "Granularity": "DAILY",
        "Metrics": ["UnblendedCost"],
        "GroupBy": [
            {"Type": "DIMENSION", "Key": "SERVICE"},
            {"Type": "DIMENSION", "Key": "USAGE_TYPE"},
        ],
        "Filter": _build_cost_filter()
    }

    rows = []
    for day in _iter_cost_and_usage_results(ce, request_params):
        date = day["TimePeriod"]["Start"]
        for group in day["Groups"]:
            keys = group.get("Keys", [])
            service = keys[0] if len(keys) > 0 else "Unknown"
            usage_type = keys[1] if len(keys) > 1 else "Unknown"
            amount = float(group["Metrics"]["UnblendedCost"]["Amount"])
            rows.append(
                {
                    "Data": date,
                    "Serviço": service,
                    "UsageType": usage_type,
                    "Custo($)": amount,
                }
            )

    df = pd.DataFrame(rows)
    if df.empty:
        raise Exception("Nenhum dado retornado do Cost Explorer (após remover TAX).")

    return df


def fetch_service_operations_from_cost_explorer(data_inicio, data_fim, services=None):
    """
    Fetch daily cost slices grouped by service and API operation.
    Returns: DataFrame with columns ['Data', 'Serviço', 'ApiOperation', 'Custo($)']
    """
    target_services = list(services or config.API_OPERATION_SERVICES)
    if not target_services:
        return pd.DataFrame(columns=["Data", "Serviço", "ApiOperation", "Custo($)"])

    ce = _build_cost_explorer_client()
    print(
        "Coletando API operations de "
        f"{data_inicio} até {data_fim} para {', '.join(target_services)}..."
    )

    data_fim_exclusiva = (
        datetime.strptime(data_fim, "%Y-%m-%d") + timedelta(days=1)
    ).strftime("%Y-%m-%d")

    request_params = {
        "TimePeriod": {
            "Start": data_inicio,
            "End": data_fim_exclusiva,
        },
        "Granularity": "DAILY",
        "Metrics": ["UnblendedCost"],
        "GroupBy": [
            {"Type": "DIMENSION", "Key": "SERVICE"},
            {"Type": "DIMENSION", "Key": "OPERATION"},
        ],
        "Filter": _build_cost_filter(included_services=target_services),
    }

    rows = []
    for day in _iter_cost_and_usage_results(ce, request_params):
        date = day["TimePeriod"]["Start"]
        for group in day.get("Groups", []):
            keys = group.get("Keys", [])
            service = keys[0] if len(keys) > 0 else "Unknown"
            operation = keys[1] if len(keys) > 1 else "Unknown"
            amount = float(group["Metrics"]["UnblendedCost"]["Amount"])
            rows.append(
                {
                    "Data": date,
                    "Serviço": service,
                    "ApiOperation": operation,
                    "Custo($)": amount,
                }
            )

    if not rows:
        return pd.DataFrame(columns=["Data", "Serviço", "ApiOperation", "Custo($)"])

    return pd.DataFrame(rows)

def fetch_sms_30d(ultimo_dia):
    """
    Fetch SMS_ANALYSIS_DAYS days of End User Messaging costs grouped by usage type.
    Usado para calcular o baseline de 30 dias de SMS, reduzindo falsos positivos
    causados pela volatilidade transacional (OTP/MFA/reset de senha).
    Returns: DataFrame com colunas ['Data', 'UsageType', 'Custo($)']
    """
    end_date = datetime.strptime(ultimo_dia, "%Y-%m-%d")
    start_date = end_date - timedelta(days=config.SMS_ANALYSIS_DAYS - 1)
    data_inicio = start_date.strftime("%Y-%m-%d")
    # Cost Explorer end date e exclusivo — avanca um dia
    data_fim_exclusiva = (end_date + timedelta(days=1)).strftime("%Y-%m-%d")

    print(f"Coletando SMS (End User Messaging) de {data_inicio} até {ultimo_dia} ({config.SMS_ANALYSIS_DAYS} dias)...")

    ce = _build_cost_explorer_client()
    request_params = {
        "TimePeriod": {"Start": data_inicio, "End": data_fim_exclusiva},
        "Granularity": "DAILY",
        "Metrics": ["UnblendedCost"],
        "GroupBy": [
            {"Type": "DIMENSION", "Key": "SERVICE"},
            {"Type": "DIMENSION", "Key": "USAGE_TYPE"},
        ],
        "Filter": _build_cost_filter(included_services=list(config.SPECIAL_SERVICES)),
    }

    rows = []
    for day in _iter_cost_and_usage_results(ce, request_params):
        date = day["TimePeriod"]["Start"]
        for group in day["Groups"]:
            keys = group.get("Keys", [])
            usage_type = keys[1] if len(keys) > 1 else "Unknown"
            amount = float(group["Metrics"]["UnblendedCost"]["Amount"])
            rows.append({"Data": date, "UsageType": usage_type, "Custo($)": amount})

    if not rows:
        return pd.DataFrame(columns=["Data", "UsageType", "Custo($)"])
    return pd.DataFrame(rows)


def fetch_costs_from_cost_explorer(data_inicio, data_fim):
    """
    Fetch cost data from AWS Cost Explorer
    Returns: DataFrame with columns ['Data', 'Serviço', 'Custo($)']
    """
    try:
        detailed_df = fetch_cost_drivers_from_cost_explorer(data_inicio, data_fim)
    except (botocore.exceptions.BotoCoreError, botocore.exceptions.ClientError):
        raise

    return (
        detailed_df.groupby(["Data", "Serviço"], as_index=False)["Custo($)"]
        .sum()
        .sort_values(["Data", "Serviço"])
    )
