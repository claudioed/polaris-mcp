"""Collection attempts: retained pull-collection executions."""

from __future__ import annotations

from typing import Literal

from mcp.server.fastmcp import FastMCP


def register(mcp: FastMCP) -> None:
    from ..client import paginate
    from ..runtime import get_client
    from ._support import require

    @mcp.tool()
    async def polaris_collection_attempts(
        action: Literal["list", "get", "collect_now", "retry"],
        fitness_function_id: str | None = None,
        attempt_id: str | None = None,
        limit: int | None = None,
        cursor: str | None = None,
        all_pages: bool = False,
    ) -> dict:
        """Manage pull collection attempts.

        Actions and required parameters:
        - list: fitness_function_id — retained attempts with measurements and provider evidence
        - get: attempt_id — one retained attempt (status SUCCEEDED|FAILED, measurements, evidence)
        - collect_now: fitness_function_id — executes the active PULL definition immediately
          (outside its schedule) and returns the recorded evaluation. Requires an ACTIVE function
          with a PULL acquisition and an ACTIVE source; provider failures surface as 500.
        - retry: attempt_id — re-runs collection after e.g. a provider outage; returns the new
          evaluation while the original attempt is retained unchanged

        Attempt JSON: {id, parentId: fitnessFunctionId, kind: "collection-attempt", status:
        SUCCEEDED|FAILED, revision, data: {sourceId, measurements: [{criterionKey, value, unit}],
        evidence: [...]}, createdAt, updatedAt}.
        """
        client = get_client()
        if action == "list":
            require(action, fitness_function_id=fitness_function_id)
            return await paginate(
                client,
                f"/fitness-functions/{fitness_function_id}/collection-attempts",
                limit=limit,
                cursor=cursor,
                all_pages=all_pages,
            )
        if action == "get":
            require(action, attempt_id=attempt_id)
            return await client.get(f"/collection-attempts/{attempt_id}")
        if action == "collect_now":
            require(action, fitness_function_id=fitness_function_id)
            return await client.post(f"/fitness-functions/{fitness_function_id}/collection-attempts")
        require(action, attempt_id=attempt_id)
        return await client.post(f"/collection-attempts/{attempt_id}/retries")
