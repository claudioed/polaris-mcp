"""Tests for the command-line entrypoint."""

from __future__ import annotations

from tests.conftest import API_BASE

from polaris_mcp.cli import _cmd_status, build_parser, main


class TestParser:
    def test_default_command_is_serve(self, monkeypatch):
        monkeypatch.setattr("polaris_mcp.server.create_server", lambda: _FakeServer())
        assert main([]) == 0  # bare invocation serves

    def test_subcommands_available(self):
        parser = build_parser()
        assert parser.parse_args(["login"]).command == "login"
        assert parser.parse_args(["status"]).command == "status"
        assert parser.parse_args(["serve"]).command == "serve"


class _FakeServer:
    def run(self):
        return None


class TestStatus:
    async def test_status_ok_with_credentials(self, settings, respx_mock):
        respx_mock.post("https://oauth2.googleapis.com/token").respond(
            json={"id_token": "x." + _payload({"email": "user@example.com", "exp": 9999999999}) + ".sig"}
        )
        respx_mock.get(f"{API_BASE}/api/v1/health/live").respond(json={"status": "ok"})
        respx_mock.get(f"{API_BASE}/api/v1/health/ready").respond(json={"status": "ok"})
        assert await _cmd_status(settings) == 0

    async def test_status_fails_without_credentials_or_server(self, settings, respx_mock):
        settings.credentials_file.unlink()
        respx_mock.get(f"{API_BASE}/api/v1/health/live").respond(status_code=503, json={})
        respx_mock.get(f"{API_BASE}/api/v1/health/ready").respond(status_code=503, json={})
        assert await _cmd_status(settings) == 1

    async def test_status_reports_refresh_failure(self, settings, respx_mock):
        respx_mock.post("https://oauth2.googleapis.com/token").respond(
            status_code=400, json={"error": "invalid_grant"}
        )
        respx_mock.get(f"{API_BASE}/api/v1/health/live").respond(json={"status": "ok"})
        respx_mock.get(f"{API_BASE}/api/v1/health/ready").respond(json={"status": "ok"})
        assert await _cmd_status(settings) == 1


class TestMainErrors:
    def test_login_without_client_id_exits_1(self, monkeypatch, capsys):
        from dataclasses import replace

        from polaris_mcp.config import Settings

        monkeypatch.setattr(
            "polaris_mcp.cli.load_settings",
            lambda: replace(
                Settings(
                    base_url=API_BASE,
                    oidc_client_id="",
                    oidc_client_secret=None,
                    ingest_api_key=None,
                    authorized_email=None,
                    credentials_file=None,
                    timeout_seconds=1.0,
                ),
                credentials_file=None,
            ),
        )
        assert main(["login"]) == 1
        assert "POLARIS_OIDC_CLIENT_ID" in capsys.readouterr().err

    def test_status_command_wires_through(self, monkeypatch):
        called = {}

        async def fake_status(settings):
            called["ok"] = True
            return 0

        monkeypatch.setattr("polaris_mcp.cli.load_settings", lambda: None)
        monkeypatch.setattr("polaris_mcp.cli._cmd_status", fake_status)
        assert main(["status"]) == 0
        assert called["ok"]


def _payload(claims: dict) -> str:
    import base64
    import json as jsonlib

    raw = base64.urlsafe_b64encode(jsonlib.dumps(claims).encode()).rstrip(b"=").decode()
    return raw
