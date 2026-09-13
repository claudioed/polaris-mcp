"""Google OIDC authentication: PKCE login flow, credential storage, token refresh.

The Polaris API verifies Google OpenID Connect ID tokens. ID tokens are short-lived
(~1h), so after a one-time `polaris-mcp login` we keep Google's refresh token on disk
and exchange it for fresh ID tokens whenever needed (the refresh grant returns a new
id_token because the original grant includes the `openid` scope). Claims are decoded
locally without signature verification: tokens come directly from Google's token
endpoint over TLS, and Polaris performs full verification on every request anyway.
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import threading
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

from .config import Settings
from .errors import AuthError, MissingCredentialsError

GOOGLE_AUTH_URI = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URI = "https://oauth2.googleapis.com/token"
OIDC_SCOPES = ("openid", "email")
CLOCK_MARGIN_SECONDS = 60
LOGIN_TIMEOUT_SECONDS = 300
PREFERRED_CALLBACK_PORT = 8887


def parse_id_token_claims(id_token: str) -> dict[str, Any]:
    """Decode the payload segment of a JWT id_token without verifying its signature."""
    parts = id_token.split(".")
    if len(parts) != 3:
        raise AuthError("malformed id_token: expected three JWT segments")
    payload = parts[1]
    payload += "=" * (-len(payload) % 4)
    try:
        claims = json.loads(base64.urlsafe_b64decode(payload))
    except (ValueError, json.JSONDecodeError) as exc:
        raise AuthError(f"malformed id_token payload: {exc}") from exc
    if not isinstance(claims, dict):
        raise AuthError("malformed id_token payload: not a JSON object")
    return claims


@dataclass(frozen=True)
class Credentials:
    """Stored Google OAuth credentials (the refresh token never expires unless revoked)."""

    refresh_token: str
    email: str | None = None


def load_credentials(settings: Settings) -> Credentials | None:
    """Load stored credentials, or None when the user has not logged in yet."""
    path = settings.credentials_file
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise AuthError(f"Cannot read credentials at {path}: {exc}. Re-run `polaris-mcp login`.") from exc
    refresh_token = payload.get("refresh_token")
    if not isinstance(refresh_token, str) or not refresh_token:
        raise AuthError(f"Credentials at {path} are invalid. Re-run `polaris-mcp login`.")
    email = payload.get("email")
    return Credentials(refresh_token=refresh_token, email=email if isinstance(email, str) else None)


def save_credentials(settings: Settings, credentials: Credentials) -> Path:
    """Persist credentials with owner-only permissions."""
    path = settings.credentials_file
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"refresh_token": credentials.refresh_token, "email": credentials.email}))
    path.chmod(0o600)
    return path


class TokenManager:
    """Keeps a valid Google ID token in memory, refreshing it via the stored refresh token."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._credentials = load_credentials(settings)
        self._id_token: str | None = None

    @property
    def credentials(self) -> Credentials | None:
        return self._credentials

    async def get_id_token(self, *, force_refresh: bool = False) -> str:
        if self._credentials is None:
            raise MissingCredentialsError()
        if not force_refresh and self._id_token and not self._expiring(self._id_token):
            return self._id_token
        self._id_token = await self._refresh()
        return self._id_token

    def _expiring(self, id_token: str) -> bool:
        try:
            claims = parse_id_token_claims(id_token)
        except AuthError:
            return True
        exp = claims.get("exp")
        if exp is None:
            return True
        return time.time() >= float(exp) - CLOCK_MARGIN_SECONDS

    async def _refresh(self) -> str:
        assert self._credentials is not None
        data: dict[str, str] = {
            "grant_type": "refresh_token",
            "refresh_token": self._credentials.refresh_token,
            "client_id": self._settings.oidc_client_id,
        }
        if self._settings.oidc_client_secret:
            data["client_secret"] = self._settings.oidc_client_secret
        async with httpx.AsyncClient(timeout=self._settings.timeout_seconds) as http:
            resp = await http.post(GOOGLE_TOKEN_URI, data=data)
        if resp.status_code != 200:
            raise AuthError(
                f"Google token refresh failed ({resp.status_code}): {resp.text[:300]}. "
                "If the refresh token was revoked, re-run `polaris-mcp login`."
            )
        id_token = resp.json().get("id_token")
        if not isinstance(id_token, str) or not id_token:
            raise AuthError(
                "Google refresh response did not include an id_token. "
                "Re-run `polaris-mcp login` (the grant needs the `openid` scope)."
            )
        return id_token


class _CallbackHandler(BaseHTTPRequestHandler):
    """Receives Google's OAuth redirect on the loopback listener."""

    def do_GET(self) -> None:  # noqa: N802 - http.server API
        server: _LoginServer = self.server  # type: ignore[assignment]
        parsed = urlparse(self.path)
        if parsed.path not in ("", "/", "/callback"):
            self.send_response(404)
            self.end_headers()
            return
        query = parse_qs(parsed.query)
        if query.get("state", [None])[0] != server.expected_state:
            server.result = {"error": "state_mismatch", "error_description": "OAuth state did not match"}
        elif "error" in query:
            server.result = {
                "error": query["error"][0],
                "error_description": query.get("error_description", [""])[0],
            }
        elif "code" in query:
            server.result = {"code": query["code"][0]}
        else:
            server.result = {"error": "invalid_redirect", "error_description": "no code in redirect"}
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(
            b"<html><body><p>polaris-mcp: login received. You can close this tab.</p></body></html>"
        )
        threading.Thread(target=server.shutdown, daemon=True).start()

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - http.server API
        return


class _LoginServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int], expected_state: str) -> None:
        super().__init__(address, _CallbackHandler)
        self.expected_state = expected_state
        self.result: dict[str, str] | None = None


def _start_callback_server(state: str) -> tuple[_LoginServer, int]:
    for port in (PREFERRED_CALLBACK_PORT, 0):
        try:
            server = _LoginServer(("127.0.0.1", port), state)
            return server, server.server_address[1]
        except OSError:
            continue
    raise AuthError("Could not bind a loopback port for the OAuth redirect")


def _exchange_code(settings: Settings, code: str, redirect_uri: str, code_verifier: str) -> dict[str, Any]:
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": settings.oidc_client_id,
        "code_verifier": code_verifier,
    }
    if settings.oidc_client_secret:
        data["client_secret"] = settings.oidc_client_secret
    resp = httpx.post(GOOGLE_TOKEN_URI, data=data, timeout=30)
    if resp.status_code != 200:
        raise AuthError(f"Google token exchange failed ({resp.status_code}): {resp.text[:300]}")
    return resp.json()


def run_login(settings: Settings, *, open_browser: bool = True, on_ready: Any = None) -> dict[str, Any]:
    """Run the interactive OAuth authorization-code + PKCE flow and store credentials.

    Returns the id_token claims (email, exp, ...) of the signed-in Google account.
    `on_ready(authorize_url)` is invoked once the loopback listener is accepting
    redirects, before waiting for the browser callback (used by tests and logging).
    """
    if not settings.oidc_client_id:
        raise AuthError(
            "POLARIS_OIDC_CLIENT_ID is not set. Use the same Google OAuth client ID that the "
            "Polaris server verifies (its POLARIS_OIDC_CLIENT_ID), with a loopback redirect URI "
            f"registered (http://localhost:{PREFERRED_CALLBACK_PORT})."
        )
    code_verifier = secrets.token_urlsafe(64)
    code_challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode()).digest()).rstrip(b"=").decode()
    )
    state = secrets.token_urlsafe(24)
    server, port = _start_callback_server(state)
    redirect_uri = f"http://localhost:{port}"
    authorize_url = (
        GOOGLE_AUTH_URI
        + "?"
        + urlencode(
            {
                "response_type": "code",
                "client_id": settings.oidc_client_id,
                "redirect_uri": redirect_uri,
                "scope": " ".join(OIDC_SCOPES),
                "state": state,
                "code_challenge": code_challenge,
                "code_challenge_method": "S256",
                "access_type": "offline",
                "prompt": "consent",
            }
        )
    )
    print(f"Opening browser for Google sign-in: {authorize_url}")
    if open_browser:
        import webbrowser

        webbrowser.open(authorize_url)

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    if on_ready is not None:
        on_ready(authorize_url)
    deadline = time.monotonic() + LOGIN_TIMEOUT_SECONDS
    try:
        while server.result is None and time.monotonic() < deadline:
            time.sleep(0.2)
    finally:
        server.shutdown()
        thread.join(timeout=5)
        server.server_close()
    result = server.result
    if result is None:
        raise AuthError(f"Login timed out after {LOGIN_TIMEOUT_SECONDS}s without a redirect from Google")
    if "code" not in result:
        raise AuthError(
            f"Authorization failed: {result.get('error')}"
            + (f" ({result.get('error_description')})" if result.get("error_description") else "")
        )
    payload = _exchange_code(settings, result["code"], redirect_uri, code_verifier)
    refresh_token = payload.get("refresh_token")
    if not isinstance(refresh_token, str) or not refresh_token:
        raise AuthError(
            "Google did not return a refresh_token (needed for silent renewal). "
            "Re-run `polaris-mcp login` and make sure to approve consent."
        )
    id_token = payload.get("id_token")
    if not isinstance(id_token, str) or not id_token:
        raise AuthError("Google did not return an id_token; the grant requires the `openid` scope.")
    claims = parse_id_token_claims(id_token)
    credentials = Credentials(refresh_token=refresh_token, email=claims.get("email"))
    path = save_credentials(settings, credentials)
    if settings.authorized_email and credentials.email != settings.authorized_email:
        print(
            f"WARNING: signed in as {credentials.email}, but Polaris authorizes only "
            f"{settings.authorized_email}; API calls will fail with 403."
        )
    print(f"Logged in as {credentials.email}. Credentials stored at {path}.")
    return claims
