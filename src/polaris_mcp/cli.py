"""Command-line entrypoint: polaris-mcp [login|status|serve]."""

from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import replace

import httpx

from .auth import AuthError, TokenManager, run_login
from .config import Settings, load_settings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="polaris-mcp",
        description="MCP server for the Polaris architectural fitness-function control plane.",
    )
    sub = parser.add_subparsers(dest="command")
    login = sub.add_parser("login", help="connect your Google account (OAuth code + PKCE, one time)")
    login.add_argument(
        "--no-browser",
        action="store_true",
        help="print the authorize URL instead of opening a browser (headless/container login)",
    )
    sub.add_parser("status", help="show credential, auth, and Polaris health status")
    serve = sub.add_parser("serve", help="run the MCP server (stdio by default; see --transport)")
    serve.add_argument(
        "--transport",
        choices=("stdio", "streamable-http"),
        default=None,
        help="MCP transport (default: POLARIS_MCP_TRANSPORT, or stdio)",
    )
    serve.add_argument(
        "--host",
        default=None,
        help="bind address for streamable-http (default: POLARIS_MCP_HOST, or 127.0.0.1)",
    )
    serve.add_argument(
        "--port",
        type=int,
        default=None,
        help="listen port for streamable-http (default: POLARIS_MCP_PORT, or 8000)",
    )
    return parser


async def _cmd_status(settings: Settings) -> int:
    ok = True
    manager = TokenManager(settings)
    if manager.credentials is None:
        print("credentials : none (run `polaris-mcp login`)")
        ok = False
    else:
        print(f"credentials : {settings.credentials_file}")
        print(f"account     : {manager.credentials.email or '(unknown)'}")
        try:
            token = await manager.get_id_token()
            from .auth import parse_id_token_claims

            claims = parse_id_token_claims(token)
            print(f"auth        : ok (id_token exp {claims.get('exp')})")
        except AuthError as exc:
            print(f"auth        : FAILED ({exc})")
            ok = False
    async with httpx.AsyncClient(base_url=settings.base_url, timeout=settings.timeout_seconds) as http:
        for name in ("live", "ready"):
            try:
                resp = await http.get(f"/api/v1/health/{name}")
                detail = "ok" if resp.status_code == 200 else f"HTTP {resp.status_code}"
                print(f"health/{name:<5}: {detail}")
                if resp.status_code != 200:
                    ok = False
            except httpx.HTTPError as exc:
                print(f"health/{name:<5}: unreachable ({exc.__class__.__name__})")
                ok = False
    return 0 if ok else 1


def _cmd_serve(settings: Settings, args: argparse.Namespace) -> int:
    """Run the MCP server, applying --transport/--host/--port overrides to the settings."""
    port = getattr(args, "port", None)
    if port is not None and not 1 <= port <= 65535:
        print(f"error: --port must be between 1 and 65535, got {port}", file=sys.stderr)
        return 1
    resolved = settings
    if getattr(args, "transport", None):
        resolved = replace(resolved, serve_transport=args.transport)
    if getattr(args, "host", None):
        resolved = replace(resolved, serve_host=args.host)
    if port is not None:
        resolved = replace(resolved, serve_port=port)
    from .server import create_server

    create_server(resolved).run(transport=resolved.serve_transport)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        settings = load_settings()
        if args.command == "login":
            run_login(settings, open_browser=not args.no_browser)
            return 0
        if args.command == "status":
            return asyncio.run(_cmd_status(settings))
    except (AuthError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return _cmd_serve(settings, args)
