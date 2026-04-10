"""
Detect cost anomalies on top of daily service and usage type data.
"""

import pandas as pd
import config


def build_usage_type_timeseries(df):
    """
    Normalize the input into daily cost series by service and usage type.
    """
    required_columns = {"Data", "Serviço", "Custo($)"}
    missing = required_columns - set(df.columns)
    if missing:
        raise KeyError(f"Colunas obrigatorias ausentes para analise de anomalias: {sorted(missing)}")

    df_normalized = df.copy()
    if "UsageType" not in df_normalized.columns:
        df_normalized["UsageType"] = "Total"

    df_normalized["Data"] = df_normalized["Data"].astype(str)
    df_normalized["Serviço"] = df_normalized["Serviço"].astype(str)
    df_normalized["UsageType"] = df_normalized["UsageType"].fillna("Total").astype(str)
    df_normalized["Custo($)"] = pd.to_numeric(df_normalized["Custo($)"], errors="coerce").fillna(0.0)

    return (
        df_normalized.groupby(["Data", "Serviço", "UsageType"], as_index=False)["Custo($)"]
        .sum()
        .sort_values(["Serviço", "UsageType", "Data"])
    )


def calculate_anomalies(timeseries_df, data_inicio, data_fim, ultimo_dia):
    """
    Calculate daily anomaly metrics by service and usage type within the consolidated window.
    """
    df_window = timeseries_df[
        (timeseries_df["Data"] >= data_inicio) & (timeseries_df["Data"] <= data_fim)
    ].copy()

    anomalies = []
    grouped = df_window.groupby(["Serviço", "UsageType"])

    for (service, usage_type), group in grouped:
        group = group.sort_values("Data")
        if group.empty:
            continue

        cost_today_rows = group[group["Data"] == ultimo_dia]
        if cost_today_rows.empty:
            continue

        cost_today = float(cost_today_rows["Custo($)"].sum())
        avg_7d = float(group["Custo($)"].mean())
        delta_usd = cost_today - avg_7d
        delta_pct = 0.0 if avg_7d == 0 else (delta_usd / avg_7d) * 100

        anomalies.append(
            {
                "service": service,
                "usage_type": usage_type,
                "cost_today": round(cost_today, 4),
                "avg_7d": round(avg_7d, 4),
                "delta_usd": round(delta_usd, 4),
                "delta_pct": round(delta_pct, 2),
                "days_present": int(group["Data"].nunique()),
                "series": [
                    {"date": row["Data"], "cost_usd": round(float(row["Custo($)"]), 4)}
                    for _, row in group.iterrows()
                ],
            }
        )

    anomalies.sort(key=lambda item: (item["delta_usd"], item["cost_today"]), reverse=True)
    return anomalies


def filter_relevant_anomalies(anomalies):
    """
    Keep only anomalies relevant enough to justify metric enrichment.
    """
    filtered = [
        item
        for item in anomalies
        if item["cost_today"] >= config.MIN_DAILY_COST_USD
        or abs(item["delta_pct"]) >= config.MIN_PERCENT_VARIATION
    ]
    filtered.sort(key=lambda item: (abs(item["delta_usd"]), item["cost_today"]), reverse=True)
    return filtered[: config.TOP_N_ANOMALIES]


def enrich_sms_complementary_usage_types(anomalies, timeseries_df, ultimo_dia):
    """
    Attach complementary Cost Explorer usage types for SMS-related anomalies.
    """
    if timeseries_df is None or timeseries_df.empty:
        return anomalies

    enriched = []
    for anomaly in anomalies:
        if anomaly.get("service") not in config.SPECIAL_SERVICES:
            enriched.append(anomaly)
            continue

        complementary_usage_types = []
        service_rows = timeseries_df[timeseries_df["Serviço"] == anomaly.get("service")].copy()
        for pattern in config.SMS_COMPLEMENTARY_USAGE_TYPE_PATTERNS:
            matching_rows = service_rows[service_rows["UsageType"].str.contains(pattern, case=False, na=False)].copy()
            if matching_rows.empty:
                continue

            grouped = (
                matching_rows.groupby(["Data", "UsageType"], as_index=False)["Custo($)"]
                .sum()
                .sort_values(["UsageType", "Data"])
            )
            for usage_type, usage_group in grouped.groupby("UsageType"):
                cost_today_rows = usage_group[usage_group["Data"] == ultimo_dia]
                cost_today = float(cost_today_rows["Custo($)"].sum()) if not cost_today_rows.empty else 0.0
                avg_7d = float(usage_group["Custo($)"].mean())
                delta_usd = cost_today - avg_7d
                delta_pct = 0.0 if avg_7d == 0 else (delta_usd / avg_7d) * 100
                complementary_usage_types.append(
                    {
                        "usage_type": usage_type,
                        "cost_today": round(cost_today, 4),
                        "avg_7d": round(avg_7d, 4),
                        "delta_usd": round(delta_usd, 4),
                        "delta_pct": round(delta_pct, 2),
                        "series": [
                            {"date": row["Data"], "cost_usd": round(float(row["Custo($)"]), 4)}
                            for _, row in usage_group.iterrows()
                        ],
                    }
                )

        enriched.append(
            {
                **anomaly,
                "complementary_usage_types": complementary_usage_types,
            }
        )

    return enriched
