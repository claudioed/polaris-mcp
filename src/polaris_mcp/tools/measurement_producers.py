"""Measurement producers: push identities authorized to submit measurements."""

from __future__ import annotations

from typing import Literal

from mcp.server.fastmcp import FastMCP


def register(mcp: FastMCP) -> None:
    from ..runtime import get_client
    from ._support import optional_body, require

    @mcp.tool()
    async def polaris_measurement_producers(
        action: Literal["create"],
        squad_id: str | None = None,
        name: str | None = None,
        description: str | None = None,
    ) -> dict:
        """Register measurement producers: identities authorized to PUSH measurements for a squad.

        Action: create — requires squad_id + name (optional description). A push fitness-function
        definition declares exactly one producerId, and only that producer may submit against it.

        Producer JSON: {id, parentId: squadId, kind: "measurement-producer", status: ACTIVE,
        revision, data: {name, description?}, ...}. The returned id is the producerId to reference
        in PUSH acquisition definitions and submissions.
        """
        require(action, squad_id=squad_id, name=name)
        client = get_client()
        return await client.post(
            f"/squads/{squad_id}/measurement-producers",
            json=optional_body(name=name, description=description),
        )
