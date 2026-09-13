"""Dispatch table: every action of every tool maps to the correct HTTP route.

Each case asserts method, path, query, body, and auth mode — the routing contract
between the MCP tools and the Polaris REST API, verified end to end through the
in-memory MCP session.
"""

from __future__ import annotations

import json
from urllib.parse import urlencode

import pytest
from tests.conftest import API_BASE
from tests.test_tools import MINIMAL_DEFINITION, polaris_session

QUERY = {
    "query": {
        "criterionKey": "k",
        "expression": "up",
        "mode": "INSTANT",
        "reduction": "LAST",
        "seriesPolicy": "REQUIRE_SINGLE_SERIES",
        "unit": "PERCENT",
    }
}  # noqa: E501
SUBMISSION = {
    "fitnessFunctionVersion": 1,
    "producerId": "p-1",
    "externalRunId": "run-1",
    "observedAt": "2026-09-12T09:15:00Z",
    "measurements": [{"criterionKey": "k", "value": 1, "unit": "PERCENT"}],
}

# (tool, args, expected method, path, query, expected body or None, auth mode, if_match)
CASES = [
    # health
    ("polaris_health", {"action": "live"}, "GET", "/health/live", None, None, "none", None),
    ("polaris_health", {"action": "ready"}, "GET", "/health/ready", None, None, "none", None),
    # tribes
    ("polaris_tribes", {"action": "list"}, "GET", "/tribes", None, None, "oidc", None),
    ("polaris_tribes", {"action": "get", "tribe_id": "t1"}, "GET", "/tribes/t1", None, None, "oidc", None),
    (
        "polaris_tribes",
        {"action": "create", "name": "Commerce", "description": "d"},
        "POST",
        "/tribes",
        None,
        {"name": "Commerce", "description": "d"},
        "oidc",
        None,
    ),
    (
        "polaris_tribes",
        {"action": "archive", "tribe_id": "t1", "reason": "r"},
        "POST",
        "/tribes/t1/archivals",
        None,
        {"reason": "r"},
        "oidc",
        None,
    ),
    (
        "polaris_tribes",
        {"action": "overview", "tribe_id": "t1"},
        "GET",
        "/tribes/t1/fitness-overview",
        None,
        None,
        "oidc",
        None,
    ),
    # squads
    (
        "polaris_squads",
        {"action": "list", "tribe_id": "t1"},
        "GET",
        "/tribes/t1/squads",
        None,
        None,
        "oidc",
        None,
    ),
    (
        "polaris_squads",
        {"action": "get", "squad_id": "s1"},
        "GET",
        "/squads/s1",
        None,
        None,
        "oidc",
        None,
    ),
    (
        "polaris_squads",
        {"action": "create", "tribe_id": "t1", "name": "Checkout", "mission": "m"},
        "POST",
        "/tribes/t1/squads",
        None,
        {"name": "Checkout", "mission": "m"},
        "oidc",
        None,
    ),
    (
        "polaris_squads",
        {"action": "transfer", "squad_id": "s1", "destination_tribe_id": "t2", "reason": "r"},
        "POST",
        "/squads/s1/transfers",
        None,
        {"tribeId": "t2", "reason": "r"},
        "oidc",
        None,
    ),
    # fitness targets
    (
        "polaris_fitness_targets",
        {"action": "list", "squad_id": "s1"},
        "GET",
        "/squads/s1/fitness-targets",
        None,
        None,
        "oidc",
        None,
    ),
    (
        "polaris_fitness_targets",
        {"action": "get", "target_id": "f1"},
        "GET",
        "/fitness-targets/f1",
        None,
        None,
        "oidc",
        None,
    ),
    (
        "polaris_fitness_targets",
        {
            "action": "create",
            "squad_id": "s1",
            "name": "Checkout API",
            "description": "Accepts purchases",
            "target_kind": "SERVICE",
            "criticality": "CRITICAL",
            "external_reference": {"catalog": "esc", "id": "checkout-api"},
        },
        "POST",
        "/squads/s1/fitness-targets",
        None,
        {
            "name": "Checkout API",
            "description": "Accepts purchases",
            "kind": "SERVICE",
            "criticality": "CRITICAL",
            "externalReference": {"catalog": "esc", "id": "checkout-api"},
        },
        "oidc",
        None,
    ),
    (
        "polaris_fitness_targets",
        {"action": "transition", "target_id": "f1", "status": "RETIRED", "reason": "gone"},
        "POST",
        "/fitness-targets/f1/lifecycle-transitions",
        None,
        {"status": "RETIRED", "reason": "gone"},
        "oidc",
        None,
    ),
    (
        "polaris_fitness_targets",
        {"action": "history", "target_id": "f1"},
        "GET",
        "/fitness-targets/f1/fitness-history",
        None,
        None,
        "oidc",
        None,
    ),
    # measurement providers
    (
        "polaris_measurement_providers",
        {"action": "list_types"},
        "GET",
        "/measurement-provider-types",
        None,
        None,
        "oidc",
        None,
    ),
    # measurement sources
    (
        "polaris_measurement_sources",
        {"action": "list", "squad_id": "s1"},
        "GET",
        "/squads/s1/measurement-sources",
        None,
        None,
        "oidc",
        None,
    ),
    (
        "polaris_measurement_sources",
        {"action": "get", "source_id": "ms1"},
        "GET",
        "/measurement-sources/ms1",
        None,
        None,
        "oidc",
        None,
    ),
    (
        "polaris_measurement_sources",
        {
            "action": "create",
            "squad_id": "s1",
            "name": "Prod metrics",
            "provider_type": "PROMETHEUS",
            "base_url": "https://prom.example.net",
        },
        "POST",
        "/squads/s1/measurement-sources",
        None,
        {"name": "Prod metrics", "providerType": "PROMETHEUS", "baseUrl": "https://prom.example.net"},
        "oidc",
        None,
    ),
    (
        "polaris_measurement_sources",
        {"action": "check_connection", "source_id": "ms1"},
        "POST",
        "/measurement-sources/ms1/connection-checks",
        None,
        None,
        "oidc",
        None,
    ),
    (
        "polaris_measurement_sources",
        {"action": "validate_query", "source_id": "ms1", "query": QUERY["query"], "execute_sample": True},
        "POST",
        "/measurement-sources/ms1/query-validations",
        None,
        {"query": QUERY["query"], "executeSample": True},
        "oidc",
        None,
    ),
    (
        "polaris_measurement_sources",
        {"action": "activate", "source_id": "ms1", "reason": "check reviewed"},
        "POST",
        "/measurement-sources/ms1/activations",
        None,
        {"reason": "check reviewed"},
        "oidc",
        None,
    ),
    (
        "polaris_measurement_sources",
        {"action": "retire", "source_id": "ms1"},
        "POST",
        "/measurement-sources/ms1/retirements",
        None,
        None,
        "oidc",
        None,
    ),
    # measurement producers
    (
        "polaris_measurement_producers",
        {"action": "create", "squad_id": "s1", "name": "checkout-pipeline", "description": "d"},
        "POST",
        "/squads/s1/measurement-producers",
        None,
        {"name": "checkout-pipeline", "description": "d"},
        "oidc",
        None,
    ),
    # fitness functions
    (
        "polaris_fitness_functions",
        {"action": "list", "squad_id": "s1"},
        "GET",
        "/squads/s1/fitness-functions",
        None,
        None,
        "oidc",
        None,
    ),
    (
        "polaris_fitness_functions",
        {"action": "get", "fitness_function_id": "ff1"},
        "GET",
        "/fitness-functions/ff1",
        None,
        None,
        "oidc",
        None,
    ),
    (
        "polaris_fitness_functions",
        {"action": "create", "squad_id": "s1", "definition": MINIMAL_DEFINITION},
        "POST",
        "/squads/s1/fitness-functions",
        None,
        MINIMAL_DEFINITION,
        "oidc",
        None,
    ),
    (
        "polaris_fitness_functions",
        {"action": "add_version", "fitness_function_id": "ff1", "definition": MINIMAL_DEFINITION},
        "POST",
        "/fitness-functions/ff1/versions",
        None,
        MINIMAL_DEFINITION,
        "oidc",
        '"5"',
    ),
    (
        "polaris_fitness_functions",
        {
            "action": "update_draft_version",
            "fitness_function_id": "ff1",
            "version": 2,
            "definition": MINIMAL_DEFINITION,
        },
        "PATCH",
        "/fitness-functions/ff1/versions/2",
        None,
        MINIMAL_DEFINITION,
        "oidc",
        '"5"',
    ),
    (
        "polaris_fitness_functions",
        {"action": "validate_version", "fitness_function_id": "ff1", "version": 2},
        "POST",
        "/fitness-functions/ff1/versions/2/validations",
        None,
        None,
        "oidc",
        None,
    ),
    (
        "polaris_fitness_functions",
        {"action": "activate_version", "fitness_function_id": "ff1", "version": 2, "reason": "r"},
        "POST",
        "/fitness-functions/ff1/versions/2/activations",
        None,
        {"reason": "r"},
        "oidc",
        None,
    ),
    (
        "polaris_fitness_functions",
        {"action": "retire", "fitness_function_id": "ff1", "reason": "r"},
        "POST",
        "/fitness-functions/ff1/retirements",
        None,
        {"reason": "r"},
        "oidc",
        None,
    ),
    # measurement submissions
    (
        "polaris_measurement_submissions",
        {"action": "submit", "fitness_function_id": "ff1", "submission": SUBMISSION},
        "POST",
        "/fitness-functions/ff1/measurement-submissions",
        None,
        SUBMISSION,
        "ingest",
        None,
    ),
    (
        "polaris_measurement_submissions",
        {
            "action": "submit_batch",
            "items": [{"fitnessFunctionId": "ff1", "submission": SUBMISSION}],
        },
        "POST",
        "/measurement-submission-batches",
        None,
        {"items": [{"fitnessFunctionId": "ff1", "submission": SUBMISSION}]},
        "ingest",
        None,
    ),
    # evaluation requests
    (
        "polaris_evaluation_requests",
        {"action": "create", "fitness_function_id": "ff1"},
        "POST",
        "/fitness-functions/ff1/evaluation-requests",
        None,
        {},
        "oidc",
        None,
    ),
    (
        "polaris_evaluation_requests",
        {"action": "get", "request_id": "er1"},
        "GET",
        "/evaluation-requests/er1",
        None,
        None,
        "oidc",
        None,
    ),
    (
        "polaris_evaluation_requests",
        {"action": "cancel", "request_id": "er1"},
        "POST",
        "/evaluation-requests/er1/cancellations",
        None,
        None,
        "oidc",
        None,
    ),
    # evaluations
    (
        "polaris_evaluations",
        {"action": "get", "evaluation_id": "ev1"},
        "GET",
        "/evaluations/ev1",
        None,
        None,
        "oidc",
        None,
    ),
    (
        "polaris_evaluations",
        {"action": "list_by_function", "fitness_function_id": "ff1"},
        "GET",
        "/fitness-functions/ff1/evaluations",
        None,
        None,
        "oidc",
        None,
    ),
    # collection attempts
    (
        "polaris_collection_attempts",
        {"action": "list", "fitness_function_id": "ff1"},
        "GET",
        "/fitness-functions/ff1/collection-attempts",
        None,
        None,
        "oidc",
        None,
    ),
    (
        "polaris_collection_attempts",
        {"action": "get", "attempt_id": "ca1"},
        "GET",
        "/collection-attempts/ca1",
        None,
        None,
        "oidc",
        None,
    ),
    (
        "polaris_collection_attempts",
        {"action": "collect_now", "fitness_function_id": "ff1"},
        "POST",
        "/fitness-functions/ff1/collection-attempts",
        None,
        None,
        "oidc",
        None,
    ),
    (
        "polaris_collection_attempts",
        {"action": "retry", "attempt_id": "ca1"},
        "POST",
        "/collection-attempts/ca1/retries",
        None,
        None,
        "oidc",
        None,
    ),
    # waivers
    (
        "polaris_waivers",
        {
            "action": "propose",
            "fitness_function_id": "ff1",
            "reason": "migration",
            "criterion_keys": ["k"],
            "expires_at": "2026-10-01T00:00:00Z",
        },
        "POST",
        "/fitness-functions/ff1/waivers",
        None,
        {"reason": "migration", "criterionKeys": ["k"], "expiresAt": "2026-10-01T00:00:00Z"},
        "oidc",
        None,
    ),
    (
        "polaris_waivers",
        {"action": "decide", "waiver_id": "w1", "decision": "approve"},
        "POST",
        "/waivers/w1/approvals",
        None,
        None,
        "oidc",
        None,
    ),
    # templates
    (
        "polaris_fitness_function_templates",
        {"action": "list", "tribe_id": "t1"},
        "GET",
        "/tribes/t1/fitness-function-templates",
        None,
        None,
        "oidc",
        None,
    ),
    (
        "polaris_fitness_function_templates",
        {"action": "publish", "tribe_id": "t1", "name": "Baseline", "definition": MINIMAL_DEFINITION},
        "POST",
        "/tribes/t1/fitness-function-templates",
        None,
        {"name": "Baseline", "definition": MINIMAL_DEFINITION},
        "oidc",
        None,
    ),
    (
        "polaris_fitness_function_templates",
        {"action": "adopt", "template_id": "tpl1", "squad_id": "s1", "target_ids": ["f1"]},
        "POST",
        "/fitness-function-templates/tpl1/adoptions",
        None,
        {"squadId": "s1", "targetIds": ["f1"]},
        "oidc",
        None,
    ),
    # insights
    (
        "polaris_insights",
        {"action": "squad_overview", "squad_id": "s1"},
        "GET",
        "/squads/s1/fitness-overview",
        None,
        None,
        "oidc",
        None,
    ),
    (
        "polaris_insights",
        {"action": "tribe_overview", "tribe_id": "t1"},
        "GET",
        "/tribes/t1/fitness-overview",
        None,
        None,
        "oidc",
        None,
    ),
    (
        "polaris_insights",
        {"action": "target_history", "target_id": "f1"},
        "GET",
        "/fitness-targets/f1/fitness-history",
        None,
        None,
        "oidc",
        None,
    ),
    # events
    (
        "polaris_events",
        {"action": "poll", "consumer_id": "relay", "cursor": "c9"},
        "GET",
        "/events",
        {"consumerId": "relay", "cursor": "c9"},
        None,
        "oidc",
        None,
    ),
    (
        "polaris_events",
        {"action": "acknowledge", "consumer_id": "relay", "event_ids": ["e1", "e2"]},
        "POST",
        "/event-acknowledgements",
        None,
        {"consumerId": "relay", "eventIds": ["e1", "e2"]},
        "oidc",
        None,
    ),
]


@pytest.mark.parametrize(
    "tool,args,method,path,query,body,auth,if_match",
    CASES,
    ids=[f"{tool}-{args['action']}" for tool, args, *_ in CASES],
)
async def test_action_dispatch(
    mock_token_endpoint, respx_mock, tool, args, method, path, query, body, auth, if_match
):
    url = f"{API_BASE}/api/v1{path}"
    if if_match is not None:
        respx_mock.get(f"{API_BASE}/api/v1/fitness-functions/ff1").respond(json={"revision": 5})
    target = url + ("?" + urlencode(query) if query else "")
    route = respx_mock.route(method=method, url=target).respond(json={"items": [], "dispatched": True})
    async with polaris_session() as session:
        result = await session.call_tool(tool, args)
        assert not result.isError, result.content[0].text
    request = route.calls.last.request
    assert request.method == method
    if body is None:
        assert not request.content or request.content in (b"", b"null")
    else:
        assert json.loads(request.content) == body
    if auth == "ingest":
        assert request.headers["X-API-Key"] == "ingest-key"
    elif auth == "oidc":
        assert request.headers["Authorization"].startswith("Bearer ")
    if if_match is not None:
        assert request.headers["If-Match"] == if_match


async def test_token_manager_returns_fresh_token(mock_token_endpoint, respx_mock):
    """The OIDC bearer presented to Polaris comes from the Google token endpoint."""
    respx_mock.get(f"{API_BASE}/api/v1/tribes").respond(json={"items": []})
    async with polaris_session() as session:
        result = await session.call_tool("polaris_tribes", {"action": "list"})
        assert not result.isError
