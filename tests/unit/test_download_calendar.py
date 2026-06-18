import importlib.util
from pathlib import Path

import pytest
from google.auth.exceptions import RefreshError


def _load_download_calendar_module():
    """Loads the CLI script as a module without requiring scripts/ to be a package."""
    module_path = Path(__file__).resolve().parents[2] / "scripts" / "download_calendar.py"
    spec = importlib.util.spec_from_file_location("download_calendar", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_load_google_credentials_reports_revoked_refresh_token(tmp_path, monkeypatch):
    module = _load_download_calendar_module()
    credentials_path = tmp_path / "client_secret.json"
    token_path = tmp_path / "token.json"

    credentials_path.write_text('{"installed": {"client_id": "abc"}}', encoding="utf-8")
    token_path.write_text('{"refresh_token": "revoked"}', encoding="utf-8")

    class FakeCredentials:
        expired = True
        refresh_token = "revoked"
        valid = False

        def refresh(self, _request):
            raise RefreshError("invalid_grant")

        def to_json(self):
            return "{}"

    monkeypatch.setattr(
        module.Credentials,
        "from_authorized_user_file",
        lambda *_args, **_kwargs: FakeCredentials(),
    )

    with pytest.raises(RuntimeError, match="setup_gdrive_auth.py novamente"):
        module.load_google_credentials(credentials_path, token_path)


def test_load_google_credentials_requires_token_for_oauth(tmp_path):
    module = _load_download_calendar_module()
    credentials_path = tmp_path / "client_secret.json"
    credentials_path.write_text('{"installed": {"client_id": "abc"}}', encoding="utf-8")

    with pytest.raises(RuntimeError, match="--token e obrigatorio"):
        module.load_google_credentials(credentials_path, None)
