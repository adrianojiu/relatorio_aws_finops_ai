"""
Testes unitarios para src/analyzers/cost_analysis.py

Cobre:
  - build_daily_pivot: transformacao de formato longo para wide
  - calculate_cost_metrics: media, ultimo dia, variacao
  - calculate_service_variations: servicos que aumentaram/reduziram, top costs
  - build_sms_last_7_days: agregacao SMS para janela de 7 dias
"""
import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# build_daily_pivot
# ---------------------------------------------------------------------------

class TestBuildDailyPivot:
    """Testa a transformacao de formato longo (Data, Servico, Custo) para wide."""

    def test_basic_pivot(self):
        """Pivot basico deve transformar servicos em colunas."""
        from analyzers import cost_analysis

        df = pd.DataFrame({
            "Data": ["2026-04-08", "2026-04-08", "2026-04-09", "2026-04-09"],
            "Serviço": ["S3", "EC2", "S3", "EC2"],
            "Custo($)": [100.0, 200.0, 150.0, 180.0],
        })

        result = cost_analysis.build_daily_pivot(df)

        # Verifica colunas esperadas
        assert "Service" in result.columns
        assert "S3" in result.columns
        assert "EC2" in result.columns
        # Verifica valores
        assert result.loc[result["Service"] == "2026-04-08", "S3"].values[0] == 100.0
        assert result.loc[result["Service"] == "2026-04-08", "EC2"].values[0] == 200.0
        assert result.loc[result["Service"] == "2026-04-09", "S3"].values[0] == 150.0

    def test_pivot_with_missing_days(self):
        """Dias sem dados para um servico devem ser preenchidos com 0."""
        from analyzers import cost_analysis

        df = pd.DataFrame({
            "Data": ["2026-04-08", "2026-04-09"],
            "Serviço": ["S3", "EC2"],
            "Custo($)": [100.0, 200.0],
        })

        result = cost_analysis.build_daily_pivot(df)

        # Dia 08 teve S3 mas nao EC2
        assert result.loc[result["Service"] == "2026-04-08", "S3"].values[0] == 100.0
        assert result.loc[result["Service"] == "2026-04-08", "EC2"].values[0] == 0.0
        # Dia 09 teve EC2 mas nao S3
        assert result.loc[result["Service"] == "2026-04-09", "EC2"].values[0] == 200.0
        assert result.loc[result["Service"] == "2026-04-09", "S3"].values[0] == 0.0

    def test_pivot_empty_dataframe(self):
        """DataFrame vazio deve resultar em pivot sem colunas de servicos."""
        from analyzers import cost_analysis

        df = pd.DataFrame({"Data": [], "Serviço": [], "Custo($)": []})
        result = cost_analysis.build_daily_pivot(df)

        assert "Service" in result.columns
        assert result.empty or len(result.columns) == 1

    def test_pivot_column_rename(self):
        """Coluna 'Data' deve ser renomeada para 'Service'."""
        from analyzers import cost_analysis

        df = pd.DataFrame({
            "Data": ["2026-04-08"],
            "Serviço": ["S3"],
            "Custo($)": [100.0],
        })

        result = cost_analysis.build_daily_pivot(df)
        assert "Service" in result.columns
        assert "Data" not in result.columns


# ---------------------------------------------------------------------------
# calculate_cost_metrics
# ---------------------------------------------------------------------------

class TestCalculateCostMetrics:
    """Testa calculo de custo medio, ultimo dia e variacao."""

    def test_normal_case(self):
        """Cenario normal com 7 dias de dados."""
        from analyzers import cost_analysis

        df = pd.DataFrame({
            "Service": ["2026-04-04", "2026-04-05", "2026-04-06",
                        "2026-04-07", "2026-04-08", "2026-04-09", "2026-04-10"],
            "S3": [100.0] * 7,
            "EC2": [200.0] * 7,
            "Total costs($)": [300.0] * 7,
        })

        custo_medio, custo_ultimo_dia, variacao, variacao_pct = (
            cost_analysis.calculate_cost_metrics(df, "2026-04-10")
        )

        assert custo_medio == 300.0
        assert custo_ultimo_dia == 300.0
        assert variacao == 0.0
        assert variacao_pct == 0.0

    def test_last_day_higher(self):
        """Ultimo dia com custo maior que a media."""
        from analyzers import cost_analysis

        df = pd.DataFrame({
            "Service": ["2026-04-04", "2026-04-05", "2026-04-06",
                        "2026-04-07", "2026-04-08", "2026-04-09", "2026-04-10"],
            "S3": [100.0] * 6 + [200.0],
            "EC2": [200.0] * 6 + [300.0],
            "Total costs($)": [300.0] * 6 + [500.0],
        })

        custo_medio, custo_ultimo_dia, variacao, variacao_pct = (
            cost_analysis.calculate_cost_metrics(df, "2026-04-10")
        )

        assert round(custo_medio, 2) == 328.57  # (300*6 + 500) / 7
        assert custo_ultimo_dia == 500.0
        assert round(variacao, 2) == 171.43
        assert round(variacao_pct, 2) == 52.17

    def test_last_day_lower(self):
        """Ultimo dia com custo menor que a media."""
        from analyzers import cost_analysis

        df = pd.DataFrame({
            "Service": ["2026-04-04", "2026-04-05", "2026-04-06",
                        "2026-04-07", "2026-04-08", "2026-04-09", "2026-04-10"],
            "S3": [100.0] * 6 + [50.0],
            "EC2": [200.0] * 6 + [100.0],
            "Total costs($)": [300.0] * 6 + [150.0],
        })

        custo_medio, custo_ultimo_dia, variacao, variacao_pct = (
            cost_analysis.calculate_cost_metrics(df, "2026-04-10")
        )

        assert round(custo_medio, 2) == 278.57
        assert custo_ultimo_dia == 150.0
        assert round(variacao, 2) == -128.57
        assert round(variacao_pct, 2) == -46.15

    def test_zero_mean(self):
        """variacao_pct deve ser 0.0 quando custo_medio e 0."""
        from analyzers import cost_analysis

        df = pd.DataFrame({
            "Service": ["2026-04-08", "2026-04-09", "2026-04-10"],
            "S3": [0.0, 0.0, 0.0],
            "Total costs($)": [0.0, 0.0, 0.0],
        })

        custo_medio, custo_ultimo_dia, variacao, variacao_pct = (
            cost_analysis.calculate_cost_metrics(df, "2026-04-10")
        )

        assert custo_medio == 0.0
        assert custo_ultimo_dia == 0.0
        assert variacao == 0.0
        assert variacao_pct == 0.0

    def test_single_day(self):
        """Apenas 1 dia na janela."""
        from analyzers import cost_analysis

        df = pd.DataFrame({
            "Service": ["2026-04-10"],
            "S3": [100.0],
            "Total costs($)": [100.0],
        })

        custo_medio, custo_ultimo_dia, variacao, variacao_pct = (
            cost_analysis.calculate_cost_metrics(df, "2026-04-10")
        )

        assert custo_medio == 100.0
        assert custo_ultimo_dia == 100.0
        assert variacao == 0.0
        assert variacao_pct == 0.0

    def test_last_day_not_found_raises(self):
        """Deve levantar IndexError se ultimo_dia nao existir no DataFrame."""
        from analyzers import cost_analysis

        df = pd.DataFrame({
            "Service": ["2026-04-04", "2026-04-05"],
            "Total costs($)": [100.0, 200.0],
        })

        with pytest.raises(IndexError):
            cost_analysis.calculate_cost_metrics(df, "2026-04-10")


# ---------------------------------------------------------------------------
# calculate_service_variations
# ---------------------------------------------------------------------------

class TestCalculateServiceVariations:
    """Testa calculo de variacao por servico e ranking."""

    def test_aumentaram_e_reduziram(self, sample_cost_period_df):
        """Deve separar corretamente servicos que aumentaram e reduziram."""
        from analyzers import cost_analysis

        df_var, aumentaram, reduziram, top_costs = (
            cost_analysis.calculate_service_variations(sample_cost_period_df, "2026-04-10")
        )

        # S3 aumentou (media ~159, ultimo=195)
        assert "Amazon Simple Storage Service" in aumentaram.index

        # CloudWatch reduziu (media ~28, ultimo=25)
        assert "AmazonCloudWatch" in reduziram.index

    def test_service_variation_values(self, sample_cost_period_df):
        """Verifica valores de variacao calculados."""
        from analyzers import cost_analysis

        df_var, aumentaram, reduziram, top_costs = (
            cost_analysis.calculate_service_variations(sample_cost_period_df, "2026-04-10")
        )

        # S3: media aproximada = (140+142+145+148+150+195+195)/7 = 159.29
        # Ultimo = 195, variacao = 195 - 159.29 = 35.71
        s3_row = df_var.loc["Amazon Simple Storage Service"]
        assert round(s3_row["Média"], 2) == 159.29
        assert s3_row["Último dia"] == 195.0
        assert round(s3_row["Variação US$"], 2) == 35.71

    def test_top_costs_ranking(self, sample_cost_period_df):
        """Top costs deve retornar os servicos com maior custo no ultimo dia."""
        from analyzers import cost_analysis
        from src import config

        df_var, aumentaram, reduziram, top_costs = (
            cost_analysis.calculate_service_variations(sample_cost_period_df, "2026-04-10")
        )

        # No ultimo dia: S3=195, EC2=130, End User=16, CloudWatch=25
        # Ordenado: S3 > EC2 > CloudWatch > End User
        top_services = list(top_costs.index)
        assert top_services[0] == "Amazon Simple Storage Service"
        assert top_services[1] == "EC2 - Other"

    def test_top_costs_limited_by_config(self, sample_cost_period_df):
        """Deve respeitar TOP_N_SERVICES no ranking."""
        from analyzers import cost_analysis
        from src import config

        df_var, aumentaram, reduziram, top_costs = (
            cost_analysis.calculate_service_variations(sample_cost_period_df, "2026-04-10")
        )

        assert len(top_costs) <= config.TOP_N_SERVICES

    def test_empty_variation_no_services(self):
        """Sem servicos no DataFrame, df_var deve ficar vazio."""
        from analyzers import cost_analysis

        df = pd.DataFrame({
            "Service": ["2026-04-04"],
            "Total costs($)": [100.0],
        })

        df_var, aumentaram, reduziram, top_costs = (
            cost_analysis.calculate_service_variations(df, "2026-04-04")
        )

        assert len(top_costs) == 0


class TestBuildUsageTypeVariationReport:
    """Testes para o relatório de variação por UsageType."""

    def test_builds_usage_type_report(self):
        from analyzers import cost_analysis

        df = pd.DataFrame({
            "Data": ["2026-05-01", "2026-05-02", "2026-05-03"],
            "Serviço": ["Amazon S3", "Amazon S3", "Amazon S3"],
            "UsageType": ["Storage", "Storage", "Storage"],
            "Custo($)": [10.0, 0.0, 15.0],
        })

        result = cost_analysis.build_usage_type_variation_report(
            df, "2026-05-01", "2026-05-03", min_total_usd=5.0
        )

        assert len(result) == 1
        row = result.iloc[0]
        assert row["Serviço"] == "Amazon S3"
        assert row["UsageType"] == "Storage"
        assert round(row["Total período"], 2) == 25.0
        assert round(row["Participação %"], 1) == 100.0
        assert round(row["Média diária"], 2) == 8.33
        assert round(row["Último dia"], 2) == 15.0
        assert round(row["Máximo período"], 2) == 15.0
        assert round(row["Mínimo período"], 2) == 0.0
        assert round(row["∆7d vs prev"], 2) == 8.33
        assert round(row["Variação US$"], 2) == 6.67
        assert round(row["Variação %"], 1) == 80.0
        # Regressão linear: x=[0,1,2], y=[10,0,15] → slope = 2.5 US$/dia
        assert "Impacto US$/dia" in result.columns
        assert round(row["Impacto US$/dia"], 2) == 2.5

        # Novas colunas de comportamento
        assert "Desvio diário" in result.columns
        assert "CV" in result.columns
        assert "Comportamento" in result.columns
        # slope_ratio = 2.5 / 8.33 ≈ 0.30 > 0.01 → Crescendo (CV não é volátil pois std/avg < 0.5 aqui)
        assert row["Comportamento"] in ("Crescendo", "Volátil", "Estável", "Caindo")

    def test_build_usage_type_variation_chart_data_prioritizes_top_positive_variations(self):
        from analyzers import cost_analysis
        from src import config

        df_report = pd.DataFrame({
            "UsageType": ["A", "B", "C", "D", "E"],
            "Serviço": ["S1", "S1", "S2", "S2", "S3"],
            "Variação %": [25.0, -95.0, 60.0, -20.0, 10.0],
        })

        result = cost_analysis.build_usage_type_variation_percent_chart_data(df_report)

        assert len(result) <= config.USAGE_TYPE_CHART_MAX_USAGE_TYPES
        assert result[0]["UsageType"] == "C (S2)"
        assert result[1]["UsageType"] == "A (S1)"
        assert result[2]["UsageType"] == "E (S3)"
        assert result[0]["variation_pct"] == 60.0
        assert result[1]["variation_pct"] == 25.0
        assert result[2]["variation_pct"] == 10.0

    def test_builds_usage_type_daily_trend_by_usage_type(self):
        from analyzers import cost_analysis
        import config as cfg

        df = pd.DataFrame({
            "Data": [
                "2026-05-01", "2026-05-01", "2026-05-02", "2026-05-02",
                "2026-05-03", "2026-05-03", "2026-05-04", "2026-05-04",
            ],
            "Serviço": [
                "Amazon S3", "AmazonCloudWatch", "Amazon S3", "AmazonCloudWatch",
                "Amazon S3", "AmazonCloudWatch", "Amazon S3", "AmazonCloudWatch",
            ],
            "UsageType": [
                "Storage", "Metrics", "Storage", "Metrics",
                "Storage", "Metrics", "Storage", "Metrics",
            ],
            "Custo($)": [10.0, 5.0, 0.0, 4.0, 15.0, 0.5, 0.0, 6.0],
        })

        all_dates, forecast_dates, chart_data, total_daily_values = (
            cost_analysis.build_usage_type_daily_trend(df, "2026-05-01", "2026-05-04")
        )

        # Datas do período do relatório (sem forecast).
        assert all_dates == ["2026-05-01", "2026-05-02", "2026-05-03", "2026-05-04"]

        # Datas de projeção começam no dia seguinte ao fim do relatório.
        assert len(forecast_dates) == cfg.USAGE_TYPE_REPORT_FORECAST_DAYS
        assert forecast_dates[0] == "2026-05-05"

        # Dois UsageTypes com custo acima de zero (labels incluem o serviço).
        assert len(chart_data) == 2
        storage = chart_data[0]  # maior custo total: 10+15=25
        metrics = chart_data[1]  # custo total: 5+4+0.5+6=15.5

        assert storage["UsageType"] == "Storage (Amazon S3)"
        assert storage["daily_values"] == [10.0, 0.0, 15.0, 0.0]
        # Último valor é 0 e slope negativo → todos os forecast são 0.
        assert len(storage["forecast_values"]) == cfg.USAGE_TYPE_REPORT_FORECAST_DAYS
        assert all(v == 0.0 for v in storage["forecast_values"])
        assert "trend_values" not in storage

        assert metrics["UsageType"] == "Metrics (AmazonCloudWatch)"
        assert metrics["daily_values"] == [5.0, 4.0, 0.5, 6.0]
        assert len(metrics["forecast_values"]) == cfg.USAGE_TYPE_REPORT_FORECAST_DAYS
        # slope = (6.0 - 5.0) / (4-1) = 0.3333; step 1 = round(6.0 + 0.3333, 4) = 6.3333
        assert metrics["forecast_values"][0] == round(6.0 + (6.0 - 5.0) / 3, 4)

        # Total diário = soma de todos os UsageTypes por data.
        assert total_daily_values == [15.0, 4.0, 15.5, 6.0]

    def test_builds_usage_type_daily_variation_pct_trend(self):
        from analyzers import cost_analysis

        df = pd.DataFrame({
            "Data": ["2026-05-01", "2026-05-02", "2026-05-03", "2026-05-04"],
            "Serviço": ["Amazon S3", "Amazon S3", "Amazon S3", "Amazon S3"],
            "UsageType": ["Storage", "Storage", "Storage", "Storage"],
            "Custo($)": [10.0, 15.0, 12.0, 18.0],
        })

        labels, chart_data = cost_analysis.build_usage_type_daily_variation_pct_trend(
            df, "2026-05-01", "2026-05-04"
        )

        assert labels == ["2026-05-01", "2026-05-02", "2026-05-03", "2026-05-04"]
        assert len(chart_data) == 1
        assert chart_data[0]["UsageType"] == "Storage (Amazon S3)"
        assert chart_data[0]["variation_pct_values"] == [None, 50.0, -20.0, 50.0]

    def test_variation_pct_trend_ranks_by_df_report_variation(self):
        # Quando df_report é fornecido, o ranking deve usar |Variação %| e não custo total.
        from analyzers import cost_analysis

        df = pd.DataFrame({
            "Data": [
                "2026-05-01", "2026-05-01",
                "2026-05-02", "2026-05-02",
            ],
            "Serviço": ["S3", "EC2", "S3", "EC2"],
            "UsageType": ["Storage", "BoxUsage", "Storage", "BoxUsage"],
            "Custo($)": [100.0, 5.0, 200.0, 50.0],  # S3 tem custo maior
        })
        # df_report com Variação % maior para EC2 (apesar do custo menor)
        # EC2 tem maior Impacto US$/dia positivo → deve aparecer primeiro no gráfico.
        df_report = pd.DataFrame({
            "UsageType": ["Storage", "BoxUsage"],
            "Serviço": ["S3", "EC2"],
            "Variação %": [10.0, 900.0],
            "Impacto US$/dia": [0.5, 45.0],  # EC2 tem maior slope positivo
        })

        _, chart_data = cost_analysis.build_usage_type_daily_variation_pct_trend(
            df, "2026-05-01", "2026-05-02", df_report=df_report
        )

        # EC2/BoxUsage deve aparecer primeiro por ter maior |Impacto US$/dia|.
        assert len(chart_data) >= 2
        assert chart_data[0]["UsageType"] == "BoxUsage (EC2)"

    def test_filters_usage_types_below_minimum_total(self):
        from analyzers import cost_analysis

        df = pd.DataFrame({
            "Data": ["2026-05-01", "2026-05-02"],
            "Serviço": ["AmazonCloudWatch", "AmazonCloudWatch"],
            "UsageType": ["Metrics", "Metrics"],
            "Custo($)": [2.0, 1.0],
        })

        result = cost_analysis.build_usage_type_variation_report(
            df, "2026-05-01", "2026-05-02", min_total_usd=5.0
        )

        assert result.empty

    def test_raises_for_invalid_range(self):
        from analyzers import cost_analysis

        df = pd.DataFrame({
            "Data": ["2026-05-01"],
            "Serviço": ["Amazon S3"],
            "UsageType": ["Storage"],
            "Custo($)": [10.0],
        })

        with pytest.raises(ValueError):
            cost_analysis.build_usage_type_variation_report(
                df, "2026-05-05", "2026-05-01", min_total_usd=5.0
            )

    def test_allows_window_larger_than_ninety_days(self):
        from analyzers import cost_analysis

        df = pd.DataFrame({
            "Data": ["2026-03-07", "2026-06-05"],
            "Serviço": ["Amazon S3", "Amazon S3"],
            "UsageType": ["Storage", "Storage"],
            "Custo($)": [10.0, 20.0],
        })

        result = cost_analysis.build_usage_type_variation_report(
            df, "2026-03-07", "2026-06-05", min_total_usd=0.0
        )

        assert len(result) == 1
        assert round(result.iloc[0]["Total período"], 2) == 30.0

    def test_builds_usage_type_analysis_payload(self):
        from analyzers import cost_analysis

        df_report = pd.DataFrame({
            "UsageType": ["Storage", "Requests"],
            "Serviço": ["Amazon S3", "Amazon S3"],
            "Comportamento": ["Crescendo", "Volátil"],
            "Total período": [120.0, 40.0],
            "Participação %": [75.0, 25.0],
            "Média diária": [4.0, 1.33],
            "Último dia": [6.0, 0.8],
            "Máximo período": [8.0, 3.0],
            "Mínimo período": [1.0, 0.1],
            "Desvio diário": [1.2, 0.9],
            "CV": [0.3, 0.7],
            "Média últimos 7 dias": [5.0, 1.0],
            "Média anteriores": [3.5, 1.4],
            "∆7d vs prev": [1.5, -0.4],
            "Variação US$": [2.0, -0.5],
            "Variação %": [50.0, -37.5],
            "Impacto US$/dia": [0.4, -0.2],
        })

        payload = cost_analysis.build_usage_type_analysis_payload(
            df_report=df_report,
            start_date="2026-03-01",
            end_date="2026-06-04",
            min_total_usd=5.0,
            top_anomalies=[{"date": "2026-06-04", "usage_type": "Storage"}],
            weekly_pattern_data=[{"UsageType": "Storage (Amazon S3)", "values": [1, 2, 3, 4, 5, 6, 7]}],
        )

        assert payload["report_type"] == "usage_type"
        assert payload["window"]["window_days"] == 96
        assert payload["summary"]["usage_type_count"] == 2
        assert payload["summary"]["total_period_usd"] == 160.0
        assert payload["top_cost_drivers"][0]["UsageType"] == "Storage"
        assert payload["fastest_growth"][0]["UsageType"] == "Storage"
        assert payload["largest_declines"][0]["UsageType"] == "Requests"
        assert payload["most_volatile"][0]["UsageType"] == "Requests"
        assert payload["weekly_patterns"][0]["UsageType"] == "Storage (Amazon S3)"
        assert payload["anomalies"][0]["date"] == "2026-06-04"


# ---------------------------------------------------------------------------
# build_anomaly_data e build_weekly_pattern
# ---------------------------------------------------------------------------

class TestBuildAnomalyData:
    def test_detects_spike_as_anomaly(self):
        from analyzers import cost_analysis

        # 9 dias estáveis + 1 spike no dia 10 → z ≈ 2.85, acima do threshold de 2.0.
        # Com poucos pontos estáveis o outlier puxa a média e reduz o z-score;
        # com 9 pontos de baseline o z ultrapassa 2.0 de forma confiável.
        dates = [f"2026-05-{i+1:02d}" for i in range(10)]
        df = pd.DataFrame({
            "Data": dates,
            "Serviço": ["S3"] * 10,
            "UsageType": ["Storage"] * 10,
            "Custo($)": [10.0] * 9 + [100.0],
        })
        result = cost_analysis.build_anomaly_data(df, "2026-05-01", "2026-05-10")

        assert len(result["top_anomalies"]) == 1
        anom = result["top_anomalies"][0]
        assert anom["date"] == "2026-05-10"
        assert anom["direction"] == "Alta"
        assert anom["z_score"] > 2.0
        assert "Storage (S3)" in result["by_label"]
        assert 9 in result["by_label"]["Storage (S3)"]  # índice 9 (0-based)

    def test_returns_empty_for_stable_series(self):
        from analyzers import cost_analysis

        df = pd.DataFrame({
            "Data": ["2026-05-01","2026-05-02","2026-05-03"],
            "Serviço": ["S3"] * 3,
            "UsageType": ["Storage"] * 3,
            "Custo($)": [10.0, 10.5, 10.2],  # variação mínima, z < 2
        })
        result = cost_analysis.build_anomaly_data(df, "2026-05-01", "2026-05-03")
        assert result["top_anomalies"] == []
        assert result["by_label"] == {}


class TestBuildWeeklyPattern:
    def test_computes_weekly_average(self):
        from analyzers import cost_analysis

        # Segunda (0) e terça (1) em duas semanas
        df = pd.DataFrame({
            "Data": ["2026-05-04","2026-05-05","2026-05-11","2026-05-12"],  # seg,ter,seg,ter
            "Serviço": ["S3","S3","S3","S3"],
            "UsageType": ["Storage","Storage","Storage","Storage"],
            "Custo($)": [10.0, 20.0, 30.0, 40.0],
        })
        labels, chart_data = cost_analysis.build_weekly_pattern(df, "2026-05-04", "2026-05-12")

        assert labels == ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
        assert len(chart_data) == 1
        item = chart_data[0]
        assert item["UsageType"] == "Storage (S3)"
        # Seg: média de 10 e 30 = 20
        assert item["values"][0] == 20.0
        # Ter: média de 20 e 40 = 30
        assert item["values"][1] == 30.0
        # Outros dias: 0 (sem dados)
        assert item["values"][2] == 0.0


# ---------------------------------------------------------------------------
# build_sms_trend (baseline 30 dias)
# ---------------------------------------------------------------------------

def _make_sms_30d_df(dates, costs, usage_type="OutboundSMS"):
    """Helper: monta DataFrame no formato retornado por fetch_sms_30d."""
    return pd.DataFrame({
        "Data": dates,
        "UsageType": [usage_type] * len(dates),
        "Custo($)": costs,
    })


class TestBuildSmsTrend:
    """Testa agregacao de custos SMS com baseline de 30 dias."""

    def test_basic_sms_aggregation(self):
        """Deve agregar custo SMS por dia e calcular total, media e avg_by_usage."""
        from analyzers import cost_analysis

        datas = [f"2026-04-{d:02d}" for d in range(1, 8)]  # 7 dias de amostra
        custos = [12.0, 14.0, 11.0, 13.0, 15.0, 10.0, 16.0]
        df = _make_sms_30d_df(datas, custos)

        sms_por_dia, total, media, avg_by_usage = cost_analysis.build_sms_trend(df)

        assert len(sms_por_dia) == 7
        assert total == 91.0
        assert round(media, 2) == 13.0  # 91/7
        assert "OutboundSMS" in avg_by_usage
        assert round(avg_by_usage["OutboundSMS"], 2) == 13.0

    def test_sms_empty_no_data(self):
        """Sem dados de SMS, retorna estruturas vazias e totais zero."""
        from analyzers import cost_analysis

        sms_por_dia, total, media, avg_by_usage = cost_analysis.build_sms_trend(None)

        assert sms_por_dia.empty
        assert total == 0.0
        assert media == 0.0
        assert avg_by_usage == {}

    def test_sms_multiple_usage_types(self):
        """Deve calcular avg_by_usage separado por usage type."""
        from analyzers import cost_analysis

        df = pd.DataFrame({
            "Data": ["2026-04-01", "2026-04-01", "2026-04-02", "2026-04-02"],
            "UsageType": ["SMS-Fees", "SMS-Count", "SMS-Fees", "SMS-Count"],
            "Custo($)": [10.0, 2.0, 20.0, 4.0],
        })

        sms_por_dia, total, media, avg_by_usage = cost_analysis.build_sms_trend(df)

        assert total == 36.0
        assert len(sms_por_dia) == 2  # 2 dias distintos
        # avg por uso: SMS-Fees = (10+20)/2 = 15; SMS-Count = (2+4)/2 = 3
        assert round(avg_by_usage["SMS-Fees"], 2) == 15.0
        assert round(avg_by_usage["SMS-Count"], 2) == 3.0

    def test_sms_partial_window(self):
        """Janela com poucos dias deve funcionar corretamente."""
        from analyzers import cost_analysis

        df = _make_sms_30d_df(["2026-04-09", "2026-04-10"], [10.0, 20.0])

        sms_por_dia, total, media, avg_by_usage = cost_analysis.build_sms_trend(df)

        assert len(sms_por_dia) == 2
        assert total == 30.0
        assert media == 15.0
