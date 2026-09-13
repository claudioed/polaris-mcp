"""Tool registration entrypoint: every module exposes register(mcp)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from . import (
    collection_attempts,
    evaluation_requests,
    evaluations,
    events,
    fitness_functions,
    fitness_targets,
    health,
    insights,
    measurement_producers,
    measurement_providers,
    measurement_sources,
    measurement_submissions,
    squads,
    templates,
    tribes,
    waivers,
)

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

TOOL_MODULES = (
    health,
    tribes,
    squads,
    fitness_targets,
    measurement_providers,
    measurement_sources,
    measurement_producers,
    fitness_functions,
    measurement_submissions,
    evaluation_requests,
    evaluations,
    collection_attempts,
    waivers,
    templates,
    insights,
    events,
)


def register_all(mcp: FastMCP) -> None:
    for module in TOOL_MODULES:
        module.register(mcp)
