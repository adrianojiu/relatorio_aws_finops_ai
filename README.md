# Relatório de Custos AWS (CIAM)

Este projeto gera relatórios de custos da AWS a partir do **Cost Explorer** da AWS ou CSV. O projeto está modularizado para facilitar manutenção e extensão, incluindo integração com IA via AWS Bedrock.

Sempre veriticar os arquivos abaixo para criar contexto e verificar requisitos:
@PROJECT_CONTEXT.md
@AGENTS.md

## Contexto do Projeto

Antes de alterar regras, correlacoes, observabilidade, formato de relatorio ou comportamento do Bedrock, consulte:

- [`AGENTS.md`](./AGENTS.md)
- [`PROJECT_CONTEXT.md`](./PROJECT_CONTEXT.md)
- [`prompts/finops_analysis.txt`](./prompts/finops_analysis.txt)
- [`src/config.py`](./src/config.py)

Esses arquivos consolidam:
- instrucoes de trabalho para agentes
- contexto operacional do ambiente
- decisoes de implementacao
- regras de parametrizacao
- convencoes de manutencao
- expectativas para README, configuracao e Bedrock
- a secao `## Contexto para Bedrock` do `PROJECT_CONTEXT.md` como fonte textual unica enviada ao modelo

### Onde alterar cada tipo de contexto

- [`PROJECT_CONTEXT.md`](./PROJECT_CONTEXT.md)
  Use para contexto de negócio, contexto técnico-operacional e regras interpretativas do ambiente.
  Coloque aqui explicações como:
  - como o ambiente funciona
  - o que é comportamento esperado ou exceção operacional
  - como interpretar eventos, pushes, PDP, Ping Directory, CloudWatch Logs e SMS
  - decisões já tomadas no projeto sobre causalidade e leitura dos relatórios
  - a secao `## Contexto para Bedrock`, que agora e a unica fonte textual enviada ao modelo

- [`AGENTS.md`](./AGENTS.md)
  Use para instruções curtas de trabalho para agentes/IA.
  Coloque aqui orientações como:
  - quais arquivos consultar antes de mudar algo
  - regras rápidas que não podem ser esquecidas
  - onde fica a fonte de verdade de cada assunto
  - como um agente deve se comportar ao editar código, prompt ou documentação

- [`prompts/finops_analysis.txt`](./prompts/finops_analysis.txt)
  Use para instruções de análise e escrita da IA no relatório final.
  Coloque aqui regras como:
  - como classificar anomalias
  - como escrever a visão consolidada de causalidade
  - o que a IA deve evitar afirmar sem evidência
  - como usar contexto de evento, SMS, TGW, S3 e CloudWatch na resposta

- [`src/config.py`](./src/config.py)
  Use para configuração executável do sistema.
  Coloque aqui somente itens objetivos usados pelo código, como:
  - regiões AWS
  - thresholds
  - listas de métricas
  - usage types
  - nomes de arquivos
  - recursos conhecidos e parâmetros técnicos de coleta

### Regra prática

- Se for explicação longa para humano entender o ambiente: `PROJECT_CONTEXT.md`
- Se for regra curta para orientar um agente: `AGENTS.md`
- Se for instrução de como a IA deve analisar e escrever: `prompts/finops_analysis.txt`
- Se for parâmetro técnico usado pelo código: `src/config.py`

## ⚡ Quickstart

Para quem quer bater o olho e já executar sem ler tudo:

1. **Preparar ambiente local**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. **Baixar a planilha de eventos do Google Drive**
   Necessário ter `client_secret.json` e `token.json` na raiz do projeto (gerados via `setup_gdrive_auth.py`).
   O `run.py` oferece o download automaticamente ao perguntar sobre a planilha — basta responder `N`.
   Para baixar manualmente antes de rodar:
   ```bash
   python3 scripts/download_calendar.py \
     --file-id     "1dS7E1dlskOqc1pXuBjpkQ7umfwAORAcj9BGkWCkZ5Gg" \
     --dest        "prompts/assets/Régua de Pushs_SMS Now Online.xlsx" \
     --credentials "./client_secret.json" \
     --token       "./token.json"
   ```

3. **Gerar o relatório diário com IA**
   ```bash
   python3 run.py --aws-profile prd-ciam --aws-region sa-east-1 --cost-explorer-region us-east-1 --bedrock-region us-east-1 --enable-bedrock --bedrock-model us.anthropic.claude-sonnet-4-6
   ```

4. **Gerar o relatório mensal com todos os serviços e somente PDP**
   ```bash
   python3 scripts/export_monthly_costs.py --month 2026-03 --aws-profile prd-ciam --cost-explorer-region us-east-1
   ```

5. **Onde ajustar contexto e instruções**
   - contexto de negócio e operação: [`PROJECT_CONTEXT.md`](./PROJECT_CONTEXT.md)
   - instruções para agentes/IA: [`AGENTS.md`](./AGENTS.md)
   - prompt principal do relatório: [`prompts/finops_analysis.txt`](./prompts/finops_analysis.txt)
   - configuração técnica e métricas: [`src/config.py`](./src/config.py)


6. **Arquivo de eventos Clarotv+**
   - `prompts/assets/Régua de Pushs_SMS Now Online.xlsx`
   - Antes de iniciar, o `run.py` pergunta se a planilha está atualizada:
     - Resposta `s` → continua normalmente
     - Resposta `N` ou Enter → baixa automaticamente do Google Drive e continua (requer `client_secret.json` e `token.json` na raiz)
   - Em automações (cron), use `--skip-calendar-confirmation` — o `cron_daily.sh` já faz o download antes de rodar
   - Este arquivo é provido pelo time do Claro TV+ e está no Google Drive do mesmo time


Esse `Quickstart` é um atalho. Os detalhes completos continuam nas seções abaixo.

## 📁 Estrutura do Projeto

```
relatorio-custo-aws/
├── AGENTS.md                      # Instruções curtas para agentes/IA
├── CLAUDE.md                      # Instruções para o Claude Code
├── PROJECT_CONTEXT.md             # Contexto de negócio e operação
├── README.md
├── requirements.txt
├── .gitignore
├── run.py                         # Script launcher do relatório diário
├── scripts/                       # Scripts auxiliares e wrappers
│   ├── cron_daily.sh              # Wrapper para agendamento do relatório diário
│   ├── cron_monthly.sh            # Wrapper para agendamento do relatório mensal
│   ├── export_monthly_costs.py    # Exporta CSVs mensais e aciona análise mensal
│   ├── generate_monthly_analysis.py  # Gera análise mensal consolidada
│   ├── download_calendar.py       # Baixa a planilha de eventos do Google Drive (usado pelo cron)
│   └── setup_gdrive_auth.py       # Autenticação OAuth2 Google — roda UMA VEZ localmente
├── src/                           # Código fonte modular
│   ├── main.py                    # Ponto de entrada principal
│   ├── config.py                  # Configurações centralizadas
│   ├── utils.py                   # Funções utilitárias
│   ├── collectors/                # Coleta de dados
│   │   ├── business_events.py
│   │   ├── cost_explorer.py
│   │   ├── csv_input.py
│   │   ├── metrics_cloudwatch.py
│   │   ├── metrics_messaging.py
│   │   └── resource_discovery.py
│   ├── analyzers/                 # Análise de custos
│   │   ├── anomaly_detection.py
│   │   ├── correlation_analysis.py
│   │   └── cost_analysis.py
│   ├── mappings/                  # Regras de correlação
│   │   └── correlation_rules.py
│   ├── renderers/                 # Geração de relatórios
│   │   ├── txt_report.py
│   │   ├── excel_report.py
│   │   └── pdf_report.py
│   └── integrations/              # Integrações externas
│       ├── bedrock.py             # Análise via AWS Bedrock
│       └── notifier.py            # Upload S3 + notificação SNS
├── output/                        # Relatórios diários gerados (por data)
│   └── monthly/                   # Relatórios mensais gerados
├── export_monthly/                # CSVs mensais exportados
├── prompts/                       # Prompts para IA
│   ├── finops_analysis.txt
│   └── assets/
│       ├── Régua de Pushs_SMS Now Online.xlsx  # Calendário de eventos Claro TV+
│       └── claro.png
├── legacy/                        # Scripts anteriores à modularização
├── csv/                           # CSVs de entrada para modo --source csv
├── samples/                       # Exemplos de arquivos
└── .venv/                         # Ambiente virtual local (opcional)
```

## 📌 Funcionalidades

- Coleta de dados via **AWS Cost Explorer API** ou **CSV**
- Análise automática de custos:
  - Custo médio por dia
  - Variação em relação à média
  - Serviços que aumentaram/reduziram custo
  - TOP N serviços por custo
  - Análise especial para AWS End User Messaging
  - Enriquecimento semântico de `usage_type` para S3, diferenciando requests, storage, retrieval e possíveis mudanças de classe/tier
  - Enriquecimento complementar de `API operation` para S3, CloudWatch, AWS End User Messaging e EC2 - Other
- Geração de relatórios em **Excel** e **TXT**
- Integração com **AWS Bedrock** para análise com IA (opcional)

## 🛠️ Requisitos

- Python 3.8+
- Credenciais AWS configuradas
- Ambiente virtual recomendado: `.venv`
- Dependências Python do projeto:
  - `boto3`
  - `pandas`
  - `openpyxl`
  - `google-auth`
  - `google-auth-oauthlib`
  - `google-api-python-client`
- AWS CLI configurado com um profile válido quando for usar `--aws-profile`
- Acesso de rede à AWS nas regiões usadas pela execução

### Permissões AWS típicas

Para a execução completa via AWS API, o profile normalmente precisa de permissões de leitura para:

- Cost Explorer: `ce:GetCostAndUsage`
- CloudWatch: `cloudwatch:GetMetricStatistics`
- STS/IAM: `sts:GetCallerIdentity`, `iam:ListAccountAliases`
- S3: `s3:ListAllMyBuckets`, `s3:GetBucketLocation`, `s3:ListBucketMetricsConfigurations`
- EC2/Auto Scaling: `ec2:DescribeInstances`, `ec2:DescribeNatGateways`, `ec2:DescribeTransitGateways`, `autoscaling:DescribeAutoScalingGroups`
- Load Balancer: `elasticloadbalancing:DescribeLoadBalancers`
- CloudWatch Logs / CloudTrail: `logs:DescribeLogGroups`, `logs:DescribeQueries`, `logs:DescribeQueryDefinitions`, `logs:GetQueryResults`, `cloudtrail:LookupEvents`
- Lambda / SQS / Step Functions / DynamoDB / Firehose / Glue / ECR / Backup:
  - `lambda:ListFunctions`
  - `sqs:ListQueues`
  - `states:ListStateMachines`
  - `dynamodb:ListTables`
  - `firehose:ListDeliveryStreams`
  - `glue:GetJobs`, `glue:GetJobRuns`
  - `ecr:DescribeRepositories`
  - `backup:ListBackupVaults`
- Bedrock, quando `--enable-bedrock` estiver ativo: `bedrock:InvokeModel`

Observações:
- se parte dessas permissões faltar, o relatório ainda pode rodar parcialmente, mas com menos contexto e menos precisão
- para o script mensal de exportação PDP, o essencial é `ce:GetCostAndUsage`

## 🚀 Como Usar

1. **Clonar e configurar ambiente:**
   ```bash
   git clone <repo>
   cd relatorio-custo-aws
   python -m venv .venv
   source .venv/bin/activate  # Linux/Mac
   # ou .venv\Scripts\Activate  # Windows
   pip install -r requirements.txt
   ```

2. **Executar relatório via Cost Explorer:**
   ```bash
   python run.py --source cost-explorer
   ```

3. **Executar relatório via CSV:**
   ```bash
   python run.py --source csv --csv-file caminho/do/arquivo.csv
   ```

4. **Com análise Bedrock:**
   ```bash
   python run.py --source cost-explorer --enable-bedrock
   ```

   Por padrão o projeto usa o modelo `amazon.nova-pro-v1:0`, configurado em `src/config.py`.

5. **Sobrescrever o modelo Bedrock nesta execução:**
   ```bash
   python run.py --source cost-explorer --enable-bedrock --bedrock-model amazon.nova-pro-v1:0
   ```

6. **Ou definir por variável de ambiente:**
   ```bash
   export BEDROCK_MODEL_ID=amazon.nova-pro-v1:0
   python run.py --source cost-explorer --enable-bedrock
   ```

7. **Prioridade de configuração do modelo Bedrock:**
   - `--bedrock-model` na execução
   - variável de ambiente `BEDROCK_MODEL_ID`
   - valor padrão em `src/config.py`

8. **Arquivos gerados para inspeção do Bedrock:**
   - `*_bedrock_payload.json`: dados estruturados enviados para analise
   - `*_bedrock_prompt.txt`: prompt final montado pelo sistema
   - `*_ai.txt`: resposta do Bedrock quando a chamada funcionar, em formato mais executivo e objetivo
   - `*_ai_error.txt`: erro retornado pela integracao, quando houver falha

9. **Compatibilidade atual da integração Bedrock:**
   - suporta payload nativo para modelos `amazon.nova*`
   - suporta payload nativo para modelos `anthropic.*`
   - suporta payload nativo para modelos `openai.*`
   - suporta payload nativo para modelos `deepseek.*`
   - suporta payload nativo para modelos `meta.llama*`
   - suporta `modelId`, `inferenceProfileId` e ARN de inference profile para os providers acima
   - outros providers ainda podem exigir ajuste antes de funcionar com `InvokeModel`

10. **Sobrescrever profile e regiões AWS na execução:**
   ```bash
   python run.py --aws-profile dev-ciam --aws-region sa-east-1 --cost-explorer-region us-east-1 --bedrock-region us-east-1
   ```

11. **Exemplo combinando AWS e Bedrock:**
   ```bash
   python run.py --aws-profile dev-ciam --aws-region sa-east-1 --cost-explorer-region us-east-1 --bedrock-region us-east-1 --enable-bedrock
   ```

12. **Exemplo completo de execução usado no ambiente PRD CIAM:**
   ```bash
   python3 run.py --aws-profile prd-ciam --aws-region sa-east-1 --cost-explorer-region us-east-1 --bedrock-region us-east-1 --enable-bedrock --bedrock-model us.anthropic.claude-sonnet-4-6
   ```
   Este e o exemplo mais completo de execucao e representa o modelo que tem apresentado melhor resultado no momento para a analise via Bedrock neste ambiente.

13. **Pular a confirmação da planilha de eventos em automações:**
   ```bash
   python3 run.py --source cost-explorer --skip-calendar-confirmation
   ```
   Use essa opcao apenas quando houver outro controle operacional garantindo que a planilha `prompts/assets/Régua de Pushs_SMS Now Online.xlsx` esta atualizada ou quando a execucao nao depender dessa confirmacao interativa.

14. **Exemplos de execução por provider suportado:**
   Amazon Nova:
   ```bash
   python run.py --enable-bedrock --bedrock-model amazon.nova-pro-v1:0
   ```
   Anthropic com inference profile:
   ```bash
   python run.py --enable-bedrock --bedrock-model us.anthropic.claude-3-5-haiku-20241022-v1:0
   ```
   OpenAI:
   ```bash
   python run.py --enable-bedrock --bedrock-model openai.gpt-oss-120b-1:0
   ```
   DeepSeek:
   ```bash
   python run.py --enable-bedrock --bedrock-model deepseek.v3.2
   ```
   Meta Llama com inference profile:
   ```bash
   python run.py --enable-bedrock --bedrock-model us.meta.llama3-3-70b-instruct-v1:0
   ```

15. **Como listar modelos disponíveis no Bedrock:**
   Listar todos:
   ```bash
   aws bedrock list-foundation-models --region us-east-1
   ```
   Filtrar por provider:
   ```bash
   aws bedrock list-foundation-models --region us-east-1 --by-provider Anthropic
   aws bedrock list-foundation-models --region us-east-1 --by-provider Amazon
   aws bedrock list-foundation-models --region us-east-1 --by-provider OpenAI
   aws bedrock list-foundation-models --region us-east-1 --by-provider DeepSeek
   aws bedrock list-foundation-models --region us-east-1 --by-provider Meta
   ```
   Listar só IDs e status:
   ```bash
   aws bedrock list-foundation-models --region us-east-1 \
     --query 'modelSummaries[].{id:modelId,provider:providerName,status:modelLifecycle.status,inference:inferenceTypesSupported}' \
     --output table
   ```

16. **Como listar inference profiles disponíveis:**
   Um `inference profile` e uma forma de invocar certos modelos no Bedrock quando eles nao aceitam chamada direta por `modelId` sob o throughput padrao da conta.
   Na pratica, ele funciona como um identificador de acesso/roteamento gerenciado pela AWS para executar o modelo compativel naquele ambiente.

   ```bash
   aws bedrock list-inference-profiles --region us-east-1
   ```
   Listar só IDs e nomes:
   ```bash
   aws bedrock list-inference-profiles --region us-east-1 \
     --query 'inferenceProfileSummaries[].{id:inferenceProfileId,name:inferenceProfileName,status:status}' \
     --output table
   ```
   Filtrar Anthropic:
   ```bash
   aws bedrock list-inference-profiles --region us-east-1 \
     --query "inferenceProfileSummaries[?contains(inferenceProfileId, 'anthropic')].[inferenceProfileId,inferenceProfileName,status]" \
     --output table
   ```

17. **Quando usar `modelId` e quando usar `inferenceProfileId`:**
   - Use `modelId` direto quando o modelo suportar `ON_DEMAND`
   - Use `inferenceProfileId` ou ARN quando o modelo exigir `INFERENCE_PROFILE`
   - Se aparecer erro dizendo que `on-demand throughput isn’t supported`, troque para o `inferenceProfileId`
   - Em geral, modelos Anthropic mais novos no seu ambiente devem ser chamados por inference profile

18. **Relatório HTML interativo:**

   O projeto gera automaticamente `relatorio_custos_YYYY-MM-DD.html` com duas abas:

   - **Aba "Visão Geral"**: gráficos interativos de custos diários (Chart.js), tabelas de variação de serviços, top N serviços, evolução do SMS e top serviços por dia
   - **Aba "Análise IA"**: cards coloridos por classificação (Anomalia Real / Desvio Esperado / Efeito em Cascata), resumo executivo, drivers analisados e recomendações
   - O HTML é gerado sem análise de IA inicialmente; se o Bedrock estiver ativo e concluir, o HTML é regenerado com a aba de IA preenchida
   - O arquivo é independente (CSS e JS inline), apenas Chart.js é carregado via CDN

1. **Notas operacionais importantes:**
   - O relatório sempre gera `*_bedrock_payload.json` e `*_bedrock_prompt.txt`, mesmo sem chamar o Bedrock
   - Se a chamada ao modelo falhar, o processo salva `*_ai_error.txt` no `output`
   - A execucao agora gera `execucao_<timestamp>.log` em tempo real e `execucao_<timestamp>.json` com o resumo estruturado da execucao
   - Antes de iniciar a coleta, a execucao do `run.py` exige confirmacao interativa de que a planilha `prompts/assets/Régua de Pushs_SMS Now Online.xlsx` esta atualizada
   - Essa confirmacao pode ser pulada explicitamente com `--skip-calendar-confirmation`
   - `BEDROCK_MAX_TOKENS` aumenta o limite da resposta; isso pode aumentar custo se o modelo realmente usar mais tokens
   - O provider e o tipo de throughput suportado variam por modelo e por conta AWS
   - `--aws-region` controla a região do workload, usada para CloudWatch e descoberta de recursos
   - `--cost-explorer-region` controla a região do Cost Explorer; no seu cenário, normalmente use `us-east-1`
   - `--bedrock-region` controla a região do Bedrock; escolha uma região onde o modelo ou inference profile exista
   - Exemplo comum de operacao: workload em `sa-east-1`, Cost Explorer em `us-east-1`, Bedrock em `us-east-1`
   - Quando existir a planilha `prompts/assets/Régua de Pushs_SMS Now Online.xlsx`, o projeto pode usa-la como calendario de eventos/push do Claro TV+ para enriquecer correlacoes de negocio
   - Essa planilha deve ser usada apenas como contexto para aumento de plays, autenticacao, autorizacao e scaling agendado; ela nao deve ser tratada como evidencia direta de custo ou volume de AWS SMS
   - Variacoes de AWS End User Messaging/SMS NAO devem ser correlacionadas com eventos do Claro TV+; SMS e exclusivamente transacional (OTP, MFA, cadastro, reset de senha) e independente de audiencia
   - PDP neste ambiente significa Policy Decision Point (Ping Identity) — nunca expandir como "Plataforma de Distribuicao de Push"
   - LCU do ELB sobe como efeito derivado do trafego de EC2/EKS; quando ELB e EC2 sobem juntos em dia de evento, sao um efeito em cascata do mesmo driver, nao anomalias independentes
   - Transit Gateway e sinal fraco para correlacionar com eventos do Claro TV+ ou scaling de EKS
   - O enriquecimento automatico de contexto tenta inferir papeis de EC2/EKS por tags e buckets S3 por nome conhecido
   - Hoje ha heuristicas para Ping Directory com `Name` contendo `PD-`, nodegroups `ping-access-app`, `ping-pdp-app`, `ping-federate-app`, cluster `prd-sso-fachada`, buckets S3 conhecidos e streams Firehose conhecidos parametrizados no `src/config.py`
   - A correlacao de Firehose usa metricas como `IncomingRecords`, `IncomingBytes`, `DeliveryToS3.Bytes`, `DeliveryToS3.Records`, `DeliveryToS3.Success` e `DeliveryToS3.DataFreshness`, configuradas no `src/config.py`
   - A correlacao de Glue usa metricas como `glue.driver.aggregate.bytesRead`, `bytesWritten`, `elapsedTime`, `numCompletedStages`, `recordsRead` e `recordsWritten`, configuradas no `src/config.py`
   - Alem das metricas CloudWatch, o projeto coleta historico de execucoes via `glue:GetJobRuns` (API gratuita) para cada job candidato, retornando DPUs alocadas, duracao media, status e contagem de execucoes na janela de analise; isso permite distinguir reprocessamento de execucoes longas como causa da variabilidade de custo
   - Para S3, se um bucket nao tiver exatamente o filtro `all-objects`, o projeto tenta usar outro `MetricsConfiguration Id` disponivel antes de concluir que nao ha request metrics utilizaveis
   - A correlacao de ECR usa `RepositoryPullCount` para repositorios conhecidos do ambiente apenas como evidencia complementar de rollout, restart ou scale-out no EKS
   - A correlacao de AWS Backup usa `NumberOfBackupJobsCompleted`, `NumberOfRecoveryPointsCreated`, `BackupVaultBytes` e `NumberOfCopyJobsCompleted` como evidencia complementar para `EC2-Other`, snapshots e backup de S3
   - A correlacao de Elastic Load Balancing usa um nucleo enxuto de metricas por tipo de load balancer, como `RequestCount`, `ProcessedBytes`, `TargetResponseTime`, `HTTPCode_Target_4XX_Count`, `HTTPCode_Target_5XX_Count`, `ActiveFlowCount` e `NewFlowCount`, para enriquecer variacoes de LCU e trafego
   - `EC2 - Other` com `NatGateway-Bytes` agora deve usar correlacao direta com recursos NAT Gateway e metricas proprias de bytes/conexoes, em vez de cair sem recurso na regra generica
   - Buckets S3 conhecidos sem `AllRequests` continuam aparecendo no payload para explicitar o gap de observabilidade, mesmo quando outro bucket ja tem metrica
   - Para `CloudWatch Logs / DataScanned-Bytes`, o payload agora pode incluir metadados de queries (`query_id`, `query_definition_name`, `bytes_scanned`, `create_time`, `execution_origin`) para reduzir inferencias fracas
   - O NLB `prd-sso-ciam-privatelink` deve ser interpretado como trilha SOMENTE de autenticacao/login do Claro TV+; o trafego de PDP/autorizacao passa por outros load balancers do stack Ping
   - Picos de PDP e de autenticacao podem estar ligados a eventos de alta audiencia do Claro TV+; operacionalmente o ambiente costuma ser escalado cerca de 1 hora antes do inicio previsto desses eventos
   - Quando as tags forem pobres ou ausentes, ainda vale complementar o `PROJECT_CONTEXT.md` com o significado de negocio dos recursos

## Parametros essenciais do `config.py`

Nem toda variavel do `src/config.py` precisa ser ajustada no dia a dia. Abaixo estao as mais importantes para operacao e tuning.

### Janela e sensibilidade

- `ANALYSIS_DAYS`
  Quantos dias entram na janela consolidada do relatorio. O padrao atual e `7`.
- `OFFSET_DAYS`
  Quantos dias voltar a partir de hoje para evitar usar um dia ainda nao consolidado pela AWS. O padrao atual e `2`.
- `MIN_DAILY_COST_USD`
  Piso de custo diario para evitar tratar ruido muito pequeno como anomalia relevante.
- `MIN_PERCENT_VARIATION`
  Variacao percentual minima para considerar uma anomalia para enriquecimento.
- `TOP_N_ANOMALIES`
  Quantas anomalias relevantes seguem para enriquecimento e ranking interno.

Normalmente voce so mexe nesses parametros quando o relatorio estiver sensivel demais a ruido ou conservador demais.

### Bedrock

- `BEDROCK_MODEL_ID`
  Modelo padrao usado quando `--enable-bedrock` estiver ativo e nao houver override por CLI ou env var.
- `BEDROCK_MAX_TOKENS`
  Limite de resposta do modelo. Aumentar pode trazer mais detalhe, mas tambem mais custo e latencia.
- `BEDROCK_TEMPERATURE`
  Controla o grau de variacao da resposta. O padrao baixo favorece analises mais consistentes.
- `BEDROCK_MAX_ANALYSIS_ANOMALIES`
  Quantas anomalias entram no payload compacto enviado ao Bedrock.

### Correlacao e descoberta

- `MAX_CANDIDATE_RESOURCES`
  Limite bruto de candidatos avaliados por descoberta antes do ranking final.
- `MAX_RESOURCES_PER_ANOMALY`
  Quantos recursos finais manter por anomalia na maioria dos casos.
- `MAX_S3_RESOURCES_PER_ANOMALY`
  Reserva maior para S3 quando houver varios buckets candidatos.
- `EKS_PRIMARY_SCALING_METRIC`
  Metrica principal para leitura de scaling em EKS. O padrao e `GroupTotalInstances`.

### CloudTrail e queries

- `LOGS_QUERY_METADATA_MAX_QUERIES`
  Quantas queries recentes de CloudWatch Logs anexar por log group.
- `ATHENA_QUERY_METADATA_MAX_QUERIES`
  Quantas queries Athena relevantes anexar por bucket candidato.
- `ATHENA_QUERY_METADATA_MAX_WORKGROUPS`
  Quantos workgroups Athena varrer no enriquecimento.
- `CLOUDTRAIL_LOOKUP_WINDOW_HOURS`
  Janela de busca de CloudTrail ao redor de queries de Athena e CloudWatch Logs.
- `CLOUDTRAIL_MAX_MATCHES_PER_QUERY`
  Quantos matches de CloudTrail guardar por query enriquecida.

### CloudTrail seletivo para S3

Esses parametros controlam o enriquecimento novo de CloudTrail para anomalias de S3. Na maioria dos casos, deixe o padrao.

- `S3_CLOUDTRAIL_LOOKUP_MAX_EVENTS`
  Teto bruto de eventos lidos por bucket antes de encerrar a busca.
- `S3_CLOUDTRAIL_MAX_MATCHES`
  Quantos eventos exemplares entram no resumo final do bucket.
- `S3_CLOUDTRAIL_MAX_SUMMARY_ITEMS`
  Quantos itens mostrar em rankings como top eventos e top atores.
- `S3_CLOUDTRAIL_TODAY_TO_AVG_RATIO`
  Gatilho minimo para consultar CloudTrail.
  Exemplo: `1.05` significa consultar quando o valor de hoje estiver pelo menos 5% acima da media.
- `S3_CLOUDTRAIL_PEAK_LOOKBACK_DAYS`
  Permite olhar tambem o `peak_date` recente de `AllRequests` quando ele ocorreu alguns dias antes do dia de referencia.

Quando faz sentido ajustar:

- se houver muito ruido no resumo de CloudTrail, reduza `S3_CLOUDTRAIL_LOOKUP_MAX_EVENTS` ou `S3_CLOUDTRAIL_MAX_MATCHES`
- se o lookup estiver conservador demais, reduza um pouco `S3_CLOUDTRAIL_TODAY_TO_AVG_RATIO`
- se o spike de requests costuma acontecer um pouco antes do custo, aumente `S3_CLOUDTRAIL_PEAK_LOOKBACK_DAYS` com cuidado

Os relatórios serão salvos em `output/YYYY-MM-DD/`, agrupando todos os artefatos da execução do dia na mesma pasta.

---

## Arquivos gerados

Em uma execução típica, o projeto gera artefatos como:

```file system
output/2026-04-09/relatorio_custos_2026-04-09.txt
output/2026-04-09/relatorio_custos_2026-04-09.pdf
output/2026-04-09/relatorio_custos_2026-04-09.xlsx
output/2026-04-09/relatorio_custos_2026-04-09.html
output/2026-04-09/execucao_2026-04-09T08-47-11.log
output/2026-04-09/execucao_2026-04-09T08-47-11.json
output/2026-04-09/relatorio_custos_2026-04-09_bedrock_context.txt
output/2026-04-09/relatorio_custos_2026-04-09_bedrock_payload.json
output/2026-04-09/relatorio_custos_2026-04-09_bedrock_prompt.txt
output/2026-04-09/relatorio_custos_2026-04-09_ai.txt
output/2026-04-09/relatorio_custos_2026-04-09_ai.pdf
output/2026-04-09/relatorio_custos_2026-04-09_ai_meta.json
```

Observações:

- `relatorio_custos_YYYY-MM-DD.html` é gerado em toda execução com duas abas interativas: visão de custos com gráficos Chart.js e análise IA com cards coloridos por classificação; quando o Bedrock conclui, o HTML é regenerado com a aba de IA preenchida
- `relatorio_custos_YYYY-MM-DD.pdf` agora é gerado junto com o TXT principal e preserva o texto original, adicionando gráficos visuais de apoio para leitura mais intuitiva
- `*_ai.txt`, `*_ai.pdf` e `*_ai_meta.json` só existem quando a análise Bedrock está habilitada e conclui a execução
- `*_ai_error.txt` pode ser gerado quando houver falha na chamada ao modelo
- `execucao_<timestamp>.log` é atualizado durante a execucao e ajuda a identificar a etapa exata de lentidao ou falha
- `execucao_<timestamp>.json` consolida status, duracao e etapas mesmo quando o relatorio principal nao chega a ser gerado
- os arquivos ficam agrupados por data para facilitar comparação e histórico
- quando `FINOPS_SNS_TOPIC_ARN` e `FINOPS_S3_BUCKET` estão configurados, o HTML do diário é automaticamente enviado por e-mail via SNS com link S3 válido por **30 dias**; para o mensal, os dois CSVs são enviados da mesma forma

---

## 🧪 Testes Unitários

O projeto possui testes unitários organizados em `tests/unit/`, cobrindo os principais módulos de análise e correlação.

### Estrutura

```
tests/
├── conftest.py                               # Fixtures compartilhadas (dataframes de exemplo, etc.)
├── unit/
│   ├── analyzers/
│   │   ├── test_anomaly_detection.py          # 31 testes: timeseries, anomalias, filtros, enriquecimentos
│   │   └── test_cost_analysis.py              # Testes de analise de custo consolidada
│   ├── mappings/
│   │   └── test_correlation_rules.py          # Testes de regras de correlacao
│   └── test_config.py                        # Testes de validacao de configuracao
└── integration/                               # Testes de integracao (futuro)
```

### Funcionalidades testadas

`tests/unit/analyzers/test_anomaly_detection.py` cobre as 6 funcoes publicas de `src/analyzers/anomaly_detection.py`:

| Classe de teste | O que testa |
|---|---|
| `TestBuildUsageTypeTimeseries` | Normalizacao e agrupamento de series temporais por Data/Servico/UsageType |
| `TestCalculateAnomalies` | Calculo de cost_today, avg_7d, delta_usd, delta_pct |
| `TestFilterRelevantAnomalies` | Filtragem por thresholds minimos (custo, variacao, top N) |
| `TestEnrichComplementaryUsageTypes` | Enriquecimento com usage types complementares (S3, SMS) |
| `TestEnrichApiOperations` | Enriquecimento com API operations do Cost Explorer |
| `TestEnrichS3TierChangeAnalysis` | Analise de evidencia de mudanca de classe/tier S3 |

### Como executar

```bash
# Instalar dependencias de desenvolvimento
pip install pytest

# Executar todos os testes unitarios
pytest tests/unit/ -v

# Executar apenas testes de anomaly_detection
pytest tests/unit/analyzers/test_anomaly_detection.py -v

# Executar com cobertura
pytest tests/unit/ --cov=src/ --cov-report=term-missing
```

### Regras de manutencao

- Toda funcao publica em `src/analyzers/anomaly_detection.py` deve ter testes correspondentes.
- Testes usam `pytest` e fixtures do `conftest.py` para dados de exemplo.
- Nao acoplar testes a chamadas reais de AWS; usar dataframes artificiais.
- Ao adicionar novo enriquecimento ou funcao de analise, criar classe de teste equivalente.
- Antes de finalizar qualquer mudanca nos analisadores, executar `pytest tests/unit/ -v` para garantir que nada quebrou.

---

## Export mensal com todos os serviços e somente PDP

Para gerar os dois CSVs mensais e já acionar a análise mensal automaticamente:

```bash
# Execução local com perfil AWS CLI
python3 scripts/export_monthly_costs.py --month 2026-03 --aws-profile prd-ciam --cost-explorer-region us-east-1
```

Em EC2 com IAM role (sem perfil), omita `--aws-profile` — boto3 usa automaticamente as credenciais da role:

```bash
python3 scripts/export_monthly_costs.py --month 2026-03 --cost-explorer-region us-east-1
```

Com análise via Bedrock (EC2 com role):

```bash
python3 scripts/export_monthly_costs.py --month 2026-03 \
  --cost-explorer-region us-east-1 \
  --enable-bedrock --bedrock-region us-east-1 \
  --bedrock-model us.anthropic.claude-sonnet-4-6
```

Com análise via Bedrock (local com perfil):

```bash
python3 scripts/export_monthly_costs.py --month 2026-03 \
  --aws-profile prd-ciam --cost-explorer-region us-east-1 \
  --enable-bedrock --bedrock-region us-east-1 \
  --bedrock-model us.anthropic.claude-sonnet-4-6
```

Para gerar apenas os CSVs sem acionar a análise:

```bash
python3 scripts/export_monthly_costs.py --month 2026-03 --aws-profile prd-ciam --cost-explorer-region us-east-1 --skip-analysis
```

Arquivos gerados:

```file system
export_monthly/costs-prd-ciam-todos-servicos-2026-03.csv
export_monthly/costs-prd-ciam-so-pdp-2026-03.csv
output/monthly/relatorio_mensal_2026-03.txt
```

Esse script usa o filtro de tag `aws:autoscaling:groupName` para:
- gerar um arquivo com todos os serviços sem filtro
- incluir apenas os grupos do PDP no arquivo `so-pdp`
- ao concluir os CSVs, chamar `generate_monthly_analysis.py` automaticamente com os mesmos parâmetros de perfil e mês

### Notificação por e-mail via SNS

Ao passar `--sns-topic-arn` e `--s3-bucket`, o script faz upload dos arquivos para S3 e envia e-mail via SNS com links de download válidos por **30 dias**.

Estrutura dos arquivos no S3: `{prefix}/YYYY/MM/DD/HHmm/arquivo`

Arquivos enviados:

- **Diário**: apenas o HTML interativo (`relatorio_custos_YYYY-MM-DD.html`)
- **Mensal**: apenas os dois CSVs:
  - `costs-prd-ciam-todos-servicos-YYYY-MM.csv`
  - `costs-prd-ciam-so-pdp-YYYY-MM.csv`

```bash
python3 scripts/export_monthly_costs.py --month 2026-04 \
  --cost-explorer-region us-east-1 \
  --enable-bedrock --bedrock-region us-east-1 \
  --bedrock-model us.anthropic.claude-sonnet-4-6 \
  --sns-topic-arn arn:aws:sns:us-east-1:123456789012:finops-relatorios \
  --s3-bucket meu-bucket-finops \
  --s3-prefix finops/relatorios/mensal
```

### Planilha de eventos (Google Drive)

A planilha `prompts/assets/Régua de Pushs_SMS Now Online.xlsx` é provida pelo time do Claro TV+ via Google Drive e deve estar sempre atualizada antes de gerar o relatório.

#### Setup de credenciais (uma vez, na máquina local)

```bash
# Autenticar — abre o navegador para login com sua conta Google pessoal
python3 scripts/setup_gdrive_auth.py --credentials ./client_secret.json
```

Isso gera `token.json` na raiz do projeto. Os dois arquivos necessários são:

| Arquivo | Onde obter |
| --- | --- |
| `client_secret.json` | Baixar do Google Cloud Console (OAuth2 → App para computador) |
| `token.json` | Gerado pelo `setup_gdrive_auth.py` na primeira autenticação |

Ambos ficam na **raiz do projeto** e estão no `.gitignore` — nunca devem ser versionados.

#### Uso local

Ao rodar `run.py`, o sistema pergunta se a planilha está atualizada:

- Resposta `s` → continua com a planilha existente
- Resposta `N` ou Enter → baixa automaticamente do Google Drive e continua

Para baixar manualmente a qualquer momento:

```bash
python3 scripts/download_calendar.py \
  --file-id     "1dS7E1dlskOqc1pXuBjpkQ7umfwAORAcj9BGkWCkZ5Gg" \
  --dest        "prompts/assets/Régua de Pushs_SMS Now Online.xlsx" \
  --credentials "./client_secret.json" \
  --token       "./token.json"
```

#### Uso na EC2 (cron)

Copie os dois arquivos de credenciais para a **raiz do projeto na EC2**:

```bash
scp client_secret.json ec2-user@<ip-da-ec2>:/caminho/do/projeto/
scp token.json         ec2-user@<ip-da-ec2>:/caminho/do/projeto/
```

O `cron_daily.sh` executa o download automaticamente antes de cada relatório — nenhuma configuração adicional é necessária além dos dois arquivos acima.

---

### Agendamento via cron (EC2 com IAM role)

Use os wrappers `scripts/cron_daily.sh` e `scripts/cron_monthly.sh` — eles ativam o virtualenv, instalam dependências, baixam a planilha do Google Drive e constroem o comando automaticamente.

#### Configuração do cron_daily.sh

**1. Edite as variáveis no topo do wrapper:**

```bash
# scripts/cron_daily.sh
PROJECT_DIR="/caminho/para/relatorio_aws_finops_ai"
AWS_REGION="sa-east-1"
COST_EXPLORER_REGION="us-east-1"
BEDROCK_REGION="us-east-1"
BEDROCK_MODEL="us.anthropic.claude-sonnet-4-6"
FINOPS_SNS_TOPIC_ARN="arn:aws:sns:us-east-1:123456789012:finops-relatorios"
FINOPS_S3_BUCKET="meu-bucket-finops"
GDRIVE_CREDENTIALS="$PROJECT_DIR/client_secret.json"
GDRIVE_TOKEN="$PROJECT_DIR/token.json"
```

**2. Adicione ao crontab (`crontab -e`):**

```cron
# Relatório diário — todo dia às 08h horário de Brasília (11h UTC)
0 11 * * * /caminho/para/relatorio_aws_finops_ai/scripts/cron_daily.sh >> /caminho/para/relatorio_aws_finops_ai/output/cron_daily.log 2>&1

# Relatório mensal — todo dia 5 do mês às 08h horário de Brasília (11h UTC)
0 11 5 * * /caminho/para/relatorio_aws_finops_ai/scripts/cron_monthly.sh >> /caminho/para/relatorio_aws_finops_ai/output/cron_monthly.log 2>&1
```

**Uso manual do wrapper mensal com mês específico:**

```bash
bash scripts/cron_monthly.sh 2026-03
```

Observações:

- o `cron_daily.sh` baixa a planilha do Google Drive antes de cada execução e aborta se o download falhar
- em caso de falha em qualquer etapa, um alerta é enviado automaticamente via SNS para o mesmo tópico do relatório
- os wrappers calculam o mês anterior automaticamente quando não é passado argumento
- sem `AWS_PROFILE` preenchido, boto3 usa a role IAM da EC2
- `FINOPS_SNS_TOPIC_ARN` e `FINOPS_S3_BUCKET` vazios desabilitam o envio SNS
- logs separados por tipo: `cron_daily.log` e `cron_monthly.log`
- ajuste o timezone da EC2 se necessário: `sudo timedatectl set-timezone America/Sao_Paulo`

---

## Análise mensal consolidada

Para gerar um relatório TXT mensal com correlação de eventos e anomalias recorrentes, use:

```bash
python3 scripts/generate_monthly_analysis.py --month 2026-04 --aws-profile prd-ciam
```

Com análise via Bedrock:

```bash
python3 scripts/generate_monthly_analysis.py --month 2026-04 \
  --aws-profile prd-ciam --bedrock-region us-east-1 \
  --bedrock-model us.anthropic.claude-sonnet-4-6 --enable-bedrock
```

Pré-requisito: os CSVs mensais devem existir em `export_monthly/` (gerados pelo `export_monthly_costs.py`).

Fontes usadas:

- `export_monthly/costs-prd-ciam-todos-servicos-YYYY-MM.csv`
- `export_monthly/costs-prd-ciam-so-pdp-YYYY-MM.csv`
- `output/YYYY-MM-DD/*_bedrock_payload.json` — anomalias dos dias com análise diária
- `prompts/assets/Régua de Pushs_SMS Now Online.xlsx` — calendário de eventos

Arquivo gerado:

```file system
output/monthly/relatorio_mensal_YYYY-MM.txt
```

O relatório inclui:

- Custo total, PDP e média diária do mês
- Top serviços com barra visual de proporção
- Tabela diária: custo × PDP × intensidade do evento (◆ = dia com GGG)
- Anomalias recorrentes — serviços que apareceram em múltiplos dias de referência
- Dias sem análise diária (gaps de cobertura de payload)
- Narrativa executiva via Bedrock (quando `--enable-bedrock` estiver ativo)
