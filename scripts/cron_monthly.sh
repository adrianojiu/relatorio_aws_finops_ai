#!/usr/bin/env bash
# =============================================================================
# cron_monthly.sh — Wrapper para o relatório mensal de custos AWS
#
# Ativa o virtualenv, seta as variáveis de ambiente e executa o
# export_monthly_costs.py, que gera os CSVs e aciona o generate_monthly_analysis.
# Todas as configurações ficam na seção abaixo — edite antes de usar.
#
# Uso manual:
#   bash scripts/cron_monthly.sh
#   bash scripts/cron_monthly.sh 2026-03   # mês específico
#
# Exemplo de entrada no crontab (todo dia 5 do mês às 08h):
#   0 8 5 * * /caminho/para/relatorio_aws_finops_ai/scripts/cron_monthly.sh >> /caminho/para/relatorio_aws_finops_ai/output/cron_monthly.log 2>&1
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
FINOPS_S3_PREFIX_MONTHLY="finops/relatorios/mensal"

# Flags
ENABLE_BEDROCK=true

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
export FINOPS_S3_PREFIX_MONTHLY

# Mês: usa o argumento passado ou calcula o mês anterior automaticamente
if [ -n "${1:-}" ]; then
  MONTH="$1"
else
  MONTH=$(date -d "$(date +%Y-%m-01) -1 month" +%Y-%m)
fi

echo "[cron_monthly] Iniciando mês $MONTH — $(date '+%Y-%m-%d %H:%M:%S')"

CMD=(python3 scripts/export_monthly_costs.py
  --month "$MONTH"
  --cost-explorer-region "$COST_EXPLORER_REGION"
)

[ -n "$AWS_PROFILE" ]        && CMD+=(--aws-profile "$AWS_PROFILE")
[ "$ENABLE_BEDROCK" = true ] && CMD+=(--enable-bedrock --bedrock-region "$BEDROCK_REGION" --bedrock-model "$BEDROCK_MODEL")

echo "[cron_monthly] Comando: ${CMD[*]}"
"${CMD[@]}"

echo "[cron_monthly] Concluído — $(date '+%Y-%m-%d %H:%M:%S')"
