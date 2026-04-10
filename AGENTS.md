# AGENTS.md

## Objetivo

Este repositório gera relatórios diários de custo AWS para um ambiente CIAM e enriquece a análise com correlação operacional e Bedrock.

## Antes de alterar algo relevante

Leia primeiro:

- `README.md`
- `PROJECT_CONTEXT.md`

Use `PROJECT_CONTEXT.md` como fonte principal de contexto de negócio, operação, correlações e decisões históricas.

## Fonte de verdade por tipo de informação

- `src/config.py`
  Use para configuração executável do sistema.
  Exemplos: regiões, thresholds, nomes de arquivos, listas de métricas, padrões de usage type e recursos conhecidos.

- `PROJECT_CONTEXT.md`
  Use para contexto de negócio e operação.
  Exemplos: interpretação de eventos, regras de causalidade, comportamento esperado de PDP, Ping Directory, CloudWatch Logs e SMS.

- `prompts/finops_analysis.txt`
  Use para instruções de escrita e análise da IA.

## Regras importantes

- Não trate a régua de push/eventos como evidência direta de AWS SMS.
- Para EKS, priorize `GroupTotalInstances` como principal evidência de scaling.
- Para Transit Gateway, use `BytesIn` e `BytesOut` como evidência principal.
- Não force tudo a ser anomalia; diferencie `anomalia real`, `desvio esperado` e `efeito em cascata`.
- Não afirme que o dia de referência foi o pico da janela sem conferir a série diária total.

## Ao fazer mudanças

- Atualize o `README.md` se mudar comando, artefato gerado ou fluxo operacional.
- Atualize o `PROJECT_CONTEXT.md` se mudar regra de negócio, observabilidade ou interpretação operacional.
- Mantenha o `config.py` objetivo; se o texto parecer explicação longa para humanos, provavelmente ele pertence ao `PROJECT_CONTEXT.md`.
- Sempre adicione comentarios no codigo para entendimento dos trechos.
