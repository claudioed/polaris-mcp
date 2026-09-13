"""Measurement submissions: push acquisition evaluated synchronously (X-API-Key auth)."""

from __future__ import annotations

from typing import Any, Literal

from mcp.server.fastmcp import FastMCP


def register(mcp: FastMCP) -> None:
    from mcp.server.fastmcp.exceptions import ToolError

    from ..runtime import get_client
    from ._support import MEASUREMENT_SUBMISSION_KEYS, require, require_list, require_object

    @mcp.tool()
    async def polaris_measurement_submissions(
        action: Literal["submit", "submit_batch"],
        fitness_function_id: str | None = None,
        submission: dict[str, Any] | None = None,
        items: list[dict[str, Any]] | None = None,
    ) -> dict:
        """Push measurements for evaluation against the ACTIVE fitness-function version.

        These are the ingest endpoints: they authenticate with the X-API-Key configured as
        POLARIS_INGEST_API_KEY (no Google login involved).

        Actions and required parameters:
        - submit: fitness_function_id + submission — evaluates synchronously and returns the recorded
          evaluation (with `replayed: true` when a duplicate producerId+externalRunId delivery
          returned the original evaluation). Submissions against a non-active version yield 409.
        - submit_batch: items — up to 100 independent submissions, each {fitnessFunctionId,
          submission}; the 207 response carries per-item status (201 success, or 404/409/422/500
          with an error message); per-item failures do not abort the batch.

        `submission` is a JSON object with camelCase keys:
        required: fitnessFunctionVersion (the active version number); producerId (the producer
        declared by the active definition); externalRunId (producer-scoped run id, the idempotency
        natural key); observedAt (RFC 3339 UTC, not in the future, within the definition's maximum
        observation age); measurements (array of {criterionKey, value, unit, observedAt?}, one per
        criterion, duplicates rejected);
        optional: evaluationRequestId (request this submission fulfills), evidence (array of
        arbitrary evidence documents).
        """
        client = get_client()
        if action == "submit":
            require(action, fitness_function_id=fitness_function_id)
            require_object(action, "submission", submission, *MEASUREMENT_SUBMISSION_KEYS)
            return await client.post(
                f"/fitness-functions/{fitness_function_id}/measurement-submissions",
                auth="ingest",
                json=submission,
            )
        batch = require_list(action, "items", items, min_items=1, max_items=100)
        for index, item in enumerate(batch):
            if not isinstance(item, dict) or "fitnessFunctionId" not in item or "submission" not in item:
                raise ToolError(
                    f"items[{index}] must be an object with 'fitnessFunctionId' and 'submission' keys"
                )
        return await client.post("/measurement-submission-batches", auth="ingest", json={"items": batch})
