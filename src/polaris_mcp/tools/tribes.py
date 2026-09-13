"""Tribes: list, get, create, archive, and tribe fitness overviews."""

from __future__ import annotations

from typing import Literal

from mcp.server.fastmcp import FastMCP


def register(mcp: FastMCP) -> None:
    from ..client import paginate
    from ..runtime import get_client
    from ._support import optional_body, require

    @mcp.tool()
    async def polaris_tribes(
        action: Literal["list", "get", "create", "archive", "overview"],
        tribe_id: str | None = None,
        name: str | None = None,
        description: str | None = None,
        reason: str | None = None,
        limit: int | None = None,
        cursor: str | None = None,
        all_pages: bool = False,
    ) -> dict:
        """Manage Polaris tribes, the topology level that groups squads.

        Actions and required parameters:
        - list: optional limit (1-200) / cursor / all_pages
        - get: tribe_id
        - create: name (optional description)
        - archive: tribe_id (optional reason) — tribe stays queryable, status becomes ARCHIVED
        - overview: tribe_id — aggregated tribe fitness overview (Insights read model)

        Tribe JSON: {id, kind: "tribe", status: ACTIVE|ARCHIVED, revision, data: {name, description?},
        createdAt, updatedAt}. Lists return {items, nextCursor}; pass nextCursor back as cursor.
        """
        client = get_client()
        if action == "list":
            return await paginate(client, "/tribes", limit=limit, cursor=cursor, all_pages=all_pages)
        if action == "get":
            require(action, tribe_id=tribe_id)
            return await client.get(f"/tribes/{tribe_id}")
        if action == "create":
            require(action, name=name)
            body = {"name": name}
            if description is not None:
                body["description"] = description
            return await client.post("/tribes", json=body)
        if action == "archive":
            require(action, tribe_id=tribe_id)
            return await client.post(f"/tribes/{tribe_id}/archivals", json=optional_body(reason=reason))
        require(action, tribe_id=tribe_id)
        return await client.get(f"/tribes/{tribe_id}/fitness-overview")
