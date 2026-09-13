"""Tests for the Polaris HTTP client: auth modes, retries, errors, pagination, If-Match."""

from __future__ import annotations

import httpx
import pytest
from tests.conftest import API_BASE

from polaris_mcp.client import PolarisClient, paginate, resolve_if_match
from polaris_mcp.errors import PolarisError

TRIBES_URL = f"{API_BASE}/api/v1/tribes"
PROBLEM = {
    "type": "https://polaris.local/problems/conflict",
    "title": "Conflict",
    "status": 409,
    "code": "RESOURCE_CONFLICT",
    "detail": "aggregate revision mismatch: expected 4, got 5",
    "correlationId": "corr_01K0RA",
}


class FakeTokens:
    def __init__(self, token: str = "tok-1") -> None:
        self.token = token
        self.forced_refreshes = 0

    async def get_id_token(self, *, force_refresh: bool = False) -> str:
        if force_refresh:
            self.forced_refreshes += 1
            self.token = "tok-refreshed"
        return self.token


def problem_body(status: int, code: str, detail: str = "boom") -> dict:
    return {
        "type": f"https://polaris.local/problems/{status}",
        "title": "Problem",
        "status": status,
        "code": code,
        "detail": detail,
        "correlationId": "corr_1",
    }


@pytest.fixture
def client(settings):
    return PolarisClient(settings, tokens=FakeTokens())


class TestAuthModes:
    async def test_oidc_bearer_header(self, client, respx_mock):
        route = respx_mock.get(TRIBES_URL).respond(json={"items": []})
        await client.get("/tribes")
        assert route.calls.last.request.headers["Authorization"] == "Bearer tok-1"

    async def test_anonymous_health(self, client, respx_mock):
        route = respx_mock.get(f"{API_BASE}/api/v1/health/live").respond(json={"status": "ok"})
        assert await client.get("/health/live", auth="none") == {"status": "ok"}
        assert "Authorization" not in route.calls.last.request.headers

    async def test_ingest_api_key_header(self, client, respx_mock):
        route = respx_mock.post(f"{API_BASE}/api/v1/measurement-submission-batches").respond(
            json={"items": []}
        )
        await client.post("/measurement-submission-batches", auth="ingest", json={"items": []})
        headers = route.calls.last.request.headers
        assert headers["X-API-Key"] == "ingest-key"
        assert "Authorization" not in headers

    async def test_ingest_without_configured_key_raises(self, no_ingest_settings):
        unauth = PolarisClient(no_ingest_settings, tokens=FakeTokens())
        with pytest.raises(PolarisError, match="MISSING_INGEST_KEY"):
            await unauth.post("/measurement-submission-batches", auth="ingest", json={})


class TestRetriesAndErrors:
    async def test_401_forces_refresh_and_retries_once(self, client, respx_mock):
        respx_mock.get(TRIBES_URL).mock(
            side_effect=[
                httpx.Response(401, json=problem_body(401, "UNAUTHENTICATED")),
                httpx.Response(200, json={"items": ["tribe"]}),
            ]
        )
        result = await client.get("/tribes")
        assert result == {"items": ["tribe"]}
        assert client.tokens.forced_refreshes == 1  # type: ignore[attr-defined]

    async def test_problem_json_raises_polaris_error(self, client, respx_mock):
        respx_mock.get(TRIBES_URL).respond(status_code=409, json=PROBLEM)
        with pytest.raises(PolarisError) as excinfo:
            await client.get("/tribes")
        assert excinfo.value.code == "RESOURCE_CONFLICT"
        assert excinfo.value.status == 409
        assert "corr_01K0RA" in str(excinfo.value)

    async def test_non_json_error_still_raises(self, client, respx_mock):
        respx_mock.get(TRIBES_URL).respond(status_code=502, text="bad gateway")
        with pytest.raises(PolarisError, match="502"):
            await client.get("/tribes")

    async def test_empty_success_body_returns_empty_dict(self, client, respx_mock):
        respx_mock.post(f"{API_BASE}/api/v1/tribes/t1/archivals").respond(status_code=201)
        assert await client.post("/tribes/t1/archivals") == {}

    async def test_non_json_success_wraps_raw(self, client, respx_mock):
        respx_mock.get(TRIBES_URL).respond(status_code=200, text="not json")
        assert await client.get("/tribes") == {"raw": "not json"}

    async def test_non_dict_page_passthrough(self, client, respx_mock):
        respx_mock.get(TRIBES_URL).respond(json=[1, 2])
        page = await paginate(client, "/tribes")
        assert page == {"items": [1, 2], "nextCursor": None}


class TestPagination:
    async def test_single_page_returns_next_cursor(self, client, respx_mock):
        respx_mock.get(TRIBES_URL).respond(json={"items": [{"id": "1"}], "nextCursor": "c1"})
        page = await paginate(client, "/tribes")
        assert page == {"items": [{"id": "1"}], "nextCursor": "c1"}

    async def test_all_pages_follows_cursors(self, client, respx_mock):
        route = respx_mock.get(TRIBES_URL).mock(
            side_effect=[
                httpx.Response(200, json={"items": [{"id": "1"}], "nextCursor": "c1"}),
                httpx.Response(200, json={"items": [{"id": "2"}], "nextCursor": None}),
            ]
        )
        page = await paginate(client, "/tribes", all_pages=True)
        assert page == {"items": [{"id": "1"}, {"id": "2"}], "nextCursor": None}
        assert len(route.calls) == 2
        assert "cursor=c1" in str(route.calls[1].request.url)

    async def test_all_pages_respects_max_items_cap(self, client, respx_mock):
        respx_mock.get(TRIBES_URL).mock(
            side_effect=[
                httpx.Response(200, json={"items": [{"id": str(i)} for i in range(50)], "nextCursor": "c"})
                for _ in range(3)
            ]
        )
        page = await paginate(client, "/tribes", all_pages=True, max_items=60)
        assert len(page["items"]) == 100  # stops after the page that crosses the cap
        assert page["nextCursor"] is not None

    async def test_limit_forwarded_as_query_param(self, client, respx_mock):
        route = respx_mock.get(TRIBES_URL).respond(json={"items": []})
        await paginate(client, "/tribes", limit=25)
        assert "limit=25" in str(route.calls.last.request.url)


class TestIfMatch:
    async def test_explicit_revision_skips_get(self, client, respx_mock):
        get_route = respx_mock.get(f"{API_BASE}/api/v1/fitness-functions/ff").respond(json={"revision": 99})
        route = respx_mock.post(f"{API_BASE}/api/v1/fitness-functions/ff/versions").respond(json={"id": "ff"})
        headers = await resolve_if_match(client, "/fitness-functions/ff", 7)
        await client.post("/fitness-functions/ff/versions", json={}, headers=headers)
        assert route.calls.last.request.headers["If-Match"] == '"7"'
        assert not get_route.calls

    async def test_missing_revision_fetches_aggregate(self, client, respx_mock):
        respx_mock.get(f"{API_BASE}/api/v1/fitness-functions/ff").respond(json={"revision": 3})
        post = respx_mock.post(f"{API_BASE}/api/v1/fitness-functions/ff/versions").respond(json={})
        headers = await resolve_if_match(client, "/fitness-functions/ff", None)
        await client.post("/fitness-functions/ff/versions", json={}, headers=headers)
        assert post.calls.last.request.headers["If-Match"] == '"3"'
