#!/usr/bin/env bash
# =============================================================================
# cron_daily.sh — Wrapper para o relatório diário de custos AWS
#
# Ativa o virtualenv, seta as variáveis de ambiente e executa o run.py.
# Todas as configurações ficam na seção abaixo — edite antes de usar.
#
# Uso manual:
#   bash scripts/cron_daily.sh
#
# Exemplo de entrada no crontab (todo dia às 08h):
#   0 8 * * * /caminho/para/relatorio_aws_finops_ai/scripts/cron_daily.sh >> /caminho/para/relatorio_aws_finops_ai/output/cron_daily.log 2>&1
# =============================================================================

# -----------------------------------------------------------------------------
# CONFIGURAÇÃO — edite conforme o ambiente
# -----------------------------------------------------------------------------

PROJECT_DIR="/caminho/para/relatorio_aws_finops_ai"
VENV_DIR="$PROJECT_DIR/.venv"

# AWS
COST_EXPLORER_REGION="us-east-1"
BEDROCK_REGION="us-east-1"
BEDROCK_MODEL="us.anthropic.claude-sonnet-4-6"
# Deixe vazio para usar a role da EC2; preencha para execução local
AWS_PROFILE=""

# Notificação SNS + S3 (deixe vazio para desabilitar)
FINOPS_SNS_TOPIC_ARN=""
FINOPS_S3_BUCKET=""
FINOPS_S3_PREFIX_DAILY="finops/relatorios/diario"

# Flags
ENABLE_BEDROCK=true
SKIP_CALENDAR_CONFIRMATION=true

# -----------------------------------------------------------------------------
# EXECUÇÃO — não é necessário editar abaixo desta linha
# -----------------------------------------------------------------------------

set -euo pipefail

cd "$PROJECT_DIR"

# Ativa o virtualenv
source "$VENV_DIR/bin/activate"

# Exporta variáveis de ambiente usadas pelo config.py
export FINOPS_SNS_TOPIC_ARN
export FINOPS_S3_BUCKET
export FINOPS_S3_PREFIX_DAILY

echo "[cron_daily] Iniciando — $(date '+%Y-%m-%d %H:%M:%S')"

CMD=(python3 run.py
  --cost-explorer-region "$COST_EXPLORER_REGION"
  --bedrock-region "$BEDROCK_REGION"
)

[ -n "$AWS_PROFILE" ]              && CMD+=(--aws-profile "$AWS_PROFILE")
[ "$ENABLE_BEDROCK" = true ]       && CMD+=(--enable-bedrock --bedrock-model "$BEDROCK_MODEL")
[ "$SKIP_CALENDAR_CONFIRMATION" = true ] && CMD+=(--skip-calendar-confirmation)

echo "[cron_daily] Comando: ${CMD[*]}"
"${CMD[@]}"

echo "[cron_daily] Concluído — $(date '+%Y-%m-%d %H:%M:%S')"
