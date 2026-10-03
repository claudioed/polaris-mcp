# polaris-mcp

An [MCP](https://modelcontextprotocol.io) server for [Polaris](https://github.com/claudioed/polaris),
the squad-owned architectural fitness-function control plane. It exposes Polaris' REST API
(`/api/v1`) as 16 grouped tools over stdio or MCP streamable HTTP (for containerized deployment),
handles Google OIDC automatically (one-time browser login, silent ID-token refresh), and uses the
ingest `X-API-Key` for measurement submissions.

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
| `POLARIS_MCP_TRANSPORT` | `stdio` or `streamable-http` | `stdio` |
| `POLARIS_MCP_HOST` | Bind address for streamable-http | `127.0.0.1` |
| `POLARIS_MCP_PORT` | Listen port for streamable-http | `8000` |
| `POLARIS_CALLBACK_BIND_HOST` | Bind address for the login redirect listener (use `0.0.0.0` inside containers) | `127.0.0.1` |

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

## Deploy with Docker Compose

To serve polaris-mcp as a container speaking MCP streamable HTTP instead of stdio, copy
[`.env.example`](.env.example) to `.env`, set at least `POLARIS_OIDC_CLIENT_ID`, then:

```sh
docker compose up -d --build     # MCP endpoint at http://localhost:8000/mcp
```

The image defaults to `streamable-http` on `0.0.0.0:8000` inside the container, and compose
publishes it loopback-only on the host. The Google refresh token lives in the `polaris-mcp-data`
volume, so a login survives container upgrades.

### Reaching the Polaris API

Pick the `POLARIS_BASE_URL` that matches where Polaris runs:

- **Same host, polaris compose stack** (its ports publish loopback-only): join its network.
  Uncomment the `networks` blocks in [compose.yaml](compose.yaml) (the network is named
  `polaris_default` unless the stack was started with `-p`), and set
  `POLARIS_BASE_URL=http://polaris:8080`.
- **A process on the Docker host listening on all interfaces**: the default
  `http://host.docker.internal:8080` works as-is.
- **A public origin** (e.g. the polaris Caddy edge): set `POLARIS_BASE_URL=https://<domain>`.

### One-time login in the container

```sh
docker compose run --rm --publish 8887:8887 \
  -e POLARIS_CALLBACK_BIND_HOST=0.0.0.0 \
  polaris-mcp login --no-browser
```

Open the printed authorize URL in a browser on your machine; Google redirects back to
`http://localhost:8887`, which is forwarded into the container. Verify afterwards:

```sh
docker compose run --rm polaris-mcp status
```

### Connecting MCP clients over HTTP

Any host that speaks streamable HTTP can point at `http://localhost:8000/mcp`. opencode:

```json
{
  "mcp": {
    "polaris": {
      "type": "remote",
      "url": "http://localhost:8000/mcp",
      "enabled": true
    }
  }
}
```

### Deploying released images

Every release is pushed to GHCR as `ghcr.io/polaris-harness/polaris-mcp:vX.Y.Z` (plus `latest`). To run
a released version instead of building from source, set `POLARIS_MCP_TAG` in `.env` and:

```sh
docker compose pull && docker compose up -d
```

> **Security note**: the streamable-http endpoint has no authentication of its own — keep it
> loopback-only (the compose default) or front it with a TLS edge before exposing it off-host.

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
make coverage  # pytest with a 95% coverage gate (currently at 100%)
make build     # sdist + wheel (twine-checked in CI)
make smoke     # install the wheel into a clean venv and drive it over stdio
make audit     # pip-audit over installed dependencies
make image     # build the Docker image locally (polaris-mcp:local)
```

## Continuous integration

The GitHub Actions workflow in [`.github/workflows/ci.yml`](.github/workflows/ci.yml) gates pushes,
pull requests (to `main`/`develop`), and a weekly schedule with:

- **Python lint** — `ruff check` and `ruff format --check`;
- **Unit tests** — pytest on Python 3.10 and 3.13 with a 95% coverage gate
  (`coverage.xml` uploaded as an artifact);
- **Build distributions** — `python -m build` + `twine check`;
- **Install smoke test** — the wheel is installed into a clean venv and exercised over real stdio
  (`scripts/smoke_stdio.py`);
- **Dependency vulnerability scan** — `pip-audit --strict`, re-run weekly to catch new CVEs;
- **Docker image** — on pull requests the image is built and exercised over real streamable HTTP
  inside a container (`scripts/smoke_http.py`).

After all gates pass on `main`, the workflow computes the next patch version from git tags, tags the
commit, and creates a GitHub release with the sdist and wheel attached, and publishes the container
image to GHCR (`ghcr.io/polaris-harness/polaris-mcp:vX.Y.Z` and `:latest`). Publishing to PyPI via
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
