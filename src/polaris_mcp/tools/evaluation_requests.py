"""Evaluation requests: asynchronous requests that a function be evaluated."""

from __future__ import annotations

from typing import Literal

from mcp.server.fastmcp import FastMCP


def register(mcp: FastMCP) -> None:
    from ..runtime import get_client
    from ._support import require

    @mcp.tool()
    async def polaris_evaluation_requests(
        action: Literal["create", "get", "cancel"],
        fitness_function_id: str | None = None,
        request_id: str | None = None,
    ) -> dict:
        """Manage evaluation requests.

        Actions and required parameters:
        - create: fitness_function_id — accepted with 202 as PENDING; fulfilled when a producer
          pushes a submission carrying the request's id (or by pull collection)
        - get: request_id — poll the state (PENDING until fulfilled, CANCELLED after cancellation)
        - cancel: request_id — cancels a PENDING request (e.g. the triggering pipeline was aborted);
          cancelling twice yields 409

        Evaluation-request JSON: {id, parentId: fitnessFunctionId, kind: "evaluation-request",
        status: PENDING|CANCELLED, revision, data, createdAt, updatedAt}. The created id is the
        evaluationRequestId a producer references in its submission.
        """
        client = get_client()
        if action == "create":
            require(action, fitness_function_id=fitness_function_id)
            return await client.post(f"/fitness-functions/{fitness_function_id}/evaluation-requests", json={})
        if action == "get":
            require(action, request_id=request_id)
            return await client.get(f"/evaluation-requests/{request_id}")
        require(action, request_id=request_id)
        return await client.post(f"/evaluation-requests/{request_id}/cancellations")
