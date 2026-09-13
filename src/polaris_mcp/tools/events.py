"""Events: transactional-outbox delivery with durable per-consumer cursors."""

from __future__ import annotations

from typing import Literal

from mcp.server.fastmcp import FastMCP


def register(mcp: FastMCP) -> None:
    from ..client import paginate
    from ..runtime import get_client
    from ._support import require, require_list

    @mcp.tool()
    async def polaris_events(
        action: Literal["poll", "acknowledge"],
        consumer_id: str | None = None,
        event_ids: list[str] | None = None,
        cursor: str | None = None,
        limit: int | None = None,
        all_pages: bool = False,
    ) -> dict:
        """Consume delivery events published through the transactional outbox.

        Actions and required parameters:
        - poll: consumer_id (stable identity, 1-100 chars) — returns events newer than `cursor`
          (optional limit). Persist the returned nextCursor between polls; without a cursor you
          start from the oldest event. After successfully processing events, acknowledge them.
        - acknowledge: consumer_id + event_ids (1-500 ids) — acknowledged events are never
          redelivered to that consumer; acknowledgement is idempotent per (consumer, event) pair.

        Event JSON: {id, type (e.g. EvaluationRecorded, FitnessFunctionVersionActivated), version,
        aggregateType, aggregateId, occurredAt, actor, correlationId, payload}.
        """
        client = get_client()
        if action == "poll":
            require(action, consumer_id=consumer_id)
            return await paginate(
                client,
                "/events",
                params={"consumerId": consumer_id},
                limit=limit,
                cursor=cursor,
                all_pages=all_pages,
            )
        require(action, consumer_id=consumer_id)
        ids = require_list(action, "event_ids", event_ids, min_items=1, max_items=500)
        return await client.post("/event-acknowledgements", json={"consumerId": consumer_id, "eventIds": ids})
