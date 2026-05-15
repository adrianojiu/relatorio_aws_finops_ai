"""
Baixa a planilha de eventos do Google Drive usando OAuth2 com refresh token.
O token.json é renovado automaticamente — não expira enquanto usado regularmente.
Executado pelo cron_daily.sh antes de cada geração de relatório.

Uso:
  python3 scripts/download_calendar.py \
    --file-id 1dS7E1dlskOqc1pXuBjpkQ7umfwAORAcj9BGkWCkZ5Gg \
    --dest    "prompts/assets/Régua de Pushs_SMS Now Online.xlsx" \
    --credentials /opt/finops/credentials/client_secret.json \
    --token       /opt/finops/credentials/token.json
"""

import argparse
import sys
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
MIME_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

parser = argparse.ArgumentParser(
    description="Baixa planilha xlsx do Google Drive via OAuth2."
)
parser.add_argument("--file-id",     required=True, help="ID do arquivo no Google Drive")
parser.add_argument("--dest",        required=True, help="Caminho local de destino do arquivo")
parser.add_argument("--credentials", required=True, help="Caminho para client_secret.json")
parser.add_argument("--token",       required=True, help="Caminho para token.json")
args = parser.parse_args()

token_path = Path(args.token)
if not token_path.exists():
    print(
        f"[download_calendar] ERRO: token.json não encontrado em '{token_path}'.\n"
        "Execute setup_gdrive_auth.py uma vez para gerar o token.",
        file=sys.stderr,
    )
    sys.exit(1)

# Carrega credenciais e renova o access token se expirado
creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
if creds.expired and creds.refresh_token:
    creds.refresh(Request())
    with open(token_path, "w", encoding="utf-8") as f:
        f.write(creds.to_json())
    print("[download_calendar] Access token renovado.")

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
