"""
Testes unitarios para src/collectors/utilization_metrics.py

Foco nas funcoes de agregacao de metricas CloudWatch (_metric_stats, _metric_avg),
que sao a base reutilizada por todos os coletores de utilizacao (EC2, RDS, ELB).
Usa um client CloudWatch mockado — sem chamadas reais a AWS.
"""
from unittest.mock import MagicMock

import botocore.exceptions
import pytest


class TestMetricStats:
    def test_returns_average_maximum_and_sum(self):
        from collectors import utilization_metrics

        cw = MagicMock()
        cw.get_metric_statistics.return_value = {
            "Datapoints": [
                {"Average": 10.0, "Maximum": 20.0, "Sum": 100.0},
                {"Average": 30.0, "Maximum": 40.0, "Sum": 200.0},
            ]
        }
        result = utilization_metrics._metric_stats(
            cw, "AWS/EC2", "CPUUtilization", [{"Name": "InstanceId", "Value": "i-1"}],
            "2026-01-01", "2026-01-02", ["Average", "Maximum", "Sum"],
        )
        assert result["Average"] == 20.0
        assert result["Maximum"] == 40.0
        assert result["Sum"] == 300.0

    def test_no_datapoints_returns_none_for_all_stats(self):
        from collectors import utilization_metrics

        cw = MagicMock()
        cw.get_metric_statistics.return_value = {"Datapoints": []}
        result = utilization_metrics._metric_stats(
            cw, "AWS/EC2", "CPUUtilization", [], "2026-01-01", "2026-01-02", ["Average"],
        )
        assert result["Average"] is None

    def test_client_error_returns_none_without_raising(self):
        from collectors import utilization_metrics

        cw = MagicMock()
        cw.get_metric_statistics.side_effect = botocore.exceptions.ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "denied"}}, "GetMetricStatistics"
        )
        result = utilization_metrics._metric_stats(
            cw, "AWS/EC2", "CPUUtilization", [], "2026-01-01", "2026-01-02", ["Average"],
        )
        assert result == {"Average": None}

    def test_active_days_pct_counts_days_above_20_percent(self):
        from collectors import utilization_metrics

        cw = MagicMock()
        cw.get_metric_statistics.return_value = {
            "Datapoints": [
                {"Average": 5.0},
                {"Average": 25.0},
                {"Average": 30.0},
                {"Average": 10.0},
            ]
        }
        result = utilization_metrics._metric_stats(
            cw, "AWS/EC2", "CPUUtilization", [], "2026-01-01", "2026-01-04", ["Average"],
        )
        # 2 de 4 dias acima de 20% = 50%
        assert result["_active_days_pct"] == 50.0


class TestMetricAvg:
    def test_returns_average_value(self):
        from collectors import utilization_metrics

        cw = MagicMock()
        cw.get_metric_statistics.return_value = {
            "Datapoints": [{"Average": 42.0}]
        }
        result = utilization_metrics._metric_avg(
            cw, "AWS/RDS", "DatabaseConnections", [], "2026-01-01", "2026-01-01",
        )
        assert result == 42.0

    def test_returns_none_when_no_data(self):
        from collectors import utilization_metrics

        cw = MagicMock()
        cw.get_metric_statistics.return_value = {"Datapoints": []}
        result = utilization_metrics._metric_avg(
            cw, "AWS/RDS", "DatabaseConnections", [], "2026-01-01", "2026-01-01",
        )
        assert result is None
