"""End-to-end tests for the interactive login flow against a real loopback listener.

Google's endpoints are intercepted with respx; the browser step is replaced by an
`on_ready` hook that hits the loopback redirect like Google would.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from urllib.parse import parse_qs, urlencode, urlparse

import pytest
from tests.conftest import TOKEN_URL, make_id_token

from polaris_mcp.auth import load_credentials, parse_id_token_claims, run_login
from polaris_mcp.errors import AuthError


@pytest.fixture
def google_mock():
    """Intercept only Google's token endpoint; the loopback listener must not be touched."""
    import respx

    with respx.mock(assert_all_mocked=False, assert_all_called=False) as mock:
        yield mock


def _callback_driver(query_params: dict[str, str]):
    """Build an on_ready hook that reads the state, then hits the loopback redirect.

    Uses urllib (not httpx) on purpose: respx intercepts every httpx request in the
    test, while the loopback listener must be reached for real.
    """

    def on_ready(authorize_url: str) -> None:
        query = parse_qs(urlparse(authorize_url).query)
        state = query["state"][0]
        port = urlparse(query["redirect_uri"][0]).port
        params = {"state": state, **query_params}
        last_error = None
        for _ in range(50):
            try:
                with urllib.request.urlopen(  # noqa: S310 - fixed loopback scheme
                    f"http://127.0.0.1:{port}/callback?{urlencode(params)}", timeout=2
                ) as response:
                    assert response.status == 200
                    return
            except OSError as exc:  # server not accepting yet
                last_error = exc
        raise AssertionError(f"loopback listener never came up: {last_error}")

    return on_ready


def _settings_with_fresh_file(settings):
    settings.credentials_file.unlink(missing_ok=True)
    return settings


class TestLoginSuccess:
    def test_full_flow_stores_credentials(self, settings, google_mock):
        id_token = make_id_token(email="user@example.com")
        exchange = google_mock.post(TOKEN_URL).respond(
            json={"id_token": id_token, "refresh_token": "rt-new", "access_token": "at"}
        )
        claims = run_login(
            _settings_with_fresh_file(settings),
            open_browser=False,
            on_ready=_callback_driver({"code": "auth-code"}),
        )
        assert claims["email"] == "user@example.com"
        stored = load_credentials(settings)
        assert stored is not None and stored.refresh_token == "rt-new"
        request = exchange.calls.last.request
        body = request.content.decode()
        assert "grant_type=authorization_code" in body
        assert "code=auth-code" in body
        assert "code_verifier=" in body
        assert settings.credentials_file.stat().st_mode & 0o777 == 0o600

    def test_authorized_email_mismatch_warns_but_stores(self, settings, google_mock, capsys):
        from dataclasses import replace

        google_mock.post(TOKEN_URL).respond(
            json={"id_token": make_id_token(email="other@example.com"), "refresh_token": "rt"}
        )
        claims = run_login(
            replace(_settings_with_fresh_file(settings), authorized_email="user@example.com"),
            open_browser=False,
            on_ready=_callback_driver({"code": "c"}),
        )
        assert claims["email"] == "other@example.com"
        assert load_credentials(settings) is not None
        assert "WARNING" in capsys.readouterr().out

    def test_state_mismatch_rejected(self, settings, google_mock):
        google_mock.post(TOKEN_URL)
        with pytest.raises(AuthError, match="state_mismatch"):
            run_login(
                _settings_with_fresh_file(settings),
                open_browser=False,
                on_ready=_callback_driver({"code": "c", "state": "forged"}),
            )

    def test_access_denied_surfaced(self, settings, google_mock):
        google_mock.post(TOKEN_URL)
        with pytest.raises(AuthError, match="access_denied"):
            run_login(
                _settings_with_fresh_file(settings),
                open_browser=False,
                on_ready=_callback_driver({"error": "access_denied"}),
            )

    def test_redirect_without_code_rejected(self, settings, google_mock):
        google_mock.post(TOKEN_URL)
        with pytest.raises(AuthError, match="invalid_redirect"):
            run_login(
                _settings_with_fresh_file(settings),
                open_browser=False,
                on_ready=_callback_driver({}),
            )

    def test_no_refresh_token_in_exchange(self, settings, google_mock):
        google_mock.post(TOKEN_URL).respond(json={"id_token": make_id_token()})
        with pytest.raises(AuthError, match="refresh_token"):
            run_login(
                _settings_with_fresh_file(settings),
                open_browser=False,
                on_ready=_callback_driver({"code": "c"}),
            )

    def test_exchange_failure(self, settings, google_mock):
        google_mock.post(TOKEN_URL).respond(status_code=400, json={"error": "invalid_grant"})
        with pytest.raises(AuthError, match="token exchange failed"):
            run_login(
                _settings_with_fresh_file(settings),
                open_browser=False,
                on_ready=_callback_driver({"code": "c"}),
            )

    def test_saved_credentials_are_valid_json(self, settings, google_mock):
        google_mock.post(TOKEN_URL).respond(json={"id_token": make_id_token(), "refresh_token": "rt"})
        run_login(
            _settings_with_fresh_file(settings),
            open_browser=False,
            on_ready=_callback_driver({"code": "c"}),
        )
        payload = json.loads(settings.credentials_file.read_text())
        assert payload["refresh_token"] == "rt"
        assert "email" in payload
        assert parse_id_token_claims(make_id_token())["email"]

    def test_exchange_sends_client_secret_when_configured(self, settings, google_mock):
        from dataclasses import replace

        exchange = google_mock.post(TOKEN_URL).respond(
            json={"id_token": make_id_token(), "refresh_token": "rt"}
        )
        run_login(
            replace(_settings_with_fresh_file(settings), oidc_client_secret="s3cret"),
            open_browser=False,
            on_ready=_callback_driver({"code": "c"}),
        )
        body = exchange.calls.last.request.content.decode()
        assert "client_secret=s3cret" in body

    def test_exchange_without_id_token(self, settings, google_mock):
        google_mock.post(TOKEN_URL).respond(json={"refresh_token": "rt"})
        with pytest.raises(AuthError, match="id_token"):
            run_login(
                _settings_with_fresh_file(settings),
                open_browser=False,
                on_ready=_callback_driver({"code": "c"}),
            )

    def test_unrelated_callback_path_is_ignored(self, settings, google_mock):
        """Non-callback paths (e.g. favicon probes) get a 404 without ending the flow."""
        google_mock.post(TOKEN_URL).respond(json={"id_token": make_id_token(), "refresh_token": "rt"})

        def on_ready(authorize_url: str) -> None:
            query = parse_qs(urlparse(authorize_url).query)
            port = urlparse(query["redirect_uri"][0]).port
            try:
                urllib.request.urlopen(  # noqa: S310 - fixed loopback scheme
                    f"http://127.0.0.1:{port}/favicon.ico", timeout=2
                )
                raise AssertionError("favicon probe should have been rejected with 404")
            except urllib.error.HTTPError as exc:
                assert exc.code == 404
            run_login_probe(port, query["state"][0])

        def run_login_probe(port: int, state: str) -> None:
            with urllib.request.urlopen(  # noqa: S310 - fixed loopback scheme
                f"http://127.0.0.1:{port}/callback?{urlencode({'state': state, 'code': 'c'})}",
                timeout=2,
            ) as response:
                assert response.status == 200

        claims = run_login(_settings_with_fresh_file(settings), open_browser=False, on_ready=on_ready)
        assert claims["email"] == "user@example.com"

    def test_login_waits_for_delayed_callback(self, settings, google_mock):
        """The poll loop sleeps while the browser has not redirected yet."""
        google_mock.post(TOKEN_URL).respond(json={"id_token": make_id_token(), "refresh_token": "rt"})

        def on_ready(authorize_url: str) -> None:
            query = parse_qs(urlparse(authorize_url).query)
            port = urlparse(query["redirect_uri"][0]).port
            state = query["state"][0]

            def delayed() -> None:
                time.sleep(0.5)
                run_login_probe(port, state)

            threading.Thread(target=delayed, daemon=True).start()

        def run_login_probe(port: int, state: str) -> None:
            urllib.request.urlopen(  # noqa: S310 - fixed loopback scheme
                f"http://127.0.0.1:{port}/callback?{urlencode({'state': state, 'code': 'c'})}",
                timeout=2,
            )

        claims = run_login(_settings_with_fresh_file(settings), open_browser=False, on_ready=on_ready)
        assert claims["email"] == "user@example.com"

    def test_login_opens_browser_by_default(self, settings, google_mock, monkeypatch):
        google_mock.post(TOKEN_URL).respond(json={"id_token": make_id_token(), "refresh_token": "rt"})
        opened = {}
        monkeypatch.setattr("webbrowser.open", lambda url: opened.setdefault("url", url) or True)
        run_login(
            _settings_with_fresh_file(settings),
            on_ready=_callback_driver({"code": "c"}),
        )
        assert str(opened["url"]).startswith("https://accounts.google.com/o/oauth2/v2/auth")

    def test_preferred_port_busy_falls_back_to_ephemeral(self, settings, google_mock):
        import socket

        blocker = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        blocker.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        blocker.bind(("127.0.0.1", 8887))
        blocker.listen(1)
        try:
            google_mock.post(TOKEN_URL).respond(json={"id_token": make_id_token(), "refresh_token": "rt"})
            claims = run_login(
                _settings_with_fresh_file(settings),
                open_browser=False,
                on_ready=_callback_driver({"code": "c"}),
            )
            assert claims["email"] == "user@example.com"
        finally:
            blocker.close()

    def test_callback_listener_binds_configured_host(self, settings, google_mock):
        """Container login: POLARIS_CALLBACK_BIND_HOST=0.0.0.0 still serves the loopback redirect."""
        from dataclasses import replace

        google_mock.post(TOKEN_URL).respond(json={"id_token": make_id_token(), "refresh_token": "rt"})
        claims = run_login(
            replace(_settings_with_fresh_file(settings), callback_bind_host="0.0.0.0"),
            open_browser=False,
            on_ready=_callback_driver({"code": "c"}),
        )
        assert claims["email"] == "user@example.com"
        assert load_credentials(settings) is not None

    def test_login_timeout_when_no_redirect_arrives(self, settings, google_mock, monkeypatch):
        import polaris_mcp.auth as auth_module

        monkeypatch.setattr(auth_module, "LOGIN_TIMEOUT_SECONDS", 0.5)
        with pytest.raises(AuthError, match="timed out"):
            run_login(
                _settings_with_fresh_file(settings),
                open_browser=False,
                on_ready=lambda url: None,
            )

    def test_bind_failure_raises_actionable_error(self, settings, monkeypatch):
        import polaris_mcp.auth as auth_module

        class _Unbindable(auth_module._LoginServer):
            def __init__(self, address, expected_state):
                raise OSError("address in use")

        monkeypatch.setattr(auth_module, "_LoginServer", _Unbindable)
        with pytest.raises(AuthError, match="Could not bind"):
            run_login(_settings_with_fresh_file(settings), open_browser=False)
