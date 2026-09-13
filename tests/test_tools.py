"""End-to-end tool tests over an in-memory MCP session."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager

from tests.conftest import API_BASE, tool_payload

from polaris_mcp.server import create_server

EXPECTED_TOOLS = {
    "polaris_health",
    "polaris_tribes",
    "polaris_squads",
    "polaris_fitness_targets",
    "polaris_measurement_providers",
    "polaris_measurement_sources",
    "polaris_measurement_producers",
    "polaris_fitness_functions",
    "polaris_measurement_submissions",
    "polaris_evaluation_requests",
    "polaris_evaluations",
    "polaris_collection_attempts",
    "polaris_waivers",
    "polaris_fitness_function_templates",
    "polaris_insights",
    "polaris_events",
}

MINIMAL_DEFINITION = {
    "name": "Checkout stays available",
    "purpose": "Protect purchases during failures",
    "objective": "Customers complete checkout with one instance down",
    "targetIds": ["t-1"],
    "criteria": [
        {
            "key": "request_failure_rate",
            "unit": "PERCENT",
            "failureComparison": "GREATER_THAN",
            "failureValue": 1.0,
        }
    ],
    "acquisition": {
        "mode": "PUSH",
        "producerId": "p-1",
        "maximumObservationAgeSeconds": 3600,
    },
    "freshnessSeconds": 2592000,
    "enforcement": "OBSERVE",
}


@asynccontextmanager
async def polaris_session():
    """In-memory MCP client session; entered/exited inside the test task on purpose."""
    from mcp.shared.memory import create_connected_server_and_client_session

    server = create_server()
    lowlevel = getattr(server, "_mcp_server", server)
    async with create_connected_server_and_client_session(lowlevel) as session:
        yield session


class TestRegistration:
    async def test_all_tools_registered(self, mock_token_endpoint):
        async with polaris_session() as session:
            result = await session.list_tools()
            names = {tool.name for tool in result.tools}
            assert names >= EXPECTED_TOOLS
            assert len(names) == len(EXPECTED_TOOLS)

    async def test_tools_carry_action_schemas(self, mock_token_endpoint):
        async with polaris_session() as session:
            result = await session.list_tools()
            by_name = {tool.name: tool for tool in result.tools}
            schema = by_name["polaris_tribes"].inputSchema
            assert "action" in schema.get("properties", {})
            assert "tribe_id" in schema.get("properties", {})
            assert schema["properties"]["action"].get("enum") == [
                "list",
                "get",
                "create",
                "archive",
                "overview",
            ]


class TestReadTools:
    async def test_list_tribes_uses_oidc(self, mock_token_endpoint, respx_mock):
        route = respx_mock.get(f"{API_BASE}/api/v1/tribes").respond(
            json={"items": [{"id": "tr-1", "kind": "tribe"}], "nextCursor": None}
        )
        async with polaris_session() as session:
            result = await session.call_tool("polaris_tribes", {"action": "list"})
            assert tool_payload(result) == {
                "items": [{"id": "tr-1", "kind": "tribe"}],
                "nextCursor": None,
            }
        request = route.calls.last.request
        assert request.headers["Authorization"].startswith("Bearer ")

    async def test_health_is_anonymous(self, mock_token_endpoint, respx_mock):
        route = respx_mock.get(f"{API_BASE}/api/v1/health/ready").respond(json={"status": "ok"})
        async with polaris_session() as session:
            result = await session.call_tool("polaris_health", {"action": "ready"})
            assert tool_payload(result) == {"status": "ok"}
        assert "Authorization" not in route.calls.last.request.headers


class TestValidationErrors:
    async def test_missing_required_param_is_tool_error(self, mock_token_endpoint):
        async with polaris_session() as session:
            result = await session.call_tool("polaris_tribes", {"action": "get"})
            assert result.isError
            assert "tribe_id" in result.content[0].text

    async def test_incomplete_definition_lists_missing_keys(self, mock_token_endpoint):
        async with polaris_session() as session:
            result = await session.call_tool(
                "polaris_fitness_functions",
                {"action": "create", "squad_id": "sq-1", "definition": {"name": "x"}},
            )
            assert result.isError
            text = result.content[0].text
            for key in ("purpose", "targetIds", "acquisition", "enforcement"):
                assert key in text


class TestMutations:
    async def test_create_tribe_body(self, mock_token_endpoint, respx_mock):
        route = respx_mock.post(f"{API_BASE}/api/v1/tribes").respond(json={"id": "tr-9"})
        async with polaris_session() as session:
            result = await session.call_tool(
                "polaris_tribes", {"action": "create", "name": "Commerce", "description": "Purchasing"}
            )
            assert tool_payload(result) == {"id": "tr-9"}
        assert json.loads(route.calls.last.request.content) == {
            "name": "Commerce",
            "description": "Purchasing",
        }

    async def test_add_version_auto_fetches_revision(self, mock_token_endpoint, respx_mock):
        respx_mock.get(f"{API_BASE}/api/v1/fitness-functions/ff-1").respond(
            json={"id": "ff-1", "revision": 3}
        )
        route = respx_mock.post(f"{API_BASE}/api/v1/fitness-functions/ff-1/versions").respond(
            json={"id": "ff-1", "revision": 4}
        )
        async with polaris_session() as session:
            result = await session.call_tool(
                "polaris_fitness_functions",
                {
                    "action": "add_version",
                    "fitness_function_id": "ff-1",
                    "definition": MINIMAL_DEFINITION,
                },
            )
            assert tool_payload(result)["revision"] == 4
        request = route.calls.last.request
        assert request.headers["If-Match"] == '"3"'
        assert json.loads(request.content) == MINIMAL_DEFINITION

    async def test_polaris_problem_surfaces_as_tool_error(self, mock_token_endpoint, respx_mock):
        respx_mock.post(f"{API_BASE}/api/v1/tribes/tr-1/archivals").respond(
            status_code=409,
            headers={"Content-Type": "application/problem+json"},
            json={
                "type": "https://polaris.local/problems/conflict",
                "title": "Conflict",
                "status": 409,
                "code": "RESOURCE_CONFLICT",
                "detail": "aggregate revision mismatch",
                "correlationId": "corr_9",
            },
        )
        async with polaris_session() as session:
            result = await session.call_tool("polaris_tribes", {"action": "archive", "tribe_id": "tr-1"})
            assert result.isError
            text = result.content[0].text
            assert "RESOURCE_CONFLICT" in text
            assert "corr_9" in text


class TestIngestTools:
    async def test_submit_sends_api_key_and_body(self, mock_token_endpoint, respx_mock):
        route = respx_mock.post(f"{API_BASE}/api/v1/fitness-functions/ff-1/measurement-submissions").respond(
            json={"evaluationId": "ev-1", "replayed": False}
        )
        submission = {
            "fitnessFunctionVersion": 2,
            "producerId": "p-1",
            "externalRunId": "run-17",
            "observedAt": "2026-09-12T09:15:00Z",
            "measurements": [{"criterionKey": "request_failure_rate", "value": 0.8, "unit": "PERCENT"}],
        }
        async with polaris_session() as session:
            result = await session.call_tool(
                "polaris_measurement_submissions",
                {"action": "submit", "fitness_function_id": "ff-1", "submission": submission},
            )
            payload = tool_payload(result)
            assert payload["evaluationId"] == "ev-1"
        request = route.calls.last.request
        assert request.headers["X-API-Key"] == "ingest-key"
        assert "Authorization" not in request.headers
        assert json.loads(request.content) == submission

    async def test_submit_rejects_incomplete_submission(self, mock_token_endpoint):
        async with polaris_session() as session:
            result = await session.call_tool(
                "polaris_measurement_submissions",
                {
                    "action": "submit",
                    "fitness_function_id": "ff-1",
                    "submission": {"fitnessFunctionVersion": 2},
                },
            )
            assert result.isError
            assert "externalRunId" in result.content[0].text

    async def test_batch_rejects_oversized_items(self, mock_token_endpoint):
        items = [
            {"fitnessFunctionId": "ff-1", "submission": {"fitnessFunctionVersion": 1}} for _ in range(101)
        ]
        async with polaris_session() as session:
            result = await session.call_tool(
                "polaris_measurement_submissions", {"action": "submit_batch", "items": items}
            )
            assert result.isError
            assert "1..100" in result.content[0].text

    async def test_batch_rejects_malformed_items(self, mock_token_endpoint):
        async with polaris_session() as session:
            for bad in ([{"submission": {}}], [{"fitnessFunctionId": "ff-1"}], [{"nope": 1}]):
                result = await session.call_tool(
                    "polaris_measurement_submissions", {"action": "submit_batch", "items": bad}
                )
                assert result.isError
                assert "fitnessFunctionId" in result.content[0].text or "submission" in result.content[0].text


class TestEventTools:
    async def test_poll_requires_consumer_id_query(self, mock_token_endpoint, respx_mock):
        route = respx_mock.get(f"{API_BASE}/api/v1/events").respond(
            json={"items": [{"id": "e-1"}], "nextCursor": None}
        )
        async with polaris_session() as session:
            result = await session.call_tool(
                "polaris_events", {"action": "poll", "consumer_id": "relay", "limit": 10}
            )
            assert tool_payload(result)["items"] == [{"id": "e-1"}]
        url = str(route.calls.last.request.url)
        assert "consumerId=relay" in url
        assert "limit=10" in url

    async def test_acknowledge_body(self, mock_token_endpoint, respx_mock):
        route = respx_mock.post(f"{API_BASE}/api/v1/event-acknowledgements").respond(
            json={"consumerId": "relay", "eventIds": ["e-1"]}
        )
        async with polaris_session() as session:
            result = await session.call_tool(
                "polaris_events",
                {"action": "acknowledge", "consumer_id": "relay", "event_ids": ["e-1"]},
            )
            assert tool_payload(result) == {"consumerId": "relay", "eventIds": ["e-1"]}
        assert json.loads(route.calls.last.request.content) == {
            "consumerId": "relay",
            "eventIds": ["e-1"],
        }


class TestWaivers:
    async def test_decide_maps_transition_segment(self, mock_token_endpoint, respx_mock):
        route = respx_mock.post(f"{API_BASE}/api/v1/waivers/w-1/rejections").respond(json={"id": "w-1"})
        async with polaris_session() as session:
            result = await session.call_tool(
                "polaris_waivers",
                {"action": "decide", "waiver_id": "w-1", "decision": "reject", "reason": "not acceptable"},
            )
            assert tool_payload(result) == {"id": "w-1"}
        assert json.loads(route.calls.last.request.content) == {"reason": "not acceptable"}
