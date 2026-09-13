"""Shared fixtures: test settings, fake Google token endpoint, MCP session helpers."""

from __future__ import annotations

import base64
import json
import time

import pytest

from polaris_mcp.config import Settings

API_BASE = "http://polaris.test"
TOKEN_URL = "https://oauth2.googleapis.com/token"


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def make_id_token(email: str = "user@example.com", exp: int | None = None) -> str:
    header = b64url(json.dumps({"alg": "RS256", "typ": "JWT"}).encode())
    claims = {"email": email, "exp": exp if exp is not None else int(time.time()) + 3600}
    payload = b64url(json.dumps(claims).encode())
    return f"{header}.{payload}.sig"


@pytest.fixture
def credentials_file(tmp_path):
    path = tmp_path / "credentials.json"
    path.write_text(json.dumps({"refresh_token": "rt-test", "email": "user@example.com"}))
    return path


@pytest.fixture
def settings(credentials_file) -> Settings:
    return Settings(
        base_url=API_BASE,
        oidc_client_id="client-id",
        oidc_client_secret=None,
        ingest_api_key="ingest-key",
        authorized_email=None,
        credentials_file=credentials_file,
        timeout_seconds=5.0,
    )


@pytest.fixture
def no_ingest_settings(settings: Settings) -> Settings:
    from dataclasses import replace

    return replace(settings, ingest_api_key=None)


@pytest.fixture(autouse=True)
def bind_runtime(monkeypatch, settings):
    """Point the lazy runtime at test settings and reset it around each test."""
    import polaris_mcp.runtime as runtime

    monkeypatch.setattr(runtime, "load_settings", lambda: settings)
    runtime.reset_client()
    yield
    runtime.reset_client()


@pytest.fixture
def respx_mock():
    import respx

    with respx.mock(assert_all_called=False) as mock:
        yield mock


@pytest.fixture
def mock_token_endpoint(respx_mock):
    respx_mock.post(TOKEN_URL).respond(json={"id_token": make_id_token(), "access_token": "at"})


def tool_payload(result):
    """Assert a successful tool call and decode its JSON payload."""
    assert not result.isError, f"tool error: {[c.text for c in result.content]}"
    return json.loads(result.content[0].text)
