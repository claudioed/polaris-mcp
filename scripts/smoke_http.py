"""Smoke test: run `polaris-mcp serve --transport streamable-http` and connect over HTTP.

Mirrors smoke_stdio.py for the container transport. By default it spawns the
server itself; set SMOKE_SPAWN=0 and SMOKE_URL=... to exercise an
already-running endpoint (e.g. a container started by the CI Docker job).
"""

import asyncio
import os
import signal
import subprocess
import sys
import time
from urllib.parse import urlparse

PORT = int(os.environ.get("SMOKE_PORT", "8765"))
URL = os.environ.get("SMOKE_URL", f"http://127.0.0.1:{PORT}/mcp")
SPAWN = os.environ.get("SMOKE_SPAWN", "1") == "1"


async def _wait_for_endpoint(url: str, timeout: float = 30.0) -> None:
    """Block until the server answers HTTP, not just TCP.

    A plain TCP check is not enough behind a Docker port publish: the proxy
    accepts connections before the server inside the container is listening,
    and the first POST then dies with a connection reset.
    """
    import httpx

    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    async with httpx.AsyncClient(timeout=2) as probe:
        while time.monotonic() < deadline:
            try:
                response = await probe.get(url)  # any HTTP status means it is answering
                print(f"endpoint ready (GET -> HTTP {response.status_code})")
                return
            except httpx.TransportError as exc:
                last_error = exc
                await asyncio.sleep(0.2)
    raise SystemExit(f"server never came up on {url}: {last_error}")


async def main() -> int:
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    parsed = urlparse(URL)
    port = parsed.port or PORT
    proc = None
    if SPAWN:
        env = {key: value for key, value in os.environ.items() if not key.startswith("POLARIS_")}
        env.update(
            {
                "POLARIS_BASE_URL": "http://localhost:8080",
                "POLARIS_OIDC_CLIENT_ID": "smoke-client-id",
                "POLARIS_CREDENTIALS_FILE": "/tmp/polaris-mcp-smoke-http/credentials.json",
            }
        )
        proc = subprocess.Popen(
            [
                f"{sys.prefix}/bin/polaris-mcp",
                "serve",
                "--transport",
                "streamable-http",
                "--port",
                str(port),
            ],
            env=env,
            start_new_session=True,
        )
    try:
        await _wait_for_endpoint(URL)
        async with (
            streamablehttp_client(URL) as (read, write, _get_session_id),
            ClientSession(read, write) as session,
        ):
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
    finally:
        if proc is not None:
            os.killpg(proc.pid, signal.SIGTERM)
            proc.wait(timeout=10)
    print("http smoke test OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
