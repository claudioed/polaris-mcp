"""Evaluations: immutable recorded outcomes of applying the active definition."""

from __future__ import annotations

from typing import Literal

from mcp.server.fastmcp import FastMCP


def register(mcp: FastMCP) -> None:
    from ..client import paginate
    from ..runtime import get_client
    from ._support import require

    @mcp.tool()
    async def polaris_evaluations(
        action: Literal["get", "list_by_function"],
        evaluation_id: str | None = None,
        fitness_function_id: str | None = None,
        limit: int | None = None,
        cursor: str | None = None,
        all_pages: bool = False,
    ) -> dict:
        """Read evaluations.

        Actions and required parameters:
        - get: evaluation_id — the immutable evaluation in full
        - list_by_function: fitness_function_id — recorded evaluations in creation order
          (optional limit/cursor/all_pages)

        Evaluation JSON: {evaluationId, fitnessFunctionId, fitnessFunctionVersion, acquisitionMode:
        PUSH|PULL, originId, outcome: PASS|WARN|FAIL|ERROR|NOT_APPLICABLE, disposition:
        ACCEPTED|ATTENTION_REQUIRED|BLOCKED|WAIVED (enforcement decision honoring approved
        unexpired waivers), observedAt, validUntil (stale after this), criterionResults:
        [{criterionKey, value, unit, outcome: PASS|WARN|FAIL}], data: retained measurements and
        evidence}. Evaluations are never modified after recording; no data never counts as success.
        """
        client = get_client()
        if action == "get":
            require(action, evaluation_id=evaluation_id)
            return await client.get(f"/evaluations/{evaluation_id}")
        require(action, fitness_function_id=fitness_function_id)
        return await paginate(
            client,
            f"/fitness-functions/{fitness_function_id}/evaluations",
            limit=limit,
            cursor=cursor,
            all_pages=all_pages,
        )
