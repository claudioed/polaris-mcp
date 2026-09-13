"""Tests for Google OIDC auth: claims parsing, credential storage, token refresh."""

from __future__ import annotations

import time

import pytest
from tests.conftest import TOKEN_URL, b64url, make_id_token

from polaris_mcp.auth import (
    Credentials,
    MissingCredentialsError,
    TokenManager,
    load_credentials,
    parse_id_token_claims,
    save_credentials,
)
from polaris_mcp.errors import AuthError


class TestParseClaims:
    def test_roundtrip(self):
        token = make_id_token(email="dev@example.com", exp=2000000000)
        claims = parse_id_token_claims(token)
        assert claims["email"] == "dev@example.com"
        assert claims["exp"] == 2000000000

    def test_malformed_tokens_raise(self):
        for bad in ("", "a.b", "a.b.c.d", f"xx.{b64url(b'not json')}.sig"):
            with pytest.raises(AuthError):
                parse_id_token_claims(bad)


class TestCredentialStorage:
    def test_save_and_load_roundtrip(self, settings):
        save_credentials(settings, Credentials(refresh_token="rt", email="e@example.com"))
        loaded = load_credentials(settings)
        assert loaded == Credentials(refresh_token="rt", email="e@example.com")

    def test_file_is_owner_only(self, settings):
        path = save_credentials(settings, Credentials(refresh_token="rt", email=None))
        assert path.stat().st_mode & 0o777 == 0o600

    def test_missing_file_returns_none(self, settings):
        settings.credentials_file.unlink()
        assert load_credentials(settings) is None

    def test_corrupt_file_raises_actionable_error(self, settings):
        settings.credentials_file.write_text("{nope")
        with pytest.raises(AuthError, match="polaris-mcp login"):
            load_credentials(settings)


class TestTokenManager:
    async def test_missing_credentials_raises(self, settings):
        settings.credentials_file.unlink()
        with pytest.raises(MissingCredentialsError, match="polaris-mcp login"):
            await TokenManager(settings).get_id_token()

    async def test_cached_token_skips_network(self, settings):
        manager = TokenManager(settings)
        manager._id_token = make_id_token()
        token = await manager.get_id_token()
        assert token == manager._id_token

    async def test_expired_cached_token_triggers_refresh(self, settings, respx_mock):
        fresh = make_id_token(exp=int(time.time()) + 3600)
        respx_mock.post(TOKEN_URL).respond(json={"id_token": fresh})
        manager = TokenManager(settings)
        manager._id_token = make_id_token(exp=int(time.time()) - 3600)
        assert await manager.get_id_token() == fresh

    async def test_refresh_failure_raises_auth_error(self, settings, respx_mock):
        respx_mock.post(TOKEN_URL).respond(status_code=400, json={"error": "invalid_grant"})
        with pytest.raises(AuthError, match="re-run `polaris-mcp login`"):
            await TokenManager(settings).get_id_token()

    async def test_refresh_without_id_token_raises(self, settings, respx_mock):
        respx_mock.post(TOKEN_URL).respond(json={"access_token": "at"})
        with pytest.raises(AuthError, match="openid"):
            await TokenManager(settings).get_id_token()

    async def test_malformed_cached_token_forces_refresh(self, settings, respx_mock):
        fresh = make_id_token()
        respx_mock.post(TOKEN_URL).respond(json={"id_token": fresh})
        manager = TokenManager(settings)
        manager._id_token = "garbage"
        assert await manager.get_id_token() == fresh


class TestLogin:
    def test_login_requires_client_id(self, settings):
        from dataclasses import replace

        from polaris_mcp.auth import run_login

        with pytest.raises(AuthError, match="POLARIS_OIDC_CLIENT_ID"):
            run_login(replace(settings, oidc_client_id=""), open_browser=False)


class TestSupportValidation:
    def test_require_object_reports_missing_keys(self):
        from mcp.server.fastmcp.exceptions import ToolError

        from polaris_mcp.tools._support import require, require_list, require_object

        with pytest.raises(ToolError, match="tribe_id"):
            require("get", tribe_id=None)
        with pytest.raises(ToolError, match="missing required key\\(s\\): name"):
            require_object("create", "definition", {"purpose": "x"}, "name", "purpose")
        with pytest.raises(ToolError, match="JSON array"):
            require_list("poll", "event_ids", "nope")
        with pytest.raises(ToolError, match="1..100"):
            require_list("batch", "items", [], min_items=1, max_items=100)
        with pytest.raises(ToolError, match="must be a JSON object"):
            require_object("create", "definition", ["not", "a", "dict"], "name")
        with pytest.raises(ToolError, match="'definition' is required"):
            require_object("create", "definition", None, "name")

    def test_optional_body_drops_nones(self):
        from polaris_mcp.tools._support import optional_body

        assert optional_body(reason=None) is None
        assert optional_body(reason="r", tribeId="t") == {"reason": "r", "tribeId": "t"}
