"""Fitness-function templates: tribe-published reusable definitions."""

from __future__ import annotations

from typing import Any, Literal

from mcp.server.fastmcp import FastMCP


def register(mcp: FastMCP) -> None:
    from ..client import paginate
    from ..runtime import get_client
    from ._support import optional_body, require

    @mcp.tool()
    async def polaris_fitness_function_templates(
        action: Literal["list", "publish", "adopt"],
        tribe_id: str | None = None,
        template_id: str | None = None,
        name: str | None = None,
        description: str | None = None,
        definition: dict[str, Any] | None = None,
        squad_id: str | None = None,
        target_ids: list[str] | None = None,
        reason: str | None = None,
        limit: int | None = None,
        cursor: str | None = None,
        all_pages: bool = False,
    ) -> dict:
        """Manage tribe-published fitness-function templates.

        Actions and required parameters:
        - list: tribe_id — the tribe's templates (optional limit/cursor/all_pages)
        - publish: tribe_id + name (optional description, optional definition — a FitnessDefinition
          object with the same camelCase keys used by polaris_fitness_functions). Names are unique
          within a tribe (duplicate yields 409).
        - adopt: template_id + squad_id (optional target_ids scope override, optional reason) —
          creates a squad-owned DRAFT fitness function; the tribe retains no ownership, and the
          squad may adapt the draft before activating it.

        Template JSON: {id, parentId: tribeId, kind: "fitness-function-template", status: ACTIVE,
        revision, data: {name, description?, definition?}, createdAt, updatedAt}.
        """
        client = get_client()
        if action == "list":
            require(action, tribe_id=tribe_id)
            return await paginate(
                client,
                f"/tribes/{tribe_id}/fitness-function-templates",
                limit=limit,
                cursor=cursor,
                all_pages=all_pages,
            )
        if action == "publish":
            require(action, tribe_id=tribe_id, name=name)
            return await client.post(
                f"/tribes/{tribe_id}/fitness-function-templates",
                json=optional_body(name=name, description=description, definition=definition),
            )
        require(action, template_id=template_id, squad_id=squad_id)
        return await client.post(
            f"/fitness-function-templates/{template_id}/adoptions",
            json=optional_body(squadId=squad_id, targetIds=target_ids, reason=reason),
        )
