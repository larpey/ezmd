# REST API

The API is asynchronous: creating a conversion returns a job, and the result is fetched (in any
profile and format) once the job is done. The machine-readable contract is
[openapi.json](api/openapi.json), also served live at `/openapi.json`. The Swagger and ReDoc UIs are
disabled because the API's Content-Security-Policy blocks their CDN assets.

Planned: an interactive reference rendered from `openapi.json` in these docs (Phase 1).

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
| GET | `/healthz` | Liveness |
| GET | `/readyz` | Readiness: database, Redis, and a live worker |
| POST | `/v1/fetch-node/{claim,heartbeat,upload,fail}` | Fetch-node protocol (mounted only when `INTOMD_FETCH_NODE_SECRET` is set; bearer secret and source CIDR checked; used from Phase 3) |

## Creating a job

Send either:

- `multipart/form-data` with a `file` part, optional `profile`, and optional `options` (a JSON
  object as a string), or
- `application/json`: `{"url": "...", "profile": "full", "options": {...}, "turnstile_token": null, "prefer_residential": false}`.

`options` takes converter options (`max_pages`, `max_duration_seconds`, `ocr`, `asr_model`, `diarize`,
`languages`, `extract_images`, `tracked_changes`, `comments`, `formulas`) and profile overrides as
dotted keys (for example `"chunks.chunk_tokens": 600`). Limits are clamped to the caller's caps.

Query parameters on `POST /v1/convert`:

- `wait` (seconds, max 60): block until the job finishes and return the rendered result directly;
  the job metadata is in the `X-Intomd-Job` header.
- `format`: the result format when `wait` returns a result.

Identical input, options, and profile from the same caller return the existing job with
`"deduplicated": true` and status `200`. An `Idempotency-Key` header (at most 255 characters) also
deduplicates. In public mode anonymous jobs are never deduplicated across clients.

The detected type, never the file extension, decides how a file is handled. Executables are
rejected with `unsupported_media_type`.

## Job states

`queued`, `fetching`, `converting`, `rendering`, then one of `done`, `failed`, or `needs_user_action`
(a URL that must be supplied by the user, for example from a residential-only host when no fetch
node is online). Jobs expire after `INTOMD_RETENTION_HOURS`.

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
`409 job_not_ready`. With `INTOMD_RETENTION_HOURS=0` the job is deleted after the first download.

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
client are capped by `INTOMD_ANON_SSE_MAX`.

## Authentication and limits

Anonymous use is allowed unless `INTOMD_REQUIRE_API_KEY=true`; API keys are sent as `X-API-Key`.
When Turnstile is enabled, URL jobs need a `turnstile_token` in the JSON body; a successful check sets
a short-lived challenge cookie. Responses carry `X-RateLimit-Limit`, `X-RateLimit-Remaining`, and
`X-RateLimit-Reset`; `429 rate_limited` and `503 queue_unavailable` include `Retry-After`. Defaults are
in [Self-hosting](selfhost.md#api-environment-variables).

Planned: API key management endpoints and per-key limits documentation (Phase 4).

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
