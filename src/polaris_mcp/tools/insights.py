"""Insights: squad and tribe fitness overviews plus per-target history."""

from __future__ import annotations

from typing import Literal

from mcp.server.fastmcp import FastMCP


def register(mcp: FastMCP) -> None:
    from ..client import paginate
    from ..runtime import get_client
    from ._support import require

    @mcp.tool()
    async def polaris_insights(
        action: Literal["squad_overview", "tribe_overview", "target_history"],
        squad_id: str | None = None,
        tribe_id: str | None = None,
        target_id: str | None = None,
        limit: int | None = None,
        cursor: str | None = None,
        all_pages: bool = False,
    ) -> dict:
        """Read insight aggregates computed from retained evaluations.

        Actions and required parameters:
        - squad_overview: squad_id — aggregated architectural fitness for one squad
        - tribe_overview: tribe_id — patterns across the tribe's squads (no league table)
        - target_history: target_id — chronological fitness-history entries for one target
          (optional limit/cursor/all_pages)

        Overviews expose outcomes and dispositions without collapsing them into a single universal
        score: {scope: squad|tribe, scopeId, generatedAt, status: AVAILABLE}.
        """
        client = get_client()
        if action == "squad_overview":
            require(action, squad_id=squad_id)
            return await client.get(f"/squads/{squad_id}/fitness-overview")
        if action == "tribe_overview":
            require(action, tribe_id=tribe_id)
            return await client.get(f"/tribes/{tribe_id}/fitness-overview")
        require(action, target_id=target_id)
        return await paginate(
            client,
            f"/fitness-targets/{target_id}/fitness-history",
            limit=limit,
            cursor=cursor,
            all_pages=all_pages,
        )
