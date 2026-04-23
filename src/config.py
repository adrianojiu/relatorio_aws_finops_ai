"""
Configuration file for AWS Cost Report Project
"""

import os
import re

PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))
PROJECT_CONTEXT_FILE = os.path.join(PROJECT_ROOT, "PROJECT_CONTEXT.md")

# ============================================================
# Shared AWS / Runtime Configuration
# Used by both the cost report pipeline and Bedrock analysis.
# ============================================================

AWS_PROFILE = "dev-ciam"
AWS_REGION = "us-east-1"
COST_EXPLORER_REGION = os.getenv("COST_EXPLORER_REGION", "us-east-1")
WORKLOAD_REGION = os.getenv("WORKLOAD_REGION", AWS_REGION)
BEDROCK_REGION = os.getenv("BEDROCK_REGION", "us-east-1")

# ============================================================
# Shared Analysis Window
# Used by both the cost report and the Bedrock payload.
# ============================================================

# Janela consolidada usada nas comparacoes do relatorio e no payload para a IA.
ANALYSIS_DAYS = 7  # Quantos dias entram na janela consolidada.
OFFSET_DAYS = 2    # Quantos dias voltar a partir de hoje para pegar o ultimo dia consolidado da AWS.

# ============================================================
# Cost Report Configuration
# Only affects the AWS cost report generation and anomaly inputs.
# ============================================================

EXCLUDED_RECORD_TYPES = ['Credit', 'Refund', 'Tax']
EXCLUDED_SERVICES = []  # Add services to exclude if needed

# Thresholds and ranking for the cost report
MIN_DAILY_COST_USD = 20.0  # Piso de custo diario para evitar enrich em ruido muito pequeno.
MIN_PERCENT_VARIATION = 30.0  # Variacao percentual minima para considerar uma anomalia relevante.
MIN_ABSOLUTE_VARIATION_USD = 5.0  # Variacao absoluta minima; util para futuros filtros e tuning de ruido.
TOP_N_SERVICES = 5  # Quantos servicos destacar nos rankings principais do relatorio.
TOP_N_DAILY_SERVICES = 10  # Quantos servicos mostrar por dia na serie do TXT.
TOP_N_ANOMALIES = 10  # Quantas anomalias relevantes manter para enriquecimento e ranking interno.

# Service-specific report handling
SPECIAL_SERVICES = ["AWS End User Messaging", "End User Messaging"]
SMS_COMPLEMENTARY_USAGE_TYPE_PATTERNS = [
    "OutboundSMS-BR-Standard-Sharedroute-MessageCount",
    "DeliveryAttempts-SMS",
]

# Output
OUTPUT_DIR = "output"
MONTHLY_EXPORT_OUTPUT_DIR = "export_monthly"
MONTHLY_EXPORT_ONLY_PDP_FILENAME = "costs-prd-ciam-so-pdp.csv"
MONTHLY_EXPORT_ALL_SERVICES_FILENAME = "costs-prd-ciam-todos-servicos.csv"
BUSINESS_EVENT_CALENDAR_FILE = os.path.join(
    "prompts",
    "assets",
    "Régua de Pushs_SMS Now Online.xlsx",
)
PDP_AUTOSCALING_GROUP_TAG_VALUES = [
    "eks-ping-pdp-20230707050838014700000007-2ac49760-29e5-0a4e-7825-19ff09a6422f",
    "eks-ping-pdp-2024081318350878980000002f-04c8a682-e18f-2d36-66fa-37635c476e77",
    "eks-ping-pdp-20240816202653314400000028-8cc8ae6f-925f-7a2e-7fff-545afaa74b14",
    "eks-ping-pdp-20240820215017566200000027-06c8b8e2-7874-82c7-20de-7e29cc9bab41",
    "eks-ping-pdp-20240821113830002300000029-5ac8ba5d-97e4-35cc-2be0-223dc4963bc9",
    "eks-ping-pdp-2024082112423732000000002d-d8c8ba7a-f245-61db-dfb1-9eabc66f8e07",
    "eks-ping-pdp-20240821134753265500000027-b0c8ba98-d2bd-99f0-9443-bd104a200e71",
    "eks-ping-pdp-2024082115423251790000002d-a2c8bacd-4e7d-ba8a-8671-44006b20fa5b",
    "eks-ping-pdp-app-20230703152303191800000004-a2c48e2c-b3a8-c3ba-b636-4591d0e16837",
    "eks-ping-pdp-app-2025032106263568570000001b-e6cadbb0-e849-3660-5a08-d4b12d8d1627",
    "eks-ping-pdp-app-20260225031304324600000006-1ece4964-97d7-c5f8-fbed-80f9172b36f1",
]

# ============================================================
# Bedrock Analysis Configuration
# Only affects prompt generation and LLM execution.
# ============================================================

ENABLE_BEDROCK = False
DEFAULT_BEDROCK_MODEL_ID = "amazon.nova-pro-v1:0"
BEDROCK_MODEL_ID = os.getenv("BEDROCK_MODEL_ID", DEFAULT_BEDROCK_MODEL_ID)
BEDROCK_MAX_TOKENS = 8000  # Limite maximo de tokens de resposta do modelo; aumentar pode elevar custo e latencia.
BEDROCK_TEMPERATURE = 0.2  # Baixa temperatura para respostas mais estaveis e menos criativas.
BEDROCK_MAX_ANALYSIS_ANOMALIES = 4  # Quantas anomalias entram no payload compacto enviado ao Bedrock.
BEDROCK_PRIORITY_METRIC_SERIES = {
    "AllRequests",
    "GroupDesiredCapacity",
    "GroupTotalInstances",
    "GroupInServiceInstances",
    "NetworkIn",
    "NetworkOut",
    "NumberOfMessagesSent",
    "NumberOfMessagesReceived",
}

# ============================================================
# Shared Correlation / Observability Configuration
# Used by the Bedrock correlation layer and supporting discovery.
# ============================================================

MAX_CANDIDATE_RESOURCES = 25  # Limite bruto de candidatos por descoberta antes do ranking final.
MAX_RESOURCES_PER_ANOMALY = 3  # Quantos recursos finais manter por anomalia na maioria dos casos.
MAX_S3_RESOURCES_PER_ANOMALY = 5  # Reserva para S3 quando houver varios buckets candidatos com sinais parciais.
EKS_PRIMARY_SCALING_METRIC = "GroupTotalInstances"  # Fonte principal de evidencia de scaling para EKS.

# S3 request metric collection
DEFAULT_S3_REQUEST_FILTER_ID = "all-objects"
S3_REQUEST_METRICS = [
    {"name": "AllRequests", "stat": "Sum"},
]

# CloudWatch Logs Insights query metadata
LOGS_QUERY_METADATA_MAX_QUERIES = 5  # Quantas queries recentes de CloudWatch Logs anexar por log group.
ATHENA_QUERY_METADATA_MAX_QUERIES = 3  # Quantas queries Athena relevantes anexar por bucket candidato.
ATHENA_QUERY_METADATA_MAX_WORKGROUPS = 3  # Quantos workgroups Athena varrer para reduzir custo/latencia.
CLOUDTRAIL_LOOKUP_WINDOW_HOURS = 2  # Janela de busca de CloudTrail ao redor de queries de Logs/Athena.
CLOUDTRAIL_MAX_MATCHES_PER_QUERY = 3  # Quantos matches de CloudTrail guardar por query enriquecida.

# Tuning do enriquecimento seletivo de CloudTrail para anomalias de S3.
# Normalmente nao precisa ajuste; mexa apenas se houver muito ruido ou latencia.
S3_CLOUDTRAIL_LOOKUP_MAX_EVENTS = 40  # Teto bruto de eventos CloudTrail lidos por bucket antes de encerrar a busca.
S3_CLOUDTRAIL_MAX_MATCHES = 5  # Quantos eventos exemplares entram no resumo final do bucket.
S3_CLOUDTRAIL_MAX_SUMMARY_ITEMS = 3  # Quantos itens mostrar em rankings como top atores e top eventos.
S3_CLOUDTRAIL_TODAY_TO_AVG_RATIO = 1.05  # Gatilho minimo para consultar CloudTrail: hoje >= 105% da media.
S3_CLOUDTRAIL_PEAK_LOOKBACK_DAYS = 2  # Permite olhar tambem o pico recente de AllRequests quando ele ocorreu ate 2 dias antes.

# Messaging correlation metrics
MESSAGING_SQS_METRICS = [
    {"name": "NumberOfMessagesSent", "stat": "Sum"},
    {"name": "NumberOfMessagesReceived", "stat": "Sum"},
    {"name": "ApproximateNumberOfMessagesVisible", "stat": "Average"},
    {"name": "ApproximateAgeOfOldestMessage", "stat": "Maximum"},
]

# Firehose correlation metrics
FIREHOSE_METRICS = [
    {"name": "IncomingRecords", "stat": "Sum"},
    {"name": "IncomingBytes", "stat": "Sum"},
    {"name": "DeliveryToS3.Records", "stat": "Sum"},
    {"name": "DeliveryToS3.Bytes", "stat": "Sum"},
    {"name": "DeliveryToS3.Success", "stat": "Average"},
    {"name": "DeliveryToS3.DataFreshness", "stat": "Maximum"},
]

# Glue correlation metrics
GLUE_METRICS = [
    {"name": "glue.driver.aggregate.bytesRead", "stat": "Sum"},
    {"name": "glue.driver.aggregate.bytesWritten", "stat": "Sum"},
    {"name": "glue.driver.aggregate.elapsedTime", "stat": "Average"},
    {"name": "glue.driver.aggregate.numCompletedStages", "stat": "Sum"},
    {"name": "glue.driver.aggregate.recordsRead", "stat": "Sum"},
    {"name": "glue.driver.aggregate.recordsWritten", "stat": "Sum"},
]

# ECR correlation metrics
ECR_METRICS = [
    {"name": "RepositoryPullCount", "stat": "Sum"},
]

# AWS Backup correlation metrics
AWS_BACKUP_METRICS = [
    {"name": "NumberOfBackupJobsCompleted", "stat": "Sum"},
    {"name": "NumberOfRecoveryPointsCreated", "stat": "Sum"},
    {"name": "BackupVaultBytes", "stat": "Average"},
    {"name": "NumberOfCopyJobsCompleted", "stat": "Sum"},
]

# NAT Gateway correlation metrics
NAT_GATEWAY_METRICS = [
    {"name": "BytesInFromSource", "stat": "Sum"},
    {"name": "BytesOutToDestination", "stat": "Sum"},
    {"name": "BytesInFromDestination", "stat": "Sum"},
    {"name": "BytesOutToSource", "stat": "Sum"},
    {"name": "ActiveConnectionCount", "stat": "Average"},
]

# Transit Gateway correlation metrics
TRANSIT_GATEWAY_METRICS = [
    {"name": "BytesIn", "stat": "Sum"},
    {"name": "BytesOut", "stat": "Sum"},
]

# Load Balancer correlation metrics
LOAD_BALANCER_METRICS = [
    {"name": "RequestCount", "stat": "Sum", "types": ["application"]},
    {"name": "ProcessedBytes", "stat": "Sum", "types": ["application", "network"]},
    {"name": "TargetResponseTime", "stat": "Average", "types": ["application"]},
    {"name": "HTTPCode_Target_4XX_Count", "stat": "Sum", "types": ["application"]},
    {"name": "HTTPCode_Target_5XX_Count", "stat": "Sum", "types": ["application"]},
    {"name": "ActiveFlowCount", "stat": "Average", "types": ["network"]},
    {"name": "NewFlowCount", "stat": "Sum", "types": ["network"]},
]

# Known business context for S3 buckets
KNOWN_S3_BUCKET_CONTEXT = {
    "prd-ciam-logs": {
        "bucket_role": "ping_raw_logs",
        "data_pipeline": "lambda_glue_redshift_quicksight",
        "request_metrics_filter_id": "all-objects",
        "notes": [
            "Bucket de logs brutos do Ping Identity; os dados seguem pipeline com Lambda, Glue, Redshift e QuickSight."
        ],
    },
    "prd-sso-ciam-pingdirectory": {
        "bucket_role": "ping_directory_backup_and_exports",
        "request_metrics_filter_id": "all-objects",
        "notes": [
            "Bucket usado para backup da base Ping Directory e extracoes LDAP enviadas pela instancia quaternaria."
        ],
    },
    "prd-ping-federate-logs-raw": {
        "bucket_role": "ping_federate_transformed_logs",
        "data_pipeline": "business_metrics_quicksight",
        "request_metrics_filter_id": "all-objects",
        "notes": [
            "Bucket com dados transformados a partir de logs do Ping, usados na geracao de metricas de negocio."
        ],
    },
}

# Known business context for messaging queues
KNOWN_MESSAGING_QUEUE_CONTEXT = {
    "prd-sso-fachada-digital-id-sms-mse": {
        "queue_role": "sms_primary_trigger_mse",
        "notes": [
            "Fila de disparo interno de SMS MSE; ajuda a evidenciar se o volume transacional subiu antes do fallback."
        ],
    },
    "prd-sso-fachada-digital-id-sms-rtdm": {
        "queue_role": "sms_primary_trigger_rtdm",
        "notes": [
            "Fila de disparo interno de SMS RTDM; variacoes podem indicar mudanca de trafego ou falha em um dos canais primarios."
        ],
    },
    "prd-sso-fachada-digital-id-sms-sns": {
        "queue_role": "sms_fallback_sns",
        "notes": [
            "Fila de fallback para envio via End User Messaging/SNS quando os dois canais internos falham."
        ],
    },
    "prd-sso-fachada-digital-id-whatsapp": {
        "queue_role": "whatsapp_notifications",
        "notes": [
            "Fila de notificacoes via WhatsApp; pode ajudar a diferenciar aumento geral de mensagens de aumento especifico em SMS."
        ],
    },
}

# Known business context for Firehose streams
KNOWN_FIREHOSE_STREAM_CONTEXT = {
    "prd-sso-fachada-firehose-s3": {
        "stream_role": "motor_regras_api_logs",
        "notes": [
            "Firehose usado para a API do motor de regras.",
        ],
    },
    "prd-sso-fachada-reset-firehose-s3": {
        "stream_role": "reset_api_logs",
        "notes": [
            "Firehose usado para a API de reset.",
        ],
    },
    "prd-sso-fachada-sms-sender-logs-firehose-s3": {
        "stream_role": "sms_sender_api_logs",
        "notes": [
            "Firehose usado para a API de envio de SMS.",
        ],
    },
}

# Known business context for ECR repositories
KNOWN_ECR_REPOSITORY_CONTEXT = {
    "pingidentity/pingaccess": {
        "repository_role": "ping_access_and_pdp_images",
        "notes": [
            "Repositorio usado por Ping Access e PDP no cluster EKS.",
        ],
    },
    "pingidentity/pingfederate": {
        "repository_role": "ping_federate_images",
        "notes": [
            "Repositorio usado por Ping Federate no cluster EKS.",
        ],
    },
    "prd-sso-fachada-identidade-orquestrador-san": {
        "repository_role": "motor_regras_api_images",
        "notes": [
            "Repositorio usado pela API do motor de regras no EKS.",
        ],
    },
    "prd-sso-fachada-identidade-sms-sender": {
        "repository_role": "sms_sender_api_images",
        "notes": [
            "Repositorio usado pela API de envio de SMS no EKS.",
        ],
    },
}

# Known business context for load balancers
KNOWN_LOAD_BALANCER_CONTEXT = {
    "prd-sso-ciam-privatelink": {
        "lb_type": "network",
        "lb_scheme": "internal",
        "lb_role": "clarotv_streaming_authentication_integration",
        "notes": [
            "Usado SOMENTE para integracao de autenticacao e login de clientes do Claro TV+ na plataforma de streaming.",
            "Este NLB nao e usado pelo PDP; autorizacao/PDP passa pelos demais load balancers do stack Ping.",
        ],
    },
    "prd-grupoPD-ldap": {
        "lb_type": "network",
        "lb_scheme": "internal",
        "lb_role": "ping_directory_ldap_reads",
        "notes": [
            "Usado para requisicoes de leitura LDAP do Ping Directory.",
        ],
    },
    "prd-grupoPD-alb": {
        "lb_type": "application",
        "lb_scheme": "internal",
        "lb_role": "ping_directory_admin_console",
        "notes": [
            "Usado pelo Ping Directory Administrative Console.",
        ],
    },
    "prd-grupopd-primary-alb": {
        "lb_type": "application",
        "lb_scheme": "internal",
        "lb_role": "ping_directory_primary_writes",
        "notes": [
            "Usado pelo Ping Directory primario para gravacao e alteracao da base.",
        ],
    },
    "prd-grupopd-secondary-alb": {
        "lb_type": "application",
        "lb_scheme": "internal",
        "lb_role": "ping_directory_secondary_writes",
        "notes": [
            "Usado pelo Ping Directory secundario quando o primario esta fora.",
        ],
    },
    "k8s-prdciam-f6d5697eb4": {
        "lb_type": "application",
        "lb_scheme": "internal",
        "lb_role": "eks_ping_access_federate_pdp",
        "notes": [
            "Load balancer do cluster EKS usado por Ping Federate, Access e PDP.",
        ],
    },
    "k8s-prdssofachada-92ddf9f6c1": {
        "lb_type": "application",
        "lb_scheme": "internal",
        "lb_role": "eks_fachada_apis",
        "notes": [
            "Load balancer do cluster EKS usado pelas APIs do fachada.",
        ],
    },
    "k8s-prdciamexternal-3fba2b5dc7": {
        "lb_type": "application",
        "lb_scheme": "internet-facing",
        "lb_role": "eks_ping_external",
        "notes": [
            "Load balancer internet-facing do cluster ping.",
        ],
    },
}

def load_project_context():
    if not os.path.exists(PROJECT_CONTEXT_FILE):
        return ""
    with open(PROJECT_CONTEXT_FILE, "r", encoding="utf-8") as file_handle:
        return file_handle.read().strip()


def _extract_markdown_section(markdown_text, heading_title):
    """
    Extract one second-level markdown section by title from PROJECT_CONTEXT.md.
    """
    if not markdown_text:
        return ""

    heading_pattern = re.compile(
        rf"^##\s+{re.escape(heading_title)}\s*$",
        flags=re.MULTILINE,
    )
    heading_match = heading_pattern.search(markdown_text)
    if not heading_match:
        return ""

    content_start = heading_match.end()
    next_heading_match = re.search(
        r"^##\s+.+$",
        markdown_text[content_start:],
        flags=re.MULTILINE,
    )
    if next_heading_match:
        section_text = markdown_text[content_start: content_start + next_heading_match.start()]
    else:
        section_text = markdown_text[content_start:]
    return section_text.strip()


def load_bedrock_context():
    """
    Use PROJECT_CONTEXT.md as the single textual source of truth for Bedrock context.
    """
    project_context = load_project_context()
    # Prefer the curated section to keep prompt size under control without duplicating text elsewhere.
    bedrock_context = _extract_markdown_section(project_context, "Contexto para Bedrock")
    return bedrock_context or project_context


BEDROCK_CONTEXT = load_bedrock_context()
