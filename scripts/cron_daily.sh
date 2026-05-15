#!/usr/bin/env bash
# =============================================================================
# cron_daily.sh — Wrapper para o relatório diário de custos AWS
#
# Fluxo:
#   1. Baixa a planilha de eventos do Google Drive
#   2. Executa o run.py para gerar o relatório
#   3. Em caso de falha em qualquer etapa, envia alerta via SNS
#
# Todas as configurações ficam na seção abaixo — edite antes de usar.
#
# Uso manual:
#   bash scripts/cron_daily.sh
#
# Exemplo de entrada no crontab (todo dia às 08h horário de Brasília = 11h UTC):
#   0 11 * * * /caminho/para/relatorio_aws_finops_ai/scripts/cron_daily.sh >> /caminho/para/relatorio_aws_finops_ai/output/cron_daily.log 2>&1
# =============================================================================

# -----------------------------------------------------------------------------
# CONFIGURAÇÃO — edite conforme o ambiente
# -----------------------------------------------------------------------------

PROJECT_DIR="/caminho/para/relatorio_aws_finops_ai"
VENV_DIR="$PROJECT_DIR/.venv"

# AWS
AWS_REGION="sa-east-1"
COST_EXPLORER_REGION="us-east-1"
BEDROCK_REGION="us-east-1"
BEDROCK_MODEL="us.anthropic.claude-sonnet-4-6"
# Deixe vazio para usar a role da EC2; preencha para execução local
AWS_PROFILE=""

# Notificação SNS + S3 — envia link do HTML por e-mail (deixe vazio para desabilitar)
FINOPS_SNS_TOPIC_ARN="arn:aws:sns:sa-east-1:141556317325:finops-relatorios"
FINOPS_S3_BUCKET="ping-revogacao-de-sessao"
FINOPS_S3_PREFIX_DAILY="finops/relatorios/diario"

# Google Drive — download da planilha de eventos antes do relatório
GDRIVE_FILE_ID="1dS7E1dlskOqc1pXuBjpkQ7umfwAORAcj9BGkWCkZ5Gg"
GDRIVE_CREDENTIALS="$PROJECT_DIR/client_secret.json"
GDRIVE_TOKEN="$PROJECT_DIR/token.json"

# Flags
ENABLE_BEDROCK=true
SKIP_CALENDAR_CONFIRMATION=true

# -----------------------------------------------------------------------------
# TRAP DE FALHA — envia alerta SNS se qualquer etapa abortar
# -----------------------------------------------------------------------------

# Usa o mesmo tópico SNS do relatório para os alertas de erro
ALERT_SNS_ARN="${FINOPS_SNS_TOPIC_ARN}"
ALERT_SNS_REGION="${BEDROCK_REGION}"

_on_failure() {
  local msg="[FinOps CIAM] ERRO no relatório diário — $(date '+%Y-%m-%d %H:%M:%S')"
  echo "$msg"
  if [ -n "${ALERT_SNS_ARN:-}" ]; then
    aws sns publish \
      --topic-arn "$ALERT_SNS_ARN" \
      --subject "[FinOps CIAM] ERRO — relatório diário falhou" \
      --message "$msg — verifique: $PROJECT_DIR/output/cron_daily.log" \
      --region "$ALERT_SNS_REGION" || true
  fi
}
trap _on_failure ERR

# -----------------------------------------------------------------------------
# EXECUÇÃO — não é necessário editar abaixo desta linha
# -----------------------------------------------------------------------------

set -euo pipefail

cd "$PROJECT_DIR"

# Ativa o virtualenv e garante dependências atualizadas
source "$VENV_DIR/bin/activate"
pip install -q -r "$PROJECT_DIR/requirements.txt"

# Exporta variáveis de ambiente usadas pelo config.py
export FINOPS_SNS_TOPIC_ARN
export FINOPS_S3_BUCKET
export FINOPS_S3_PREFIX_DAILY

echo "[cron_daily] Iniciando — $(date '+%Y-%m-%d %H:%M:%S')"

# Baixa a planilha de eventos do Google Drive antes de gerar o relatório
echo "[cron_daily] Baixando planilha de eventos do Google Drive..."
python3 scripts/download_calendar.py \
  --file-id     "$GDRIVE_FILE_ID" \
  --dest        "prompts/assets/Régua de Pushs_SMS Now Online.xlsx" \
  --credentials "$GDRIVE_CREDENTIALS" \
  --token       "$GDRIVE_TOKEN"

CMD=(python3 run.py
  --aws-region "$AWS_REGION"
  --cost-explorer-region "$COST_EXPLORER_REGION"
  --bedrock-region "$BEDROCK_REGION"
)

[ -n "$AWS_PROFILE" ]                            && CMD+=(--aws-profile "$AWS_PROFILE")
[ "$ENABLE_BEDROCK" = true ]                     && CMD+=(--enable-bedrock --bedrock-model "$BEDROCK_MODEL")
[ "$SKIP_CALENDAR_CONFIRMATION" = true ]         && CMD+=(--skip-calendar-confirmation)
[ -n "${FINOPS_SNS_TOPIC_ARN:-}" ] && [ -n "${FINOPS_S3_BUCKET:-}" ] && CMD+=(--sns-topic-arn "$FINOPS_SNS_TOPIC_ARN" --s3-bucket "$FINOPS_S3_BUCKET" --s3-prefix "$FINOPS_S3_PREFIX_DAILY")

echo "[cron_daily] Comando: ${CMD[*]}"
"${CMD[@]}"

echo "[cron_daily] Concluído — $(date '+%Y-%m-%d %H:%M:%S')"
