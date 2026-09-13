"""Squads: list, get, create, and transfer between tribes."""

from __future__ import annotations

from typing import Literal

from mcp.server.fastmcp import FastMCP


def register(mcp: FastMCP) -> None:
    from ..client import paginate
    from ..runtime import get_client
    from ._support import optional_body, require

    @mcp.tool()
    async def polaris_squads(
        action: Literal["list", "get", "create", "transfer"],
        tribe_id: str | None = None,
        squad_id: str | None = None,
        destination_tribe_id: str | None = None,
        name: str | None = None,
        mission: str | None = None,
        reason: str | None = None,
        limit: int | None = None,
        cursor: str | None = None,
        all_pages: bool = False,
    ) -> dict:
        """Manage squads, the owning unit of fitness targets, sources, producers, and fitness functions.

        Actions and required parameters:
        - list: tribe_id — squads currently in the tribe (optional limit/cursor/all_pages)
        - get: squad_id
        - create: tribe_id + name (optional mission) — squad is registered ACTIVE in the tribe
        - transfer: squad_id + destination_tribe_id (optional reason) — squad keeps ownership of
          everything it owns

        Squad JSON: {id, parentId: tribeId, kind: "squad", status: ACTIVE, revision,
        data: {name, mission?}, createdAt, updatedAt}.
        """
        client = get_client()
        if action == "list":
            require(action, tribe_id=tribe_id)
            return await paginate(
                client, f"/tribes/{tribe_id}/squads", limit=limit, cursor=cursor, all_pages=all_pages
            )
        if action == "get":
            require(action, squad_id=squad_id)
            return await client.get(f"/squads/{squad_id}")
        if action == "create":
            require(action, tribe_id=tribe_id, name=name)
            body = {"name": name}
            if mission is not None:
                body["mission"] = mission
            return await client.post(f"/tribes/{tribe_id}/squads", json=body)
        require(action, squad_id=squad_id, destination_tribe_id=destination_tribe_id)
        return await client.post(
            f"/squads/{squad_id}/transfers",
            json=optional_body(tribeId=destination_tribe_id, reason=reason),
        )
