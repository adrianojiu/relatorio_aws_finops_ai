"""
Baixa a planilha de eventos do Google Drive.

Suporta dois modos de autenticacao, detectados automaticamente pelo conteudo
do arquivo de credenciais:

  Service Account (recomendado para cron/EC2 - nao expira):
    python3 scripts/download_calendar.py \
      --file-id 1dS7E1dlskOqc1pXuBjpkQ7umfwAORAcj9BGkWCkZ5Gg \
      --dest    "prompts/assets/Regua de Pushs_SMS Now Online.xlsx" \
      --credentials /opt/finops/credentials/service_account.json

  OAuth2 com refresh token (uso local interativo):
    python3 scripts/download_calendar.py \
      --file-id 1dS7E1dlskOqc1pXuBjpkQ7umfwAORAcj9BGkWCkZ5Gg \
      --dest    "prompts/assets/Regua de Pushs_SMS Now Online.xlsx" \
      --credentials /opt/finops/credentials/client_secret.json \
      --token       /opt/finops/credentials/token.json

Para service account, compartilhe a planilha no Google Drive com o e-mail
da service account (campo "client_email" no JSON) como Viewer.
"""

import argparse
import json
import sys
from pathlib import Path

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2 import service_account
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
MIME_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def build_parser():
    """Builds the CLI parser to keep the entry point testable."""
    parser = argparse.ArgumentParser(
        description="Baixa planilha xlsx do Google Drive (service account ou OAuth2)."
    )
    parser.add_argument("--file-id", required=True, help="ID do arquivo no Google Drive")
    parser.add_argument("--dest", required=True, help="Caminho local de destino do arquivo")
    parser.add_argument(
        "--credentials",
        required=True,
        help="Caminho para service_account.json ou client_secret.json",
    )
    parser.add_argument(
        "--token",
        default=None,
        help="Caminho para token.json (apenas no modo OAuth2)",
    )
    return parser


def _read_credential_metadata(credentials_path):
    """Reads the raw JSON only to identify the credential type."""
    with open(credentials_path, encoding="utf-8") as file_handle:
        return json.load(file_handle)


def _oauth_recovery_message():
    """Centralizes the operator guidance for revoked OAuth tokens."""
    return (
        "[download_calendar] ERRO: refresh token expirado, revogado ou invalido.\n"
        "Execute setup_gdrive_auth.py novamente para gerar um novo token.json.\n"
        "Exemplo: python3 scripts/setup_gdrive_auth.py --credentials ./client_secret.json\n"
        "Considere migrar para service_account.json para evitar expiracao em automacoes."
    )


def load_google_credentials(credentials_path, token_path=None):
    """Loads either service-account or OAuth2 credentials with explicit error handling."""
    if not credentials_path.exists():
        raise FileNotFoundError(
            f"[download_calendar] ERRO: arquivo de credenciais nao encontrado: '{credentials_path}'"
        )

    cred_data = _read_credential_metadata(credentials_path)
    cred_type = cred_data.get("type", "")

    if cred_type == "service_account":
        print("[download_calendar] Autenticando via Service Account.")
        return service_account.Credentials.from_service_account_file(
            str(credentials_path),
            scopes=SCOPES,
        )

    if token_path is None:
        raise RuntimeError(
            "[download_calendar] ERRO: --token e obrigatorio no modo OAuth2.\n"
            "Use --credentials com um service_account.json para evitar expiracao de token."
        )

    if not token_path.exists():
        raise FileNotFoundError(
            f"[download_calendar] ERRO: token.json nao encontrado em '{token_path}'.\n"
            "Execute setup_gdrive_auth.py uma vez para gerar o token.\n"
            "Considere migrar para service_account.json para evitar esse problema."
        )

    creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    if creds.expired and creds.refresh_token:
        try:
            # Refreshes the short-lived access token without forcing a new login when possible.
            creds.refresh(Request())
        except RefreshError as exc:
            raise RuntimeError(_oauth_recovery_message()) from exc

        with open(token_path, "w", encoding="utf-8") as file_handle:
            file_handle.write(creds.to_json())
        print("[download_calendar] Access token OAuth2 renovado.")

    if not creds.valid:
        raise RuntimeError(_oauth_recovery_message())

    return creds


def download_calendar(file_id, dest_path, creds):
    """Downloads the spreadsheet and persists it locally."""
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    service = build("drive", "v3", credentials=creds, cache_discovery=False)
    request = service.files().export_media(fileId=file_id, mimeType=MIME_XLSX)
    with open(dest_path, "wb") as file_handle:
        downloader = MediaIoBaseDownload(file_handle, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()


def main(argv=None):
    """CLI entry point used by both shell execution and tests."""
    parser = build_parser()
    args = parser.parse_args(argv)

    credentials_path = Path(args.credentials)
    token_path = Path(args.token) if args.token else None
    dest_path = Path(args.dest)

    try:
        creds = load_google_credentials(credentials_path, token_path)
        download_calendar(args.file_id, dest_path, creds)
    except (FileNotFoundError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except HttpError as exc:
        print(f"[download_calendar] ERRO HTTP ao acessar o Drive: {exc}", file=sys.stderr)
        return 1

    print(f"[download_calendar] Planilha salva em: {dest_path.resolve()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
