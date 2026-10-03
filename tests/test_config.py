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
    assert settings.serve_transport == "stdio"
    assert settings.serve_host == "127.0.0.1"
    assert settings.serve_port == 8000
    assert settings.callback_bind_host == "127.0.0.1"


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


class TestServeSettings:
    def test_http_serve_overrides(self, tmp_path):
        settings = load_settings(
            {
                "POLARIS_OIDC_CLIENT_ID": "cid",
                "POLARIS_CREDENTIALS_FILE": str(tmp_path / "creds.json"),
                "POLARIS_MCP_TRANSPORT": "streamable-http",
                "POLARIS_MCP_HOST": "0.0.0.0",
                "POLARIS_MCP_PORT": "9000",
                "POLARIS_CALLBACK_BIND_HOST": "0.0.0.0",
            }
        )
        assert settings.serve_transport == "streamable-http"
        assert settings.serve_host == "0.0.0.0"
        assert settings.serve_port == 9000
        assert settings.callback_bind_host == "0.0.0.0"

    def test_blank_values_fall_back_to_defaults(self, tmp_path):
        settings = load_settings(
            {
                "POLARIS_CREDENTIALS_FILE": str(tmp_path / "creds.json"),
                "POLARIS_MCP_TRANSPORT": "  ",
                "POLARIS_MCP_HOST": "",
                "POLARIS_CALLBACK_BIND_HOST": "",
            }
        )
        assert settings.serve_transport == "stdio"
        assert settings.serve_host == "127.0.0.1"
        assert settings.callback_bind_host == "127.0.0.1"

    def test_invalid_transport_rejected(self, tmp_path):
        with pytest.raises(ValueError, match="POLARIS_MCP_TRANSPORT must be one of"):
            load_settings(
                {
                    "POLARIS_CREDENTIALS_FILE": str(tmp_path / "creds.json"),
                    "POLARIS_MCP_TRANSPORT": "sse",
                }
            )

    def test_non_integer_port_rejected(self, tmp_path):
        with pytest.raises(ValueError, match="POLARIS_MCP_PORT must be an integer"):
            load_settings(
                {
                    "POLARIS_CREDENTIALS_FILE": str(tmp_path / "creds.json"),
                    "POLARIS_MCP_PORT": "https",
                }
            )

    @pytest.mark.parametrize("port", ["0", "65536", "-1"])
    def test_port_out_of_range_rejected(self, tmp_path, port):
        with pytest.raises(ValueError, match="POLARIS_MCP_PORT must be between"):
            load_settings(
                {
                    "POLARIS_CREDENTIALS_FILE": str(tmp_path / "creds.json"),
                    "POLARIS_MCP_PORT": port,
                }
            )

    def test_valid_boundary_ports(self, tmp_path):
        for port in ("1", "65535"):
            settings = load_settings(
                {
                    "POLARIS_CREDENTIALS_FILE": str(tmp_path / "creds.json"),
                    "POLARIS_MCP_PORT": port,
                }
            )
            assert settings.serve_port == int(port)
