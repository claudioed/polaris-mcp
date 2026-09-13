"""Command-line entrypoint: polaris-mcp [login|status|serve]."""

from __future__ import annotations

import argparse
import asyncio
import sys

import httpx

from .auth import AuthError, TokenManager, run_login
from .config import Settings, load_settings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="polaris-mcp",
        description="MCP server for the Polaris architectural fitness-function control plane.",
    )
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("login", help="connect your Google account (OAuth code + PKCE, one time)")
    sub.add_parser("status", help="show credential, auth, and Polaris health status")
    sub.add_parser("serve", help="run the MCP server over stdio (default)")
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


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        settings = load_settings()
        if args.command == "login":
            run_login(settings)
            return 0
        if args.command == "status":
            return asyncio.run(_cmd_status(settings))
    except (AuthError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    from .server import create_server

    create_server().run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
