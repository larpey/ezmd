# REST API

The API is asynchronous: creating a conversion returns a job, and the result is fetched (in any
profile and format) once the job is done. The machine-readable contract is
[openapi.json](api/openapi.json), also served live at `/openapi.json`. The Swagger and ReDoc UIs are
disabled on the API because its Content-Security-Policy blocks their CDN assets; this site renders the
same file in the [OpenAPI reference](api-reference.md) with a bundled viewer.

Every operation in `openapi.json` has an `operationId`, a summary, a description, its tag, its
security, and the error responses it can return (all using the error schema below). The document
lints clean with Spectral 6.15.0 and the ruleset in `apps/api/.spectral.yaml`:

```
npx -y @stoplight/spectral-cli@6.15.0 lint docs/api/openapi.json --ruleset apps/api/.spectral.yaml --fail-severity hint
```

`apps/api/tests/test_api_openapi_lint.py` repeats the important checks in Python on every test run
(and runs Spectral itself with `EZMD_SPECTRAL=1`). Regenerate the file with
`uv run python apps/api/scripts/export_openapi.py`; a test fails when it is stale.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| POST | `/v1/convert` | Create a job from a multipart upload or a JSON URL request |
| GET | `/v1/jobs/{id}` | Job state and metadata |
| GET | `/v1/jobs/{id}/events` | Server-sent events for progress and state |
| GET | `/v1/jobs/{id}/result` | Rendered output (`profile`, `format`, and profile overrides as query parameters) |
| GET | `/v1/jobs/{id}/attachments/{path}` | CSV table sidecars and extracted images |
| POST | `/v1/jobs/{id}/supply` | Upload the file or caption JSON a `needs_user_action` job asks for |
| DELETE | `/v1/jobs/{id}` | Delete the job and its blobs now |
| GET | `/v1/capabilities` | Converters, profiles, formats, limits, fetch-node status |
| GET | `/v1/warnings` | The warning code registry: code, severity, family, description, suggestion, `truncates`, aliases |
| GET | `/healthz` | Liveness |
| GET | `/readyz` | Readiness: database, Redis, and a live worker |
| POST | `/v1/fetch-node/{claim,heartbeat,upload,fail}` | Fetch-node protocol (mounted only when `EZMD_FETCH_NODE_SECRET` is set; bearer secret and source CIDR checked; used from Phase 3) |

## Creating a job

Send either:

- `multipart/form-data` with a `file` part, optional `profile`, and optional `options` (a JSON
  object as a string), or
- `application/json`: `{"url": "...", "profile": "full", "options": {...}, "turnstile_token": null, "prefer_residential": false}`.

`options` takes converter options (`max_pages`, `max_duration_seconds`, `ocr`, `asr_model`, `diarize`,
`languages`, `extract_images`, `tracked_changes`, `comments`, `formulas`) and profile overrides as
dotted keys (for example `"chunks.chunk_tokens": 600`). Limits are clamped to the caller's caps.

These are the client-settable fields of the Python library's `ezmd.library.Options`: the API's
`ConvertOptionsIn` schema is generated from `Options` (same types and constraints, plus a 64-character
cap on `asr_model` and at most 10 `languages`), and the worker converts through `Options`, so an
options object that works with `ezmd.convert(..., options=...)` works over REST and the other way
round. The remaining `Options` fields (`max_seconds`, `max_bytes`, `experimental`, `converter`,
`allow_private_networks`, `extra`, `render`) are set by the server; sending them is `400
invalid_request`. Omitted fields use the library defaults.

Query parameters on `POST /v1/convert`:

- `wait` (seconds, max 60): block until the job finishes and return the rendered result directly;
  the job metadata is in the `X-Ezmd-Job` header.
- `format`: the result format when `wait` returns a result.

Identical input, options, and profile from the same caller return the existing job with
`"deduplicated": true` and status `200`. An `Idempotency-Key` header (at most 255 characters) also
deduplicates. In public mode anonymous jobs are never deduplicated across clients.

The detected type, never the file extension, decides how a file is handled. Executables are
rejected with `unsupported_media_type`.

## Job states

`queued`, `fetching`, `converting`, `rendering`, then one of `done`, `failed`, or `needs_user_action`
(a URL that must be supplied by the user, for example from a residential-only host when no fetch
node is online). Jobs expire after `EZMD_RETENTION_HOURS`.

## Results

`GET /v1/jobs/{id}/result?profile=compact&format=md`

| `format` | Content type | Notes |
|---|---|---|
| `md` | `text/markdown; charset=utf-8` | Default |
| `json` | `application/json` | The JSON rendering of the result |
| `txt` | `text/plain` | Plain text |
| `zip` | `application/zip` | Markdown, sidecar JSON, and attachments; sent as an attachment |
| `docx` | | `501 not_implemented` (Planned) |

`profile` defaults to the job's profile. Any other query parameter must be a dotted profile override
(for example `chunks.chunk_tokens=600`). A result requested before the job is done returns
`409 job_not_ready`. With `EZMD_RETENTION_HOURS=0` the job is deleted after the first download.

## Server-sent events

`GET /v1/jobs/{id}/events` streams `text/event-stream`. Each event has an `id` (resume with the
`Last-Event-ID` header or `?last_event_id=`), a name, and a JSON `data` object:

| Event | Data |
|---|---|
| `state` | `{"state": "converting"}` |
| `progress` | `{"progress": 40, "stage_message": "..."}` |
| `warning` | A warning object (`kind`, `severity`, `message`, ...) |
| `done` | `{"result_url": "...", "warnings_count": 0}`; the stream ends |
| `failed` | The error object; the stream ends |
| `needs_user_action` | What the job needs; the stream ends |

A `: keepalive` comment is sent every 15 seconds and a stream closes after one hour. Connections per
client are capped by `EZMD_ANON_SSE_MAX`.

## Authentication and limits

Anonymous use is allowed unless `EZMD_REQUIRE_API_KEY=true`; API keys are sent as `X-API-Key`.
When Turnstile is enabled, URL jobs need a `turnstile_token` in the JSON body; a successful check sets
a short-lived challenge cookie. Responses carry `X-RateLimit-Limit`, `X-RateLimit-Remaining`, and
`X-RateLimit-Reset`; `429 rate_limited` and `503 queue_unavailable` include `Retry-After`. Defaults are
in [Self-hosting](selfhost.md#api-environment-variables).

## API keys

Keys come from two places, and both store only `HMAC-SHA256(EZMD_KEY_PEPPER, key)`:

- the `api_keys` table, managed with `ezmd-admin keys create|list|revoke`;
- the bootstrap file at `EZMD_KEYS_FILE` (`keys.json`, mode 600), read at startup and re-read within
  a few seconds of any change. A malformed file stops the API at startup; a file that becomes
  malformed later keeps the previously loaded keys and logs an error.

`keys.json` is a JSON list in cobalt's shape:

```json
[
  {
    "key_hash": "<64 hex: HMAC-SHA256(pepper, key)>",
    "name": "obsidian-plugin-ci",
    "tier": "free",
    "unlimited": false,
    "limits": {"requests_per_window": 200, "window_s": 60, "requests_per_day": 10000, "concurrency": 3,
               "max_upload_mb": 200, "max_duration_s": 3600, "max_pages": 10000},
    "ips": ["203.0.113.0/24"],
    "user_agents": ["ezmd-obsidian/*"],
    "allowed_sources": ["*"],
    "disabled_sources": [],
    "residential_allowed": false,
    "expires": "2027-01-01T00:00:00Z",
    "notes": "issued 2026-11-02 via email"
  }
]
```

Every field except `name` and one of `key_hash` / `key` is optional (defaults shown). A plaintext
`key` (8 to 256 characters) is accepted for compatibility and hashed at load, but `key_hash` is
preferred: `ezmd-admin keys create --store file --name NAME` appends an entry with the hash and
prints the key once. Unknown fields are rejected (typos fail loudly). `ips` (CIDRs) and `user_agents`
(globs) restrict where a key may be used (`403 forbidden` otherwise); `allowed_sources` /
`disabled_sources` are host globs checked for URL inputs. Expired keys are `401 unauthorized`.
`allowed_families` is stored but not enforced yet.

## Warning codes

`GET /v1/warnings` returns every warning code (`ezmd.warnings.codes`) with its default severity,
family, description, suggested action, whether it means content was cut (`truncates`), and the retired
spellings that normalize to it (`aliases`). `GET /v1/jobs/{id}` includes `warnings`: the canonical
codes the conversion emitted, without duplicates, in first-seen order, next to `warnings_count`.

## Metrics

`GET /metrics` serves Prometheus text format. It exists only when `EZMD_METRICS_TOKEN` (16+
characters) is set, and every scrape must send `Authorization: Bearer <token>`; Caddy also returns 404
for `/metrics` at the public edge. It is not in `openapi.json`. Series:

| Series | Type | Labels |
|---|---|---|
| `ezmd_jobs` | gauge | `state`, `queue` (job rows until purged) |
| `ezmd_queue_depth` | gauge | `queue` (queued jobs) |
| `ezmd_jobs_finished_total` | counter | `state` (done, failed, needs_user_action), `queue` |
| `ezmd_conversion_duration_seconds` | histogram | `converter` |
| `ezmd_warnings_total` | counter | `code` |
| `ezmd_rate_limited_total` | counter | `reason` (create, result, sse, concurrency, active_job_cap, fetch-claim) |
| `ezmd_fetch_node_online` | gauge | `node_id` (1 per node seen in the last 60 s) |
| `ezmd_fetch_nodes_online` | gauge | none (count; alert on `== 0`) |
| `ezmd_build_info` | gauge | `version` |

Counters live in Redis (memory in inline mode), so API and worker processes add to the same series.

## Admin CLI

Administration is host-only: there are no admin HTTP endpoints. `ezmd-admin` reads the same
`EZMD_*` environment as the API (`docker compose exec api ezmd-admin ...`):

| Command | Does |
|---|---|
| `ezmd-admin keys create --name NAME [--store db\|file] [--env live] [limits...]` | Create a key and print it once |
| `ezmd-admin keys list [--json]` | Database and file keys with their limits (never hashes or keys) |
| `ezmd-admin keys revoke ID` | Revoke a database key (`key_...`) or remove a file key (`kf_...`) |
| `ezmd-admin jobs list [--state STATE\|active] [--limit N] [--json]` | Most recent jobs |
| `ezmd-admin jobs kill ID` | Fail an active job and cancel or stop its RQ job |
| `ezmd-admin reap [--now] [--temp-age-s N]` | One reaper pass: expired claims, stale jobs, expired jobs, orphaned temp dirs |

The reaper (also run by the API scheduler every 30 s and by `python -m ezmd_api.purge`) fails
jobs nobody updated for longer than their queue's timeout plus 150 s with `timeout`, unless the job
is still waiting in its queue. `--now` drops the 150 s grace.

## Errors

Every error has the same shape:

```json
{
  "error": {
    "code": "input_too_large",
    "message": "Upload exceeds the limit.",
    "status": 413,
    "request_id": "req_...",
    "detail": {"limit_bytes": 209715200},
    "docs": "https://<host>/docs/errors#input_too_large"
  }
}
```

Messages never contain stack traces, server paths, or engine internals. See [Errors](errors.md) for
every code, and [Warning codes](warnings.md) for the warnings attached to successful results.
