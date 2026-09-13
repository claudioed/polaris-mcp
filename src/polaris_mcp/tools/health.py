"""Health probes (anonymous)."""

from __future__ import annotations

from typing import Literal

from mcp.server.fastmcp import FastMCP


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    async def polaris_health(action: Literal["live", "ready"]) -> dict:
        """Probe Polaris health.

        - live: process liveness (no dependencies; use for restart probes)
        - ready: readiness to serve traffic (verifies PostgreSQL; 503 problem document while down)

        Returns {"status": "ok"} on success.
        """
        from ..runtime import get_client

        client = get_client()
        return await client.get(f"/health/{action}", auth="none")
