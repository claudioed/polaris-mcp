"""Measurement sources: squad-owned provider connections (Prometheus)."""

from __future__ import annotations

from typing import Any, Literal

from mcp.server.fastmcp import FastMCP


def register(mcp: FastMCP) -> None:
    from ..client import paginate
    from ..runtime import get_client
    from ._support import optional_body, require, require_object

    @mcp.tool()
    async def polaris_measurement_sources(
        action: Literal["list", "get", "create", "check_connection", "validate_query", "activate", "retire"],
        squad_id: str | None = None,
        source_id: str | None = None,
        name: str | None = None,
        provider_type: Literal["PROMETHEUS"] | None = None,
        base_url: str | None = None,
        description: str | None = None,
        query: dict[str, Any] | None = None,
        execute_sample: bool = False,
        reason: str | None = None,
        limit: int | None = None,
        cursor: str | None = None,
        all_pages: bool = False,
    ) -> dict:
        """Manage measurement sources: squad-owned connections to pull providers.

        Lifecycle: create → DRAFT, then check_connection must succeed, then activate. Retirement is
        rejected (409) while an active fitness-function version still depends on the source.

        Actions and required parameters:
        - list: squad_id (optional limit/cursor/all_pages)
        - get: source_id
        - create: squad_id + name + provider_type (PROMETHEUS) + base_url (optional description).
          Never include credentials; none are stored or returned. Created in DRAFT.
        - check_connection: source_id — probes the provider; retained as evidence. A failed probe
          yields 422 with the provider error in the detail.
        - validate_query: source_id + query (a MetricQuery object; optional execute_sample=true also
          executes it once and returns the sample value with provider evidence). Query keys
          (camelCase): criterionKey, expression (PromQL), mode (INSTANT|RANGE), reduction
          (LAST|MIN|MAX|AVERAGE|SUM|COUNT), seriesPolicy (REQUIRE_SINGLE_SERIES|REDUCE_ACROSS_SERIES|
          ERROR_ON_MULTIPLE_SERIES), unit, plus lookbackSeconds/stepSeconds for RANGE.
        - activate: source_id (optional reason, e.g. which check id was reviewed)
        - retire: source_id (optional reason)

        Source JSON: {id, parentId: squadId, kind: "measurement-source", status: DRAFT|ACTIVE|RETIRED,
        revision, data: {name, providerType, baseUrl, description?}, ...}.
        """
        client = get_client()
        if action == "list":
            require(action, squad_id=squad_id)
            return await paginate(
                client,
                f"/squads/{squad_id}/measurement-sources",
                limit=limit,
                cursor=cursor,
                all_pages=all_pages,
            )
        if action == "get":
            require(action, source_id=source_id)
            return await client.get(f"/measurement-sources/{source_id}")
        if action == "create":
            require(action, squad_id=squad_id, name=name, provider_type=provider_type, base_url=base_url)
            return await client.post(
                f"/squads/{squad_id}/measurement-sources",
                json=optional_body(
                    name=name, providerType=provider_type, baseUrl=base_url, description=description
                ),
            )
        if action == "check_connection":
            require(action, source_id=source_id)
            return await client.post(f"/measurement-sources/{source_id}/connection-checks")
        if action == "validate_query":
            require_object(
                action,
                "query",
                query,
                "criterionKey",
                "expression",
                "mode",
                "reduction",
                "seriesPolicy",
                "unit",
            )
            require(action, source_id=source_id)
            return await client.post(
                f"/measurement-sources/{source_id}/query-validations",
                json={"query": query, "executeSample": execute_sample},
            )
        if action == "activate":
            require(action, source_id=source_id)
            return await client.post(
                f"/measurement-sources/{source_id}/activations", json=optional_body(reason=reason)
            )
        require(action, source_id=source_id)
        return await client.post(
            f"/measurement-sources/{source_id}/retirements", json=optional_body(reason=reason)
        )
