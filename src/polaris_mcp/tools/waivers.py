"""Waivers: justified, time-limited exceptions for failing criteria."""

from __future__ import annotations

from typing import Literal

from mcp.server.fastmcp import FastMCP


def register(mcp: FastMCP) -> None:
    from ..runtime import get_client
    from ._support import optional_body, require

    @mcp.tool()
    async def polaris_waivers(
        action: Literal["propose", "decide"],
        fitness_function_id: str | None = None,
        waiver_id: str | None = None,
        decision: Literal["approve", "reject", "revoke"] | None = None,
        reason: str | None = None,
        criterion_keys: list[str] | None = None,
        risk: str | None = None,
        compensating_action: str | None = None,
        starts_at: str | None = None,
        expires_at: str | None = None,
    ) -> dict:
        """Manage waivers: explicit, justified, time-limited exceptions for failing criteria.

        Actions and required parameters:
        - propose: fitness_function_id + reason (why the exception is temporarily acceptable);
          optional criterion_keys (failing criteria covered; omit for all), risk, compensating_action,
          starts_at / expires_at (RFC 3339; expiresAt must be in the future and after startsAt).
          Enters state PROPOSED; only takes effect on approval.
        - decide: waiver_id + decision (approve|reject|revoke, optional reason). Approving accepts
          the risk (the waiver then influences dispositions until it expires); rejecting declines
          the proposal; revoking ends an approved waiver early. Deciding twice yields 409.

        Waiver JSON: {id, parentId: fitnessFunctionId, kind: "waiver", status: PROPOSED|APPROVED|
        REJECTED|REVOKED, revision, data: {reason, criterionKeys?, risk?, compensatingAction?,
        startsAt?, expiresAt?}, createdAt, updatedAt}. Only APPROVED, unexpired waivers influence
        dispositions.
        """
        client = get_client()
        if action == "propose":
            require(action, fitness_function_id=fitness_function_id, reason=reason)
            return await client.post(
                f"/fitness-functions/{fitness_function_id}/waivers",
                json=optional_body(
                    reason=reason,
                    criterionKeys=criterion_keys,
                    risk=risk,
                    compensatingAction=compensating_action,
                    startsAt=starts_at,
                    expiresAt=expires_at,
                ),
            )
        require(action, waiver_id=waiver_id, decision=decision)
        transition = {"approve": "approvals", "reject": "rejections", "revoke": "revocations"}[decision]
        return await client.post(f"/waivers/{waiver_id}/{transition}", json=optional_body(reason=reason))
