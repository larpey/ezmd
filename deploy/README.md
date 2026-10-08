# deploy/

Self-host and CI deployment files for intomd (P0-T11, P0-T12, P1-T14). Operator guide: docs/selfhost.md.

| File | Purpose |
|---|---|
| `Dockerfile` | One multi-stage file. Targets `api`, `worker`, `fetch-node` (`worker-media` lands in Phase 2). Build from the repo root. |
| `docker-compose.yml` | Core stack: `caddy`, `api`, `worker-default`, `worker-fetch`, `redis`, `purge`. |
| `docker-compose.gpu.yml` | Overlay adding `worker-media` on NVIDIA (profile `media`, Phase 2 image). |
| `Caddyfile` | Edge: TLS, upload cap, security headers, fetch-node path restriction, log redaction. |
| `seccomp-worker.json` | Docker's default seccomp profile plus explicit denials of `ptrace`, the `mount` family, `keyctl`/`add_key`/`request_key`, `bpf`, `userfaultfd`. |
| `egress-allowlist.sh` | Worker entrypoint wrapper. No-op by default; optional iptables allowlist (see below). |
| `smoke.sh` | End-to-end check: bring-up, convert a text file, poll, fetch `md` and `json`, verify worker isolation and container hardening. `--remote URL` tests an existing instance. |
| `env.example` | Every `INTOMD_*` variable (owned by the API; `tests/test_env_example.py` guards drift). |
| `bootstrap.sh` | Idempotent first run: env file (mode 600) with generated secrets, pull or `--build`, migrations, `keys.json` with an owner key, `up --wait`, smoke. |
| `backup.sh` | Online SQLite snapshot + `keys.json` + blobs + Caddy data + env file into a timestamped, checksummed `.tar.gz`; keeps the newest `INTOMD_BACKUP_KEEP`. |
| `restore.sh` | Verify checksums, stop, restore data and Caddy volume (`--with-env` for the env file), start, smoke. |
| `upgrade.sh` | Backup, set `INTOMD_VERSION`, pull, migrate, `up --wait`; rolls back (and restores the backup if migrations ran) on failure. |
| `lib.sh` | Shared shell helpers (`compose`, env file editing, `stackctl`). |
| `stackctl.py` | Runs inside a one-off `api` container: backup/verify/restore/migrate/has-keys. |

## Quick start

```bash
deploy/bootstrap.sh --domain intomd.example.com --email you@example.com --version 0.1.0
# or, locally: deploy/bootstrap.sh --plain-http --build
```

By hand: `cp deploy/env.example deploy/.env`, fill in the secrets, `docker compose -f deploy/docker-compose.yml up -d --build --wait`, `bash deploy/smoke.sh --no-build`.

- `INTOMD_DOMAIN` empty: plain HTTP on `:8080` (host port `INTOMD_PLAIN_PORT`).
- `INTOMD_DOMAIN=localhost`: HTTPS with Caddy's internal CA.
- `INTOMD_DOMAIN=intomd.example.com`: Let's Encrypt; set `INTOMD_ACME_EMAIL` for the contact.
- `INTOMD_REDIS_PASSWORD` should be hex (it is embedded in the Redis URL). Compose builds `INTOMD_REDIS_URL` from it and overrides any value in `.env`.

Images: `ghcr.io/larpey/intomd-api`, `ghcr.io/larpey/intomd-worker`, `ghcr.io/larpey/intomd-fetch-node`, pushed by `.github/workflows/release.yml` on `v*` tags only. Compose builds them locally with `--build`; `INTOMD_VERSION` picks a pushed tag otherwise.

## Security model

- Every app container: uid/gid 10001, `read_only: true`, `tmpfs /tmp`, `cap_drop: [ALL]`, `no-new-privileges`, cpu/memory/pids limits. Workers also load `seccomp-worker.json`.
- Networks: `internal` (`internal: true`, no internet) holds api, workers, purge, redis. Only `caddy` and `worker-fetch` (URL fetches through `intomd.core.netguard`) are also on `egress`. `worker-default` and the API have no internet route; `smoke.sh` asserts this from inside `worker-default`.
- Redis: no host port, `requirepass` when `INTOMD_REDIS_PASSWORD` is set, no persistence (tmpfs).
- Caddy keeps root inside its container with every capability dropped except `NET_BIND_SERVICE` (its image and volumes expect root). It is read-only apart from its `/data` and `/config` volumes.
- `/v1/fetch-node/*` is answered 404 at the edge unless the TCP peer is in the Tailscale ranges (`100.64.0.0/10`, `fd7a:115c:a1e0::/48`). The API enforces `INTOMD_FETCH_NODE_CIDR` again.
- bubblewrap is not installed in the worker image: with no capabilities and `mount`/`unshare` blocked by seccomp it cannot create namespaces there, and `intomd.core.sandbox` would select it from `PATH` and fail. The container is the sandbox; `sandbox.run` still applies rlimits, timeouts, minimal env, and output caps.

### Egress allowlist (optional)

Phase 0 workers need no egress (Magika's model ships in its wheel and is loaded at build time). When a later phase needs specific hosts (e.g. `huggingface.co`), prefer the Part 4 design: a one-shot `model-init` container on `egress` fills the read-only model volume. If a worker itself must reach a few hosts, run it with an override like:

```yaml
services:
  worker-default:
    user: "0:0"                      # the script drops to 10001 with no caps before exec
    cap_add: [NET_ADMIN, SETUID, SETGID, SETPCAP]
    networks: [internal, egress]
    environment:
      INTOMD_EGRESS_ALLOWLIST: "huggingface.co cdn-lfs.huggingface.co"
```

`egress-allowlist.sh` resolves the hosts once, sets `OUTPUT` to DROP except loopback, established flows, the container's own subnets, and the resolved IPs on 80/443, then `setpriv`s to 10001 with an empty bounding set and `no_new_privs`. It fails closed if the rules cannot be installed.

## Retention

The `purge` sidecar runs `python -m intomd_api.purge --loop` (retention purge every `INTOMD_PURGE_INTERVAL_S`, default 600 s, plus the fetch-node claim reaper), and the API runs with `INTOMD_SCHEDULER_ENABLED=false` so the uvicorn workers do not also purge.

## Image sizes (local build, uncompressed)

Recorded by CI in the job summary (`images` job) and enforced against budgets: api 600 MB, worker 1200 MB, fetch-node 400 MB (docs/decisions/P1-T14-T16.md). See STATUS.md for the latest numbers.

## TODO (later phases)

- `docker-compose.public.yml` (Phase 4): public-instance env, `egress-proxy` (squid, `squid.conf` from Part 4 4.12.1), metrics. Compose overlays cannot remove networks, so in public mode the bootstrap script must write a `compose.override.yml` that sets `networks: [internal, egressproxy]` for the workers.
- `docker-compose.pi.yml` (Phase 3): the Raspberry Pi fetch node (`network_mode: host`, Tailscale, watchtower) once `intomd fetch-node run` exists.
- `worker-media` target and service (Phase 2): ffmpeg, `[media]` extra, model volume, `model-init`.
- Host provisioning in `bootstrap.sh` (Docker install, ufw, fail2ban, sshd, systemd units; Part 4 4.9.8) with the public-instance runbook (Phase 4).
- Postgres and MinIO profiles (Part 4 4.9.2) once the API supports them.
