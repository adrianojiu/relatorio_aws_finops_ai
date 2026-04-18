# Contexto do Projeto

Este arquivo e a fonte principal de contexto de negocio, operacao e causalidade do projeto `relatorio_aws_finops_ai`.

Objetivo:

- preservar decisoes ja tomadas
- evitar perda de contexto entre sessoes
- registrar regras de interpretacao do ambiente
- manter coerencia entre codigo, documentacao e analise da IA

Se houver divergencia entre implementacao e este arquivo:

- a implementacao deve ser revisada
- este arquivo deve ser atualizado se a regra correta tiver mudado

## Fonte de verdade por tipo de informacao

Use este arquivo para:

- contexto operacional do ambiente
- explicacoes de causalidade
- comportamento esperado de eventos
- excecoes operacionais
- decisoes historicas do projeto

Use `src/config.py` para:

- configuracao executavel
- thresholds
- listas de metricas
- usage types
- nomes tecnicos de arquivos
- recursos conhecidos e parametros tecnicos de coleta

Use `prompts/finops_analysis.txt` para:

- instrucoes operacionais da IA
- formato da resposta
- regras de classificacao
- limites de redacao
- o que a resposta final deve ou nao afirmar

Use `README.md` para:

- comandos
- fluxo de execucao
- artefatos gerados
- orientacoes de uso

## Regras de manutencao

Este arquivo deve ser revisado sempre que houver mudanca relevante em:

- especificacao funcional
- regra de correlacao
- convencao operacional
- comportamento esperado da analise
- estrategia de observabilidade

O `README.md` deve ser revisado quando mudarem:

- comandos
- parametros de execucao
- artefatos gerados
- fluxo operacional

Evitar hardcode sempre que possivel.

Preferencias do projeto:

- configuracao executavel fica em `config.py`
- contexto de negocio e interpretacao ficam aqui
- descoberta tecnica dinamica deve vir da AWS quando fizer sentido

## Objetivo do projeto

Gerar um relatorio diario de custos AWS com:

- consolidacao de custos da janela analisada
- identificacao de variacoes relevantes por `service` e `usage_type`
- correlacao com recursos AWS reais
- enriquecimento com metricas operacionais
- analise causal via Bedrock

Saidas principais:

- `output/YYYY-MM-DD/relatorio_custos_YYYY-MM-DD.txt`
- `output/YYYY-MM-DD/relatorio_custos_YYYY-MM-DD.pdf`
- `output/YYYY-MM-DD/relatorio_custos_YYYY-MM-DD.xlsx`
- `output/YYYY-MM-DD/execucao_<timestamp>.log`
- `output/YYYY-MM-DD/execucao_<timestamp>.json`
- `output/YYYY-MM-DD/relatorio_custos_YYYY-MM-DD_bedrock_payload.json`
- `output/YYYY-MM-DD/relatorio_custos_YYYY-MM-DD_bedrock_prompt.txt`
- `output/YYYY-MM-DD/relatorio_custos_YYYY-MM-DD_bedrock_context.txt`
- `output/YYYY-MM-DD/relatorio_custos_YYYY-MM-DD_ai.txt`
- `output/YYYY-MM-DD/relatorio_custos_YYYY-MM-DD_ai_meta.json`

## Regioes AWS

O projeto trata regioes separadamente.

- `WORKLOAD_REGION`
  Uso: recursos operacionais do workload, CloudWatch e descoberta de recursos
- `COST_EXPLORER_REGION`
  Uso: Cost Explorer
- `BEDROCK_REGION`
  Uso: Bedrock

No ambiente atual:

- workloads podem estar em `sa-east-1`
- Cost Explorer costuma ser usado em `us-east-1`
- Bedrock costuma ser usado em `us-east-1`

Nao voltar para uma unica regiao compartilhada para tudo.

## Perfis e conta AWS

- O projeto aceita `--aws-profile`
- O cabecalho do TXT tenta mostrar `account alias + account id`
- Se o alias nao estiver disponivel, o fallback deve usar `AWS_PROFILE + account id`

Exemplo esperado:

- `Custo de Cloud AWS conta prd-ciam (123456789012)`

## Janela de analise

- `ANALYSIS_DAYS = 7`
- `OFFSET_DAYS = 2`

Importante:

- o relatorio nao analisa "hoje"
- ele analisa o ultimo dia consolidado da AWS, com atraso de 2 dias

Na comunicacao humana e preferivel usar:

- `dia de referencia`
- ou a data absoluta

## Artefatos e separacao de responsabilidades

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

Separacao atual:

- TXT principal: foco executivo
- `*_bedrock_context.txt`: apoio tecnico de correlacao
- `*_bedrock_payload.json`: payload real enviado para a IA
- `*_bedrock_prompt.txt`: prompt final gerado
- `*_ai.txt`: resposta da IA
- `*_ai_meta.json`: metadados da resposta

Essa separacao deve ser mantida.

Os artefatos de cada execucao devem ficar agrupados em uma subpasta por data dentro de `output/`.

## Observabilidade da execucao

A execucao deve registrar eventos em tempo real no console e tambem em arquivo dedicado dentro de `output/YYYY-MM-DD/`.

Objetivos:

- identificar em qual etapa a execucao falhou
- identificar em qual etapa a execucao ficou lenta
- manter rastreabilidade mesmo quando o TXT principal nao for gerado

Arquivos esperados por execucao:

- `execucao_<timestamp>.log`
- `execucao_<timestamp>.json`

Quando o relatorio TXT final for gerado, o artefato `*_execution_log.json` pode continuar existindo como visao associada diretamente ao relatorio.

Antes de iniciar a coleta principal, a execucao do `run.py` deve pedir confirmacao explicita de que a planilha `prompts/assets/Régua de Pushs_SMS Now Online.xlsx` esta atualizada.

Regra operacional:

- se a confirmacao for negativa, vazia ou indisponivel, a execucao deve ser cancelada
- em situacoes excepcionais ou automacoes controladas, a etapa pode ser pulada com `--skip-calendar-confirmation`
- o objetivo e evitar analise com calendario de negocio desatualizado

## Regras gerais de implementacao

Preferencias estruturais:

- separar entrada, regra de negocio e integracoes
- evitar espalhar regras de negocio no codigo
- preferir descoberta automatica da AWS para tags, account id, account alias, regiao real de bucket e configuracao de metricas

Quando uma regra for principalmente explicacao de dominio, ela deve viver aqui.

Quando for parametro tecnico mutavel, ela deve viver em `config.py`.

## Regras de negocio e causalidade

### Classificacao interpretativa

O projeto diferencia:

- `anomalia real`
- `desvio esperado`
- `efeito em cascata`

Essa distincao e importante porque nem toda variacao relevante deve ser tratada como incidente ou desperdicio.

### Eventos e push do Claro TV+

A regua de eventos e push do Claro TV+ e contexto de negocio importante para correlacionar:

- aumento de plays
- aumento de autenticacao e autorizacao
- aumento de trafego
- scaling agendado

Regras do ambiente:

- picos de audiencia frequentemente pressionam o `prd-sso-ciam`
- o aumento de compute em EKS costuma acontecer antes do inicio previsto desses eventos
- o nodegroup de PDP e um candidato recorrente quando ha evento relevante e evidencia compativel de scaling

Importante:

- a regua de push/eventos nao deve ser tratada como evidencia direta de custo ou contagem de AWS End User Messaging/SMS
- evento com push costuma ser sinal mais forte de pressao de negocio do que evento sem push

### EKS e EC2 Compute

Para workloads EKS:

- nao focar em `NetworkIn` ou `NetworkOut` como explicacao principal
- instancias de EKS sao efemeras
- o mais importante e quantas instancias foram usadas e por quanto tempo

Prioridade de leitura para scaling:

1. `GroupTotalInstances`
2. `GroupDesiredCapacity`
3. `GroupInServiceInstances`

Regras adicionais:

- nao afirmar causalidade principal para um nodegroup apenas porque houve scaling visivel
- antes de atribuir custo a um nodegroup, conferir se o tipo de instancia observado combina com o `usage_type`
- quando houver mais de um nodegroup plausivel, preferir leitura de `candidato principal` ou `hipotese mais provavel`
- quando `min_value` e `peak_value` estiverem disponiveis, a faixa real observada e melhor do que um resumo de primeiro e ultimo ponto

### Ping Directory

Contexto correto:

- `primary`, `secondary` e `ternary` atendem o trafego principal
- `quaternary` fica fora do balanceamento
- `quaternary` executa backup, relatorios e limpeza

Consequencias:

- nao tratar `quaternary` como explicacao principal para compute de EKS
- nao tratar `NetworkOut` alto da `quaternary` como anomalia por si so quando o contexto indicar backup

### S3

Objetivo atual:

- identificar bucket candidato a partir de `AllRequests`

Decisao atual do projeto:

- simplificar request metrics para `AllRequests`
- nao depender neste momento de `GetRequests`, `PutRequests`, `ListRequests` e similares

Limitacoes importantes:

- `AllRequests` so existe para buckets com request metrics configurada
- bucket sem `all-objects` ou filtro equivalente pode nao ter `AllRequests`
- isso nao significa falha do codigo automaticamente

Interpretacao correta:

- tamanho do bucket, numero de objetos, score interno e contexto operacional nao provam sozinhos o bucket causador
- bucket com `AllRequests` vira candidato forte apenas quando houver coincidencia temporal com o spike de custo
- se so um bucket estiver instrumentado e os demais nao, tratar como candidato principal, nao como causa confirmada
- com apenas `AllRequests`, a leitura correta e `aumento de requisicoes`, sem inferir tipos especificos de operacao

Observabilidade:

- quando houver buckets candidatos relevantes sem `AllRequests`, o gap de observabilidade deve permanecer visivel no payload
- buckets conhecidos do `config.py` devem ser priorizados antes do corte por `MAX_CANDIDATE_RESOURCES`

Coleta esperada:

1. listar buckets
2. descobrir a regiao real do bucket com `get_bucket_location`
3. descobrir o `MetricsConfiguration Id`
4. usar esse `FilterId` na consulta CloudWatch
5. consultar o CloudWatch na regiao real do bucket

Se o bucket nao tiver exatamente `all-objects`, deve-se tentar outro `MetricsConfiguration Id` disponivel antes de concluir que nao ha request metrics utilizaveis.

Historico importante:

- houve um bug em que `s3_request_filter_id` ficava em `derived_context`, mas a busca procurava apenas no topo do recurso
- isso ja foi corrigido

### GuardDuty

Existe regra especifica para:

- `SAE1-PaidS3DataEventsAnalyzed`

Essa anomalia deve ser correlacionada com buckets S3.

Regra de leitura:

- sem `AllRequests`, nao concluir bucket lider com alta confianca
- com `AllRequests`, comparar a data do spike do bucket com a data do spike de custo
- quando um bucket lider estiver claramente identificado por requests, correlacoes com EKS, logs ou outros servicos viram contexto secundario
- para anomalias de S3, vale sempre tentar uma correlacao leve com a propria anomalia de `SAE1-PaidS3DataEventsAnalyzed` quando ela existir na mesma execucao
- se GuardDuty estiver presente no payload e subir na mesma direcao da anomalia de S3, isso reforca a hipotese; se estiver em queda ou neutro, ele nao deve ser usado como reforco indevido
- GuardDuty entra como evidencia complementar, nunca como substituto do bucket lider por `AllRequests`

### SMS e End User Messaging

SMS deve ser lido com apoio de filas SQS conhecidas configuradas em `config.py`.

Leitura esperada:

- `NumberOfMessagesSent` e `NumberOfMessagesReceived` sao a evidencia operacional principal de volume
- `ApproximateNumberOfMessagesVisible` e `ApproximateAgeOfOldestMessage` indicam backlog ou degradacao
- crescimento organico de volume tende a ser `desvio esperado`
- `anomalia real` em SMS exige sinais de fallback excessivo, falha, retries, backlog ou comportamento desproporcional

### Transit Gateway e servicos de rede

Para `TransitGateway-Bytes`:

- `BytesIn` e `BytesOut` sao a evidencia principal de aumento real de trafego
- sem essas metricas, a leitura deve ser tratada como correlacao indireta

Para LCU, Transit Gateway e outros servicos de rede:

- quando o comportamento acompanhar trafego legitimo, scaling agendado ou evento conhecido, a tendencia e `desvio esperado` ou `efeito em cascata`

### NAT Gateway

Usage type `NatGateway-Bytes` nao deve cair na regra generica de `EC2-Other` sem recursos.

Deve usar descoberta direta de NAT Gateway com metricas proprias de bytes e conexoes.

Sem coincidencia temporal clara entre trafego, scaling ou evento, nao associar NAT automaticamente a streaming, autenticacao ou backup.

### CloudWatch Logs / DataScanned-Bytes

Para `DataScanned-Bytes`, o payload deve ser enriquecido com metadados objetivos de query sempre que possivel:

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
- `IncomingBytes` sozinho nao prova investigacao, dashboard ou consulta
- nao relacionar `DataScanned-Bytes` com GuardDuty sem evidencia direta nas queries ou no payload

Contexto operacional conhecido:

- no inicio do mes, normalmente por volta do dia 2, pode haver queries nos logs do CloudWatch para consumo de APIs e envio ao time de FinOps
- na primeira semana do mes tambem podem ocorrer queries para preparacao de reunioes de MBR

### CloudTrail para anomalias de S3

Para anomalias de S3, CloudTrail deve ser usado como enriquecimento seletivo, nao como consulta pesada obrigatoria para todo bucket.

Regra pratica:

- sempre tentar uma correlacao leve com GuardDuty
- fazer lookup adicional de CloudTrail apenas quando houver bucket candidato com `AllRequests` minimamente aderente ao spike
- usar CloudTrail para identificar ator, origem e tipo de evento quando isso ajudar a distinguir atividade legitima de anomalia real
- mesmo com CloudTrail, `AllRequests` continua sendo a evidencia principal para bucket lider

### AWS Backup

AWS Backup entra como evidencia complementar para:

- `EC2-Other`
- snapshots
- backup de S3

Regras:

- nao tratar AWS Backup como causa principal isolada sem coincidencia temporal com a anomalia
- nao anexar AWS Backup em usage types de rede como `NatGateway-Bytes`, `TransitGateway-Bytes` ou `DataTransfer`
- restringir o uso complementar a usage types com cara de snapshot, backup ou recovery point

### ECR

ECR entra apenas como evidencia complementar para EKS.

Leitura esperada:

- aumento de `RepositoryPullCount` pode reforcar hipoteses de rollout, restart ou scale-out
- ECR nao deve ser tratado como causa principal isolada de custo

## Modelos Bedrock

O projeto suporta hoje, via `InvokeModel`, pelo menos:

- Anthropic
- Amazon Nova
- OpenAI
- DeepSeek
- Meta Llama

O modelo padrao atual fica em `config.py`.

Importante:

- alguns modelos exigem `inference profile`
- Anthropic ativo em Bedrock frequentemente precisa de `us.anthropic...` ou `global.anthropic...`

## Como evoluir o projeto sem perder coerencia

Antes de mudar algo, verificar:

1. isso e configuracao ou contexto?
2. isso impacta relatorio humano, payload Bedrock, ou ambos?
3. a mudanca traz evidencia real ou apenas narrativa?

Preferencias do projeto:

- relatorio TXT principal limpo
- detalhes tecnicos em arquivo separado
- contexto de negocio centralizado neste arquivo
- Bedrock apoiado por evidencias objetivas
- evitar hardcode fora de configuracao

## Checklist rapido para futuras alteracoes

- Se mexer em S3: validar bucket region, filter id e CloudWatch metric
- Se mexer em EKS: priorizar `GroupTotalInstances`
- Se mexer em SMS: preferir SQS conhecido via `config.py`
- Se mexer no prompt: manter estrutura, classificacao e marcador de fim
- Se mexer no TXT: nao poluir o relatorio principal com dump tecnico Bedrock
- Se adicionar contexto de negocio: colocar neste arquivo
