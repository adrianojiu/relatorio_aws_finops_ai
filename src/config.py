"""
Configuration file for AWS Cost Report Project
"""

import os

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

ANALYSIS_DAYS = 7  # Inclusive analysis window size
OFFSET_DAYS = 2    # Days to step back from today to the latest consolidated AWS day

# ============================================================
# Cost Report Configuration
# Only affects the AWS cost report generation and anomaly inputs.
# ============================================================

EXCLUDED_RECORD_TYPES = ['Credit', 'Refund', 'Tax']
EXCLUDED_SERVICES = []  # Add services to exclude if needed

# Thresholds and ranking for the cost report
MIN_DAILY_COST_USD = 20.0
MIN_PERCENT_VARIATION = 30.0
MIN_ABSOLUTE_VARIATION_USD = 5.0
TOP_N_SERVICES = 5
TOP_N_DAILY_SERVICES = 10
TOP_N_ANOMALIES = 10

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
BEDROCK_MAX_TOKENS = 8000
BEDROCK_TEMPERATURE = 0.2
BEDROCK_MAX_ANALYSIS_ANOMALIES = 4
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

MAX_CANDIDATE_RESOURCES = 25
MAX_RESOURCES_PER_ANOMALY = 3
MAX_S3_RESOURCES_PER_ANOMALY = 5
EKS_PRIMARY_SCALING_METRIC = "GroupTotalInstances"

# S3 request metric collection
DEFAULT_S3_REQUEST_FILTER_ID = "all-objects"
S3_REQUEST_METRICS = [
    {"name": "AllRequests", "stat": "Sum"},
]

# CloudWatch Logs Insights query metadata
LOGS_QUERY_METADATA_MAX_QUERIES = 5
ATHENA_QUERY_METADATA_MAX_QUERIES = 3
ATHENA_QUERY_METADATA_MAX_WORKGROUPS = 3
CLOUDTRAIL_LOOKUP_WINDOW_HOURS = 2
CLOUDTRAIL_MAX_MATCHES_PER_QUERY = 3

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

# ============================================================
# Bedrock Operational Context
# Short runtime summary. Detailed context lives in PROJECT_CONTEXT.md.
# ============================================================

CONTEXT_OPERATIONAL_SUMMARY = """
- Ambiente AWS de CIAM com Ping Identity em EKS e Ping Directory em EC2.
- PDP oscila mais em dias de eventos de streaming do Claro TV+; scaling costuma ser agendado e, em poucos casos, reativo.
- Ping Federate e Ping Access tambem oscilam com eventos, mas normalmente menos que o PDP.
- Eventos e pushes do Claro TV+ devem ser usados como contexto de negocio para plays, autenticacao, autorizacao e scaling agendado, nodegroup do EKS PDP tende fortemente(mas não completamente) a ser utilizado em eventos do Claro tv+.
- Sempre que mencionar eventos que e=tema relação com o Clato TV+ deixe explicito na que é do Claro TV+ para evitar confusão com outros eventos ou atividades.
- Eventos de Pull acima do normal no ECR pode indicar que o cluster prd-sso-ciam esta sendo escalado para atender a demanda de eventos do Claro TV+ ou outro scaling.
- Cluster EKS prd-sso-ciam é responsavel por hospedas o Ping Access, Ping Federate e PDP.
- Calendario de push/eventos não deve ser usado como evidencia direta de custo ou volume de AWS End User Messaging/SMS.
- Ping Directory: primary, secondary e ternary atendem producao; quaternary fica fora do balanceamento e executa backup para S3, relatorios e limpeza de base ldap rodando em scripts nesta instancia. 
- Nat gateway Bytes costuma sofrer influencia de atividades de backup, mas não tem correlação direta com eventos do Claro TV+.
- SMS e transacional; AWS End User Messaging é usado para fallback, não campanha, RTDM e MSE (ferramentas internas não estão na aws) são os principais para envios, AWS End User Messaging só é usado se eles falham.
- Para CloudWatch Logs DataScanned-Bytes, priorize evidencias de queries executadas e metadados de consulta.
- É comum execuções manuais ou agendadas de queries no CloudWatch Logs para investigar eventos, estas consultas podem gerar custos significativos dependendo do volume de dados escaneados, mas são parte importante da operação e investigação.
- No inicio do mes e na primeira semana podem ocorrer queries operacionais recorrentes no CloudWatch Logs para FinOps e reunioes de MBR.
- Temos APIs de cadastro de clientes e reset de senhas e envio de SMS que rodam no EKS cluster prd-sso-fachada, clientes usam estas para Cadastro, Reset e por consequencia para envios de SMS, eventos do Claro TV+ não constumam ter relação com envio de SMS.
- Sempre atento a filas SQS relacionadas a SMS e envios de mensagens do fachada, principalmente as internas de MSE e RTDM, mas também a fila de fallback do SNS; variações nestas filas podem indicar mudanças no volume transacional ou falhas nos canais primários.
- Possuimos buckets S3 com diferentes papeis, incluindo logs brutos do Ping, dados transformados para metricas de negocio e backup/exportacao do Ping Directory; entender o papel de cada bucket é crucial para correlacionar custos e atividades.
- Sempre fique atendo a atividades anomalas de buckets S3 existentes, time de dados costuma fazer queries de leitura em buckets de logs do Ping para gerar metricas e dashboards, mas atividades incomuns podem indicar problemas ou mudanças no comportamento do sistema.
- Temos guardduty configurado para monitorar atividades suspeitas, mas é importante correlacionar alertas do GuardDuty com outros dados operacionais para entender o contexto completo.
- Loadbalancers usados pelo cluster EKS prd-sso-ciam, tendem a ter alto consumo quando eventos do Claro TV+ acontecem, mas o load balancer interno de integracao com a Claro TV+ tem comportamento mais diretamente correlacionado com estes eventos.
- Stress test foi executado na plataforma em 15/04/2026 entre 00:00 e 05:00 horas UTC-3, deve ser verificado a relação deste teste com o custo deste dia na plataforma comparando co outros recursos e eventos, gerando alto consumo geral considerarndo este contexto para qualquer anomalia ou atividade relacionada a esta data.
- Eventos no Brasil como Black Friday, Dia das mães, Natal, Copa do mundo, Jogos Olimpicos, tendem a gerar aumento na demanda, pelo aumento na utilização dos recursos da plataforma.
""".strip()


def load_project_context():
    if not os.path.exists(PROJECT_CONTEXT_FILE):
        return ""
    with open(PROJECT_CONTEXT_FILE, "r", encoding="utf-8") as file_handle:
        return file_handle.read().strip()


def build_runtime_context():
    project_context = load_project_context()
    sections = []
    if CONTEXT_OPERATIONAL_SUMMARY:
        sections.append(f"Resumo operacional objetivo:\n{CONTEXT_OPERATIONAL_SUMMARY}")
    if project_context:
        sections.append(f"Contexto detalhado do projeto:\n{project_context}")
    return "\n\n".join(section for section in sections if section).strip()


CONTEXT_OPERATIONAL = build_runtime_context()
