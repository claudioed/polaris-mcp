"""Error types surfaced to MCP clients."""

from __future__ import annotations

from typing import Any


class PolarisError(Exception):
    """A non-2xx response from the Polaris API (RFC 9457 problem document)."""

    def __init__(
        self,
        status: int,
        code: str,
        title: str,
        detail: str | None = None,
        correlation_id: str | None = None,
    ) -> None:
        self.status = status
        self.code = code
        self.title = title
        self.detail = detail
        self.correlation_id = correlation_id
        message = f"{status} {code}: {detail or title}"
        if correlation_id:
            message += f" (correlationId={correlation_id})"
        super().__init__(message)


class AuthError(Exception):
    """Authentication against Google OIDC failed or is not configured."""


class MissingCredentialsError(AuthError):
    """No stored credentials; the user must run `polaris-mcp login`."""

    def __init__(self, message: str | None = None) -> None:
        super().__init__(
            message
            or "No Polaris credentials found. Run `polaris-mcp login` once to connect your Google account."
        )


def problem_from_response(status: int, body: Any, reason: str) -> PolarisError:
    """Build a PolarisError from a parsed problem+json body (or a fallback)."""
    if isinstance(body, dict):
        return PolarisError(
            status=status,
            code=str(body.get("code") or "HTTP_ERROR"),
            title=str(body.get("title") or reason),
            detail=body.get("detail"),
            correlation_id=body.get("correlationId"),
        )
    return PolarisError(status, "HTTP_ERROR", reason, detail=str(body)[:300] if body else None)
