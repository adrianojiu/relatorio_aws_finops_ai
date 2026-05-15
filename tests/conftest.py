"""
Fixtures compartilhadas para todos os testes do projeto relatorio_aws_finops_ai.

Uso:
    pytest tests/ --cov=src --cov-report=term-missing
"""
import sys
import os
from pathlib import Path
from datetime import datetime, date
import pytest

# Adiciona src/ ao path para que os imports funcionem
PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = str(PROJECT_ROOT / "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)


# ---------------------------------------------------------------------------
# Fixtures de dados de custo (DataFrames e listas de anomalias)
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_cost_data_long():
    """
    DataFrame no formato longo padrao do projeto (7 dias, 5 servicos, usage types variados).
    Colunas: Data, Serviço, UsageType, Custo($)
    """
    import pandas as pd
    data = {
        "Data": [
            # S3 - Requests-Tier1
            "2026-04-04", "2026-04-05", "2026-04-06", "2026-04-07",
            "2026-04-08", "2026-04-09", "2026-04-10",
            # S3 - TimedStorage-ByteHrs
            "2026-04-04", "2026-04-05", "2026-04-06", "2026-04-07",
            "2026-04-08", "2026-04-09", "2026-04-10",
            # S3 - LifecycleTransition
            "2026-04-09", "2026-04-10",
            # EC2 - Other - NatGateway-Bytes
            "2026-04-04", "2026-04-05", "2026-04-06", "2026-04-07",
            "2026-04-08", "2026-04-09", "2026-04-10",
            # CloudWatch - DataScanned-Bytes
            "2026-04-04", "2026-04-05", "2026-04-06", "2026-04-07",
            "2026-04-08", "2026-04-09", "2026-04-10",
            # AWS End User Messaging - OutboundSMS
            "2026-04-04", "2026-04-05", "2026-04-06", "2026-04-07",
            "2026-04-08", "2026-04-09", "2026-04-10",
            # GuardDuty - SAE1-PaidS3DataEventsAnalyzed
            "2026-04-09", "2026-04-10",
        ],
        "Serviço": (
            ["Amazon Simple Storage Service"] * 7
            + ["Amazon Simple Storage Service"] * 7
            + ["Amazon Simple Storage Service"] * 2
            + ["EC2 - Other"] * 7
            + ["AmazonCloudWatch"] * 7
            + ["AWS End User Messaging"] * 7
            + ["Amazon GuardDuty"] * 2
        ),
        "UsageType": (
            ["Requests-Tier1"] * 7
            + ["TimedStorage-ByteHrs"] * 7
            + ["LifecycleTransition"] * 2
            + ["NatGateway-Bytes"] * 7
            + ["DataScanned-Bytes"] * 7
            + ["OutboundSMS-BR-Standard-Sharedroute-MessageCount"] * 7
            + ["SAE1-PaidS3DataEventsAnalyzed"] * 2
        ),
        "Custo($)": [
            # S3 Requests-Tier1: crescendo ate pico no dia 9-10
            40.0, 42.0, 45.0, 48.0, 50.0, 95.0, 95.0,
            # S3 TimedStorage-ByteHrs: estavel
            100.0, 100.0, 100.0, 100.0, 100.0, 100.0, 100.0,
            # S3 LifecycleTransition: pico no dia 9-10
            0.0, 0.0,
            # EC2 NatGateway-Bytes: estavel com leve alta
            110.0, 112.0, 113.0, 115.0, 118.0, 125.0, 130.0,
            # CloudWatch DataScanned-Bytes: leve queda
            30.0, 29.0, 28.0, 28.0, 27.0, 26.0, 25.0,
            # End User Messaging OutboundSMS: variacao organica
            12.0, 14.0, 11.0, 13.0, 15.0, 10.0, 16.0,
            # GuardDuty: pico nos dias 9-10
            5.0, 8.0,
        ],
    }
    return pd.DataFrame(data)


@pytest.fixture
def sample_cost_data_wide():
    """
    DataFrame no formato WIDE (formato de exportacao CSV do projeto).
    Primeira coluna = Service, demais colunas = servicos com ($)
    """
    import pandas as pd
    data = {
        "Service": ["Service total", "2026-04-04", "2026-04-05", "2026-04-06"],
        "EC2-Instances($)": ["150.00", "50.00", "50.00", "50.00"],
        "S3($)": ["90.00", "30.00", "30.00", "30.00"],
        "Total costs($)": ["240.00", "80.00", "80.00", "80.00"],
    }
    return pd.DataFrame(data)


@pytest.fixture
def sample_cost_data_no_usage_type():
    """
    DataFrame sem coluna UsageType (para testar fallback para "Total").
    """
    import pandas as pd
    data = {
        "Data": ["2026-04-08", "2026-04-09", "2026-04-10"],
        "Serviço": ["S3", "S3", "EC2"],
        "Custo($)": [50.0, 60.0, 100.0],
    }
    return pd.DataFrame(data)


@pytest.fixture
def sample_anomaly_list():
    """
    Lista de anomalias pre-processadas para testar enriquecimento.
    """
    return [
        {
            "service": "Amazon Simple Storage Service",
            "usage_type": "Requests-Tier1",
            "cost_today": 95.0,
            "avg_7d": 50.0,
            "delta_usd": 45.0,
            "delta_pct": 90.0,
            "days_present": 7,
            "series": [
                {"date": "2026-04-04", "cost_usd": 40.0},
                {"date": "2026-04-05", "cost_usd": 42.0},
                {"date": "2026-04-06", "cost_usd": 45.0},
                {"date": "2026-04-07", "cost_usd": 48.0},
                {"date": "2026-04-08", "cost_usd": 50.0},
                {"date": "2026-04-09", "cost_usd": 95.0},
                {"date": "2026-04-10", "cost_usd": 95.0},
            ],
        },
        {
            "service": "EC2 - Other",
            "usage_type": "NatGateway-Bytes",
            "cost_today": 130.0,
            "avg_7d": 115.0,
            "delta_usd": 15.0,
            "delta_pct": 13.04,
            "days_present": 7,
            "series": [
                {"date": "2026-04-04", "cost_usd": 110.0},
                {"date": "2026-04-05", "cost_usd": 112.0},
                {"date": "2026-04-06", "cost_usd": 113.0},
                {"date": "2026-04-07", "cost_usd": 115.0},
                {"date": "2026-04-08", "cost_usd": 118.0},
                {"date": "2026-04-09", "cost_usd": 125.0},
                {"date": "2026-04-10", "cost_usd": 130.0},
            ],
        },
        {
            "service": "AmazonCloudWatch",
            "usage_type": "DataScanned-Bytes",
            "cost_today": 25.0,
            "avg_7d": 28.0,
            "delta_usd": -3.0,
            "delta_pct": -10.71,
            "days_present": 7,
            "series": [
                {"date": "2026-04-04", "cost_usd": 30.0},
                {"date": "2026-04-05", "cost_usd": 29.0},
                {"date": "2026-04-06", "cost_usd": 28.0},
                {"date": "2026-04-07", "cost_usd": 28.0},
                {"date": "2026-04-08", "cost_usd": 27.0},
                {"date": "2026-04-09", "cost_usd": 26.0},
                {"date": "2026-04-10", "cost_usd": 25.0},
            ],
        },
    ]


@pytest.fixture
def sample_s3_anomaly():
    """
    Anomalia S3 completa com usage_type_context e series para testar tier change analysis.
    """
    return {
        "service": "Amazon Simple Storage Service",
        "usage_type": "Requests-Tier1",
        "cost_today": 95.0,
        "avg_7d": 50.0,
        "delta_usd": 45.0,
        "delta_pct": 90.0,
        "days_present": 7,
        "usage_type_context": {
            "cost_family": "s3_requests",
            "summary": "Custo ligado a requisicoes S3; em `Requests-Tier1/Tier2`, tier significa preco de request, nao classe de armazenamento do bucket.",
            "is_storage_class_change_signal": False,
            "storage_tier_candidates": [],
        },
        "complementary_usage_types": [
            {
                "usage_type": "TimedStorage-ByteHrs",
                "cost_today": 100.0,
                "avg_7d": 100.0,
                "delta_usd": 0.0,
                "delta_pct": 0.0,
                "usage_type_context": {
                    "cost_family": "s3_storage",
                    "is_storage_class_change_signal": True,
                    "storage_tier_candidates": ["Standard"],
                },
            }
        ],
        "top_api_operations": [
            {
                "operation": "GetObject",
                "cost_today": 60.0,
                "avg_7d": 25.0,
                "delta_usd": 35.0,
                "delta_pct": 140.0,
            },
        ],
    }


@pytest.fixture
def sample_s3_anomaly_with_tier_transition():
    """
    Anomalia S3 com sinais fortes de transicao de classe/tier.
    """
    return {
        "service": "Amazon Simple Storage Service",
        "usage_type": "LifecycleTransition",
        "cost_today": 250.0,
        "avg_7d": 30.0,
        "delta_usd": 220.0,
        "delta_pct": 733.33,
        "days_present": 2,
        "usage_type_context": {
            "cost_family": "s3_storage_class_transition",
            "summary": "Custo compativel com transicao entre classes/tier de armazenamento do S3, incluindo lifecycle e Intelligent-Tiering.",
            "is_storage_class_change_signal": True,
            "storage_tier_candidates": ["Glacier", "Standard-IA"],
        },
        "complementary_usage_types": [
            {
                "usage_type": "TimedStorage-ByteHrs",
                "cost_today": 80.0,
                "avg_7d": 100.0,
                "delta_usd": -20.0,
                "delta_pct": -20.0,
                "usage_type_context": {
                    "cost_family": "s3_storage",
                    "is_storage_class_change_signal": True,
                    "storage_tier_candidates": ["Standard"],
                },
            },
            {
                "usage_type": "TimedStorage-GlacierByteHrs",
                "cost_today": 40.0,
                "avg_7d": 10.0,
                "delta_usd": 30.0,
                "delta_pct": 300.0,
                "usage_type_context": {
                    "cost_family": "s3_storage",
                    "is_storage_class_change_signal": True,
                    "storage_tier_candidates": ["Glacier"],
                },
            },
        ],
        "top_api_operations": [
            {
                "operation": "LifecycleTransition",
                "cost_today": 200.0,
                "avg_7d": 20.0,
                "delta_usd": 180.0,
                "delta_pct": 900.0,
            },
            {
                "operation": "CopyObject",
                "cost_today": 50.0,
                "avg_7d": 10.0,
                "delta_usd": 40.0,
                "delta_pct": 400.0,
            },
        ],
    }


@pytest.fixture
def sample_cost_period_df():
    """
    DataFrame com custos do periodo para testar calculo de metricas.
    Colunas: Service (datas), servicos como colunas, Total costs($) como ultima coluna.
    """
    import pandas as pd
    return pd.DataFrame({
        "Service": [
            "2026-04-04", "2026-04-05", "2026-04-06", "2026-04-07",
            "2026-04-08", "2026-04-09", "2026-04-10",
        ],
        "Amazon Simple Storage Service": [140.0, 142.0, 145.0, 148.0, 150.0, 195.0, 195.0],
        "EC2 - Other": [110.0, 112.0, 113.0, 115.0, 118.0, 125.0, 130.0],
        "AmazonCloudWatch": [30.0, 29.0, 28.0, 28.0, 27.0, 26.0, 25.0],
        "AWS End User Messaging": [12.0, 14.0, 11.0, 13.0, 15.0, 10.0, 16.0],
        "Total costs($)": [292.0, 297.0, 297.0, 304.0, 310.0, 356.0, 366.0],
    })
