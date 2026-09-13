"""End-to-end tests for the interactive login flow against a real loopback listener.

Google's endpoints are intercepted with respx; the browser step is replaced by an
`on_ready` hook that hits the loopback redirect like Google would.
"""

from __future__ import annotations

import json
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
