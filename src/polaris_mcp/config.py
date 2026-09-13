"""Environment-driven configuration for polaris-mcp."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from platformdirs import user_config_dir

DEFAULT_BASE_URL = "http://localhost:8080"
DEFAULT_TIMEOUT_SECONDS = 30.0


@dataclass(frozen=True)
class Settings:
    """Resolved runtime settings."""

    base_url: str
    oidc_client_id: str
    oidc_client_secret: str | None
    ingest_api_key: str | None
    authorized_email: str | None
    credentials_file: Path
    timeout_seconds: float

    @property
    def api_base_url(self) -> str:
        return self.base_url.rstrip("/") + "/api/v1"


def load_settings(env: Mapping[str, str] | None = None) -> Settings:
    """Resolve settings from the environment with sensible defaults."""
    source = os.environ if env is None else env
    base_url = source.get("POLARIS_BASE_URL", DEFAULT_BASE_URL).strip().rstrip("/")
    parsed = urlparse(base_url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError(f"POLARIS_BASE_URL must be an absolute http(s) URL, got {base_url!r}")
    credentials_override = source.get("POLARIS_CREDENTIALS_FILE", "").strip()
    credentials_file = (
        Path(credentials_override).expanduser()
        if credentials_override
        else Path(user_config_dir("polaris-mcp")) / "credentials.json"
    )
    timeout_raw = source.get("POLARIS_TIMEOUT_SECONDS", "").strip()
    return Settings(
        base_url=base_url,
        oidc_client_id=source.get("POLARIS_OIDC_CLIENT_ID", "").strip(),
        oidc_client_secret=(source.get("POLARIS_OIDC_CLIENT_SECRET") or "").strip() or None,
        ingest_api_key=(source.get("POLARIS_INGEST_API_KEY") or "").strip() or None,
        authorized_email=(source.get("POLARIS_AUTHORIZED_EMAIL") or "").strip() or None,
        credentials_file=credentials_file,
        timeout_seconds=float(timeout_raw) if timeout_raw else DEFAULT_TIMEOUT_SECONDS,
    )
