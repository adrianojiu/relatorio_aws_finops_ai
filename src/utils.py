"""
Utility functions for the AWS Cost Report Project
"""

from datetime import datetime, date, timedelta
import os
import re
import shutil
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


def cleanup_old_reports(retention_months: int = config.REPORT_RETENTION_MONTHS) -> None:
    """
    Remove arquivos e pastas com mais de retention_months meses nas pastas output/ e export_monthly/.

    Regras:
    - output/YYYY-MM-DD/  → remove pastas cujo nome de data é anterior ao corte
    - output/monthly/*.txt → remove arquivos cujo nome contém YYYY-MM anterior ao corte
    - export_monthly/*.csv → remove arquivos cujo nome contém YYYY-MM anterior ao corte

    Falhas individuais são logadas e ignoradas para não interromper a execução principal.
    """
    cutoff = _retention_cutoff(retention_months)
    _cleanup_daily_output_dirs(cutoff)
    _cleanup_monthly_files(cutoff)
    _cleanup_export_monthly_files(cutoff)


def _retention_cutoff(retention_months: int) -> date:
    """Retorna o primeiro dia do mês que marca o início do período de retenção."""
    today = date.today()
    total = today.year * 12 + today.month - retention_months
    year, month = divmod(total, 12)
    if month == 0:
        month = 12
        year -= 1
    return date(year, month, 1)


def _cleanup_daily_output_dirs(cutoff: date) -> None:
    """Remove subpastas YYYY-MM-DD dentro de output/ que são anteriores ao corte."""
    output_dir = config.OUTPUT_DIR
    if not os.path.isdir(output_dir):
        return
    pattern = re.compile(r"^\d{4}-\d{2}-\d{2}$")
    for entry in os.scandir(output_dir):
        if not entry.is_dir() or not pattern.match(entry.name):
            continue
        try:
            entry_date = date.fromisoformat(entry.name)
            if entry_date < cutoff:
                shutil.rmtree(entry.path)
                print(f"[cleanup] Removida pasta antiga: {entry.path}")
        except (ValueError, OSError) as exc:
            print(f"[cleanup] Aviso: não foi possível remover {entry.path}: {exc}")


def _cleanup_monthly_files(cutoff: date) -> None:
    """Remove arquivos em output/monthly/ com YYYY-MM no nome anteriores ao corte."""
    monthly_dir = os.path.join(config.OUTPUT_DIR, "monthly")
    if not os.path.isdir(monthly_dir):
        return
    _remove_old_dated_files(monthly_dir, cutoff, pattern="*")


def _cleanup_export_monthly_files(cutoff: date) -> None:
    """Remove arquivos CSV em export_monthly/ com YYYY-MM no nome anteriores ao corte."""
    export_dir = config.MONTHLY_EXPORT_OUTPUT_DIR
    if not os.path.isdir(export_dir):
        return
    _remove_old_dated_files(export_dir, cutoff, pattern="*.csv")


def _remove_old_dated_files(directory: str, cutoff: date, pattern: str) -> None:
    """Remove arquivos cujo nome contém YYYY-MM anterior ao corte dentro de directory."""
    import glob
    date_re = re.compile(r"(\d{4})-(\d{2})")
    for filepath in glob.glob(os.path.join(directory, pattern)):
        if not os.path.isfile(filepath):
            continue
        basename = os.path.basename(filepath)
        match = date_re.search(basename)
        if not match:
            continue
        try:
            file_date = date(int(match.group(1)), int(match.group(2)), 1)
            if file_date < cutoff:
                os.remove(filepath)
                print(f"[cleanup] Removido arquivo antigo: {filepath}")
        except (ValueError, OSError) as exc:
            print(f"[cleanup] Aviso: não foi possível remover {filepath}: {exc}")


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
