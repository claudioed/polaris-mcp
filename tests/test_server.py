"""Tests for FastMCP assembly: transport bind settings and server identity."""

from __future__ import annotations

from dataclasses import replace

from polaris_mcp.server import INSTRUCTIONS, create_server


class TestCreateServer:
    def test_http_settings_applied(self, settings):
        mcp = create_server(
            replace(
                settings,
                serve_transport="streamable-http",
                serve_host="0.0.0.0",
                serve_port=9123,
            )
        )
        assert mcp.settings.host == "0.0.0.0"
        assert mcp.settings.port == 9123

    def test_without_settings_fastmcp_defaults_apply(self):
        mcp = create_server()
        assert mcp.settings.host == "127.0.0.1"
        assert mcp.settings.port == 8000

    def test_identity_and_instructions_preserved(self, settings):
        mcp = create_server(settings)
        assert mcp.name == "polaris"
        assert mcp.instructions == INSTRUCTIONS
