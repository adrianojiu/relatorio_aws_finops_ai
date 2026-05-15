"""Testes unitarios para `src/analyzers/anomaly_detection.py`."""

import pandas as pd
import pytest


def _build_cost_rows(service, usage_type, daily_costs, start_date="2026-04-04"):
    """Cria uma serie diaria simples no formato esperado pelo modulo."""
    base_date = pd.Timestamp(start_date)
    rows = []
    for offset, cost in enumerate(daily_costs):
        rows.append(
            {
                "Data": (base_date + pd.Timedelta(days=offset)).strftime("%Y-%m-%d"),
                "Serviço": service,
                "UsageType": usage_type,
                "Custo($)": cost,
            }
        )
    return rows


def _build_operation_rows(service, operation, daily_costs, start_date="2026-04-04"):
    """Cria uma serie diaria de API operations para os testes de enriquecimento."""
    base_date = pd.Timestamp(start_date)
    rows = []
    for offset, cost in enumerate(daily_costs):
        rows.append(
            {
                "Data": (base_date + pd.Timedelta(days=offset)).strftime("%Y-%m-%d"),
                "Serviço": service,
                "ApiOperation": operation,
                "Custo($)": cost,
            }
        )
    return rows


class TestBuildUsageTypeTimeseries:
    """Valida a normalizacao da serie por data, servico e usage type."""

    def test_basic_timeseries(self, sample_cost_data_long):
        from analyzers import anomaly_detection as ad

        result = ad.build_usage_type_timeseries(sample_cost_data_long)

        assert isinstance(result, pd.DataFrame)
        assert {"Data", "Serviço", "UsageType", "Custo($)"} <= set(result.columns)
        assert not result.empty

    def test_missing_usage_type_adds_total(self):
        from analyzers import anomaly_detection as ad

        df = pd.DataFrame(
            {
                "Data": ["2026-04-10", "2026-04-10"],
                "Serviço": ["Amazon Simple Storage Service", "EC2"],
                "Custo($)": [100.0, 200.0],
            }
        )

        result = ad.build_usage_type_timeseries(df)

        assert (result["UsageType"] == "Total").all()

    def test_missing_required_columns_raises_keyerror(self):
        from analyzers import anomaly_detection as ad

        with pytest.raises(KeyError):
            ad.build_usage_type_timeseries(pd.DataFrame({"DataErrada": ["2026-04-10"], "Custo": [100.0]}))

    def test_empty_dataframe_returns_empty(self):
        from analyzers import anomaly_detection as ad

        df = pd.DataFrame(
            {
                "Data": pd.Series(dtype="str"),
                "Serviço": pd.Series(dtype="str"),
                "UsageType": pd.Series(dtype="str"),
                "Custo($)": pd.Series(dtype="float64"),
            }
        )

        result = ad.build_usage_type_timeseries(df)

        assert result.empty

    def test_groups_multiple_records_same_day(self):
        from analyzers import anomaly_detection as ad

        df = pd.DataFrame(
            {
                "Data": ["2026-04-10", "2026-04-10"],
                "Serviço": ["S3", "S3"],
                "UsageType": ["Requests-Tier1", "Requests-Tier1"],
                "Custo($)": [50.0, 30.0],
            }
        )

        result = ad.build_usage_type_timeseries(df)
        row = result[(result["Data"] == "2026-04-10") & (result["UsageType"] == "Requests-Tier1")]

        assert row["Custo($)"].iloc[0] == 80.0


class TestCalculateAnomalies:
    """Valida os calculos basicos da janela consolidada."""

    def test_basic_anomalies(self):
        from analyzers import anomaly_detection as ad

        df = pd.DataFrame(
            _build_cost_rows(
                "Amazon Simple Storage Service",
                "Requests-Tier1",
                [40.0, 42.0, 45.0, 48.0, 50.0, 95.0, 95.0],
            )
        )
        timeseries = ad.build_usage_type_timeseries(df)

        anomalies = ad.calculate_anomalies(
            timeseries,
            data_inicio="2026-04-04",
            data_fim="2026-04-10",
            ultimo_dia="2026-04-10",
        )

        anomaly = next(
            item
            for item in anomalies
            if item["service"] == "Amazon Simple Storage Service" and item["usage_type"] == "Requests-Tier1"
        )

        assert round(anomaly["avg_7d"], 2) == 59.29
        assert anomaly["cost_today"] == 95.0
        assert round(anomaly["delta_usd"], 2) == 35.71
        assert round(anomaly["delta_pct"], 2) == 60.24
        assert anomaly["days_present"] == 7
        assert len(anomaly["series"]) == 7

    def test_missing_days_are_filled_with_zero(self):
        from analyzers import anomaly_detection as ad

        df = pd.DataFrame(
            _build_cost_rows("EC2", "Total", [1.0] * 7)
            + [
                {
                    "Data": "2026-04-08",
                    "Serviço": "S3",
                    "UsageType": "Requests-Tier1",
                    "Custo($)": 100.0,
                },
                {
                    "Data": "2026-04-09",
                    "Serviço": "S3",
                    "UsageType": "Requests-Tier1",
                    "Custo($)": 100.0,
                },
                {
                    "Data": "2026-04-10",
                    "Serviço": "S3",
                    "UsageType": "Requests-Tier1",
                    "Custo($)": 100.0,
                },
            ]
        )
        timeseries = ad.build_usage_type_timeseries(df)

        anomalies = ad.calculate_anomalies(
            timeseries,
            data_inicio="2026-04-04",
            data_fim="2026-04-10",
            ultimo_dia="2026-04-10",
        )

        anomaly = next(item for item in anomalies if item["usage_type"] == "Requests-Tier1")

        assert round(anomaly["avg_7d"], 2) == 42.86
        assert anomaly["days_present"] == 3
        assert [point["cost_usd"] for point in anomaly["series"][:4]] == [0.0, 0.0, 0.0, 0.0]

    def test_single_day_window(self):
        from analyzers import anomaly_detection as ad

        df = pd.DataFrame(
            {
                "Data": ["2026-04-10"],
                "Serviço": ["Amazon Simple Storage Service"],
                "UsageType": ["Requests-Tier1"],
                "Custo($)": [100.0],
            }
        )
        timeseries = ad.build_usage_type_timeseries(df)

        anomalies = ad.calculate_anomalies(
            timeseries,
            data_inicio="2026-04-10",
            data_fim="2026-04-10",
            ultimo_dia="2026-04-10",
        )

        anomaly = next(item for item in anomalies if item["usage_type"] == "Requests-Tier1")

        assert anomaly["cost_today"] == 100.0
        assert anomaly["avg_7d"] == 100.0
        assert anomaly["delta_usd"] == 0.0
        assert anomaly["delta_pct"] == 0.0

    def test_multiple_usage_types_are_independent(self):
        from analyzers import anomaly_detection as ad

        df = pd.DataFrame(
            _build_cost_rows("S3", "Requests-Tier1", [50.0, 60.0], start_date="2026-04-09")
            + _build_cost_rows("S3", "TimedStorage-ByteHrs", [190.0, 200.0], start_date="2026-04-09")
        )
        timeseries = ad.build_usage_type_timeseries(df)

        anomalies = ad.calculate_anomalies(
            timeseries,
            data_inicio="2026-04-09",
            data_fim="2026-04-10",
            ultimo_dia="2026-04-10",
        )

        assert {item["usage_type"] for item in anomalies} == {"Requests-Tier1", "TimedStorage-ByteHrs"}


class TestFilterRelevantAnomalies:
    """Valida os filtros de relevancia aplicados antes do enriquecimento."""

    def test_filters_by_min_cost_threshold(self):
        from analyzers import anomaly_detection as ad

        anomalies = [
            {
                "usage_type": "Requests-Tier1",
                "cost_today": 50.0,
                "delta_usd": 10.0,
                "delta_pct": 25.0,
                "days_present": 7,
                "series": [],
                "service": "S3",
            },
            {
                "usage_type": "Requests-Tier2",
                "cost_today": 5.0,
                "delta_usd": 2.0,
                "delta_pct": 10.0,
                "days_present": 7,
                "series": [],
                "service": "S3",
            },
        ]

        result = ad.filter_relevant_anomalies(anomalies)

        assert len(result) == 1
        assert result[0]["usage_type"] == "Requests-Tier1"

    def test_filters_by_min_variation_percent(self):
        from analyzers import anomaly_detection as ad

        anomalies = [
            {
                "usage_type": "Requests-Tier1",
                "cost_today": 100.0,
                "delta_usd": 50.0,
                "delta_pct": 100.0,
                "days_present": 7,
                "series": [],
                "service": "S3",
            },
            {
                "usage_type": "Requests-Tier2",
                "cost_today": 10.0,
                "delta_usd": 3.0,
                "delta_pct": 17.64,
                "days_present": 7,
                "series": [],
                "service": "S3",
            },
        ]

        result = ad.filter_relevant_anomalies(anomalies)

        assert len(result) == 1
        assert result[0]["usage_type"] == "Requests-Tier1"

    def test_negative_variation_is_kept(self):
        from analyzers import anomaly_detection as ad

        anomalies = [
            {
                "usage_type": "Requests-Tier1",
                "cost_today": 10.0,
                "delta_usd": -50.0,
                "delta_pct": -33.33,
                "days_present": 7,
                "series": [],
                "service": "S3",
            }
        ]

        result = ad.filter_relevant_anomalies(anomalies)

        assert len(result) == 1

    def test_respects_top_n_limit(self):
        from analyzers import anomaly_detection as ad
        from src import config

        anomalies = []
        for index in range(15):
            anomalies.append(
                {
                    "usage_type": f"Type-{index}",
                    "cost_today": 100.0 + index,
                    "delta_usd": 50.0 + index,
                    "delta_pct": 100.0 + index,
                    "days_present": 7,
                    "series": [],
                    "service": "S3",
                }
            )

        result = ad.filter_relevant_anomalies(anomalies)

        assert len(result) == config.TOP_N_ANOMALIES

    def test_empty_list_returns_empty(self):
        from analyzers import anomaly_detection as ad

        assert ad.filter_relevant_anomalies([]) == []


class TestEnrichComplementaryUsageTypes:
    """Valida enrich de usage types pareados para SMS e S3."""

    def test_enrich_s3_storage_as_complementary(self):
        from analyzers import anomaly_detection as ad

        anomalies = [{"service": "Amazon Simple Storage Service", "usage_type": "Requests-Tier1"}]
        rows = _build_cost_rows("Amazon Simple Storage Service", "Requests-Tier1", [40.0, 45.0], "2026-04-09")
        rows += _build_cost_rows(
            "Amazon Simple Storage Service",
            "TimedStorage-ByteHrs",
            [100.0, 140.0],
            "2026-04-09",
        )
        timeseries_df = ad.build_usage_type_timeseries(pd.DataFrame(rows))

        enriched = ad.enrich_complementary_usage_types(anomalies, timeseries_df, ultimo_dia="2026-04-10")

        assert enriched[0]["usage_type_context"]["cost_family"] == "s3_requests"
        assert any(item["usage_type"] == "TimedStorage-ByteHrs" for item in enriched[0]["complementary_usage_types"])

    def test_sms_complementary_detected(self):
        from analyzers import anomaly_detection as ad

        anomalies = [
            {
                "service": "AWS End User Messaging",
                "usage_type": "OutboundSMS-BR-Standard-Sharedroute-MessageCount",
            }
        ]
        rows = _build_cost_rows(
            "AWS End User Messaging",
            "OutboundSMS-BR-Standard-Sharedroute-MessageCount",
            [20.0, 50.0],
            "2026-04-09",
        )
        rows += _build_cost_rows("AWS End User Messaging", "DeliveryAttempts-SMS", [25.0, 60.0], "2026-04-09")
        timeseries_df = ad.build_usage_type_timeseries(pd.DataFrame(rows))

        enriched = ad.enrich_complementary_usage_types(anomalies, timeseries_df, ultimo_dia="2026-04-10")

        assert any("DeliveryAttempts" in item["usage_type"] for item in enriched[0]["complementary_usage_types"])

    def test_self_not_included_in_s3_complementary_list(self):
        from analyzers import anomaly_detection as ad

        anomalies = [{"service": "S3", "usage_type": "Requests-Tier1"}]
        rows = _build_cost_rows("S3", "Requests-Tier1", [100.0, 150.0], "2026-04-09")
        rows += _build_cost_rows("S3", "TimedStorage-ByteHrs", [120.0, 200.0], "2026-04-09")
        timeseries_df = ad.build_usage_type_timeseries(pd.DataFrame(rows))

        enriched = ad.enrich_complementary_usage_types(anomalies, timeseries_df, ultimo_dia="2026-04-10")

        assert not any(item["usage_type"] == "Requests-Tier1" for item in enriched[0]["complementary_usage_types"])

    def test_empty_timeseries_keeps_input_unchanged(self):
        from analyzers import anomaly_detection as ad

        anomalies = [{"service": "S3", "usage_type": "Requests-Tier1"}]

        assert ad.enrich_complementary_usage_types(anomalies, pd.DataFrame(), ultimo_dia="2026-04-10") == anomalies


class TestEnrichApiOperations:
    """Valida o enrich das operacoes da API do Cost Explorer."""

    def test_attach_api_operations(self):
        from analyzers import anomaly_detection as ad

        anomalies = [{"service": "Amazon Simple Storage Service", "usage_type": "Requests-Tier1"}]
        rows = _build_operation_rows("Amazon Simple Storage Service", "GetObject", [25.0, 60.0], "2026-04-09")
        rows += _build_operation_rows("Amazon Simple Storage Service", "PutObject", [15.0, 20.0], "2026-04-09")
        op_timeseries = pd.DataFrame(rows)

        enriched = ad.enrich_api_operations(anomalies, op_timeseries, ultimo_dia="2026-04-10")

        assert len(enriched[0]["top_api_operations"]) == 2
        assert enriched[0]["top_api_operations"][0]["operation"] == "GetObject"

    def test_skip_non_allowed_service(self):
        from analyzers import anomaly_detection as ad

        anomalies = [{"service": "SomeRandomService", "usage_type": "Type-A"}]

        enriched = ad.enrich_api_operations(anomalies, pd.DataFrame(), ultimo_dia="2026-04-10")

        assert "top_api_operations" not in enriched[0]

    def test_no_api_data_available(self):
        from analyzers import anomaly_detection as ad

        anomalies = [{"service": "Amazon Simple Storage Service", "usage_type": "Requests-Tier1"}]
        empty_df = pd.DataFrame({"Data": [], "Serviço": [], "ApiOperation": [], "Custo($)": []})

        enriched = ad.enrich_api_operations(anomalies, empty_df, ultimo_dia="2026-04-10")

        assert "top_api_operations" not in enriched[0]

    def test_empty_anomalies_list(self):
        from analyzers import anomaly_detection as ad

        assert ad.enrich_api_operations([], pd.DataFrame(), ultimo_dia="2026-04-10") == []


class TestEnrichS3TierChangeAnalysis:
    """Valida o diagnostico explicito de tier/class change em S3."""

    def test_supported_transition(self):
        from analyzers import anomaly_detection as ad

        anomaly = {
            "service": "Amazon Simple Storage Service",
            "usage_type": "LifecycleTransition",
            "cost_today": 250.0,
            "avg_7d": 30.0,
            "delta_usd": 220.0,
            "delta_pct": 733.33,
            "days_present": 2,
            "usage_type_context": {
                "cost_family": "s3_storage_class_transition",
                "summary": "Transicao de classe/tier.",
                "is_storage_class_change_signal": True,
                "storage_tier_candidates": ["Glacier", "Standard-IA"],
            },
            "complementary_usage_types": [
                {
                    "usage_type": "TimedStorage-GlacierByteHrs",
                    "cost_today": 500.0,
                    "avg_7d": 100.0,
                    "delta_usd": 400.0,
                    "delta_pct": 400.0,
                    "usage_type_context": {
                        "cost_family": "s3_storage",
                        "summary": "Storage Glacier.",
                        "is_storage_class_change_signal": True,
                        "storage_tier_candidates": ["Glacier"],
                    },
                }
            ],
            "top_api_operations": [
                {
                    "operation": "LifecycleTransition",
                    "cost_today": 200.0,
                    "avg_7d": 20.0,
                    "delta_usd": 180.0,
                    "delta_pct": 900.0,
                }
            ],
        }

        enriched = ad.enrich_s3_tier_change_analysis([anomaly])
        result = enriched[0]["s3_tier_change_analysis"]

        assert result["status"] == "supported"
        assert result["storage_cost_signals"]
        assert result["transition_operation_signals"]
        assert "summary" in result

    def test_not_supported_without_storage_signals(self):
        from analyzers import anomaly_detection as ad

        anomaly = {
            "service": "Amazon Simple Storage Service",
            "usage_type": "Requests-Tier1",
            "cost_today": 100.0,
            "avg_7d": 50.0,
            "delta_usd": 50.0,
            "delta_pct": 100.0,
            "days_present": 7,
            "usage_type_context": {
                "cost_family": "s3_requests",
                "summary": "Requests.",
                "is_storage_class_change_signal": False,
                "storage_tier_candidates": [],
            },
            "complementary_usage_types": [],
            "top_api_operations": [],
        }

        enriched = ad.enrich_s3_tier_change_analysis([anomaly])

        assert enriched[0]["s3_tier_change_analysis"]["status"] == "not_supported"

    def test_non_s3_service_not_enriched(self):
        from analyzers import anomaly_detection as ad

        anomaly = {
            "service": "AWS End User Messaging",
            "usage_type": "OutboundSMS-BR-Standard-Sharedroute-MessageCount",
        }

        enriched = ad.enrich_s3_tier_change_analysis([anomaly])

        assert "s3_tier_change_analysis" not in enriched[0]

    def test_s3_driver_analysis_present(self):
        from analyzers import anomaly_detection as ad

        anomaly = {
            "service": "Amazon Simple Storage Service",
            "usage_type": "Requests-Tier1",
            "cost_today": 100.0,
            "avg_7d": 50.0,
            "delta_usd": 50.0,
            "delta_pct": 100.0,
            "days_present": 7,
            "usage_type_context": {
                "cost_family": "s3_requests",
                "summary": "Requests.",
                "is_storage_class_change_signal": False,
                "storage_tier_candidates": [],
            },
            "complementary_usage_types": [],
            "top_api_operations": [],
        }

        enriched = ad.enrich_s3_tier_change_analysis([anomaly])
        driver_analysis = enriched[0]["s3_driver_analysis"]

        assert "primary_driver" in driver_analysis
        assert "confidence" in driver_analysis
        assert "narrative_summary" in driver_analysis
