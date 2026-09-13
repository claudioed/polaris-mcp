"""FastMCP application assembly."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from .tools import register_all

INSTRUCTIONS = """Polaris is a squad-owned architectural fitness-function control plane: squads define
versioned definitions of intent, scope, criteria, acquisition (PUSH or PULL from Prometheus), freshness,
and enforcement; Polaris records immutable evaluations with evidence and dispositions.

Conventions for these tools:
- Every list action returns {items, nextCursor}; pass nextCursor back as `cursor` to page, or set
  all_pages=true to follow cursors automatically (capped at 10 pages / 1000 items).
- Identifiers are opaque UUIDs; times are RFC 3339 UTC; request/response payloads use the API's
  camelCase keys exactly as documented in each tool.
- Fitness-function version mutations (add_version, update_draft_version) are guarded by optimistic
  concurrency: pass the aggregate `revision` (from the `revision` field) or omit it to use the
  current one automatically; a stale revision yields 409.
- Measurement submissions authenticate with the ingest X-API-Key (POLARIS_INGEST_API_KEY); every
  other business route uses the Google account connected via `polaris-mcp login`.
- Errors surface Polaris' RFC 9457 problem codes (RESOURCE_NOT_FOUND, RESOURCE_CONFLICT, ...) with a
  correlationId; consult the tool description before retrying.
"""


def create_server() -> FastMCP:
    """Build the FastMCP server with all Polaris tools registered."""
    mcp = FastMCP("polaris", instructions=INSTRUCTIONS)
    register_all(mcp)
    return mcp
