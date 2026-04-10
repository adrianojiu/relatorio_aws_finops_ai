# Contexto do Projeto
se você é uma IA e esta lendo isso, estas são as definições de contexto deste projeto, são importantes para entender definições ja tabalhadas e decididas, este arquivo pode te ajuda a entender melhor o projeto, alem do codigo e readme.
Este arquivo consolida o contexto operacional, as regras de implementacao e as decisoes praticas do projeto `local-relatorio-custo-aws-diario-prd-ciam`.

O objetivo e evitar perda de contexto entre sessoes e facilitar manutencao futura.

## Regras de Manutencao do Contexto

Este arquivo deve ser consultado antes de propor ou implementar mudancas relevantes no projeto.

Sempre que houver alteracao de:
- especificacao funcional
- regra de correlacao
- formato de relatorio
- convencao operacional
- comportamento da analise Bedrock
- estrategia de observabilidade

deve-se atualizar este arquivo para manter o contexto do projeto sincronizado.

Se houver divergencia entre implementacao e este arquivo:
- a implementacao deve ser revisada
- e este arquivo deve ser atualizado se a regra correta tiver mudado

## Regras de Parametrizacao

Evitar hardcoded sempre que possivel.

Preferencias do projeto:
- tudo que for configuracao executavel, lista de recursos conhecidos, filtro, limite, nome relevante ou comportamento ajustavel deve ser parametrizado
- a preferencia de parametrizacao tecnica e no `config.py`
- contexto de negocio, interpretacao operacional e decisoes historicas devem viver neste `PROJECT_CONTEXT.md`
- descoberta tecnica dinamica deve continuar vindo da AWS quando fizer sentido

Exemplos que devem preferencialmente ficar em `config.py`:
- buckets conhecidos
- filas conhecidas
- filtros de metricas
- limites de analise
- nomes ou roles de recursos conhecidos

Exemplos que devem preferencialmente ficar neste `PROJECT_CONTEXT.md`:
- contexto operacional do ambiente
- explicacoes de causalidade
- comportamento esperado de eventos
- regras interpretativas para Bedrock

Nao espalhar definicoes de negocio em varios arquivos quando elas puderem ficar centralizadas neste documento.

## Regra de Documentacao

Sempre que houver mudanca relevante em:
- uso do projeto
- parametros de execucao
- arquivos gerados
- fluxo operacional
- modelos suportados
- comportamento do Bedrock
- estrategias de correlacao e observabilidade

o `README.md` deve ser revisado e atualizado.

O projeto deve manter coerencia entre:
- codigo
- `README.md`
- `AGENTS.md`
- `PROJECT_CONTEXT.md`

## Objetivo

Gerar um relatorio diario de custos AWS com:
- consolidacao de custos da janela analisada
- identificacao de anomalias por `service` e `usage_type`
- correlacao com recursos AWS reais
- enriquecimento com metricas operacionais
- analise causal via Amazon Bedrock

Saidas principais:
- `output/YYYY-MM-DD/relatorio_custos_YYYY-MM-DD.txt`
- `output/YYYY-MM-DD/relatorio_custos_YYYY-MM-DD.xlsx`
- `output/YYYY-MM-DD/relatorio_custos_YYYY-MM-DD_bedrock_payload.json`
- `output/YYYY-MM-DD/relatorio_custos_YYYY-MM-DD_bedrock_prompt.txt`
- `output/YYYY-MM-DD/relatorio_custos_YYYY-MM-DD_bedrock_context.txt`
- `output/YYYY-MM-DD/relatorio_custos_YYYY-MM-DD_ai.txt`
- `output/YYYY-MM-DD/relatorio_custos_YYYY-MM-DD_ai_meta.json`

## Regioes AWS

O projeto trata regioes separadamente.

- `WORKLOAD_REGION`
  Uso: recursos operacionais do workload, CloudWatch e descoberta de recursos.
- `COST_EXPLORER_REGION`
  Uso: Cost Explorer.
- `BEDROCK_REGION`
  Uso: Bedrock.

No caso deste ambiente:
- workloads podem estar em `sa-east-1`
- Cost Explorer costuma ser usado em `us-east-1`
- Bedrock costuma ser usado em `us-east-1`

Nao voltar para uma unica regiao compartilhada para tudo.

## Perfis e Conta AWS

- O projeto aceita `--aws-profile`.
- O cabecalho do TXT tenta mostrar `account alias + account id`.
- Se o alias da conta nao estiver disponivel, o fallback deve usar `AWS_PROFILE + account id`.

Exemplo esperado:
- `Custo de Cloud AWS conta prd-ciam (123456789012)`

## Janela de Analise

- `ANALYSIS_DAYS = 7`
- `OFFSET_DAYS = 2`

Importante:
- o relatorio nao analisa "hoje"
- ele analisa o ultimo dia consolidado da AWS, com atraso de 2 dias

Na resposta da IA, preferir:
- `dia de referencia`
- ou a data absoluta

Evitar:
- `anchor day`
- `hoje`

## Estrutura do Relatorio TXT

O TXT principal deve ficar limpo e orientado a leitura humana.

Deve conter:
- cabecalho com conta AWS
- custo medio por dia
- custos por dia na janela com grafico textual
- variacao media
- servicos que aumentaram custo
- top 5 servicos que reduziram custo
- top N servicos do dia de referencia
- bloco de SMS dos ultimos 7 dias
- top 5 servicos por dia na janela

Nao deve conter:
- dump tecnico completo de correlacao Bedrock

Esse contexto tecnico foi movido para:
- `*_bedrock_context.txt`

## Arquivos de Bedrock

Separacao atual:
- TXT principal: foco executivo
- `*_bedrock_context.txt`: apoio tecnico de correlacao
- `*_bedrock_payload.json`: payload real enviado para a IA
- `*_bedrock_prompt.txt`: prompt final gerado
- `*_ai.txt`: resposta da IA
- `*_ai_meta.json`: metadados da resposta

Essa separacao deve ser mantida.

Os artefatos de cada execucao devem ficar agrupados em uma subpasta por data dentro de `output/`, para evitar poluicao da raiz de saida.

## Regras Gerais de Implementacao

### 1. Evitar hardcode desnecessario

Sempre que possivel:
- colocar configuracao executavel no `config.py`
- nao espalhar listas de buckets, filas, filtros e nomes no codigo

Exemplos:
- contexto de buckets S3
- contexto de filas SQS
- metricas priorizadas
- filtros de request metrics

### 2. Se for contexto de negocio, preferir documentacao

Preferir `PROJECT_CONTEXT.md` para:
- contexto operacional
- contexto de negocio
- excecoes operacionais
- explicacoes de causalidade

Preferir `config.py` para:
- buckets conhecidos
- filas conhecidas
- filtros de metricas

### 3. Se for descoberta tecnica, preferir AWS

Preferir obter automaticamente da AWS:
- tags EC2
- `eks:cluster-name`
- `eks:nodegroup-name`
- account id
- account alias
- regiao real do bucket S3
- configuracao de metricas de bucket S3

## Regras de Analise de EKS / EC2

Para workloads EKS:
- nao focar em `NetworkIn` / `NetworkOut` como explicacao principal
- instancias de EKS sao efemeras
- o que importa mais e quantas instancias foram usadas e por quanto tempo
- picos de PDP frequentemente estao ligados a eventos de alta audiencia do Claro TV+
- normalmente o ambiente e escalado cerca de 1 hora antes do inicio previsto desses eventos
- a grade de eventos do Claro TV+ e uma fonte de correlacao de negocio valiosa para explicar aumentos de autenticacao/autorizacao
- a regua de push/eventos do Claro TV+ pode ser usada como calendario de negocio para correlacionar aumento de plays e scaling agendado
- essa regua nao deve ser usada como evidencia direta de custo ou contagem de AWS End User Messaging/SMS

Prioridade de leitura para EKS:
1. `GroupTotalInstances`
2. `GroupDesiredCapacity`
3. `GroupInServiceInstances`

O prompt deve orientar a IA a usar:
- `GroupTotalInstances` como principal evidencia de scaling
- `min_value` e `peak_value` para descrever faixa real observada

Evitar resumos pobres como:
- `10 -> 9`
- `10 fixo`

Quando houver oscilacao real na janela, preferir:
- `faixa observada: 8 a 10`
- `faixa observada: 19 a 27`

## Regras de Ping Directory

Contexto correto:
- `primary`, `secondary` e `ternary` atendem o trafego principal
- `quaternary` fica fora do balanceamento
- `quaternary` executa backup, relatorios e limpeza

Consequencias:
- nao tratar `quaternary` como explicacao principal para compute de EKS
- nao tratar `NetworkOut` alto da `quaternary` como anomalia por si so quando o contexto indicar backup

## Regras de S3

### Objetivo atual

O objetivo atual e conseguir identificar o bucket associado ao pico usando:
- `AllRequests`

Por decisao atual do projeto:
- simplificar request metrics para `AllRequests`
- nao depender neste momento de `GetRequests`, `PutRequests`, `ListRequests` etc.

### Coleta de S3

A coleta de S3 deve:
1. listar buckets
2. descobrir a regiao real do bucket com `get_bucket_location`
3. descobrir o `MetricsConfiguration Id` do bucket
4. usar esse `FilterId` na consulta CloudWatch
5. consultar o CloudWatch na regiao real do bucket

Se o bucket nao tiver exatamente `all-objects`, o projeto deve tentar qualquer outro `MetricsConfiguration Id` disponivel antes de concluir que nao ha request metrics utilizaveis.

Foi identificado um bug historico:
- `s3_request_filter_id` estava em `derived_context`
- mas a query procurava esse campo apenas no topo do recurso

Isso foi corrigido.

Quando houver pelo menos um bucket com metrica, os buckets conhecidos sem metrica ainda devem permanecer visiveis no payload para explicitar o gap de observabilidade. Eles nao devem sumir do contexto.

Na descoberta de S3, buckets conhecidos do `config.py` devem ser priorizados antes do corte por `MAX_CANDIDATE_RESOURCES`, para evitar que buckets importantes do ambiente fiquem de fora apenas por ordem da listagem.

### Limitacoes importantes

`AllRequests` so existe para buckets que tenham request metrics configurada.

Logo:
- buckets sem `all-objects` ou filtro equivalente nao terao `AllRequests`
- isso nao significa falha do codigo automaticamente

### Interpretacao correta da IA para S3

A IA:
- nao deve usar apenas tamanho do bucket
- nao deve usar apenas numero de objetos
- nao deve usar apenas contexto operacional
- nao deve usar score interno como prova

Se um bucket tiver `AllRequests`:
- ele pode virar candidato forte

Mas so deve ser tratado como causador do spike se:
- a data do pico de requests coincidir com a data do spike de custo
- ou houver aumento material exatamente naquela data

Se so um bucket estiver instrumentado e os outros nao:
- tratar como `candidato principal`
- nao tratar como `causa confirmada`

Com apenas `AllRequests`, a IA nao deve afirmar:
- `PUT`
- `GET`
- `LIST`
- `COPY`
- `DELETE`

Ela deve falar apenas em:
- `aumento de requisicoes`

### Recomendacao padrao de observabilidade S3

Quando buckets candidatos relevantes nao tiverem `AllRequests`:
- recomendar habilitar `S3 Request Metrics`
- com filtro de bucket inteiro, por exemplo `all-objects`

## Regras de GuardDuty

Existe regra especifica para:
- `SAE1-PaidS3DataEventsAnalyzed`

Essa anomalia deve ser correlacionada com buckets S3.

Mas:
- se nao houver `AllRequests`, nao concluir bucket lider com alta confianca
- se houver `AllRequests`, comparar a data do spike do bucket com a data do spike de custo

Correlacoes com scaling de EKS, ingestao de logs ou outros servicos devem ser tratadas como contexto secundario, nao como explicacao principal, quando o bucket lider com requests estiver claramente identificado.

## Regras de CloudWatch Logs / DataScanned-Bytes

Para `DataScanned-Bytes`, o projeto deve enriquecer o payload com metadados objetivos de query sempre que possivel:
- `query_id`
- `query_definition_id`
- `query_definition_name`
- `log_groups`
- `bytes_scanned`
- `create_time`
- `execution_origin`

Importante:
- a API pode nao permitir concluir se a query foi manual, agendada ou disparada por automacao
- quando isso acontecer, `execution_origin` deve permanecer `unknown`
- nao relacionar `DataScanned-Bytes` com GuardDuty sem evidencia direta nas queries ou no payload
- metrica de ingestao (`IncomingBytes`) sozinha nao prova investigacao, dashboard ou consulta

## Regras de SMS / End User Messaging

SMS deve ser apoiado por filas SQS conhecidas, configuradas em `config.py`.

Filas atuais:
- `prd-sso-fachada-digital-id-sms-mse`
- `prd-sso-fachada-digital-id-sms-rtdm`
- `prd-sso-fachada-digital-id-sms-sns`
- `prd-sso-fachada-digital-id-whatsapp`

Metricas SQS importantes:
- `NumberOfMessagesSent`
- `NumberOfMessagesReceived`
- `ApproximateNumberOfMessagesVisible`
- `ApproximateAgeOfOldestMessage`

Leitura esperada:
- `Sent` e `Received` = evidencia principal de volume
- `Visible` e `AgeOfOldestMessage` = backlog ou degradacao

## Prompt e Conclusao da IA

O prompt deve orientar a IA a:
- nao inventar causalidade sem evidencia
- separar hipotese forte de hipotese fraca
- usar data absoluta
- fechar a resposta com `ANALISE CONCLUIDA`

O programa deve avisar no shell se:
- o texto da IA nao terminar com `ANALISE CONCLUIDA`

Isso ja foi implementado.

## Modelos Bedrock

O projeto suporta hoje, via `InvokeModel`, pelo menos:
- Anthropic
- Amazon Nova
- OpenAI
- DeepSeek
- Meta Llama

Mas o modelo padrao atual esta em `config.py`.

Importante:
- alguns modelos exigem `inference profile`
- Anthropic ativo em Bedrock frequentemente precisa de `us.anthropic...` ou `global.anthropic...`

## Convencoes Operacionais Importantes

### Buckets conhecidos

Ja mapeados no `config.py`:
- `prd-ciam-logs`
- `prd-sso-ciam-pingdirectory`
- `prd-ping-federate-logs-raw`

### Filas conhecidas

Ja mapeadas no `config.py`:
- `prd-sso-fachada-digital-id-sms-mse`
- `prd-sso-fachada-digital-id-sms-rtdm`
- `prd-sso-fachada-digital-id-sms-sns`
- `prd-sso-fachada-digital-id-whatsapp`

### Firehose streams conhecidos

Ja mapeados no `config.py`:
- `prd-sso-fachada-firehose-s3`
  Uso: API do motor de regras
- `prd-sso-fachada-reset-firehose-s3`
  Uso: API de reset
- `prd-sso-fachada-sms-sender-logs-firehose-s3`
  Uso: API de envio de SMS

Metricas de Firehose priorizadas para correlacao:
- `IncomingRecords`
- `IncomingBytes`
- `DeliveryToS3.Records`
- `DeliveryToS3.Bytes`
- `DeliveryToS3.Success`
- `DeliveryToS3.DataFreshness`

Metricas de Glue priorizadas para correlacao:
- `glue.driver.aggregate.bytesRead`
- `glue.driver.aggregate.bytesWritten`
- `glue.driver.aggregate.elapsedTime`
- `glue.driver.aggregate.numCompletedStages`
- `glue.driver.aggregate.recordsRead`
- `glue.driver.aggregate.recordsWritten`

### Repositorios ECR conhecidos

Ja mapeados no `config.py`:
- `pingidentity/pingaccess`
  Uso: imagens de Ping Access e PDP no EKS
- `pingidentity/pingfederate`
  Uso: imagens de Ping Federate no EKS
- `prd-sso-fachada-identidade-orquestrador-san`
  Uso: imagens da API do motor de regras no EKS
- `prd-sso-fachada-identidade-sms-sender`
  Uso: imagens da API de envio de SMS no EKS

Metricas de ECR priorizadas para correlacao:
- `RepositoryPullCount`

Uso esperado:
- ECR deve entrar apenas como evidencia complementar para EKS
- aumento de pulls pode reforcar hipoteses de rollout, restart ou scale-out
- ECR nao deve ser tratado como causa principal isolada de custo

### AWS Backup

Metricas priorizadas para correlacao complementar:
- `NumberOfBackupJobsCompleted`
- `NumberOfRecoveryPointsCreated`
- `BackupVaultBytes`
- `NumberOfCopyJobsCompleted`

Uso esperado:
- AWS Backup deve entrar como evidencia complementar para `EC2-Other`, snapshots e backup de S3
- pode ajudar a identificar aumento de jobs, recovery points, volume armazenado e copias
- nao deve ser tratado como causa principal isolada sem coincidencia temporal com a anomalia
- AWS Backup nao deve ser anexado em usage types de rede como `NatGateway-Bytes`, `TransitGateway-Bytes` ou `DataTransfer`
- o anexo complementar de AWS Backup deve ser restrito a usage types com cara de snapshot/backup/recovery point

### Cloudwatch

No inicio do mês, normalmente no dia 2, sempre é executado um querie nos logs do cloudwatch para coletar consumo de apis e enviar para o time de finops.
Na primeira semana do mês não tem um dia especifico, tambem pode acontecer algumas queries nos logs para gerar dados para a reunião de MBR dos gestores.

### NAT Gateway

Usage type `NatGateway-Bytes` nao deve cair na regra generica de `EC2-Other` sem recursos. Deve usar descoberta direta de NAT Gateway com metricas proprias de bytes e conexoes.

### Load Balancers conhecidos

Ja mapeados no `config.py`:
- `prd-sso-ciam-privatelink`
  Tipo: network | Uso: SOMENTE integracao de autenticacao/login do Claro TV+; nao carrega PDP/autorizacao
- `prd-grupoPD-ldap`
  Tipo: network | Uso: leitura LDAP do Ping Directory
- `prd-grupoPD-alb`
  Tipo: application | Uso: Ping Directory Administrative Console
- `prd-grupopd-primary-alb`
  Tipo: application | Uso: gravacao e alteracao na base do primario
- `prd-grupopd-secondary-alb`
  Tipo: application | Uso: gravacao e alteracao na base do secundario quando o primario esta fora
- `k8s-prdciam-f6d5697eb4`
  Tipo: application | Uso: Ping Federate, Access e PDP no EKS
- `k8s-prdssofachada-92ddf9f6c1`
  Tipo: application | Uso: APIs do fachada no EKS
- `k8s-prdciamexternal-3fba2b5dc7`
  Tipo: application | Uso: cluster ping external

Metricas de Load Balancer priorizadas para correlacao:
- `RequestCount`
- `ProcessedBytes`
- `TargetResponseTime`
- `HTTPCode_Target_4XX_Count`
- `HTTPCode_Target_5XX_Count`
- `ActiveFlowCount`
- `NewFlowCount`

### Clusters conhecidos

- `prd-sso-ciam`
  Uso: Ping Access, Ping Federate, PDP
- `prd-sso-fachada`
  Uso: APIs de credenciais e orquestracao

### Nodegroups e ASGs conhecidos

- `eks-ping-access*`
- `eks-ping-pdp*`
- `eks-ping-federate*`
- `eks-app-*` com `eks:cluster-name = prd-sso-fachada`

## Como evoluir o projeto sem perder coerencia

Antes de mudar algo, verificar:
1. isso e configuracao ou descoberta?
2. isso impacta relatorio humano, payload Bedrock, ou ambos?
3. a IA vai ganhar evidencia real ou so contexto narrativo?

Preferencias do projeto:
- relatorio TXT principal limpo
- detalhes tecnicos em arquivo separado
- contexto de negocio em `PROJECT_CONTEXT.md`
- Bedrock com evidencias objetivas
- evitar hardcode fora de configuracao

## Checklist rapido para futuras alteracoes

- Se mexer em S3: validar bucket region + filter id + CloudWatch metric
- Se mexer em EKS: priorizar `GroupTotalInstances`
- Se mexer em SMS: preferir SQS conhecido via `config.py`
- Se mexer em prompt: manter `ANALISE CONCLUIDA`
- Se mexer no TXT: nao poluir o relatorio principal com dump tecnico Bedrock
- Se adicionar contexto de negocio: colocar neste arquivo
