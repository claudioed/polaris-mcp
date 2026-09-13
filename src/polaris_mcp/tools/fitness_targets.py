"""Fitness targets: the systems squads are architecturally accountable for."""

from __future__ import annotations

from typing import Any, Literal

from mcp.server.fastmcp import FastMCP


def register(mcp: FastMCP) -> None:
    from ..client import paginate
    from ..runtime import get_client
    from ._support import optional_body, require

    @mcp.tool()
    async def polaris_fitness_targets(
        action: Literal["list", "get", "create", "transition", "history"],
        squad_id: str | None = None,
        target_id: str | None = None,
        name: str | None = None,
        description: str | None = None,
        target_kind: str | None = None,
        criticality: str | None = None,
        external_reference: dict[str, Any] | None = None,
        status: Literal["ACTIVE", "DEPRECATED", "RETIRED"] | None = None,
        reason: str | None = None,
        limit: int | None = None,
        cursor: str | None = None,
        all_pages: bool = False,
    ) -> dict:
        """Manage fitness targets: systems (services, databases, queues, ...) a squad is accountable for.

        Actions and required parameters:
        - list: squad_id (optional limit/cursor/all_pages)
        - get: target_id
        - create: squad_id + name (optional description, target_kind e.g. SERVICE/DATABASE/QUEUE,
          criticality e.g. CRITICAL/HIGH, external_reference object) — created ACTIVE
        - transition: target_id + status (ACTIVE|DEPRECATED|RETIRED, optional reason) — explicit,
          auditable lifecycle change; history stays queryable
        - history: target_id — chronological fitness-history entries (Insights read model)

        Target JSON: {id, parentId: squadId, kind: "fitness-target", status: ACTIVE|DEPRECATED|RETIRED,
        revision, data: {name, description?, kind?, criticality?, externalReference?}, ...}.
        """
        client = get_client()
        if action == "list":
            require(action, squad_id=squad_id)
            return await paginate(
                client,
                f"/squads/{squad_id}/fitness-targets",
                limit=limit,
                cursor=cursor,
                all_pages=all_pages,
            )
        if action == "get":
            require(action, target_id=target_id)
            return await client.get(f"/fitness-targets/{target_id}")
        if action == "create":
            require(action, squad_id=squad_id, name=name)
            body: dict[str, Any] = {"name": name}
            if description is not None:
                body["description"] = description
            if target_kind is not None:
                body["kind"] = target_kind
            if criticality is not None:
                body["criticality"] = criticality
            if external_reference is not None:
                body["externalReference"] = external_reference
            return await client.post(f"/squads/{squad_id}/fitness-targets", json=body)
        if action == "transition":
            require(action, target_id=target_id, status=status)
            return await client.post(
                f"/fitness-targets/{target_id}/lifecycle-transitions",
                json=optional_body(status=status, reason=reason),
            )
        require(action, target_id=target_id)
        return await paginate(
            client,
            f"/fitness-targets/{target_id}/fitness-history",
            limit=limit,
            cursor=cursor,
            all_pages=all_pages,
        )
