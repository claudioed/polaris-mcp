"""Measurement provider capability discovery."""

from __future__ import annotations

from typing import Literal

from mcp.server.fastmcp import FastMCP


def register(mcp: FastMCP) -> None:
    @mcp.tool()
    async def polaris_measurement_providers(action: Literal["list_types"]) -> dict:
        """Discover supported pull measurement providers.

        Action: list_types — returns the provider capability catalog. Each entry states the query
        capabilities (INSTANT_QUERY, RANGE_QUERY) and supported outbound authentication modes (only
        NONE in v1; only PROMETHEUS is supported). Use this instead of hard-coding provider
        assumptions; new providers appear here without changing other resource shapes.
        """
        from ..runtime import get_client

        return await get_client().get("/measurement-provider-types")
