"""
Baixa a planilha de eventos do Google Drive.

Suporta dois modos de autenticação, detectados automaticamente pelo conteúdo
do arquivo de credenciais:

  Service Account (recomendado para cron/EC2 — não expira):
    python3 scripts/download_calendar.py \
      --file-id 1dS7E1dlskOqc1pXuBjpkQ7umfwAORAcj9BGkWCkZ5Gg \
      --dest    "prompts/assets/Régua de Pushs_SMS Now Online.xlsx" \
      --credentials /opt/finops/credentials/service_account.json

  OAuth2 com refresh token (uso local interativo):
    python3 scripts/download_calendar.py \
      --file-id 1dS7E1dlskOqc1pXuBjpkQ7umfwAORAcj9BGkWCkZ5Gg \
      --dest    "prompts/assets/Régua de Pushs_SMS Now Online.xlsx" \
      --credentials /opt/finops/credentials/client_secret.json \
      --token       /opt/finops/credentials/token.json

Para service account, compartilhe a planilha no Google Drive com o e-mail
da service account (campo "client_email" no JSON) como Viewer.
"""

import argparse
import json
import sys
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2 import service_account
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
MIME_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

parser = argparse.ArgumentParser(
    description="Baixa planilha xlsx do Google Drive (service account ou OAuth2)."
)
parser.add_argument("--file-id",     required=True, help="ID do arquivo no Google Drive")
parser.add_argument("--dest",        required=True, help="Caminho local de destino do arquivo")
parser.add_argument("--credentials", required=True, help="Caminho para service_account.json ou client_secret.json")
parser.add_argument("--token",       default=None,  help="Caminho para token.json (apenas no modo OAuth2)")
args = parser.parse_args()

credentials_path = Path(args.credentials)
if not credentials_path.exists():
    print(f"[download_calendar] ERRO: arquivo de credenciais não encontrado: '{credentials_path}'", file=sys.stderr)
    sys.exit(1)

# Detecta o tipo de credencial pelo campo "type" do JSON
with open(credentials_path, encoding="utf-8") as f:
    cred_data = json.load(f)

cred_type = cred_data.get("type", "")

if cred_type == "service_account":
    # Service Account: sem expiração de refresh token, ideal para automações
    creds = service_account.Credentials.from_service_account_file(
        str(credentials_path), scopes=SCOPES
    )
    print("[download_calendar] Autenticando via Service Account.")

else:
    # OAuth2: requer token.json gerado pelo setup_gdrive_auth.py
    if not args.token:
        print(
            "[download_calendar] ERRO: --token é obrigatório no modo OAuth2.\n"
            "Use --credentials com um service_account.json para evitar expiração de token.",
            file=sys.stderr,
        )
        sys.exit(1)

    token_path = Path(args.token)
    if not token_path.exists():
        print(
            f"[download_calendar] ERRO: token.json não encontrado em '{token_path}'.\n"
            "Execute setup_gdrive_auth.py uma vez para gerar o token.\n"
            "Considere migrar para service_account.json para evitar esse problema.",
            file=sys.stderr,
        )
        sys.exit(1)

    creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(token_path, "w", encoding="utf-8") as f:
            f.write(creds.to_json())
        print("[download_calendar] Access token OAuth2 renovado.")
    elif not creds.valid:
        print(
            "[download_calendar] ERRO: refresh token expirado ou revogado.\n"
            "Execute setup_gdrive_auth.py novamente para gerar um novo token.json.\n"
            "Considere migrar para service_account.json para evitar esse problema no futuro.",
            file=sys.stderr,
        )
        sys.exit(1)

# Garante que o diretório de destino existe
dest_path = Path(args.dest)
dest_path.parent.mkdir(parents=True, exist_ok=True)

try:
    service = build("drive", "v3", credentials=creds, cache_discovery=False)
    # export_media converte Sheets → xlsx; para arquivos já em xlsx usa get_media
    request = service.files().export_media(fileId=args.file_id, mimeType=MIME_XLSX)
    with open(dest_path, "wb") as fh:
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
except HttpError as exc:
    print(f"[download_calendar] ERRO HTTP ao acessar o Drive: {exc}", file=sys.stderr)
    sys.exit(1)

print(f"[download_calendar] Planilha salva em: {dest_path.resolve()}")
