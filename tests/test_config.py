"""Tests for settings resolution."""

from __future__ import annotations

import pytest

from polaris_mcp.config import load_settings


def test_defaults_and_api_base(tmp_path):
    settings = load_settings(
        {
            "POLARIS_OIDC_CLIENT_ID": "cid",
            "POLARIS_CREDENTIALS_FILE": str(tmp_path / "creds.json"),
        }
    )
    assert settings.base_url == "http://localhost:8080"
    assert settings.api_base_url == "http://localhost:8080/api/v1"
    assert settings.oidc_client_id == "cid"
    assert settings.ingest_api_key is None
    assert settings.credentials_file == tmp_path / "creds.json"
    assert settings.timeout_seconds == 30.0


def test_trailing_slash_and_overrides(tmp_path):
    settings = load_settings(
        {
            "POLARIS_BASE_URL": "https://polaris.example.com/",
            "POLARIS_INGEST_API_KEY": "key",
            "POLARIS_TIMEOUT_SECONDS": "1.5",
            "POLARIS_CREDENTIALS_FILE": str(tmp_path / "creds.json"),
        }
    )
    assert settings.api_base_url == "https://polaris.example.com/api/v1"
    assert settings.ingest_api_key == "key"
    assert settings.timeout_seconds == 1.5


def test_invalid_base_url_rejected():
    with pytest.raises(ValueError, match="absolute http"):
        load_settings({"POLARIS_BASE_URL": "not-a-url"})
