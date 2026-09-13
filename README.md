# polaris-mcp

An [MCP](https://modelcontextprotocol.io) server for [Polaris](https://github.com/claudioed/polaris),
the squad-owned architectural fitness-function control plane. It exposes Polaris' REST API
(`/api/v1`) as 16 grouped tools over stdio, handles Google OIDC automatically (one-time browser
login, silent ID-token refresh), and uses the ingest `X-API-Key` for measurement submissions.

## Tools

| Tool | Actions |
|---|---|
| `polaris_health` | `live`, `ready` |
| `polaris_tribes` | `list`, `get`, `create`, `archive`, `overview` |
| `polaris_squads` | `list`, `get`, `create`, `transfer` |
| `polaris_fitness_targets` | `list`, `get`, `create`, `transition`, `history` |
| `polaris_measurement_providers` | `list_types` |
| `polaris_measurement_sources` | `list`, `get`, `create`, `check_connection`, `validate_query`, `activate`, `retire` |
| `polaris_measurement_producers` | `create` |
| `polaris_fitness_functions` | `list`, `get`, `create`, `add_version`, `update_draft_version`, `validate_version`, `activate_version`, `retire` |
| `polaris_measurement_submissions` | `submit`, `submit_batch` (X-API-Key) |
| `polaris_evaluation_requests` | `create`, `get`, `cancel` |
| `polaris_evaluations` | `get`, `list_by_function` |
| `polaris_collection_attempts` | `list`, `get`, `collect_now`, `retry` |
| `polaris_waivers` | `propose`, `decide` (approve / reject / revoke) |
| `polaris_fitness_function_templates` | `list`, `publish`, `adopt` |
| `polaris_insights` | `squad_overview`, `tribe_overview`, `target_history` |
| `polaris_events` | `poll`, `acknowledge` |

Payloads use the REST API's camelCase keys exactly as documented in each tool description. Lists
return `{items, nextCursor}`; pass `nextCursor` back as `cursor`, or set `all_pages: true` to follow
cursors automatically (capped at 10 pages / 1000 items). Fitness-function version mutations are
guarded by `If-Match`: pass the aggregate `revision` explicitly, or omit it to use the current one
automatically. Errors surface Polaris' RFC 9457 problem `code` and `correlationId`.

## Setup

### 1. Google OAuth client

Business endpoints require a Google OpenID Connect ID token, and Polaris verifies the audience —
use **the same OAuth client ID the Polaris server is configured with** (`POLARIS_OIDC_CLIENT_ID`).

1. In Google Cloud Console, open the OAuth client used by Polaris (type **Web application**).
2. Add `http://localhost:8887` as an authorized redirect URI (polaris-mcp listens there during
   login; it falls back to a random port if 8887 is taken, in which case also allow
   `http://localhost` — Google ignores the port for loopback URIs).

### 2. Configure environment

| Variable | Meaning | Default |
|---|---|---|
| `POLARIS_BASE_URL` | Polaris API origin | `http://localhost:8080` |
| `POLARIS_OIDC_CLIENT_ID` | Google OAuth client ID (same as the server's) | — (required for login) |
| `POLARIS_OIDC_CLIENT_SECRET` | Client secret, for clients that require it at token exchange | — |
| `POLARIS_INGEST_API_KEY` | Ingest secret (`X-API-Key`) enabling the submission tools | — |
| `POLARIS_AUTHORIZED_EMAIL` | Optional client-side sanity check at login | — |
| `POLARIS_CREDENTIALS_FILE` | Where the refresh token is stored | `~/.config/polaris-mcp/credentials.json` (0600) |
| `POLARIS_TIMEOUT_SECONDS` | HTTP timeout | `30` |

### 3. Install and log in

```sh
python3 -m venv .venv && .venv/bin/pip install -e .
.venv/bin/polaris-mcp login    # one-time browser sign-in (OAuth code + PKCE)
.venv/bin/polaris-mcp status   # verify credentials, token refresh, and health
```

`login` opens a browser at Google, receives the redirect on a loopback port, and stores the refresh
token locally. ID tokens (~1h lifetime) are refreshed silently from then on; no credentials or
tokens are ever sent anywhere except Google's and Polaris's endpoints.

### 4. Register with an MCP host

Claude Desktop (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "polaris": {
      "command": "/Users/you/polaris-mcp/.venv/bin/polaris-mcp",
      "env": {
        "POLARIS_BASE_URL": "http://localhost:8080",
        "POLARIS_OIDC_CLIENT_ID": "<client-id>",
        "POLARIS_INGEST_API_KEY": "<ingest-secret>"
      }
    }
  }
}
```

opencode (`opencode.json`):

```json
{
  "mcp": {
    "polaris": {
      "type": "local",
      "command": ["polaris-mcp", "serve"],
      "enabled": true,
      "environment": {
        "POLARIS_BASE_URL": "http://localhost:8080",
        "POLARIS_OIDC_CLIENT_ID": "<client-id>",
        "POLARIS_INGEST_API_KEY": "<ingest-secret>"
      }
    }
  }
}
```

(`serve` is the default subcommand, so `command: ["polaris-mcp"]` works too. If the script is on
`PATH` — e.g. installed with `pipx` — no absolute path is needed.)

## Development

```sh
python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'
.venv/bin/pytest        # client, auth, and in-memory MCP session tests (no network)
```

Or through the Makefile:

```sh
make install   # pip install -e '.[dev]'
make lint      # ruff check + format check
make format    # ruff autofix + format
make test      # pytest
make coverage  # pytest with a 90% coverage gate
make build     # sdist + wheel (twine-checked in CI)
make smoke     # install the wheel into a clean venv and drive it over stdio
make audit     # pip-audit over installed dependencies
```

## Continuous integration

The GitHub Actions workflow in [`.github/workflows/ci.yml`](.github/workflows/ci.yml) gates pushes,
pull requests (to `main`/`develop`), and a weekly schedule with:

- **Python lint** — `ruff check` and `ruff format --check`;
- **Unit tests** — pytest on Python 3.10 and 3.13 with a 90% coverage gate
  (`coverage.xml` uploaded as an artifact);
- **Build distributions** — `python -m build` + `twine check`;
- **Install smoke test** — the wheel is installed into a clean venv and exercised over real stdio
  (`scripts/smoke_stdio.py`);
- **Dependency vulnerability scan** — `pip-audit --strict`, re-run weekly to catch new CVEs.

After all gates pass on `main`, the workflow computes the next patch version from git tags, tags the
commit, and creates a GitHub release with the sdist and wheel attached. Publishing to PyPI via
[trusted publishing](https://docs.pypi.org/trusted-publishers/) is opt-in: set the repository
variable `PYPI_PUBLISH=true` and configure a `pypi` environment (with this repository as a trusted
publisher) to enable it.

## Security notes

- The Google refresh token is stored with `0600` permissions and used only against
  `https://oauth2.googleapis.com/token`.
- ID-token claims are decoded locally (no signature verification) only to decide when to refresh;
  Polaris performs full verification (issuer, audience, expiry, signature) on every request.
- The ingest API key is only attached to the two measurement-submission endpoints, matching the
  server's expectations.

## License

Proprietary, following Polaris.
