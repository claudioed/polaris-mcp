"""Tests for the command-line entrypoint."""

from __future__ import annotations

import httpx
import pytest
from tests.conftest import API_BASE

from polaris_mcp.cli import _cmd_status, build_parser, main


class TestParser:
    def test_default_command_is_serve(self, monkeypatch, settings):
        monkeypatch.setattr("polaris_mcp.cli.load_settings", lambda: settings)
        captured = {}

        class _FakeServer:
            def run(self, transport=None):
                captured["transport"] = transport

        monkeypatch.setattr("polaris_mcp.server.create_server", lambda s: _FakeServer())
        assert main([]) == 0  # bare invocation serves
        assert captured["transport"] == "stdio"

    def test_subcommands_available(self):
        parser = build_parser()
        assert parser.parse_args(["login"]).command == "login"
        assert parser.parse_args(["login", "--no-browser"]).no_browser is True
        assert parser.parse_args(["status"]).command == "status"
        assert parser.parse_args(["serve"]).command == "serve"


class TestServe:
    def _serve(self, monkeypatch, settings, argv):
        captured = {}

        class _FakeServer:
            def run(self, transport=None):
                captured["transport"] = transport

        def fake_create(resolved):
            captured["host"] = resolved.serve_host
            captured["port"] = resolved.serve_port
            return _FakeServer()

        monkeypatch.setattr("polaris_mcp.cli.load_settings", lambda: settings)
        monkeypatch.setattr("polaris_mcp.server.create_server", fake_create)
        return main(argv), captured

    def test_http_flags_override_settings(self, monkeypatch, settings):
        code, captured = self._serve(
            monkeypatch,
            settings,
            ["serve", "--transport", "streamable-http", "--host", "0.0.0.0", "--port", "9000"],
        )
        assert code == 0
        assert captured == {"transport": "streamable-http", "host": "0.0.0.0", "port": 9000}

    def test_env_configured_transport_used_without_flags(self, monkeypatch, settings):
        from dataclasses import replace

        code, captured = self._serve(
            monkeypatch,
            replace(settings, serve_transport="streamable-http", serve_host="10.0.0.1", serve_port=9123),
            ["serve"],
        )
        assert code == 0
        assert captured == {"transport": "streamable-http", "host": "10.0.0.1", "port": 9123}

    def test_port_out_of_range_rejected(self, monkeypatch, settings, capsys):
        code, captured = self._serve(monkeypatch, settings, ["serve", "--port", "70000"])
        assert code == 1
        assert captured == {}
        assert "--port" in capsys.readouterr().err

    def test_unknown_transport_rejected_by_argparse(self):
        with pytest.raises(SystemExit):
            main(["serve", "--transport", "carrier-pigeon"])


class TestLoginFlags:
    def _login(self, monkeypatch, argv):
        captured = {}

        def fake_login(settings, open_browser=True):
            captured["open_browser"] = open_browser
            return {}

        monkeypatch.setattr("polaris_mcp.cli.load_settings", lambda: None)
        monkeypatch.setattr("polaris_mcp.cli.run_login", fake_login)
        code = main(argv)
        return code, captured

    def test_no_browser_flag_forwarded(self, monkeypatch):
        code, captured = self._login(monkeypatch, ["login", "--no-browser"])
        assert code == 0
        assert captured["open_browser"] is False

    def test_browser_opened_by_default(self, monkeypatch):
        code, captured = self._login(monkeypatch, ["login"])
        assert code == 0
        assert captured["open_browser"] is True


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

    async def test_status_reports_unreachable_server(self, settings, respx_mock):
        from tests.conftest import TOKEN_URL, make_id_token

        respx_mock.post(TOKEN_URL).respond(json={"id_token": make_id_token()})
        respx_mock.get(f"{API_BASE}/api/v1/health/live").mock(side_effect=httpx.ConnectError("boom"))
        respx_mock.get(f"{API_BASE}/api/v1/health/ready").mock(side_effect=httpx.ConnectError("boom"))
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

    def test_login_success_returns_zero(self, monkeypatch):
        monkeypatch.setattr("polaris_mcp.cli.load_settings", lambda: None)
        monkeypatch.setattr(
            "polaris_mcp.cli.run_login", lambda settings, open_browser=True: {"email": "user@example.com"}
        )
        assert main(["login"]) == 0


class TestModuleEntrypoint:
    def test_python_dash_m_invokes_cli_main(self, monkeypatch):
        import runpy

        monkeypatch.setattr("polaris_mcp.cli.main", lambda argv=None: 0)
        try:
            runpy.run_module("polaris_mcp", run_name="__main__", alter_sys=True)
        except SystemExit as exc:
            assert exc.code == 0
        else:
            raise AssertionError("python -m polaris_mcp should exit via sys.exit")


def _payload(claims: dict) -> str:
    import base64
    import json as jsonlib

    raw = base64.urlsafe_b64encode(jsonlib.dumps(claims).encode()).rstrip(b"=").decode()
    return raw
