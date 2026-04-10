"""
Cost Explorer data collector
"""

import boto3
import botocore
import pandas as pd
from datetime import datetime, timedelta
import config


def _build_cost_filter():
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

    return filters[0] if len(filters) == 1 else {'And': filters}


def fetch_cost_drivers_from_cost_explorer(data_inicio, data_fim):
    """
    Fetch daily cost drivers grouped by service and usage type.
    Returns: DataFrame with columns ['Data', 'Serviço', 'UsageType', 'Custo($)']
    """
    session = boto3.Session(profile_name=config.AWS_PROFILE, region_name=config.COST_EXPLORER_REGION)
    ce = session.client("ce")

    print(f"Coletando custos de {data_inicio} até {data_fim} (sem TAX)...")

    data_fim_exclusiva = (
        datetime.strptime(data_fim, "%Y-%m-%d") + timedelta(days=1)
    ).strftime("%Y-%m-%d")

    response = ce.get_cost_and_usage(
        TimePeriod={
            "Start": data_inicio,
            "End": data_fim_exclusiva
        },
        Granularity="DAILY",
        Metrics=["UnblendedCost"],
        GroupBy=[
            {"Type": "DIMENSION", "Key": "SERVICE"},
            {"Type": "DIMENSION", "Key": "USAGE_TYPE"},
        ],
        Filter=_build_cost_filter()
    )

    rows = []
    for day in response["ResultsByTime"]:
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
