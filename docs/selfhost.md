# Self-hosting

intomd ships as a Docker Compose stack: Caddy at the edge, the API (which also serves the web UI),
an RQ worker for local conversions, a fetch worker for URL jobs, Redis, and a retention purge service.
The public instance and self-hosted instances use the same defaults; you may loosen limits through
environment variables, never the sandbox.

## Docker Compose (core stack)

```sh
git clone https://github.com/larpey/intomd && cd intomd
deploy/bootstrap.sh --domain intomd.example.com --email you@example.com --version 0.1.0
```

`bootstrap.sh` is safe to run again; it only fills in what is missing:

1. creates `deploy/.env` from `deploy/env.example` (mode 600) and sets the domain, public URL, ACME email and image tag you pass;
2. generates `INTOMD_KEY_PEPPER`, `INTOMD_JWT_SECRET`, `INTOMD_IP_HASH_SALT`, `INTOMD_REDIS_PASSWORD` and `INTOMD_METRICS_TOKEN` once (a re-run never rotates them: a new pepper invalidates every API key);
3. pulls the images (`--build` builds this checkout instead);
4. applies database migrations, so the database is under Alembic from the first start;
5. creates `keys.json` in the state volume (`INTOMD_KEYS_FILE=/var/lib/intomd/keys.json`) with an unlimited `owner` key via `intomd-admin`, and writes that key to `deploy/intomd-owner.key` (mode 600; move it to a password manager);
6. starts the stack, waits for every healthcheck, and runs `deploy/smoke.sh`.

Options: `--domain localhost` (HTTPS with Caddy's internal CA), `--plain-http` (no TLS, port 8080), `--no-smoke`, `--key-out PATH`. `INTOMD_ENV_FILE=/path/to/env` selects another env file (every script honors it, and compose passes it to every container). Host hardening (firewall, fail2ban, sshd, unattended upgrades) is not done by the script yet; follow your distribution's guidance or the public-instance runbook (Phase 4).

By hand: `cp deploy/env.example deploy/.env`, fill in the secrets, `docker compose -f deploy/docker-compose.yml up -d --build --wait`, then `bash deploy/smoke.sh --no-build`.

- `INTOMD_DOMAIN` empty: plain HTTP on port 8080 (host port `INTOMD_PLAIN_PORT`). Open http://localhost:8080.
- `INTOMD_DOMAIN=localhost`: HTTPS with Caddy's internal CA.
- `INTOMD_DOMAIN=intomd.example.com`: a Let's Encrypt certificate; set `INTOMD_ACME_EMAIL`.

| Service | Role | Networks |
|---|---|---|
| `caddy` | TLS, upload cap, security headers, fetch-node path restriction | internal, egress |
| `api` | REST API and web UI | internal |
| `worker-default` | Conversions of uploaded files | internal (no internet route) |
| `worker-fetch` | URL fetches through the SSRF guard, then conversion | internal, egress |
| `redis` | Queues, job events, rate limits (no persistence) | internal |
| `purge` | Retention purge and fetch-node claim reaper | internal |

Every app container runs as uid 10001 with a read-only root filesystem, a `/tmp` tmpfs, all
capabilities dropped, `no-new-privileges`, and CPU, memory, and pid limits. Workers also load
`deploy/seccomp-worker.json`. See [Security](security.md) and `deploy/README.md` for details.

Planned: the media worker and model init container (Phase 2), Postgres and MinIO profiles, and the
public and Raspberry Pi overlays (Phases 3 and 4).

The worker image includes the `data` extra (pyarrow, for Parquet). Build arguments add more:
`INTOMD_WORKER_EXTRAS="data docs"` adds Docling (several GB: the lock resolves CUDA torch wheels on
Linux), and `INTOMD_WORKER_APT_PACKAGES="libreoffice-core-nogui libreoffice-writer-nogui
libreoffice-calc-nogui libreoffice-impress-nogui"` adds LibreOffice for legacy `.doc`/`.xls`/`.ppt`.
`nonfree` and `7z` are refused in the image.
`deploy/docker-compose.gpu.yml` adds a `worker-media` service for the Phase 2 image.

## Backups

```sh
deploy/backup.sh                 # online; the stack keeps running
deploy/backup.sh --no-blobs      # database, keys and certificates only
```

Each run writes `intomd-<UTC timestamp>.tar.gz` (mode 600) to `INTOMD_BACKUP_DIR` (default `deploy/backups/`, mode 700) and keeps the newest `INTOMD_BACKUP_KEEP` (default 14). It holds a consistent SQLite snapshot (SQLite's online backup API, then `PRAGMA integrity_check`), `keys.json`, the blob store, Caddy's certificates and the env file, with SHA-256 checksums for every file. The env file holds every secret: keep backups private and copy them off the host (for example with `rclone copy`). Schedule it daily, e.g. `17 3 * * * /opt/intomd/deploy/backup.sh >/dev/null`.

Only SQLite and the filesystem blob store are covered; with Postgres or S3 use those services' own backups.

## Restore

```sh
deploy/restore.sh --verify-only deploy/backups/intomd-20261008T031700Z.tar.gz
deploy/restore.sh deploy/backups/intomd-20261008T031700Z.tar.gz
deploy/restore.sh --with-env backup.tar.gz     # new host: also restore the env file
```

The script checks the archive's checksums, and every file against the backup's manifest, before it changes anything. Then it stops every service except Redis, replaces the database, `keys.json`, blobs and Caddy data, starts the stack and runs the smoke test. Without `--with-env` the current env file stays; the script warns when its key pepper differs from the backup's (API keys would stop validating). It works on an empty volume set (after `docker compose down -v`, or on a fresh host).

## Upgrades

```sh
deploy/upgrade.sh 0.2.0
```

Backup first, then `INTOMD_VERSION=0.2.0` in the env file, `docker compose pull`, migrations with the new image, `up --wait`, and `/readyz` through Caddy. If any step fails it puts the previous version back; when migrations already ran it first restores the pre-upgrade backup (migrations are forward-only), then starts the old version and exits 1. Patch releases are safe to auto-update (Watchtower); minor releases may add env vars or models and should go through `upgrade.sh`; major releases may change the API and are announced one minor release ahead.

Every process brings the database to the Alembic head at startup. A database created by an older release's `create_all` start (no `alembic_version` table) is adopted when its tables match this release's models, and refused with a clear error otherwise; restore a backup made by `backup.sh` in that case.

## Releases and image verification

The owner pushes release tags. `vX.Y.Z-rcN` builds the images and a GitHub pre-release and publishes to TestPyPI only; `vX.Y.Z` also publishes to PyPI, npm (`@intomd/sdk`) and the MCP registry. Images are pushed by digest, scanned with Trivy (HIGH/CRITICAL findings with a fix fail the release), given an SPDX SBOM (syft; also attached to the GitHub release) and signed with cosign keyless before any tag points at them:

```sh
cosign verify ghcr.io/larpey/intomd-api:0.1.0 \
  --certificate-identity-regexp '^https://github.com/larpey/intomd/.github/workflows/images.yml@refs/tags/v' \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com
cosign verify-attestation --type spdxjson ghcr.io/larpey/intomd-api:0.1.0 \
  --certificate-identity-regexp '^https://github.com/larpey/intomd/.github/workflows/images.yml@refs/tags/v' \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com
```

One-time owner setup before the first publish (until then the publish jobs skip with a notice):

1. GitHub, Settings, Environments: create `release` with required reviewers (the owner) and deployment tags limited to `v*`; create `testpypi` (reviewers optional). `publish-gate` refuses to publish when `release` has no required reviewers.
2. PyPI and TestPyPI: add a trusted publisher (a pending publisher for new names) for each of `intomd`, `intomd-converters` and `intomd-mcp`: owner `larpey`, repository `intomd`, workflow `release.yml`, environment `release` (PyPI) or `testpypi` (TestPyPI).
3. npm: create the `@intomd` scope and configure trusted publishing for `@intomd/sdk`: repository `larpey/intomd`, workflow `release.yml`, environment `release`. npm requires the package to exist before trusted publishing can be set, so the very first publish may need a one-off manual `npm publish` by the owner.
4. MCP registry: nothing to configure; `mcp-publisher login github-oidc` proves ownership of `io.github.larpey/*`.
5. Settings, Variables: set `INTOMD_PUBLISH_ENABLED` to `true`.

## Running without Docker

```sh
uv sync --all-packages --dev
uv run intomd serve                          # API and web UI on http://127.0.0.1:8080
```

`intomd serve` uses the inline queue when Redis is not configured and refuses to bind a non-loopback
address without `--i-know-this-is-public`. For a split setup run the API with
`uv run uvicorn intomd_api.main:app --port 8000` and a worker with
`uv run python -m intomd_api.worker --queues default`.

## Retention

Jobs, inputs, and results are deleted `INTOMD_RETENTION_HOURS` (default 24) after creation by the
`purge` service. `DELETE /v1/jobs/{id}` deletes a job immediately.

## Compose-only variables

These are read by `deploy/docker-compose.yml` and Caddy, not by the API:

| Variable | Default | Purpose |
|---|---|---|
| `INTOMD_DOMAIN` | empty | Site address for Caddy (empty: plain HTTP on `:8080`). |
| `INTOMD_ACME_EMAIL` | empty | Contact address for Let's Encrypt. |
| `INTOMD_REDIS_PASSWORD` | empty | Redis `requirepass`; compose builds `INTOMD_REDIS_URL` from it. Use hex. |
| `INTOMD_VERSION` | `latest` | Image tag when not building locally. |
| `INTOMD_PLAIN_PORT`, `INTOMD_HTTP_PORT`, `INTOMD_HTTPS_PORT` | `8080`, `80`, `443` | Host ports. |
| `INTOMD_CADDY_MAX_BODY` | `512MB` | Edge request body cap. |
| `INTOMD_TMPFS_SIZE` | `2g` | Size of each container's `/tmp`. |
| `INTOMD_API_WORKERS` | `2` | Uvicorn worker processes. |
| `INTOMD_REDIS_MAXMEM` | `256mb` | Redis memory cap. |
| `INTOMD_BACKUP_DIR` | `deploy/backups` | Where `backup.sh` writes tarballs. |
| `INTOMD_BACKUP_KEEP` | `14` | How many backups `backup.sh` keeps. |
| `INTOMD_ENV_FILE` | `deploy/.env` | Shell variable only: the env file the scripts and containers use. |

## API environment variables

Every variable the API and its workers read, generated from `intomd_api.settings.Settings`.
Field `foo_bar` is read from `INTOMD_FOO_BAR`. Comma lists are plain comma-separated strings.

<!-- BEGIN gen_env_doc (generated by tools/gen_env_doc.py; do not edit by hand) -->

### Instance

| Variable | Type | Default | Description |
|---|---|---|---|
| `INTOMD_PUBLIC_MODE` | bool | `false` | Public-instance mode. Requires `INTOMD_JWT_SECRET` and `INTOMD_KEY_PEPPER` of at least 32 bytes, requires a Turnstile challenge for URL jobs, and never deduplicates anonymous jobs across clients. |
| `INTOMD_PUBLIC_URL` | str | `http://localhost:8000` | Externally visible base URL. Used for links in error documents and to decide whether cookies are marked `Secure`. |
| `INTOMD_DATA_DIR` | path | `~/.intomd` | Base directory for the default SQLite database and filesystem blob store. |
| `INTOMD_WEB_DIST` | path | unset | Directory with the built web UI (`apps/web/dist`) to serve at `/`. Unset: `apps/web/dist` next to the source tree when present, else no UI. The compose stack defaults it to the image's `/app/apps/web/dist`. |
| `INTOMD_SCHEDULER_ENABLED` | bool | `true` | Run the retention purge inside the API process. Compose sets `false` and runs the separate `purge` service instead. |

### Storage

| Variable | Type | Default | Description |
|---|---|---|---|
| `INTOMD_DATABASE_URL` | str | unset | Database URL. Unset: SQLite at `<data_dir>/intomd.db`. |
| `INTOMD_BLOB_BACKEND` | fs / s3 | `fs` | Where inputs, IR, and rendered results are stored: local filesystem or S3-compatible storage. |
| `INTOMD_BLOB_FS_ROOT` | path | unset | Root of the filesystem blob store. Unset: `<data_dir>/blobs`. |
| `INTOMD_S3_ENDPOINT` | str | unset | S3 endpoint URL (for MinIO or another S3-compatible service). Unset: the AWS default. |
| `INTOMD_S3_BUCKET` | str | `intomd` | S3 bucket name. |
| `INTOMD_S3_ACCESS_KEY` | secret | unset | S3 access key id (secret). |
| `INTOMD_S3_SECRET_KEY` | secret | unset | S3 secret access key (secret). |
| `INTOMD_S3_REGION` | str | `us-east-1` | S3 region. |
| `INTOMD_RETENTION_HOURS` | int | `24` | Hours a job and its blobs are kept. `0` deletes the job on first result download (it is kept for at most one hour otherwise). |
| `INTOMD_PURGE_INTERVAL_S` | int | `600` | Seconds between retention purge runs. |

### Queue

| Variable | Type | Default | Description |
|---|---|---|---|
| `INTOMD_REDIS_URL` | str | `redis://localhost:6379/0` | Redis URL for the RQ queues, job events, and rate limits. Compose builds it from `INTOMD_REDIS_PASSWORD`. |
| `INTOMD_QUEUE` | rq / inline | `rq` | `rq` sends jobs to RQ workers; `inline` converts in the API process (development and tests). |
| `INTOMD_JOB_TIMEOUT_S` | int | `1800` | Upper bound on any job's wall-clock time. Per-queue timeouts (default 600 s, media 3600 s, fetch 120 s) are capped by it. |
| `INTOMD_JOB_MEM_MB` | int | `4096` | Address-space limit (RLIMIT_AS) for a conversion child process on the default queue. |
| `INTOMD_MEDIA_JOB_MEM_MB` | int | `8192` | Address-space limit for a conversion child process on the media queue (Phase 2). |
| `INTOMD_WORKER_DEFAULT_CONCURRENCY` | int | `2` | Default-queue worker slots. Used to size the global active-job cap. |
| `INTOMD_WORKER_MEDIA_CONCURRENCY` | int | `1` | Media-queue worker slots. Used to size the global active-job cap. |
| `INTOMD_MAX_ACTIVE_JOBS` | int | unset | Global cap on queued and running jobs; beyond it the API answers `queue_unavailable`. Unset: 2 x (default + media worker slots). |
| `INTOMD_RESIDENTIAL_WAIT_SECONDS` | int | `180` | How long a residential-only fetch job waits while no fetch node is online before it asks the user to upload the file instead (`needs_user_action`). |
| `INTOMD_MAX_RESULT_BYTES` | int | `268435456` | Largest IR JSON a conversion child process may hand back, in bytes; larger results fail with `result_too_large`. |

### Limits (anonymous callers; API keys carry their own)

| Variable | Type | Default | Description |
|---|---|---|---|
| `INTOMD_ANON_MAX_UPLOAD_MB` | int | `200` | Maximum upload size for anonymous callers, in MB. |
| `INTOMD_ANON_MAX_HTML_MB` | int | `10` | Maximum size of a fetched page for anonymous callers, in MB. |
| `INTOMD_ANON_MAX_DURATION_S` | int | `10800` | Maximum media duration for anonymous callers, in seconds. |
| `INTOMD_ANON_MAX_PAGES` | int | `2000` | Maximum pages converted per document. |
| `INTOMD_ANON_RATELIMIT_MAX` | int | `20` | Job creations allowed per client per window. |
| `INTOMD_ANON_RATELIMIT_WINDOW_S` | int | `60` | Length of the job-creation rate-limit window, in seconds. |
| `INTOMD_ANON_DAILY_MAX` | int | `200` | Job creations allowed per client per day. |
| `INTOMD_ANON_CONCURRENCY` | int | `1` | Active (queued or running) jobs allowed per anonymous client. |
| `INTOMD_ANON_RESULT_RATELIMIT_MAX` | int | `40` | Result and attachment fetches allowed per client per minute. |
| `INTOMD_ANON_SSE_MAX` | int | `10` | Concurrent SSE connections allowed per client. |
| `INTOMD_FETCH_NODE_CLAIMS_PER_MINUTE` | int | `60` | Job claims allowed per fetch node per minute. |

### Auth

| Variable | Type | Default | Description |
|---|---|---|---|
| `INTOMD_REQUIRE_API_KEY` | bool | `false` | Reject requests without a valid `X-API-Key` header. |
| `INTOMD_KEY_PEPPER` | secret | empty | Secret pepper for hashing API keys (secret). At least 32 bytes in public mode. |
| `INTOMD_JWT_SECRET` | secret | empty | Secret for signing the short-lived challenge cookie (secret). At least 32 bytes in public mode. |
| `INTOMD_IP_HASH_SALT` | secret | empty | Salt for client IP hashes (secret). Unset: falls back to the key pepper, then a fixed local salt. |
| `INTOMD_KEYS_FILE` | path | unset | keys.json of API keys with per-key limits (hashed; docs/api.md). Unset: database keys only. |

### Challenge

| Variable | Type | Default | Description |
|---|---|---|---|
| `INTOMD_TURNSTILE_SITEKEY` | str | empty | Cloudflare Turnstile site key shown by the web UI. |
| `INTOMD_TURNSTILE_SECRET` | secret | empty | Cloudflare Turnstile secret (secret). Setting it turns the challenge on for URL jobs. |
| `INTOMD_TURNSTILE_REQUIRED_FOR_FETCH` | bool | `false` | Require a Turnstile challenge for URL jobs even outside public mode. |
| `INTOMD_TURNSTILE_JWT_TTL_S` | int | `120` | Lifetime of the challenge cookie issued after a successful Turnstile check, in seconds. |

### Fetch

| Variable | Type | Default | Description |
|---|---|---|---|
| `INTOMD_ALLOW_PRIVATE_NETWORKS` | bool | `false` | Let URL jobs reach private, loopback, and link-local addresses. Leave `false` unless the instance is on a trusted network. |
| `INTOMD_PLATFORMS_FILE` | path | unset | Path to a `platforms.toml` that marks hosts `sanctioned`, `residential_only`, or `disabled`. |
| `INTOMD_FETCH_NODE_SECRET` | secret | unset | Shared secret fetch nodes send as a bearer token (secret, at least 16 characters). Unset: the fetch-node endpoints are not mounted. |
| `INTOMD_FETCH_NODE_CIDR` | comma list | `100.64.0.0/10` | Comma-separated CIDRs fetch nodes may connect from (the Tailscale range by default). |

### HTTP

| Variable | Type | Default | Description |
|---|---|---|---|
| `INTOMD_CORS_ORIGINS` | comma list | empty | Comma-separated origins allowed by CORS. Empty: same-origin only. |
| `INTOMD_TRUST_PROXY_HEADER` | str | empty | Header carrying the client IP (for example `X-Forwarded-For` or `CF-Connecting-IP`). Honored only when the peer is in `INTOMD_TRUSTED_PROXIES`. |
| `INTOMD_TRUSTED_PROXIES` | comma list | empty | Comma-separated CIDRs of reverse proxies whose client-IP header is trusted. |

### Observability

| Variable | Type | Default | Description |
|---|---|---|---|
| `INTOMD_LOG_LEVEL` | debug / info / warning / error | `info` | Log level. |
| `INTOMD_LOG_FORMAT` | json / text | `json` | `json` (one object per line) or `text`. |
| `INTOMD_METRICS_TOKEN` | secret | unset | Bearer token (16+ chars, secret) for GET /metrics. Unset: /metrics is not mounted. |

<!-- END gen_env_doc -->
