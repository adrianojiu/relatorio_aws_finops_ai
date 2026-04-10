"""
Utility functions for the AWS Cost Report Project
"""

from datetime import datetime, timedelta
import os
import boto3
import botocore
import config

def get_analysis_period():
    """
    Calculate the analysis period based on config.
    Returns: data_inicio, data_fim, ultimo_dia
    """
    hoje = datetime.now().date()
    ultimo_dia_date = hoje - timedelta(days=config.OFFSET_DAYS)
    data_inicio_date = ultimo_dia_date - timedelta(days=config.ANALYSIS_DAYS - 1)

    data_inicio = data_inicio_date.strftime("%Y-%m-%d")
    data_fim = ultimo_dia_date.strftime("%Y-%m-%d")
    ultimo_dia = data_fim
    return data_inicio, data_fim, ultimo_dia

def ensure_output_dir():
    """Ensure dated output directory exists and return it."""
    output_dir = get_output_dir()
    os.makedirs(output_dir, exist_ok=True)
    return output_dir


def get_output_dir():
    """Return the dated output directory for the current execution date."""
    data_atual = datetime.now().strftime("%Y-%m-%d")
    return os.path.join(config.OUTPUT_DIR, data_atual)

def get_output_filename(prefix, extension):
    """Generate output filename with current date"""
    data_atual = datetime.now().strftime("%Y-%m-%d")
    return f"{prefix}_{data_atual}.{extension}"


def align_period_to_available_data(df, data_inicio, data_fim, ultimo_dia):
    """
    For historical CSV inputs, align the 7-day window to the latest available date when needed.
    """
    if "Data" not in df.columns or df.empty:
        return data_inicio, data_fim, ultimo_dia

    df_dates = df["Data"].astype(str)
    has_current_window_data = ((df_dates >= data_inicio) & (df_dates <= data_fim)).any()
    if has_current_window_data:
        return data_inicio, data_fim, ultimo_dia

    latest_date = df_dates.max()
    latest_dt = datetime.strptime(latest_date, "%Y-%m-%d")
    aligned_start = (latest_dt - timedelta(days=config.ANALYSIS_DAYS - 1)).strftime("%Y-%m-%d")
    aligned_end = latest_date
    return aligned_start, aligned_end, aligned_end


def get_aws_account_label():
    """
    Best-effort label with AWS account alias and ID for report headers.
    """
    try:
        session = boto3.Session(profile_name=config.AWS_PROFILE, region_name=config.WORKLOAD_REGION)
        sts_client = session.client("sts")
        identity = sts_client.get_caller_identity()
        account_id = identity.get("Account")
    except (botocore.exceptions.BotoCoreError, botocore.exceptions.ClientError):
        return f"perfil {config.AWS_PROFILE}"

    alias = None
    try:
        iam_client = session.client("iam")
        aliases = iam_client.list_account_aliases().get("AccountAliases", [])
        if aliases:
            alias = aliases[0]
    except (botocore.exceptions.BotoCoreError, botocore.exceptions.ClientError):
        alias = None

    profile_name = config.AWS_PROFILE
    if alias and account_id:
        return f"{alias} ({account_id})"
    if profile_name and account_id:
        return f"{profile_name} ({account_id})"
    if account_id:
        return account_id
    return f"perfil {config.AWS_PROFILE}"
