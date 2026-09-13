"""Smoke test: spawn `polaris-mcp serve` over real stdio and exercise it as a client."""

import asyncio
import os
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main() -> int:
    env = {key: value for key, value in os.environ.items() if not key.startswith("POLARIS_")}
    env.update(
        {
            "POLARIS_BASE_URL": "http://localhost:8080",
            "POLARIS_OIDC_CLIENT_ID": "smoke-client-id",
            "POLARIS_CREDENTIALS_FILE": "/tmp/polaris-mcp-smoke/credentials.json",
        }
    )
    params = StdioServerParameters(command=f"{sys.prefix}/bin/polaris-mcp", args=["serve"], env=env)
    async with stdio_client(params) as (read, write), ClientSession(read, write) as session:
        await session.initialize()
        tools = await session.list_tools()
        names = sorted(tool.name for tool in tools.tools)
        print(f"tools ({len(names)}): {', '.join(names)}")
        assert len(names) == 16, f"expected 16 tools, got {len(names)}"
        result = await session.call_tool("polaris_tribes", {"action": "get", "tribe_id": "x"})
        assert result.isError
        text = result.content[0].text
        print(f"unauthenticated call surfaced as tool error: {text[:120]}")
        assert "polaris-mcp login" in text
    print("stdio smoke test OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
