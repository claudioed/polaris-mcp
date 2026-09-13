"""Fitness functions: versioned definitions with optimistic-concurrency-guarded mutations."""

from __future__ import annotations

from typing import Any, Literal

from mcp.server.fastmcp import FastMCP


def register(mcp: FastMCP) -> None:
    from ..client import paginate, resolve_if_match
    from ..runtime import get_client
    from ._support import (
        FITNESS_DEFINITION_KEYS,
        optional_body,
        require,
        require_object,
    )

    @mcp.tool()
    async def polaris_fitness_functions(
        action: Literal[
            "list",
            "get",
            "create",
            "add_version",
            "update_draft_version",
            "validate_version",
            "activate_version",
            "retire",
        ],
        squad_id: str | None = None,
        fitness_function_id: str | None = None,
        version: int | None = None,
        revision: int | None = None,
        definition: dict[str, Any] | None = None,
        reason: str | None = None,
        limit: int | None = None,
        cursor: str | None = None,
        all_pages: bool = False,
    ) -> dict:
        """Manage fitness functions: versioned definitions of intent, scope, criteria, acquisition,
        freshness, and enforcement. Definitions evolve as immutable draft-then-activate versions.

        Actions and required parameters:
        - list: squad_id — the squad's functions with full version history (limit/cursor/all_pages)
        - get: fitness_function_id — aggregate with lifecycle (DRAFT|ACTIVE|RETIRED), revision, and
          complete version history
        - create: squad_id + definition — creates the function with draft version 1
        - add_version: fitness_function_id + definition — appends a new draft version (guarded by
          If-Match: pass the aggregate `revision` explicitly, or omit it to use the current one)
        - update_draft_version: fitness_function_id + version + definition — replaces a still-DRAFT
          version (If-Match as above; activated versions are immutable)
        - validate_version: fitness_function_id + version — re-runs validation without side effects
        - activate_version: fitness_function_id + version (optional reason) — makes it the active
          definition; evaluations then use it
        - retire: fitness_function_id (optional reason) — terminal; history stays queryable

        `definition` is a JSON object with camelCase keys (Polaris FitnessDefinition):
        required: name; purpose; objective; targetIds (array of the squad's fitness-target ids);
        criteria (array of {key (pattern ^[a-z][a-z0-9_]{0,62}$, unit, warningComparison?,
        warningValue?, failureComparison (GREATER_THAN|GREATER_THAN_OR_EQUAL|LESS_THAN|LESS_THAN_OR_EQUAL|
        EQUAL|NOT_EQUAL), failureValue, required?});
        acquisition ({mode: "PUSH", producerId, maximumObservationAgeSeconds} or {mode: "PULL",
        sourceId, trigger: SCHEDULED|ON_DEMAND, intervalSeconds? (>=60, SCHEDULED only),
        timeoutSeconds (1-30), queries: array of {criterionKey, expression (PromQL), mode:
        INSTANT|RANGE, lookbackSeconds?, stepSeconds?, reduction (LAST|MIN|MAX|AVERAGE|SUM|COUNT),
        seriesPolicy (REQUIRE_SINGLE_SERIES|REDUCE_ACROSS_SERIES|ERROR_ON_MULTIPLE_SERIES), unit}
        covering every criterion key});
        freshnessSeconds (how long an evaluation stays fresh); enforcement (OBSERVE|WARN|BLOCK);
        optional: characteristic (e.g. RELIABILITY), changeRationale.
        Warning thresholds must be milder than failure thresholds when both are declared.
        """
        client = get_client()
        if action == "list":
            require(action, squad_id=squad_id)
            return await paginate(
                client,
                f"/squads/{squad_id}/fitness-functions",
                limit=limit,
                cursor=cursor,
                all_pages=all_pages,
            )
        if action == "get":
            require(action, fitness_function_id=fitness_function_id)
            return await client.get(f"/fitness-functions/{fitness_function_id}")
        if action == "create":
            require(action, squad_id=squad_id)
            require_object(action, "definition", definition, *FITNESS_DEFINITION_KEYS)
            return await client.post(f"/squads/{squad_id}/fitness-functions", json=definition)
        if action == "add_version":
            require(action, fitness_function_id=fitness_function_id)
            require_object(action, "definition", definition, *FITNESS_DEFINITION_KEYS)
            headers = await resolve_if_match(client, f"/fitness-functions/{fitness_function_id}", revision)
            return await client.post(
                f"/fitness-functions/{fitness_function_id}/versions",
                json=definition,
                headers=headers,
            )
        if action == "update_draft_version":
            require(action, fitness_function_id=fitness_function_id, version=version)
            require_object(action, "definition", definition, *FITNESS_DEFINITION_KEYS)
            headers = await resolve_if_match(client, f"/fitness-functions/{fitness_function_id}", revision)
            return await client.patch(
                f"/fitness-functions/{fitness_function_id}/versions/{version}",
                json=definition,
                headers=headers,
            )
        if action == "validate_version":
            require(action, fitness_function_id=fitness_function_id, version=version)
            return await client.post(
                f"/fitness-functions/{fitness_function_id}/versions/{version}/validations"
            )
        if action == "activate_version":
            require(action, fitness_function_id=fitness_function_id, version=version)
            return await client.post(
                f"/fitness-functions/{fitness_function_id}/versions/{version}/activations",
                json=optional_body(reason=reason),
            )
        require(action, fitness_function_id=fitness_function_id)
        return await client.post(
            f"/fitness-functions/{fitness_function_id}/retirements", json=optional_body(reason=reason)
        )
