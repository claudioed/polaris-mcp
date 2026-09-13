"""Async HTTP client for the Polaris REST API (auth, ETag, errors, pagination)."""

from __future__ import annotations

from typing import Any

import httpx

from .auth import TokenManager
from .config import Settings
from .errors import PolarisError, problem_from_response

DEFAULT_MAX_PAGES = 10
DEFAULT_MAX_ITEMS = 1000


class PolarisClient:
    """Thin Polaris API wrapper handling the three auth modes and problem+json errors."""

    def __init__(self, settings: Settings, tokens: TokenManager | None = None) -> None:
        self.settings = settings
        self.tokens = tokens or TokenManager(settings)
        self._http = httpx.AsyncClient(
            base_url=settings.api_base_url,
            timeout=settings.timeout_seconds,
            headers={"Accept": "application/json, application/problem+json"},
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def request(
        self,
        method: str,
        path: str,
        *,
        auth: str = "oidc",
        params: dict[str, Any] | None = None,
        json: Any = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        base_headers = dict(headers or {})
        if auth == "ingest":
            if not self.settings.ingest_api_key:
                raise PolarisError(
                    0,
                    "MISSING_INGEST_KEY",
                    "POLARIS_INGEST_API_KEY is not configured",
                    "The measurement-submission endpoints require the ingest X-API-Key.",
                )
            base_headers["X-API-Key"] = self.settings.ingest_api_key
        elif auth == "oidc":
            token = await self.tokens.get_id_token()
            base_headers["Authorization"] = f"Bearer {token}"
        resp = await self._http.request(method, path, params=params, json=json, headers=base_headers)
        if resp.status_code == 401 and auth == "oidc":
            refreshed = await self.tokens.get_id_token(force_refresh=True)
            retry_headers = dict(headers or {})
            retry_headers["Authorization"] = f"Bearer {refreshed}"
            resp = await self._http.request(method, path, params=params, json=json, headers=retry_headers)
        return self._interpret(resp)

    def _interpret(self, resp: httpx.Response) -> Any:
        if 200 <= resp.status_code < 300:
            if not resp.content:
                return {}
            try:
                return resp.json()
            except ValueError:
                return {"raw": resp.text}
        try:
            body: Any = resp.json()
        except ValueError:
            body = None
        raise problem_from_response(resp.status_code, body, resp.reason_phrase)

    async def get(self, path: str, **kwargs: Any) -> Any:
        return await self.request("GET", path, **kwargs)

    async def post(self, path: str, **kwargs: Any) -> Any:
        return await self.request("POST", path, **kwargs)

    async def patch(self, path: str, **kwargs: Any) -> Any:
        return await self.request("PATCH", path, **kwargs)


async def paginate(
    client: PolarisClient,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    limit: int | None = None,
    cursor: str | None = None,
    all_pages: bool = False,
    max_pages: int = DEFAULT_MAX_PAGES,
    max_items: int = DEFAULT_MAX_ITEMS,
) -> dict[str, Any]:
    """List one page ({items, nextCursor}) or follow cursors up to a safety cap."""
    items: list[Any] = []
    next_cursor: str | None = cursor
    pages = 0
    while True:
        query = dict(params or {})
        if limit is not None:
            query["limit"] = limit
        if next_cursor:
            query["cursor"] = next_cursor
        page = await client.get(path, params=query)
        if not isinstance(page, dict):
            return {"items": page, "nextCursor": None}
        items.extend(page.get("items", []))
        next_cursor = page.get("nextCursor")
        pages += 1
        if not all_pages or not next_cursor or pages >= max_pages or len(items) >= max_items:
            return {"items": items, "nextCursor": next_cursor}


async def resolve_if_match(
    client: PolarisClient,
    aggregate_path: str,
    revision: int | None,
) -> dict[str, str]:
    """Build the If-Match header; fetches the current revision when not supplied."""
    if revision is None:
        aggregate = await client.get(aggregate_path)
        revision = aggregate.get("revision") if isinstance(aggregate, dict) else None
        if revision is None:
            raise PolarisError(
                0, "NO_REVISION", "aggregate has no revision", f"GET {aggregate_path} returned no revision"
            )
    return {"If-Match": f'"{revision}"'}


__all__ = ["PolarisClient", "paginate", "resolve_if_match"]
