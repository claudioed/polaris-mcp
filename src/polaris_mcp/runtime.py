"""Process-wide lazy runtime (settings + shared HTTP client)."""

from __future__ import annotations

from .client import PolarisClient
from .config import load_settings

_client: PolarisClient | None = None


def get_client() -> PolarisClient:
    """Return the shared PolarisClient, creating it on first use."""
    global _client
    if _client is None:
        _client = PolarisClient(load_settings())
    return _client


def reset_client() -> None:
    """Drop the shared client (used by tests to rebind configuration)."""
    global _client
    if _client is not None:
        _client = None
