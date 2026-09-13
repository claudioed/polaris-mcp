"""Shared helpers and payload validation for tool implementations."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp.exceptions import ToolError

FITNESS_DEFINITION_KEYS = (
    "name",
    "purpose",
    "objective",
    "targetIds",
    "criteria",
    "acquisition",
    "freshnessSeconds",
    "enforcement",
)
MEASUREMENT_SUBMISSION_KEYS = (
    "fitnessFunctionVersion",
    "producerId",
    "externalRunId",
    "observedAt",
    "measurements",
)


def require(action: str, **values: Any) -> None:
    """Raise a ToolError naming the parameters that are missing for the given action."""
    missing = sorted(name for name, value in values.items() if value is None)
    if missing:
        raise ToolError(f"Parameter(s) required for action '{action}': {', '.join(missing)}")


def require_object(action: str, parameter: str, value: Any, *keys: str) -> dict[str, Any]:
    """Validate that `value` is a JSON object carrying the required camelCase keys."""
    if value is None:
        hint = f" with required keys: {', '.join(keys)}" if keys else ""
        raise ToolError(f"Parameter '{parameter}' is required for action '{action}'{hint}")
    if not isinstance(value, dict):
        raise ToolError(f"Parameter '{parameter}' must be a JSON object")
    if keys:
        missing = [key for key in keys if key not in value or value[key] is None]
        if missing:
            raise ToolError(
                f"'{parameter}' for action '{action}' is missing required key(s): {', '.join(missing)}"
            )
    return value


def require_list(
    action: str,
    parameter: str,
    value: Any,
    *,
    min_items: int = 1,
    max_items: int | None = None,
) -> list[Any]:
    """Validate that `value` is a JSON array within the given size bounds."""
    if value is None:
        raise ToolError(f"Parameter '{parameter}' is required for action '{action}'")
    if not isinstance(value, list):
        raise ToolError(f"Parameter '{parameter}' must be a JSON array")
    if len(value) < min_items or (max_items is not None and len(value) > max_items):
        bounds = f"{min_items}..{max_items}" if max_items is not None else f">= {min_items}"
        raise ToolError(f"Parameter '{parameter}' must contain {bounds} items")
    return value


def optional_body(**values: Any) -> dict[str, Any] | None:
    """Build a request body from the non-None values, or None when everything is absent."""
    body = {key: value for key, value in values.items() if value is not None}
    return body or None
