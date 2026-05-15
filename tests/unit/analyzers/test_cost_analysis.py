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


# ---------------------------------------------------------------------------
# build_sms_last_7_days
# ---------------------------------------------------------------------------

class TestBuildSmsLast7Days:
    """Testa agregacao de custos SMS dos ultimos 7 dias."""

    def test_basic_sms_aggregation(self):
        """Deve agregar custo SMS por dia e calcular total e media."""
        from analyzers import cost_analysis

        df = pd.DataFrame({
            "Data": [
                "2026-04-04", "2026-04-05", "2026-04-06",
                "2026-04-07", "2026-04-08", "2026-04-09", "2026-04-10",
            ],
            "Serviço": ["AWS End User Messaging"] * 7,
            "UsageType": ["OutboundSMS"] * 7,
            "Custo($)": [12.0, 14.0, 11.0, 13.0, 15.0, 10.0, 16.0],
        })

        sms_por_dia, total, media = cost_analysis.build_sms_last_7_days(df, "2026-04-10")

        assert len(sms_por_dia) == 7
        assert total == 91.0  # 12+14+11+13+15+10+16
        assert round(media, 2) == 13.0  # 91/7

    def test_sms_empty_no_data(self):
        """Sem dados de SMS, retorna DataFrames vazios e totais zero."""
        from analyzers import cost_analysis

        df = pd.DataFrame({
            "Data": ["2026-04-08"],
            "Serviço": ["EC2"],
            "Custo($)": [100.0],
        })

        sms_por_dia, total, media = cost_analysis.build_sms_last_7_days(df, "2026-04-10")

        assert sms_por_dia.empty or len(sms_por_dia) == 0
        assert total == 0.0
        assert media == 0.0

    def test_sms_only_relevant_services(self):
        """Deve considerar apenas servicos em SPECIAL_SERVICES."""
        from analyzers import cost_analysis
        from src import config

        df = pd.DataFrame({
            "Data": ["2026-04-10", "2026-04-10"],
            "Serviço": ["End User Messaging", "EC2"],
            "Custo($)": [30.0, 500.0],
        })

        sms_por_dia, total, media = cost_analysis.build_sms_last_7_days(df, "2026-04-10")

        # Apenas "End User Messaging" esta em SPECIAL_SERVICES
        assert total == 30.0

    def test_sms_partial_window(self):
        """Janela parcial (menos de 7 dias) deve funcionar."""
        from analyzers import cost_analysis

        df = pd.DataFrame({
            "Data": ["2026-04-09", "2026-04-10"],
            "Serviço": ["AWS End User Messaging"] * 2,
            "Custo($)": [10.0, 20.0],
        })

        sms_por_dia, total, media = cost_analysis.build_sms_last_7_days(df, "2026-04-10")

        assert len(sms_por_dia) == 2
        assert total == 30.0
        assert media == 15.0
