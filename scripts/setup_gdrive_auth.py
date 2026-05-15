"""
Script one-time para autenticar com a conta Google pessoal e gerar token.json.
Deve ser executado UMA VEZ na máquina local (com navegador disponível).
Após a autenticação, copie client_secret.json e token.json para a EC2.

Uso:
  pip install google-auth-oauthlib google-api-python-client
  python3 scripts/setup_gdrive_auth.py --credentials ./client_secret.json
  python3 scripts/setup_gdrive_auth.py --credentials ./client_secret.json --token-out ./token.json
"""

import argparse
from pathlib import Path
from google_auth_oauthlib.flow import InstalledAppFlow

# Escopo mínimo: leitura do Drive (não permite escrita)
SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]

parser = argparse.ArgumentParser(
    description="Gera token.json para download automático do Google Drive."
)
parser.add_argument(
    "--credentials",
    required=True,
    help="Caminho para o client_secret.json baixado do Google Cloud Console",
)
parser.add_argument(
    "--token-out",
    default="token.json",
    help="Caminho de saída para o token.json (padrão: ./token.json)",
)
args = parser.parse_args()

credentials_path = Path(args.credentials)
if not credentials_path.exists():
    raise FileNotFoundError(f"Arquivo não encontrado: {credentials_path}")

print(f"[setup_gdrive_auth] Usando credenciais: {credentials_path}")
print("[setup_gdrive_auth] Abrindo navegador para autenticação...")

flow = InstalledAppFlow.from_client_secrets_file(str(credentials_path), SCOPES)
# run_local_server abre o navegador e captura o callback automaticamente
creds = flow.run_local_server(port=0)

token_path = Path(args.token_out)
token_path.parent.mkdir(parents=True, exist_ok=True)
with open(token_path, "w", encoding="utf-8") as f:
    f.write(creds.to_json())

print(f"[setup_gdrive_auth] token.json salvo em: {token_path.resolve()}")
print()
print("Próximos passos:")
print(f"  1. Copie '{credentials_path}' para /opt/finops/credentials/client_secret.json na EC2")
print(f"  2. Copie '{token_path}' para /opt/finops/credentials/token.json na EC2")
print("  3. Na EC2: chmod 600 /opt/finops/credentials/*.json")
