# 1 - CRIAR CONTA DE SERVIÇO GOOGLE

## CONTA DE SERVIÇO NÃO EXPIRA, DA FORMA COMO ESTA HOJE O TOKEN EXPIRA E DOWNLOAD NÃO E FEITO

Solução definitiva: Service Account
Por que é melhor:

Chave JSON estática, nunca expira por inatividade
Não precisa de fluxo interativo (browser)
Ideal para EC2/cron
Passo a passo:

No Google Cloud Console → IAM & Admin → Service Accounts → Create Service Account
Dê um nome (ex: finops-gdrive-reader) e crie
Na service account criada → Keys → Add Key → JSON → baixe como service_account.json
No Google Drive, abra a planilha → Compartilhar → cole o client_email do JSON → permissão Viewer
Coloque service_account.json na raiz do projeto
Uso no cron_daily.sh — troque --credentials para apontar para service_account.json e remova --token:


python3 scripts/download_calendar.py \
  --file-id "1dS7E1dlskOqc1pXuBjpkQ7umfwAORAcj9BGkWCkZ5Gg" \
  --dest "prompts/assets/Régua de Pushs_SMS Now Online.xlsx" \
  --credentials "./service_account.json"
O script já detecta automaticamente o tipo pelo campo "type" do JSON — sem necessidade de flag extra.

Para hoje, o imediato é regenerar o token OAuth2:

python3 scripts/setup_gdrive_auth.py --credentials ./client_secret.json
Mas assim que possível, migre para service account para não ter esse problema novamente.

----

# 2 