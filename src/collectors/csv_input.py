"""
CSV data collector
"""

import pandas as pd
import os


def _normalize_wide_cost_csv(df):
    service_column = df.columns[0]
    df = df.rename(columns={service_column: "Data"})
    df = df[df["Data"].astype(str).str.lower() != "service total"].copy()
    excluded_columns = {"Total costs($)"}
    remaining_columns = [column for column in df.columns if column not in {"Data"} | excluded_columns]
    df = df[["Data"] + remaining_columns]

    melted = df.melt(id_vars=["Data"], var_name="Serviço", value_name="Custo($)")
    melted["Serviço"] = melted["Serviço"].astype(str).str.replace(r"\(\$\)$", "", regex=True).str.strip()
    melted["UsageType"] = "Total"
    melted["Custo($)"] = pd.to_numeric(melted["Custo($)"], errors="coerce").fillna(0.0)
    melted = melted[melted["Custo($)"] != 0].copy()
    return melted[["Data", "Serviço", "UsageType", "Custo($)"]]


def load_csv_data(csv_file):
    """
    Load cost data from CSV file
    Returns: DataFrame
    """
    if not os.path.exists(csv_file):
        raise FileNotFoundError(f"Arquivo CSV não encontrado: {csv_file}")

    df = pd.read_csv(csv_file, encoding="utf-8-sig")

    if {"Data", "Serviço", "Custo($)"}.issubset(df.columns):
        normalized = df.copy()
        if "UsageType" not in normalized.columns:
            normalized["UsageType"] = "Total"
        return normalized

    if "Service" in df.columns:
        return _normalize_wide_cost_csv(df)

    raise ValueError(
        "Formato CSV nao suportado. Esperado formato longo com Data/Serviço/Custo($) "
        "ou formato wide com a primeira coluna Service."
    )
