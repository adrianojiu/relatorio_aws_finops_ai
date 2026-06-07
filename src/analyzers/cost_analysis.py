"""
Cost analysis functions
"""

from datetime import datetime

import numpy as np

import pandas as pd
import config


def _usage_type_report_columns():
    """Mantém nomes de colunas estáveis e corretos para qualquer janela."""
    return [
        "UsageType",
        "Serviço",
        "Comportamento",
        "Total período",
        "Participação %",
        "Média diária",
        "Último dia",
        "Máximo período",
        "Mínimo período",
        "Desvio diário",
        "CV",
        "Média últimos 7 dias",
        "Média anteriores",
        "∆7d vs prev",
        "Variação US$",
        "Variação %",
        "Impacto US$/dia",
    ]


def build_usage_type_analysis_payload(
    df_report,
    start_date,
    end_date,
    min_total_usd,
    top_anomalies=None,
    weekly_pattern_data=None,
):
    """Resume o relatório de UsageType em um payload compacto para análise textual."""
    window_days = (
        datetime.strptime(end_date, "%Y-%m-%d").date()
        - datetime.strptime(start_date, "%Y-%m-%d").date()
    ).days + 1

    if df_report is None or df_report.empty:
        return {
            "report_type": "usage_type",
            "window": {
                "start_date": start_date,
                "end_date": end_date,
                "window_days": window_days,
                "min_total_usd": float(min_total_usd),
            },
            "summary": {
                "usage_type_count": 0,
                "total_period_usd": 0.0,
                "average_daily_usd": 0.0,
            },
            "top_cost_drivers": [],
            "fastest_growth": [],
            "largest_declines": [],
            "most_volatile": [],
            "weekly_patterns": [],
            "anomalies": list(top_anomalies or []),
        }

    def _records(frame, columns, limit):
        if frame.empty:
            return []
        return frame.loc[:, columns].head(limit).to_dict(orient="records")

    top_cost_drivers = _records(
        df_report.sort_values(["Participação %", "Total período"], ascending=[False, False]),
        ["UsageType", "Serviço", "Total período", "Participação %", "Comportamento"],
        10,
    )
    fastest_growth = _records(
        df_report[df_report["Impacto US$/dia"] > 0].sort_values(
            ["Impacto US$/dia", "Variação %"], ascending=[False, False]
        ),
        ["UsageType", "Serviço", "Impacto US$/dia", "Variação %", "Comportamento"],
        10,
    )
    largest_declines = _records(
        df_report[df_report["Impacto US$/dia"] < 0].sort_values(
            ["Impacto US$/dia", "Variação %"], ascending=[True, True]
        ),
        ["UsageType", "Serviço", "Impacto US$/dia", "Variação %", "Comportamento"],
        10,
    )
    most_volatile = _records(
        df_report.sort_values(["CV", "Total período"], ascending=[False, False]),
        ["UsageType", "Serviço", "CV", "Média diária", "Comportamento"],
        10,
    )

    return {
        "report_type": "usage_type",
        "window": {
            "start_date": start_date,
            "end_date": end_date,
            "window_days": window_days,
            "min_total_usd": float(min_total_usd),
        },
        "summary": {
            "usage_type_count": int(len(df_report)),
            "total_period_usd": round(float(df_report["Total período"].sum()), 4),
            "average_daily_usd": round(float(df_report["Média diária"].sum()), 4),
        },
        "top_cost_drivers": top_cost_drivers,
        "fastest_growth": fastest_growth,
        "largest_declines": largest_declines,
        "most_volatile": most_volatile,
        "weekly_patterns": list((weekly_pattern_data or [])[:10]),
        "anomalies": list((top_anomalies or [])[:20]),
    }

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


def build_usage_type_variation_report(
    df,
    start_date,
    end_date,
    min_total_usd=None,
):
    """
    Build a UsageType variation report over a custom date range.

    Returns a DataFrame with one row per (Serviço, UsageType), including total
    cost over the range, daily average, last-day cost, and variation metrics.
    """
    if df is None:
        raise ValueError("DataFrame is required for usage type report generation.")

    if min_total_usd is None:
        min_total_usd = config.USAGE_TYPE_REPORT_MIN_TOTAL_USD
    if min_total_usd < 0:
        raise ValueError("min_total_usd must be >= 0")

    required_columns = {"Data", "Serviço", "UsageType", "Custo($)"}
    missing_columns = required_columns - set(df.columns)
    if missing_columns:
        raise ValueError(
            f"Missing required columns for usage type report: {', '.join(sorted(missing_columns))}"
        )

    try:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
        end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError("start_date and end_date must be in YYYY-MM-DD format") from exc

    if start_dt > end_dt:
        raise ValueError("start_date must be before or equal to end_date")

    window_days = (end_dt - start_dt).days + 1
    # Respeita um teto configurável apenas quando ele existir.
    if (
        config.USAGE_TYPE_REPORT_MAX_RANGE_DAYS is not None
        and window_days > config.USAGE_TYPE_REPORT_MAX_RANGE_DAYS
    ):
        raise ValueError(
            f"Date range cannot exceed {config.USAGE_TYPE_REPORT_MAX_RANGE_DAYS} days"
        )

    df_period = df.copy()
    df_period["Data"] = pd.to_datetime(df_period["Data"], errors="coerce").dt.strftime("%Y-%m-%d")
    df_period = df_period[(df_period["Data"] >= start_date) & (df_period["Data"] <= end_date)].copy()

    report_columns = _usage_type_report_columns()

    if df_period.empty:
        return pd.DataFrame(columns=report_columns)

    grouped = (
        df_period.groupby(["Serviço", "UsageType", "Data"], as_index=False)["Custo($)"]
        .sum()
    )

    all_dates = [
        single_date.strftime("%Y-%m-%d")
        for single_date in pd.date_range(start=start_dt, end=end_dt)
    ]

    total_window_cost = grouped.groupby(["Serviço", "UsageType"])["Custo($)"].sum().sum()
    total_window_cost = float(total_window_cost)

    records = []
    for (service, usage_type), usage_group in grouped.groupby(["Serviço", "UsageType"]):
        timeline = usage_group.set_index("Data")["Custo($)"].reindex(all_dates, fill_value=0.0)
        total_cost = float(timeline.sum())
        if total_cost < min_total_usd:
            continue

        average_daily = float(timeline.mean())
        last_day_cost = float(timeline.loc[end_date])
        variation_usd = last_day_cost - average_daily
        variation_pct = 0.0 if average_daily == 0 else (variation_usd / average_daily) * 100
        max_30d = float(timeline.max())
        min_30d = float(timeline.min())
        avg_last_7_days = float(timeline.tail(min(7, len(timeline))).mean())
        avg_previous_days = float(timeline.iloc[:-7].mean()) if len(timeline) > 7 else 0.0
        delta_last7_vs_previous = avg_last_7_days - avg_previous_days
        share_pct = 0.0 if total_window_cost == 0 else (total_cost / total_window_cost) * 100

        # Regressão linear sobre os dias do período → slope em US$/dia.
        n = len(timeline)
        if n >= 2 and total_cost > 0:
            x = np.arange(n, dtype=float)
            slope_usd_per_day = float(np.polyfit(x, timeline.values, 1)[0])
        else:
            slope_usd_per_day = 0.0

        # Desvio padrão e coeficiente de variação para classificar volatilidade.
        std_daily = float(timeline.std()) if n > 1 else 0.0
        cv = std_daily / average_daily if average_daily > 0 else 0.0

        # Classificação de comportamento:
        # Volátil tem prioridade — CV > 0.5 indica oscilações frequentes e intensas.
        # Crescendo / Caindo: slope > ±1% da média diária por dia.
        slope_ratio = slope_usd_per_day / average_daily if average_daily > 0 else 0.0
        if cv > 0.5:
            comportamento = "Volátil"
        elif slope_ratio > 0.01:
            comportamento = "Crescendo"
        elif slope_ratio < -0.01:
            comportamento = "Caindo"
        else:
            comportamento = "Estável"

        records.append({
            "UsageType": usage_type,
            "Serviço": service,
            "Comportamento": comportamento,
            "Total período": round(total_cost, 4),
            "Participação %": round(share_pct, 2),
            "Média diária": round(average_daily, 4),
            "Último dia": round(last_day_cost, 4),
            "Máximo período": round(max_30d, 4),
            "Mínimo período": round(min_30d, 4),
            "Desvio diário": round(std_daily, 4),
            "CV": round(cv, 4),
            "Média últimos 7 dias": round(avg_last_7_days, 4),
            "Média anteriores": round(avg_previous_days, 4),
            "∆7d vs prev": round(delta_last7_vs_previous, 4),
            "Variação US$": round(variation_usd, 4),
            "Variação %": round(variation_pct, 2),
            "Impacto US$/dia": round(slope_usd_per_day, 4),
        })

    if not records:
        return pd.DataFrame(columns=report_columns)

    result = pd.DataFrame(records)
    result = result.sort_values(
        by=["Variação US$", "Variação %", "Total período"],
        ascending=[False, False, False],
    ).reset_index(drop=True)
    return result


def build_anomaly_data(df, start_date, end_date, z_threshold=2.0, min_cost_usd=5.0):
    """Detecta dias anômalos por UsageType usando z-score.

    Retorna um dict com:
    - top_anomalies: lista dos dias mais anômalos (|z| maior), já ordenados.
    - by_label: {label: [day_indices]} para marcar pontos no gráfico.
    """
    if df is None:
        return {"top_anomalies": [], "by_label": {}}

    df_period = df.copy()
    df_period["Data"] = pd.to_datetime(df_period["Data"], errors="coerce").dt.strftime("%Y-%m-%d")
    df_period = df_period[(df_period["Data"] >= start_date) & (df_period["Data"] <= end_date)]

    all_dates = [d.strftime("%Y-%m-%d") for d in pd.date_range(start=start_date, end=end_date)]
    grouped = (
        df_period.groupby(["Serviço", "UsageType", "Data"], as_index=False)["Custo($)"].sum()
    )

    top_anomalies = []
    by_label = {}

    for (service, usage_type), grp in grouped.groupby(["Serviço", "UsageType"]):
        timeline = grp.set_index("Data")["Custo($)"].reindex(all_dates, fill_value=0.0)
        total = float(timeline.sum())
        if total < min_cost_usd:
            continue

        mean = float(timeline.mean())
        std = float(timeline.std())
        if std == 0:
            continue

        label = f"{usage_type} ({service})"
        anomaly_indices = []

        for i, (date, cost) in enumerate(zip(all_dates, timeline)):
            z = (float(cost) - mean) / std
            if abs(z) >= z_threshold:
                anomaly_indices.append(i)
                top_anomalies.append({
                    "date": date,
                    "usage_type": usage_type,
                    "service": service,
                    "cost": round(float(cost), 2),
                    "mean": round(mean, 2),
                    "z_score": round(z, 2),
                    "direction": "Alta" if z > 0 else "Queda",
                })

        if anomaly_indices:
            by_label[label] = anomaly_indices

    top_anomalies.sort(key=lambda x: abs(x["z_score"]), reverse=True)
    return {"top_anomalies": top_anomalies[:20], "by_label": by_label}


def build_weekly_pattern(df, start_date, end_date):
    """Calcula o custo médio por dia da semana para os top UsageTypes.

    Retorna (day_labels, chart_data) onde chart_data tem {UsageType, values: [seg..dom]}.
    """
    if df is None:
        return [], []

    df_period = df.copy()
    df_period["Data"] = pd.to_datetime(df_period["Data"], errors="coerce")
    df_period = df_period[
        (df_period["Data"].dt.strftime("%Y-%m-%d") >= start_date) &
        (df_period["Data"].dt.strftime("%Y-%m-%d") <= end_date)
    ].copy()
    df_period["dow"] = df_period["Data"].dt.weekday  # 0=Seg, 6=Dom
    df_period["label"] = df_period["UsageType"] + " (" + df_period["Serviço"] + ")"

    # Top N labels por custo total
    top_labels = (
        df_period.groupby("label")["Custo($)"].sum()
        .sort_values(ascending=False)
        .head(config.USAGE_TYPE_CHART_MAX_USAGE_TYPES)
        .index.tolist()
    )

    # Média de custo por (label, dow)
    avg_by_dow = (
        df_period.groupby(["label", "dow"])["Custo($)"].mean()
    )

    day_labels = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
    chart_data = []
    for label in top_labels:
        values = []
        for dow in range(7):
            try:
                values.append(round(float(avg_by_dow.loc[label, dow]), 4))
            except KeyError:
                values.append(0.0)
        chart_data.append({"UsageType": label, "values": values})

    return day_labels, chart_data


def build_usage_type_daily_trend(df, start_date, end_date):
    """Build daily totals, forecast and aggregated totals for UsageType report charts.

    Returns a 4-tuple: (all_dates, forecast_dates, chart_data, total_daily_values).
    - all_dates: date strings covering the report period (labels for "Uso diário" and "Variação %").
    - forecast_dates: date strings for the forecast window after end_date.
    - chart_data: one dict per top-N UsageType with:
        - daily_values: cost per day in the report period
        - forecast_values: linear projection for each forecast day (window = full report period)
    - total_daily_values: total cost per day across all UsageTypes (used for "Others" in bar chart).
    """
    if df is None:
        return [], [], [], []

    df_period = df.copy()
    df_period["Data"] = pd.to_datetime(df_period["Data"], errors="coerce").dt.strftime("%Y-%m-%d")
    df_period = df_period[(df_period["Data"] >= start_date) & (df_period["Data"] <= end_date)].copy()

    all_dates = [
        single_date.strftime("%Y-%m-%d")
        for single_date in pd.date_range(start=start_date, end=end_date)
    ]

    grouped = (
        df_period.groupby(["Serviço", "UsageType", "Data"], as_index=False)["Custo($)"].sum()
    )
    grouped["UsageTypeLabel"] = grouped["UsageType"] + " (" + grouped["Serviço"] + ")"

    pivot = grouped.pivot(index="Data", columns="UsageTypeLabel", values="Custo($)")
    pivot = pivot.reindex(all_dates, fill_value=0.0).fillna(0.0)

    # Total diário somando todos os UsageTypes (usado para calcular "Others" no gráfico de barras).
    total_daily_values = [float(v) for v in pivot.sum(axis=1).tolist()]

    usage_types_by_cost = pivot.sum(axis=0).sort_values(ascending=False)
    top_usage_types = list(usage_types_by_cost.head(config.USAGE_TYPE_CHART_MAX_USAGE_TYPES).index)

    forecast_dates = [
        future_date.strftime("%Y-%m-%d")
        for future_date in pd.date_range(
            start=pd.to_datetime(end_date) + pd.Timedelta(days=1),
            periods=config.USAGE_TYPE_REPORT_FORECAST_DAYS,
        )
    ]

    def _forecast_future(values):
        # Extrapolação linear usando toda a janela do relatório como base (não apenas os últimos 7 dias).
        series = pd.Series(values)
        if len(series) < 2:
            base = float(series.iloc[-1]) if len(series) else 0.0
            return [base] * config.USAGE_TYPE_REPORT_FORECAST_DAYS
        slope = (series.iloc[-1] - series.iloc[0]) / (len(series) - 1)
        last_value = float(series.iloc[-1])
        return [
            round(max(0.0, last_value + slope * step), 4)
            for step in range(1, config.USAGE_TYPE_REPORT_FORECAST_DAYS + 1)
        ]

    chart_data = []
    for usage_type_label in top_usage_types:
        daily_series = [float(value) for value in pivot[usage_type_label].tolist()]
        chart_data.append({
            "UsageType": usage_type_label,
            "daily_values": daily_series,
            "forecast_values": _forecast_future(daily_series),
        })

    return all_dates, forecast_dates, chart_data, total_daily_values


def build_usage_type_daily_variation_pct_trend(df, start_date, end_date, df_report=None):
    """Build a daily percentage variation trend for selected UsageTypes.

    When df_report is provided, selects the top-N UsageTypes by "Variação %" descending
    (maior positivo primeiro → menor/mais negativo por último). Otherwise ranks by total cost.
    """
    if df is None:
        return [], []

    df_period = df.copy()
    df_period["Data"] = pd.to_datetime(df_period["Data"], errors="coerce").dt.strftime("%Y-%m-%d")
    df_period = df_period[(df_period["Data"] >= start_date) & (df_period["Data"] <= end_date)].copy()

    all_dates = [
        single_date.strftime("%Y-%m-%d")
        for single_date in pd.date_range(start=start_date, end=end_date)
    ]

    grouped = (
        df_period.groupby(["Serviço", "UsageType", "Data"], as_index=False)["Custo($)"].sum()
    )
    grouped["UsageTypeLabel"] = grouped["UsageType"] + " (" + grouped["Serviço"] + ")"

    pivot = grouped.pivot(index="Data", columns="UsageTypeLabel", values="Custo($)")
    pivot = pivot.reindex(all_dates, fill_value=0.0).fillna(0.0)

    if df_report is not None and not df_report.empty and "Impacto US$/dia" in df_report.columns:
        # Rankeia por Impacto US$/dia decrescente (sem abs): espelha a ordenação da tabela,
        # mostrando os itens com maior crescimento financeiro real no topo do gráfico.
        ranked = df_report.copy()
        ranked["UsageTypeLabel"] = ranked["UsageType"] + " (" + ranked["Serviço"] + ")"
        ranked = ranked.sort_values("Impacto US$/dia", ascending=False)
        top_usage_types = [
            lbl for lbl in ranked["UsageTypeLabel"].tolist()
            if lbl in pivot.columns
        ][:config.USAGE_TYPE_CHART_MAX_USAGE_TYPES]
    else:
        # Fallback: rankeia por custo total no período.
        top_usage_types = list(
            pivot.sum(axis=0).sort_values(ascending=False)
            .head(config.USAGE_TYPE_CHART_MAX_USAGE_TYPES).index
        )

    chart_data = []
    for usage_type_label in top_usage_types:
        values = pivot[usage_type_label].astype(float).tolist()
        pct_change = []
        previous_value = None
        for current_value in values:
            if previous_value is None or previous_value == 0.0:
                pct_change.append(None)
            else:
                pct_change.append(round(((current_value - previous_value) / previous_value) * 100, 4))
            previous_value = current_value

        chart_data.append({
            "UsageType": usage_type_label,
            "variation_pct_values": pct_change,
        })

    return all_dates, chart_data


def build_usage_type_variation_percent_chart_data(df_report):
    """Build a chart dataset for usage type percentage variation."""
    if df_report is None or df_report.empty:
        return []

    df_sorted = df_report.copy()
    df_sorted["UsageTypeLabel"] = df_sorted["UsageType"] + " (" + df_sorted["Serviço"] + ")"

    positive_variations = (
        df_sorted[df_sorted["Variação %"] > 0]
        .sort_values("Variação %", ascending=False)
    )
    negative_variations = (
        df_sorted[df_sorted["Variação %"] <= 0]
        .sort_values("Variação %", ascending=False)
    )

    top_variations = pd.concat([positive_variations, negative_variations]).head(
        config.USAGE_TYPE_CHART_MAX_USAGE_TYPES
    )

    records = []
    for _, row in top_variations.iterrows():
        records.append({
            "UsageType": row["UsageTypeLabel"],
            "variation_pct": float(row["Variação %"]),
        })

    return records


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
