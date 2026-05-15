"""
Cost analysis functions
"""

import pandas as pd
import config

def build_daily_pivot(df):
    """
    Build pivoted DataFrame with services as columns
    Returns: df_pivot with 'Service' as date column
    """
    df_pivot = df.pivot(index="Data", columns="Serviço", values="Custo($)").fillna(0).reset_index()
    df_pivot.rename(columns={"Data": "Service"}, inplace=True)
    return df_pivot

def calculate_cost_metrics(df_periodo, ultimo_dia):
    """
    Calculate cost metrics: mean, last day, variation
    Returns: custo_medio, custo_ultimo_dia, variacao_media, variacao_media_pct
    """
    custo_medio = df_periodo["Total costs($)"].mean()
    custo_ultimo_dia = df_periodo.loc[df_periodo["Service"] == ultimo_dia, "Total costs($)"].values[0]
    variacao_media = custo_ultimo_dia - custo_medio
    variacao_media_pct = 0.0 if custo_medio == 0 else (variacao_media / custo_medio) * 100
    return custo_medio, custo_ultimo_dia, variacao_media, variacao_media_pct

def calculate_service_variations(df_periodo, ultimo_dia):
    """
    Calculate variations for each service
    Returns: df_var, aumentaram, reduziram, top_costs
    """
    servicos = df_periodo.drop(columns=["Service", "Total costs($)"])
    medias = servicos.mean()
    ultimo = df_periodo.loc[df_periodo["Service"] == ultimo_dia, servicos.columns].iloc[0]

    df_var = pd.DataFrame({
        "Média": medias,
        "Último dia": ultimo,
    })
    df_var["Variação US$"] = df_var["Último dia"] - df_var["Média"]
    df_var["Variação %"] = (df_var["Variação US$"] / df_var["Média"]) * 100

    aumentaram = df_var[df_var["Variação US$"] > 0].sort_values("Variação US$", ascending=False)
    reduziram = df_var[df_var["Variação US$"] < 0].sort_values("Variação US$")
    top_costs = ultimo.sort_values(ascending=False).head(config.TOP_N_SERVICES)

    return df_var, aumentaram, reduziram, top_costs

def build_sms_trend(df_sms_30d):
    """
    Build SMS cost trend from a pre-fetched 30-day DataFrame.
    Recebe df com colunas ['Data', 'UsageType', 'Custo($)'] do fetch_sms_30d.
    Returns:
        sms_por_dia       — DataFrame diario agregado (para grafico)
        total_sms_30d     — custo total no periodo
        media_sms_30d     — media diaria (baseline para anomalia)
        avg_30d_by_usage  — dict {usage_type: avg_diario} para rebase de anomalias
    """
    if df_sms_30d is None or df_sms_30d.empty:
        empty = pd.DataFrame(columns=["Data", "Custo($)"])
        return empty, 0.0, 0.0, {}

    # Agrega por dia para o grafico
    sms_por_dia = (
        df_sms_30d
        .groupby("Data")["Custo($)"]
        .sum()
        .reset_index()
        .sort_values("Data")
    )

    total_sms_30d = float(sms_por_dia["Custo($)"].sum())
    media_sms_30d = 0.0 if sms_por_dia.empty else float(sms_por_dia["Custo($)"].mean())

    # Media diaria por usage_type — usada para rebase de anomalias
    n_days = max(1, len(sms_por_dia))
    avg_30d_by_usage = (
        df_sms_30d
        .groupby("UsageType")["Custo($)"]
        .sum()
        .div(n_days)
        .to_dict()
    )

    return sms_por_dia, total_sms_30d, media_sms_30d, avg_30d_by_usage
