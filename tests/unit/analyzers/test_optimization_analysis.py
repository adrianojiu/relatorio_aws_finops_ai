"""
Testes unitarios para src/analyzers/optimization_analysis.py

Cobre:
  - build_service_trends: tendencia de custo por servico (3 meses)
  - build_unit_economics: serie diaria, projecao anual e crescimento MoM
  - build_optimization_opportunities: deteccao de oportunidades por regras deterministicas
  - build_unclassified_services: servicos sem regra mapeada mas com comportamento relevante
  - build_optimization_payload: montagem do payload final para o Bedrock
"""
import pandas as pd
import pytest


def _make_df(rows):
    return pd.DataFrame(rows, columns=["Data", "Serviço", "UsageType", "Custo($)"])


@pytest.fixture
def stable_ec2_df():
    """90 dias de custo estavel para o servico EC2 Compute."""
    dates = pd.date_range("2026-01-01", periods=90, freq="D").strftime("%Y-%m-%d")
    rows = [(d, "Amazon Elastic Compute Cloud - Compute", "BoxUsage:m5.large", 20.0) for d in dates]
    return _make_df(rows)


@pytest.fixture
def growing_service_df():
    """90 dias de custo crescente para um servico sem regra deterministica mapeada."""
    dates = pd.date_range("2026-01-01", periods=90, freq="D")
    rows = [
        (d.strftime("%Y-%m-%d"), "Amazon Kinesis Firehose", "DataIngested-Bytes", 30.0 + i * 1.0)
        for i, d in enumerate(dates)
    ]
    return _make_df(rows)


class TestBuildServiceTrends:
    def test_empty_dataframe_returns_empty(self):
        from analyzers import optimization_analysis

        result = optimization_analysis.build_service_trends(pd.DataFrame(), "2026-01-01", "2026-03-31")
        assert result.empty

    def test_stable_service_classified_as_estavel(self, stable_ec2_df):
        from analyzers import optimization_analysis

        result = optimization_analysis.build_service_trends(stable_ec2_df, "2026-01-01", "2026-03-31")
        assert not result.empty
        row = result.iloc[0]
        assert row["Serviço"] == "Amazon Elastic Compute Cloud - Compute"
        assert row["Comportamento"] == "Estável"
        assert row["Total 3M (US$)"] == pytest.approx(20.0 * 90, abs=1)

    def test_growing_service_classified_as_crescendo(self, growing_service_df):
        from analyzers import optimization_analysis

        result = optimization_analysis.build_service_trends(growing_service_df, "2026-01-01", "2026-03-31")
        assert not result.empty
        row = result.iloc[0]
        assert row["Comportamento"] == "Crescendo"
        assert row["Tendência (US$/dia)"] > 0

    def test_service_below_threshold_is_excluded(self):
        from analyzers import optimization_analysis

        rows = [("2026-01-01", "Serviço Pequeno", "Usage-Tipo", 0.5)]
        result = optimization_analysis.build_service_trends(_make_df(rows), "2026-01-01", "2026-01-01")
        assert result.empty


class TestBuildUnitEconomics:
    def test_empty_dataframe_returns_zeroed_dict(self):
        from analyzers import optimization_analysis

        result = optimization_analysis.build_unit_economics(pd.DataFrame(), "2026-01-01", "2026-03-31")
        assert result["daily_series"] == []
        assert result["daily_avg_usd"] == 0.0
        assert result["projected_annual_usd"] == 0.0

    def test_stable_cost_produces_consistent_projection(self, stable_ec2_df):
        from analyzers import optimization_analysis

        result = optimization_analysis.build_unit_economics(stable_ec2_df, "2026-01-01", "2026-03-31")
        assert result["daily_avg_usd"] == pytest.approx(20.0, abs=0.5)
        assert result["projected_annual_usd"] == pytest.approx(20.0 * 365, rel=0.05)
        assert len(result["daily_series"]) == 90

    def test_monthly_avg_has_three_entries(self, stable_ec2_df):
        from analyzers import optimization_analysis

        result = optimization_analysis.build_unit_economics(stable_ec2_df, "2026-01-01", "2026-03-31")
        assert len(result["monthly_avg_usd"]) == 3


class TestBuildOptimizationOpportunities:
    def test_empty_trends_returns_empty_list(self):
        from analyzers import optimization_analysis

        result = optimization_analysis.build_optimization_opportunities(pd.DataFrame(), pd.DataFrame(), [])
        assert result == []

    def test_stable_high_cost_ec2_suggests_savings_plan(self, stable_ec2_df):
        from analyzers import optimization_analysis

        trends = optimization_analysis.build_service_trends(stable_ec2_df, "2026-01-01", "2026-03-31")
        result = optimization_analysis.build_optimization_opportunities(stable_ec2_df, trends, [])
        categories = {op["categoria"] for op in result}
        assert "savings_plans" in categories

    def test_unattached_ebs_volume_suggests_idle_cleanup(self, stable_ec2_df):
        from analyzers import optimization_analysis

        trends = optimization_analysis.build_service_trends(stable_ec2_df, "2026-01-01", "2026-03-31")
        utilization = {
            "ebs": [
                {
                    "volume_id": "vol-123",
                    "name": "vol-123",
                    "size_gb": 500,
                    "unattached": True,
                    "is_kubernetes_pvc": False,
                    "has_recent_io": False,
                    "read_ops_45d": 0,
                    "write_ops_45d": 0,
                }
            ]
        }
        result = optimization_analysis.build_optimization_opportunities(
            stable_ec2_df, trends, [], utilization=utilization
        )
        idle_ops = [op for op in result if op["categoria"] == "idle_cleanup"]
        assert idle_ops
        assert "EBS" in idle_ops[0]["acao"]

    def test_opportunities_are_deduplicated_by_service_and_category(self, stable_ec2_df):
        from analyzers import optimization_analysis

        trends = optimization_analysis.build_service_trends(stable_ec2_df, "2026-01-01", "2026-03-31")
        result = optimization_analysis.build_optimization_opportunities(stable_ec2_df, trends, [])
        keys = [(op["servico"], op["categoria"]) for op in result]
        assert len(keys) == len(set(keys))


class TestBuildUnclassifiedServices:
    def test_growing_service_without_rule_is_listed(self, growing_service_df):
        from analyzers import optimization_analysis

        trends = optimization_analysis.build_service_trends(growing_service_df, "2026-01-01", "2026-03-31")
        opportunities = optimization_analysis.build_optimization_opportunities(growing_service_df, trends, [])
        result = optimization_analysis.build_unclassified_services(growing_service_df, trends, opportunities)
        assert any(item["servico"] == "Amazon Kinesis Firehose" for item in result)

    def test_service_already_classified_is_excluded(self, stable_ec2_df):
        from analyzers import optimization_analysis

        trends = optimization_analysis.build_service_trends(stable_ec2_df, "2026-01-01", "2026-03-31")
        opportunities = optimization_analysis.build_optimization_opportunities(stable_ec2_df, trends, [])
        result = optimization_analysis.build_unclassified_services(stable_ec2_df, trends, opportunities)
        assert not any(item["servico"] == "Amazon Elastic Compute Cloud - Compute" for item in result)


class TestBuildOptimizationPayload:
    def test_payload_has_expected_top_level_keys(self, stable_ec2_df):
        from analyzers import optimization_analysis

        trends = optimization_analysis.build_service_trends(stable_ec2_df, "2026-01-01", "2026-03-31")
        opportunities = optimization_analysis.build_optimization_opportunities(stable_ec2_df, trends, [])
        unit_economics = optimization_analysis.build_unit_economics(stable_ec2_df, "2026-01-01", "2026-03-31")

        payload = optimization_analysis.build_optimization_payload(
            df_service_trends=trends,
            opportunities=opportunities,
            unit_economics=unit_economics,
            start_date="2026-01-01",
            end_date="2026-03-31",
            df_raw=stable_ec2_df,
        )
        assert payload["report_type"] == "optimization"
        assert payload["window"]["start_date"] == "2026-01-01"
        assert "top_services" in payload
        assert "high_priority_opportunities" in payload
        assert "unclassified_services_for_investigation" in payload

    def test_payload_without_raw_df_skips_unclassified(self, stable_ec2_df):
        from analyzers import optimization_analysis

        trends = optimization_analysis.build_service_trends(stable_ec2_df, "2026-01-01", "2026-03-31")
        opportunities = optimization_analysis.build_optimization_opportunities(stable_ec2_df, trends, [])
        unit_economics = optimization_analysis.build_unit_economics(stable_ec2_df, "2026-01-01", "2026-03-31")

        payload = optimization_analysis.build_optimization_payload(
            df_service_trends=trends,
            opportunities=opportunities,
            unit_economics=unit_economics,
            start_date="2026-01-01",
            end_date="2026-03-31",
        )
        assert payload["unclassified_services_for_investigation"] == []
