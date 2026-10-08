## Part 4: Interfaces, deployment, operations, and roadmap

### 4.0 Scope and conventions

This part covers everything a user touches (web UI, CLI, library, MCP, SDK, extension, share sheet, integrations), everything an operator touches (compose, runbook, abuse controls, hardening, legal pages), the quality gates (tests, CI, docs), and the phased roadmap with the risk register. It does not redefine the core data model, the converter registry, the output profiles, or the REST contract. Those live in Parts 1 through 3. Where this part needs them it references them by name:

- `POST /v1/convert`, `GET /v1/jobs/{id}`, `GET /v1/jobs/{id}/events` (SSE), `GET /v1/jobs/{id}/result`, `GET /v1/capabilities`, `GET /healthz`, the fetch-node `POST /v1/fetch-node/claim` and `/upload` endpoints, and API key headers: Part 3.
- `Result`, `Warning`, `Provenance`, `Profile` types and the frontmatter schema: Part 1.
- Converter registry, MIME routing, engine tiers, sidecar JSON: Part 2.

Rules that apply to every section here:

1. Every interface is a thin client over the same `ezmd.core` library or the same REST API. No interface may contain conversion logic. If you find yourself parsing a document in `apps/web` or `packages/mcp`, stop and move it into `packages/core` or a converter package.
2. Every interface reports warnings from `Result.warnings` verbatim to the user. Silent loss is the failure mode this project exists to eliminate. A UI that hides a warning is a bug.
3. Every interface defaults to the `compact` profile for interactive use and `full` for file output, unless the user picks one. The MCP server defaults to `agent`.
4. Every interface sends `User-Agent: ezmd-<interface>/<version>` so the public instance can see which surfaces carry traffic.
5. Phases referenced below map to ROADMAP.md in section 4.17. Do not build a Phase 3 interface before the Phase 2 gate passes.
6. After every task ID in this part is finished, update `STATUS.md` (format in 4.17.8) before starting the next task.

---

## A. Interfaces

### 4.1 Web UI (`apps/web`)

Phase: 1 (v1), with Phase 2 additions (in-browser Whisper) and Phase 3 additions (share target, extension handoff warnings).

#### 4.1.1 Design direction

Plain, fast, utilitarian. One screen. No marketing page, no hero image, no carousel. The whole first paint is: a one-line explainer, the input box, a "self-host" link, and a footer with Terms, Privacy, DMCA, Source, and Support links. Mobile-first: most anonymous users arrive from a TikTok or YouTube link on a phone, so the input box must be reachable and usable without zooming, with a 44px minimum tap target on every control. Target: Lighthouse performance 95+ on a throttled mobile profile, total JS under 180 KB gzipped for the main bundle (Whisper WASM is a separate lazy chunk).

Stack: React 18, Vite 5, TypeScript strict, Tailwind for utility styles with a small token file (`src/theme.css`) for colors so dark mode is a CSS variable swap. No component library. No analytics, no fonts from third-party CDNs (system font stack), no tracking scripts of any kind. The build is static and is served by the API container from `apps/api/static/` (Part 3 mounts it at `/`). The web app talks only to same-origin `/v1/*`, with `VITE_API_BASE` overridable at build time for self-hosters who split hosts.

#### 4.1.2 Build steps

1. Scaffold `apps/web` with `pnpm create vite --template react-ts`. Add `@tailwindcss/vite`, `react-markdown`, `remark-gfm`, `rehype-sanitize`, `@tanstack/react-query`, `zod`. Pin exact versions. No `react-router`; this is a single route plus hash state.
2. Implement `src/api/client.ts` by importing the TS SDK from `packages/sdk-ts` (4.5). Do not hand-write fetch calls in the UI.
3. Build `src/components/InputBox.tsx`: a single `<textarea>` with a drop zone overlay. It accepts (a) pasted text containing a URL (detected with a strict URL regex, trimmed, single URL), (b) pasted plain text (anything not a lone URL), (c) dropped or picked files (multiple, `<input type="file" multiple>` fallback for mobile), (d) a clipboard image via `paste` event `clipboardData.files`. The box decides the input kind and shows a one-line chip ("URL", "Text, 1,240 words", "3 files, 4.2 MB", "Image from clipboard") so the user sees what will be sent. A profile selector (segmented control: full / compact / rag / agent) and a "Convert" button sit beneath. Enter submits for a URL; Ctrl/Cmd+Enter submits for text.
4. On submit call `POST /v1/convert` once per file (one job per source; the UI keeps a job list) or once for a URL/text. If the capabilities response (fetched once on load, cached in memory) says `turnstile_required_for_fetch`, render the Turnstile widget in invisible mode before the first URL submit and attach the resulting token per Part 3. Never render Turnstile for file uploads unless capabilities says so.
5. Build `src/components/Progress.tsx`: subscribe to the job's SSE stream with `EventSource`. Map Part 3 stage names to labels: `queued` → "Waiting in queue (position N)", `fetching` → "Fetching", `detecting` → "Detecting type", `converting` → "Converting (engine name)", `transcribing` → "Transcribing (MM:SS of MM:SS)", `ocr` → "Reading images", `postprocessing` → "Formatting", `done`, `failed`. Show a determinate bar when the event carries `progress` 0..1, otherwise an indeterminate bar. On SSE error fall back to polling `GET /v1/jobs/{id}` every 2 s with backoff to 10 s.
6. Build `src/components/ResultView.tsx` with two tabs: "Rendered" (react-markdown with GFM and rehype-sanitize; raw HTML in the Markdown is never rendered, it is shown escaped) and "Raw" (a `<pre>` with soft wrap toggle). Above the tabs: a copy button (copies raw Markdown; shows "Copied" for 1.5 s), the profile switcher, the download menu, and the token badge. The profile switcher re-requests the result with `?profile=` per Part 3 (the server re-renders from the cached intermediate within the job TTL; it does not re-convert). The token badge shows `tokens` from frontmatter with a tooltip "cl100k estimate".
7. Download menu: `.md` (raw body with frontmatter), `.txt` (body with frontmatter stripped and Markdown syntax left intact), `.json` (sidecar), `.srt` (only when the result has `segments` from a transcript), `.docx` (server-side via `GET /v1/jobs/{id}/result?format=docx`, which Part 3 implements with pandoc; the UI hides the option if capabilities lacks `docx_export`). File name is derived from frontmatter `title` slugified, capped at 80 chars, falling back to the job id.
8. Build `src/components/Warnings.tsx`: a panel above the result, collapsed to a single line count ("2 warnings") when there are warnings, expanded by default when any warning has severity `error`. Each warning renders `code`, `message`, and a suggested action from a local map. Required mappings: `fetch_blocked_by_platform` → "This platform blocked our server. Upload the file directly, or install the browser extension to fetch from your own connection." with a link to the extension docs; `pages_without_text` → "N pages had no text layer and OCR is off on this instance. Self-host with the `ocr` extra to read them."; `duration_cap_exceeded` → "This instance caps audio at MM:SS. The transcript covers the first MM:SS."; `injection_flagged` → "Some text looks like instructions aimed at an AI. It was kept, not removed, and is flagged in the sidecar."; `truncated` → "Output was truncated at the size cap. Download the full result or self-host."
9. History: store the last 50 jobs in `localStorage` under `ezmd.history.v1` as `{id, title, source_kind, created_at, profile, tokens, expires_at}`. Never store result bodies in `localStorage` by default (a 2 MB transcript blows the quota on Safari); store a 200-char preview. A "Keep result on this device" toggle per item stores the full body in IndexedDB. History is a collapsible list beneath the input box, each row re-opens the result if the job is still within the server TTL, otherwise shows "Expired on the server" with the local copy if kept. A "Clear history" button wipes both stores. Wrap every storage access in try/catch and render correctly with storage unavailable.
10. Dark mode: respect `prefers-color-scheme`, with a three-state toggle (system/light/dark) persisted to `localStorage`. Body has an explicit background in both modes. Contrast ratio 4.5:1 minimum on all text.
11. Accessibility: every control has a visible label or `aria-label`; the drop zone is a labelled button for keyboard users; focus order is input → profile → convert → result tabs → actions; progress uses `role="status"` with `aria-live="polite"`; warnings use `role="alert"` when severity is error; result tabs follow the WAI-ARIA tabs pattern with arrow key navigation; all icon buttons have text alternatives; the app is fully operable with keyboard only and tested with VoiceOver on iOS Safari and NVDA on Firefox.
12. Explainer and links: a single sentence under the title, e.g. "Paste a link, drop a file, or paste text. Get clean Markdown with nothing silently dropped." A "Self-host" link to the docs quickstart. The footer shows the instance's `instance_name` and `sponsor` fields from capabilities if set ("Hosting by X"), the retention note ("Results are deleted after 24 hours"), and the legal links.
13. Phase 2: in-browser Whisper. Add a lazy-loaded module `src/local/whisper.ts` using `@huggingface/transformers` with `whisper-tiny` or `whisper-base` (user-selectable) on WebGPU when available, falling back to WASM. Offer it only when (a) the user drops an audio/video file under 25 MB and (b) `navigator.gpu` exists or the file is under 5 MB. The UI shows a checkbox "Transcribe in my browser (private, slower)". When checked, the browser decodes audio with `AudioContext` to 16 kHz mono, runs the model, and posts the resulting segments as text to `POST /v1/convert` with `source_type: transcript_segments` so the server applies the same paragraphing, chaptering, and profile rendering as a server-side transcript. Model weights are fetched from the instance's `/models/` path (the API serves them from the model cache volume) so no third-party CDN is contacted. Show download size before fetching.
14. Phase 3: PWA manifest with `share_target` (4.7.2), service worker that caches the shell only (never results), install prompt suppressed unless the user opens the menu.
15. Playwright tests per 4.14.6.

#### 4.1.3 Acceptance criteria

- A phone user on a 3G throttle profile can paste a URL and see the first progress event within 3 s of tapping Convert (excluding Turnstile).
- Dropping five mixed files creates five jobs, each with its own progress and result, and a "Download all as zip" option appears (client-side zip with `fflate`).
- Switching profile on a finished result does not create a new job.
- Every warning code emitted by any converter in `fixtures/` renders with a non-empty suggested action (test enumerates codes from `packages/core` and asserts the map covers them all).
- Keyboard-only run through paste → convert → copy → download succeeds in Playwright.
- axe-core reports zero serious or critical violations.
- No network request leaves the origin except to Turnstile when enabled (Playwright asserts on request domains).
- Bundle size check in CI fails above 180 KB gzipped for the main chunk.

### 4.2 CLI (`ezmd`)

Phase: 1 (`convert`, `batch`, `serve`, `doctor`), Phase 2 (`models pull`, `watch`), Phase 3 (`fetch-node run`).

#### 4.2.1 Design

The CLI lives in `packages/core/src/ezmd/cli/` and is installed by the `ezmd` package as the `ezmd` console script. It uses `typer` for parsing and `rich` for progress and tables, both optional-free (they are core dependencies, small). It runs conversions in-process by default (no server needed) and can target a remote instance with `--remote URL` or `EZMD_REMOTE`, in which case it uses the same REST client the SDK uses. Every command supports `--json` for machine output on stdout with all human output on stderr, and `--quiet`.

Config file `~/.config/ezmd/config.toml` (XDG on Linux, `~/Library/Application Support/ezmd/config.toml` on macOS, `%APPDATA%\ezmd\config.toml` on Windows; `EZMD_CONFIG` overrides):

```toml
[defaults]
profile = "full"          # full | compact | rag | agent
format = "md"             # md | txt | json | docx | srt
out_dir = "."             # for batch and watch
sidecar = true            # write .json beside .md

[remote]
url = ""                  # empty = in-process
api_key = ""              # or EZMD_API_KEY

[engines]
pdf = "docling"           # engine preference per family, see Part 2
asr = "faster-whisper"    # faster-whisper | parakeet | groq
asr_model = "small"
ocr = "auto"

[fetch]
cookies_file = ""         # self-host only, see Part 2
proxy = ""
yt_dlp_extra_args = []

[limits]
max_file_mb = 500
max_duration_s = 14400

[watch]
debounce_ms = 1500
delete_source = false
```

Environment variables override the file (`EZMD_PROFILE`, `EZMD_REMOTE`, `EZMD_API_KEY`, etc.). CLI flags override both.

#### 4.2.2 Commands

1. `ezmd convert <path|url|-> [--profile P] [--out FILE|DIR] [--format md|txt|json|docx|srt] [--no-sidecar] [--engine family=name] [--lang xx] [--remote URL]`. Reads stdin when `-`. Writes to stdout when `--out` is omitted and the input is a single source; writes `<title>.md` plus sidecar into `--out DIR` when it is a directory. Shows a Rich progress bar on stderr with stage labels identical to the web UI's. Prints warnings to stderr as `WARN [code] message` after the output, and in `--json` mode includes them in the JSON object.
2. `ezmd batch <dir|glob> --out <dir> [--recursive] [--workers N] [--profile P] [--format F] [--continue-on-error] [--manifest manifest.jsonl]`. Walks inputs, skips files whose output already exists with a matching `content_hash` in the sidecar (idempotent re-runs), converts with a process pool of `N` workers (default: CPU count minus one, max 8), writes a `manifest.jsonl` with one line per input (`path, status, out, warnings, seconds, tokens`), and prints a Rich table summary (converted, skipped, failed, total tokens). Exit code 0 only if every file converted or was skipped; 3 if any failed and `--continue-on-error` was set; 1 otherwise. Output directory mirrors the input tree.
3. `ezmd watch <dir> --out <dir> [--profile P] [--format F]`. Uses `watchfiles`. On a new or modified file, waits `debounce_ms`, then converts and writes to `--out` mirroring the tree. Writes `.ezmd-failed/<name>.md` stub notes on failure with the warnings list, so the user's note tool sees something rather than nothing. Logs one line per event. Runs until SIGINT. Documented systemd user unit and launchd plist in docs.
4. `ezmd serve [--host 127.0.0.1] [--port 8080] [--workers N] [--no-ui]`. Starts the FastAPI app in-process with an in-process RQ-compatible worker when Redis is absent (`EZMD_QUEUE=inline`), so `pip install ezmd && ezmd serve` gives a working single-process server for a laptop. Binds loopback by default; binding `0.0.0.0` without `EZMD_API_KEYS` set prints a red warning and requires `--i-know-this-is-public`. Prints the URL and the MCP URL.
5. `ezmd doctor [--json]`. Checks and prints a table: Python version, `ezmd` version, installed extras, `ffmpeg` and `ffprobe` on PATH with version, `pandoc` presence, `libmagic`, Magika model present, each ASR/OCR model present in the cache with size, CUDA/ROCm/MPS availability via torch if installed, free disk in the model cache, Redis reachability if configured, `yt-dlp` version and Deno/Node presence, write access to config and cache dirs. Each row is OK, WARN, or MISSING with a one-line fix ("Install ffmpeg: apt install ffmpeg"). Exit 0 if no MISSING for the installed extras, 2 otherwise.
6. `ezmd models pull [name|--all-for-extras] [--cache DIR]` and `ezmd models list`, `ezmd models rm <name>`. Pulls from Hugging Face by pinned revision (revision hashes live in `packages/core/src/ezmd/models/registry.toml` with name, repo, revision, size, license, SPDX id, and the extras that need it). Shows download size before starting, a progress bar, and verifies SHA256 after. Refuses to pull a model whose license is not on the allowlist (4.15.2) unless `--accept-license <spdx>` is passed, and prints the license text location.
7. `ezmd fetch-node run [--instance URL] [--token T] [--concurrency 1]`. Runs the fetch-node loop from `apps/fetch-node` (Part 3 defines claim/upload). Included so a Pi needs only `pip install ezmd[fetch]`.
8. `ezmd capabilities [--remote URL]` prints the capabilities JSON (handy for support tickets).
9. `ezmd version` prints version, commit, and build date.

Exit codes: 0 success; 1 generic failure; 2 bad arguments or missing dependency; 3 partial success (batch); 4 fetch blocked by platform (so scripts can route to a fallback); 5 input too large or duration cap; 6 unsupported type; 130 interrupted.

#### 4.2.3 Acceptance criteria

- `uvx ezmd convert https://example.com` works on a clean machine with only the core extras and prints Markdown with frontmatter.
- `ezmd convert file.pdf --json | jq .warnings` is valid JSON even when conversion fails (status `failed`, warnings present, exit code non-zero).
- `ezmd batch fixtures/docs --out /tmp/out` twice in a row: second run reports every file as skipped and takes under 1 s per 100 files.
- `ezmd doctor` on a machine without ffmpeg shows MISSING with the install hint and exits 2 only if the `media` extra is installed.
- Shell completion scripts generate for bash, zsh, fish via `ezmd --install-completion`.
- `--help` for every command fits in 40 lines.

### 4.3 Python library

Phase: 1.

#### 4.3.1 Public API

The library is the product; everything else wraps it. The public surface, exported from `ezmd/__init__.py`, is deliberately small:

```python
from ezmd import convert, convert_async, Result, Profile, Options, Progress
from ezmd import capabilities, register_converter

def convert(
    source: str | Path | bytes | IO[bytes] | "Source",
    *,
    profile: Profile | str = "full",
    options: Options | dict | None = None,
    on_progress: Callable[[Progress], None] | None = None,
    filename: str | None = None,        # hint when source is bytes/IO
    mime: str | None = None,            # override detection
) -> Result: ...

async def convert_async(...same signature...) -> Result: ...

def convert_many(sources: Iterable[...], *, workers: int = 4, **kw) -> Iterator[Result]: ...
```

`Result` is the Part 1 dataclass; the library adds convenience methods `result.markdown` (body with frontmatter), `result.body`, `result.frontmatter` (dict), `result.sidecar` (dict), `result.warnings` (list of `Warning`), `result.render(profile)` to re-render another profile from the retained intermediate representation without re-converting, `result.save(path, sidecar=True)`, `result.chunks(chunk_tokens=400, overlap=0)` for the `rag` profile, and `result.tokens`.

`Progress` is a frozen dataclass `(stage: str, progress: float | None, message: str, detail: dict)`, emitted on the calling thread for sync and awaited in the loop for async. Stage names match Part 3's SSE events exactly, so a UI backed by the library and a UI backed by the API behave identically.

`Options` mirrors the request body of `POST /v1/convert` (Part 3) field for field, so `Options(**request_json)` round-trips. This is the mechanism that keeps the API and the library from drifting: the API handler builds `Options` from the request and calls `convert`, nothing else.

#### 4.3.2 In-process embedding

1. `convert` runs the full pipeline on the calling thread: detect → route → fetch (if URL) → convert → postprocess → render. It never spawns a server, never touches Redis, never writes outside the configured cache dir. Heavy engines (Docling, ASR models) are loaded lazily on first use and cached in a module-level LRU keyed by engine config, so a long-running process pays model load once. `ezmd.unload_models()` frees them.
2. Thread safety: `convert` is safe to call from multiple threads; model singletons are guarded by a lock and engines that are not thread-safe (some ONNX runtimes) are wrapped in a per-engine semaphore sized from `Options.engine_concurrency`.
3. `convert_async` runs the CPU-bound pipeline in a thread executor and awaits network I/O natively (fetch stages use `httpx.AsyncClient`), so FastAPI handlers and MCP servers can await it without blocking the loop.
4. The library reads `~/.config/ezmd/config.toml` for defaults only when `Options.load_user_config=True` (default True in the CLI, False when imported as a library, to keep library behavior deterministic).
5. Fetching from URLs in-process uses the same SSRF guard and fetch chain as the server (Part 2), with `Options.allow_private_networks` defaulting to False. Library users who need to fetch from an intranet set it explicitly.
6. Logging goes to the `ezmd` logger with no handlers attached; the CLI attaches a Rich handler. Never print from library code.

#### 4.3.3 Install matrix

| Install | Adds | Approx size | Notes |
|---|---|---|---|
| `pip install ezmd` | core, CLI, HTML/Markdown/text/data/code/email/notebook converters, Magika, Trafilatura, Defuddle port, openpyxl, python-pptx, pandoc shim (uses system pandoc if present) | under 120 MB | no torch |
| `ezmd[docs]` | Docling and its CPU torch dependency | ~1.2 GB | PDF layout, Office via Docling |
| `ezmd[media]` | ffmpeg-python, faster-whisper, silero-vad, pyannote (CC-BY weights pulled separately), ctranslate2 | ~600 MB plus models | ASR and diarization |
| `ezmd[ocr]` | rapidocr-onnxruntime (PP-OCR), zxing-cpp, optional PaddleOCR-VL loader, Florence-2 loader | ~400 MB plus models | OCR and captions |
| `ezmd[web]` | Crawl4AI, Playwright (browser downloaded via `ezmd models pull playwright`) | ~500 MB | JS rendering and crawls |
| `ezmd[fetch]` | yt-dlp, bgutil provider client, fetch-node loop | ~50 MB plus Deno | self-host and Pi only |
| `ezmd[server]` | FastAPI, uvicorn, redis, rq, sqlalchemy, alembic | ~40 MB | `ezmd serve` with a real queue |
| `ezmd[mcp]` | `mcp` SDK | ~10 MB | `ezmd-mcp` entry point |
| `ezmd[all]` | everything above except `fetch` | | `fetch` is excluded from `all` deliberately so the public instance image never carries yt-dlp |
| `ezmd[nonfree]` | PyMuPDF4LLM (AGPL), extract-msg (GPL) | | prints license notice on install via a `.pth` hook and at first use |

Extras must install cleanly on Linux x86_64 and arm64, macOS arm64, and Windows x86_64 (CI matrix in 4.15). A converter whose extra is missing registers itself as `unavailable` with a reason, and `ezmd.capabilities()` lists it, so `convert` on a PDF without `[docs]` falls back to the pure-Python `pypdf` text-layer engine and emits `warning: engine_downgraded`.

#### 4.3.4 Acceptance criteria

- `python -c "import ezmd; print(ezmd.convert('fixtures/docs/simple.docx').markdown)"` works in a fresh venv with only `pip install ezmd`.
- Importing `ezmd` takes under 400 ms (no torch import at module load; measured in CI with `python -X importtime`).
- `convert_async` on a 20 MB PDF does not block a FastAPI event loop (test: a `/healthz` request during conversion returns in under 50 ms).
- `Result.render("compact")` on a result produced with `full` is byte-identical to converting with `compact` directly (golden test over the fixture corpus).
- The type stubs pass `mypy --strict` and the package ships `py.typed`.

### 4.4 MCP server (`packages/mcp`)

Phase: 1.

#### 4.4.1 Design

`packages/mcp` is a Python package `ezmd-mcp` (entry point `ezmd-mcp`) built on the official `mcp` Python SDK using `FastMCP`. It has two modes: local (imports `ezmd` and converts in-process; this is the `uvx ezmd-mcp` default) and remote (`--remote URL --api-key K` forwards to an instance using the REST client, with local fallback disabled by default). Default profile is `agent`, because the consumer is a model and the `agent` profile carries the untrusted-content fence, section IDs, and the pagination cursor.

Large outputs are the known pain point of every competing converter MCP server. This server never returns more than the caller's token budget in one tool result. Results are paginated: the first call returns the frontmatter, the section list, page 1, and `next_cursor`; subsequent calls with the cursor return the next page. Pages split on section boundaries first and never inside a table or code block (reuse the `rag` chunker with `chunk_tokens = budget`).

#### 4.4.2 Tools

All tools accept `profile` (default `agent`), `max_tokens` (default 8000, max 50000), and return a structured object plus a text block.

1. `convert_url(url, profile?, max_tokens?, options?)`: converts a URL. Returns `{job_id, title, source, tokens_total, pages_total, page: 1, next_cursor, warnings, frontmatter, sections: [{id, heading, tokens}], content}`. In remote mode it creates the job and waits up to 120 s (configurable), returning `{job_id, status: "running"}` with instructions to call `get_job` if the job is still running.
2. `convert_file(path, profile?, max_tokens?, options?)`: converts a local file path (local mode) or uploads it (remote mode). Path must be absolute and within `--allowed-dirs` (defaults to the current working directory and the user's home; the server refuses `/etc`, `/proc`, and any path containing `..`). Also accepts `data_url` for small inline files (under 1 MB) so hosted clients without a filesystem can pass bytes.
3. `convert_text(text, source_hint?, profile?, max_tokens?)`: converts pasted text, HTML, CSV, JSON, or any string. `source_hint` is a MIME or extension hint.
4. `get_job(job_id, cursor?, max_tokens?, profile?)`: returns the job status if not done, otherwise the page at `cursor` (or page 1). This is the pagination endpoint for all three convert tools. A cursor is an opaque base64 string encoding `(job_id, profile, page_index, chunker_version)`; cursors from a different profile are rejected with a clear error.
5. `list_capabilities()`: returns the capabilities object (supported types, installed extras, limits, instance name, whether fetch is allowed) so a model can decide up front whether to try a YouTube URL or ask the user to upload.
6. `search_result(job_id, query, max_tokens?)` (Phase 2): BM25 over the result's chunks, returns matching chunks with section breadcrumbs. Lets a model find the relevant part of a 200-page document without paging through it.

Resources: `ezmd://jobs/{id}` exposes the full raw Markdown as a resource for clients that support resources, and `ezmd://jobs/{id}/sidecar` the JSON. Prompts: one prompt `summarize_with_provenance` that instructs the model to cite section IDs and page markers from the result.

Error handling: every tool returns `isError: false` with a `warnings` array for partial success (this is the whole point), and `isError: true` only for hard failures (unsupported type, fetch refused, size cap). Error text includes the warning code and the same suggested action strings the web UI uses, pulled from the shared map in `packages/core`.

#### 4.4.3 Transports and auth

1. stdio: default. `uvx ezmd-mcp` or `ezmd-mcp --transport stdio`.
2. Streamable HTTP: `ezmd-mcp --transport http --host 127.0.0.1 --port 8765`. Binds loopback by default. Binding a non-loopback host requires `--token` or `EZMD_MCP_TOKEN`; the server refuses to start otherwise. Bearer token checked on every request. The API container also mounts the MCP HTTP app at `/mcp` (Part 3) behind the same API key middleware, so a remote instance is one URL for REST and MCP.
3. SSE transport is not implemented (deprecated in the MCP spec); document this.

#### 4.4.4 Client configuration examples

Claude Desktop (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "ezmd": {
      "command": "uvx",
      "args": ["ezmd-mcp"],
      "env": { "EZMD_PROFILE": "agent" }
    }
  }
}
```

Claude Code (`.mcp.json` in the project or `claude mcp add`):

```bash
claude mcp add ezmd -- uvx ezmd-mcp
# remote instance:
claude mcp add --transport http ezmd https://ezmd.example/mcp --header "Authorization: Bearer $EZMD_API_KEY"
```

Cursor (`.cursor/mcp.json`):

```json
{
  "mcpServers": {
    "ezmd": { "command": "uvx", "args": ["ezmd-mcp", "--allowed-dirs", "${workspaceFolder}"] }
  }
}
```

Document all three plus Windsurf and VS Code Copilot in `docs/mcp.md`.

#### 4.4.5 Registry listing

1. Add `mcp-name: io.github.<owner>/ezmd` to the README of the PyPI package (the registry checks this marker).
2. Create `packages/mcp/server.json` per the official registry schema: name `io.github.<owner>/ezmd`, description under 100 chars, `packages: [{registry_type: "pypi", identifier: "ezmd-mcp", version, transport: {type: "stdio"}}]`, plus a `remotes` entry for the public instance's `/mcp` URL marked as requiring a token.
3. In the release workflow (4.15.6), after PyPI publish, run `mcp-publisher login github-oidc && mcp-publisher publish`. The official registry propagates to GitHub's MCP registry and the aggregators (Glama, PulseMCP, Smithery), so do not submit to those separately beyond claiming the listing.
4. Add the Docker label `io.modelcontextprotocol.server.name=io.github.<owner>/ezmd` to the API image.

#### 4.4.6 Acceptance criteria

- `uvx ezmd-mcp` starts in under 2 s and answers `list_capabilities` in Claude Desktop without any config beyond the JSON above.
- A 300-page PDF via `convert_file` with `max_tokens=8000` returns page 1 under 8000 tokens (measured with tiktoken in the test) and a cursor; walking all cursors reconstructs the full body byte-for-byte.
- `convert_url` on a URL the fetch guard refuses returns `isError: true` with code `fetch_refused_private_network`.
- HTTP transport refuses to bind `0.0.0.0` without a token (test asserts non-zero exit and the message).
- `server.json` validates with `mcp-publisher validate` in CI.

### 4.5 TS SDK (`packages/sdk-ts`) and REST docs

Phase: 1.

#### 4.5.1 SDK

A thin, dependency-free (uses global `fetch` and `EventSource` or a tiny SSE parser for Node) TypeScript client published as `@ezmd/sdk` on npm, ESM and CJS, with `.d.ts`. Target: under 8 KB gzipped. It is used by `apps/web`, `apps/extension`, and external users.

```ts
import { EzmdClient } from "@ezmd/sdk";

const client = new EzmdClient({ baseUrl: "https://ezmd.example", apiKey?: string, turnstileToken?: () => Promise<string> });

const job = await client.convert({ url: "https://..." , profile: "compact" });          // returns Job
const job2 = await client.convert({ file: blob, filename: "a.pdf", profile: "full" });
const job3 = await client.convert({ text: "...", sourceHint: "text/html" });

for await (const ev of client.events(job.id)) { /* {stage, progress, message} */ }
const result = await client.result(job.id, { profile: "rag", format: "md" });          // string
const sidecar = await client.sidecar(job.id);                                           // object
const caps = await client.capabilities();
const done = await client.waitFor(job.id, { timeoutMs: 120000, onProgress });          // Job with status
```

Types are generated from the OpenAPI document (4.5.2) with `openapi-typescript` so the SDK cannot drift from the API; a CI step regenerates and fails on diff. Errors throw `EzmdError` with `code`, `status`, `warnings`, and `retryAfter`. The client honors `Retry-After` on 429 and 503 with a single automatic retry when `retry: true`. For `file` inputs over 8 MB it uses the multipart upload path from Part 3; for smaller, a single request.

Also ship `@ezmd/sdk/node` with a helper `convertPath(path)` that streams from disk.

#### 4.5.2 REST docs

FastAPI generates OpenAPI 3.1 at `/openapi.json`. Steps:

1. Annotate every route with `summary`, `description`, `response_model`, `responses` for 400/401/413/422/429/503 using the shared error model, and `tags` (Convert, Jobs, Capabilities, FetchNode, Admin). Examples on every request body using the fixture corpus.
2. Serve Swagger UI at `/docs` and ReDoc at `/redoc` (FastAPI defaults), with the Swagger UI assets vendored into the image rather than loaded from a CDN (the UI must work air-gapped and must not leak visitor IPs to a CDN). Set `swagger_ui_parameters={"persistAuthorization": True}`.
3. Export `openapi.json` into `docs/api/openapi.json` on every build; the docs site renders it with `mkdocs-swagger-ui-tag`. The SDK type generation reads the same file.
4. A spectral lint (`.spectral.yaml` with the `oas` ruleset) runs in CI against the exported file; operation IDs must be stable snake_case because the SDK method names derive from them.
5. Document rate limit headers (`X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`) and the `X-Markdown-Tokens` header on result downloads (the one metadata header with external spec support) in the OpenAPI description.

#### 4.5.3 Acceptance criteria

- `pnpm -F @ezmd/sdk build` produces ESM, CJS, and types; `size-limit` enforces 8 KB gzipped.
- The SDK's generated types match `openapi.json` (CI diff check).
- A Node 20 script using the SDK converts a fixture against the compose stack in the integration test.
- `/docs` loads with no external requests.
- Spectral lint passes with zero errors.

### 4.6 Browser extension (`apps/extension`)

Phase: 3.

#### 4.6.1 Purpose

The extension exists for one reason the research made unambiguous: YouTube, TikTok, Instagram, and X block datacenter IPs, and the only durable workaround that costs nothing and carries no proxy liability is fetching in the user's browser on the user's residential IP. The extension does two things: on an ordinary page it sends the current URL to the instance (one click, no content script needed); on a video platform it captures the media in the browser and uploads audio or captions to the instance, so the instance never contacts the platform.

#### 4.6.2 Architecture

Manifest V3, one codebase, built with Vite and `@crxjs/vite-plugin` (or WXT; pick one and record in DECISIONS.md), producing Chrome and Firefox bundles. Firefox needs `browser_specific_settings.gecko.id` and uses `background.scripts` instead of a service worker (handled by the build target).

Permissions (minimal):

- `activeTab`: read the current tab URL on click, no host permissions at rest.
- `storage`: instance URL, API key, default profile.
- `scripting`: inject the capture content script on demand into the active tab only, after the click.
- Optional host permissions requested at runtime for the configured instance origin (so self-hosters can point it anywhere) and, only when the user enables "capture media", for `*://*.youtube.com/*`, `*://*.tiktok.com/*`, `*://*.instagram.com/*`, `*://*.x.com/*`, `*://*.twitter.com/*`, `*://*.vimeo.com/*`, `*://*.loom.com/*`. Requested via `permissions.request` on first use with a plain explanation. No `<all_urls>`. No `cookies` permission: a content-script fetch runs with the page's credentials automatically (`credentials: "include"` on same-origin), which is the point.
- No `tabs`, no `webRequest`, no `history`.

Components:

1. `background.ts` (service worker): handles the toolbar click and the keyboard shortcut (`Alt+Shift+M`), reads settings, decides the path (URL send vs capture), talks to the instance via the TS SDK, opens the result tab, and shows progress in the badge (`...` then `OK` or `!`).
2. `popup.html`: shows the instance name (from capabilities), a profile selector, "Convert this page" and "Capture media and convert" buttons, status, and a link to settings. Keyboard operable.
3. `options.html`: instance URL (default: the public instance; validated by calling `/v1/capabilities`), API key (stored in `storage.local`, never `sync`), default profile, "Always capture on video sites" toggle, "Open result in new tab / copy to clipboard / both".
4. `content/capture.ts`: injected on demand. Per-platform strategies, each a small module registered by hostname, selected at runtime:
   - YouTube: read `ytInitialPlayerResponse` from the page (available in page context via an injected `<script>` relay or `world: "MAIN"` injection), extract `captions.playerCaptionsTracklistRenderer.captionTracks`, fetch the `baseUrl` with `fmt=json3` from the page context (same origin, same cookies, same IP, so the PO-token problem does not apply because the page already holds a valid session). If captions exist, upload them as `source_type: captions_json3` with the video metadata. If none, fall back to audio capture: pick the lowest-bitrate audio-only format from `streamingData.adaptiveFormats` (these URLs are bound to the page's IP, which is exactly the user's IP, so they work), fetch it as a blob in chunks, and upload.
   - TikTok, Instagram, X: capture via the page's `<video>` element source when it is a direct URL (fetch as blob from the page context), otherwise `MediaRecorder` on a `captureStream()` of the playing video element at 1x speed as the last resort (slow but universal; the popup shows "Recording, MM:SS of MM:SS" and the user must keep the tab open). Prefer the direct URL path and record which strategy worked in the upload metadata so the maintainers can watch breakage.
   - Vimeo, Loom: use the player config JSON exposed in the page for caption tracks and progressive URLs.
   - Any other site: no capture; just send the URL.
5. Upload: audio blobs are posted to the multipart path from Part 3 with `source_type: media_upload`, `origin_url`, `platform`, `strategy`, `duration_s`, and any captions. Size cap read from capabilities before capture; if the estimated size exceeds it, the extension transcodes to 16 kHz mono Opus in-browser with the WebCodecs API when available (cuts a 100 MB video to under 10 MB of audio) and otherwise refuses with a clear message.
6. Result: open `https://<instance>/#job=<id>` in a new tab (the web UI reads the hash and subscribes), or copy the Markdown to the clipboard when the job finishes, per settings.

#### 4.6.3 Build steps

1. Scaffold `apps/extension` with the chosen tooling; configure two targets (`chrome`, `firefox`) producing `dist/chrome/` and `dist/firefox/`, zipped by the release workflow.
2. Implement settings and the plain URL path first; test against the compose stack.
3. Implement the YouTube caption path, then YouTube audio, then the generic `<video>` blob path, then `MediaRecorder`. Each strategy has a Playwright test against a fixture page in `fixtures/extension/` that mimics the platform's DOM and JSON (synthetic, no real platform content).
4. Add the Firefox manifest differences and test in Firefox via `web-ext run`.
5. Write `apps/extension/PRIVACY.md`: the extension sends only the active tab URL or captured media to the instance the user configured, stores settings locally, has no analytics, and requests host permissions only on demand. The store listings link to it.
6. Store listing: Chrome Web Store (developer account, one-time fee; listing text, 5 screenshots at 1280x800, 128px icon, privacy practices form answering "no remote code", "data sent to a user-configured server"); Firefox Add-ons via `web-ext sign` with source upload since the bundle is built. Edge Add-ons accepts the Chrome zip. Safari is deferred: it requires the Apple developer program and an Xcode wrapper; track as a Phase 5 item funded only if sponsorship exists (MarkDownload's precedent of charging for the Safari build is acceptable).
7. Self-update is handled by the stores; self-hosters loading unpacked get a banner in the popup when `/v1/capabilities` reports a newer minimum extension version.

#### 4.6.4 Acceptance criteria

- On a synthetic YouTube fixture page with captions, one click produces a transcript job on the compose instance with `strategy: captions_json3` and the instance made no outbound request to any `youtube.com` host (asserted by the test proxy log).
- On a fixture page without captions, the audio path uploads an Opus blob under 10 MB for a 5-minute synthetic video.
- The extension requests no host permission until the user clicks "Capture media" on a video site.
- `web-ext lint` passes with zero errors; Chrome's manifest validation passes.
- Settings survive a browser restart; the API key is not present in `storage.sync`.

### 4.7 iOS Shortcut and Android share target

Phase: 3.

#### 4.7.1 iOS Shortcut

iOS has no extension path a free project can afford, but Shortcuts can accept a shared link or file and POST it. Ship two Shortcuts as signed `.shortcut` files in `docs/shortcuts/` and as iCloud links in the docs, plus the exact steps so users can rebuild them if the links expire.

Shortcut A, "Markdown from link" (receives URLs from the share sheet):

1. Shortcut settings: enable "Show in Share Sheet"; Share Sheet Types: URLs, Text.
2. Action "Receive URLs and Text from Share Sheet" (Shortcut Input). If there is no input, "Ask for Input" (Text, prompt "Paste a link").
3. Action "Text": `https://ezmd.example` (users editing for self-host change this one line). Set variable `Instance`.
4. Action "Get Contents of URL": URL `[Instance]/v1/convert`, Method POST, Headers `Accept: application/json`, `User-Agent: ezmd-shortcut/1`, Request Body JSON: `url` = Shortcut Input, `profile` = `compact`, `client` = `ios-shortcut`. (Turnstile is not possible from Shortcuts; Part 3 defines a per-client allowance for the `ios-shortcut` client with tighter per-IP limits in place of a challenge. Self-hosters add an `Authorization: Bearer` header here.)
5. Action "Get Dictionary Value" `id` from the response. Set variable `JobID`.
6. Action "Repeat" 60 times: "Wait" 2 seconds; "Get Contents of URL" `[Instance]/v1/jobs/[JobID]` GET; "Get Dictionary Value" `status`; "If" status is `done` then "Exit Repeat" (use "Stop and Output" pattern: set a variable `Done` and break via "If" on the next loop). Shortcuts has no break, so the loop body checks `Done` first and skips work when set.
7. "If" status is `failed`: "Show Alert" with the first warning message; "Stop Shortcut".
8. "Get Contents of URL" `[Instance]/v1/jobs/[JobID]/result?format=md&profile=compact` GET. Set variable `Markdown`.
9. "Choose from Menu" with options: "Copy", "Share", "Save to Files", "Open in Obsidian". Copy → "Copy to Clipboard"; Share → "Share" `Markdown`; Save → "Save File" to `/ezmd/` with the title from the `title` dictionary value; Obsidian → "Open URL" `obsidian://new?content=[Markdown url-encoded]&name=[title]`.
10. Show a "Done" notification with the token count.

Shortcut B, "Markdown from video" (receives a video or audio file shared from Photos, Files, or a platform's "Save video" output): identical, except step 4 uses the multipart form: "Get Contents of URL" with Request Body "Form", field `file` = Shortcut Input (type File), field `profile` = `compact`, field `client` = `ios-shortcut`. Add a "Get Details of Files" size check before upload and alert if over the instance cap (read once from `/v1/capabilities` at the start and cached in a variable).

Document that for TikTok and Instagram on iOS the workflow is: use the platform's own "Save video" to Photos, then share the video to Shortcut B. This keeps the platform fetch on the user's device and off the instance, consistent with the extension's rationale.

#### 4.7.2 Android share target

Android Chrome supports the Web Share Target API for installed PWAs, which the web app becomes in Phase 3. In `apps/web/public/manifest.webmanifest`:

```json
{
  "name": "ezmd",
  "short_name": "ezmd",
  "start_url": "/",
  "display": "standalone",
  "background_color": "#ffffff",
  "theme_color": "#111111",
  "icons": [
    { "src": "/icons/192.png", "sizes": "192x192", "type": "image/png" },
    { "src": "/icons/512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable" }
  ],
  "share_target": {
    "action": "/share",
    "method": "POST",
    "enctype": "multipart/form-data",
    "params": {
      "title": "title",
      "text": "text",
      "url": "url",
      "files": [
        { "name": "files", "accept": ["video/*", "audio/*", "application/pdf", "image/*", "text/*",
          "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
          "application/vnd.openxmlformats-officedocument.presentationml.presentation",
          "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "application/epub+zip"] }
      ]
    }
  }
}
```

Steps:

1. The service worker intercepts `POST /share` (fetch event, `event.request.method === "POST"` and URL path `/share`), reads the form data, stores files in a Cache Storage entry keyed by a nonce, and responds with a redirect to `/#share=<nonce>`. The server never sees `/share` (there is a server route that returns 405 with a hint for non-PWA callers).
2. On load with `#share=`, the app pulls the stored files or URL, pre-fills the input box, and auto-submits (URL and text) or waits for the user to confirm (files, since they may be large). TikTok's and Instagram's share sheets pass a URL (text), so the URL path applies; for a downloaded video the user shares the file from Files or Gallery.
3. The app shows an "Install for share sheet" hint in the menu (not a banner) explaining that installing adds ezmd to the Android share menu.
4. Test with Playwright on Chrome for Android emulation where possible and document a manual test matrix (Pixel, Samsung) in `docs/mobile.md`.

Acceptance: sharing a URL from the Android TikTok app to the installed PWA lands on the result view with a job created, with no third-party request; sharing a 30 MB MP4 from Files prompts, uploads, and transcribes on the compose stack.

### 4.8 Integrations (Phase 5, scope only)

Each is a separate small repository or a `packages/integrations/<name>` directory, built only after the Phase 4 gate, with one maintainer week each. Each uses the REST API or the library and contains no conversion logic.

1. Obsidian plugin (`ezmd-obsidian`): a command "Convert URL or file to note" that takes a URL (from a modal or the clipboard) or a file picked from the vault's attachments folder, calls the configured instance (or a local `ezmd serve`), and writes a note into a configured folder with frontmatter merged from the result (`source`, `fetched`, `tokens`, plus user-defined tags) and the body in `full` or `compact` profile. Stub notes on failure with the warnings list. A "watch attachments folder" setting converts dropped PDFs and audio automatically. Submit to the community plugin directory with the required `manifest.json`, `versions.json`, and release assets.
2. Raycast extension and Alfred workflow: "Convert clipboard" and "Convert URL" commands that call the instance and put Markdown on the clipboard or paste it. Raycast extension in TypeScript via the SDK; Alfred workflow as a Python script using the library when installed and the REST API otherwise. Raycast store submission via PR to the extensions repo.
3. n8n and Zapier: no custom nodes in v1; publish ready-made workflow templates (n8n JSON export, Zapier Webhooks by Zapier recipe) in `docs/integrations/` that call `POST /v1/convert`, poll, and fetch the result. An n8n community node (`n8n-nodes-ezmd`) is a Phase 5 stretch only if templates see use.
4. GitHub Action (`ezmd-action`): a composite action that installs `ezmd` with `uv`, runs `ezmd batch` over a glob, and uploads the Markdown as an artifact or commits it to a branch. Inputs: `paths`, `out`, `profile`, `format`, `commit` (bool), `remote` and `api-key` (optional, for instances with heavy extras). Use case: a docs repo that keeps `docs/*.pdf` converted to `docs/md/` for an LLM index. Publish to the Marketplace with a `action.yml` and a README.

---

## B. Deployment and operations

### 4.9 Docker Compose self-host

Phase: 1 (compose with api, worker-default, redis, caddy), Phase 2 (worker-media, model cache, GPU override), Phase 3 (pi compose), Phase 4 (public instance profile).

#### 4.9.1 Layout

```
deploy/
  docker-compose.yml          # the one file self-hosters use
  docker-compose.gpu.yml      # override: NVIDIA runtime for worker-media
  docker-compose.public.yml   # override: public-instance settings (Turnstile, tighter caps, metrics)
  docker-compose.pi.yml       # the fetch node on a Raspberry Pi
  .env.example
  Caddyfile
  bootstrap.sh
  backup.sh
  restore.sh
  upgrade.sh
  seccomp-worker.json
  ../Dockerfile               # multi-stage, targets: api, worker, worker-media, fetch-node
```

One image `ghcr.io/<owner>/ezmd` with build targets selected by `--target`, tagged `:<version>`, `:<version>-media`, `:<version>-fetch`, plus `:latest` aliases. All images run as uid 10001 (`ezmd`), have `HEALTHCHECK`, carry OCI labels (`org.opencontainers.image.source`, `.version`, `.licenses=Apache-2.0`) and the MCP label from 4.4.5. The `api` target contains the core extras and the built web UI, no torch. The `worker` target adds `[docs]` and `[ocr]` (CPU). The `worker-media` target adds `[media]` and ffmpeg. The `fetch-node` target adds `[fetch]`, yt-dlp, Deno, and nothing else; it is the only image that contains yt-dlp.

#### 4.9.2 `deploy/docker-compose.yml`

```yaml
# ezmd self-host. Copy .env.example to .env, edit EZMD_PUBLIC_URL, then: docker compose up -d
name: ezmd

x-common: &common
  image: ghcr.io/OWNER/ezmd:${EZMD_VERSION:-latest}
  restart: unless-stopped
  env_file: .env
  user: "10001:10001"
  read_only: true
  tmpfs:
    - /tmp:size=${EZMD_TMPFS_SIZE:-2g},mode=1777
  security_opt:
    - no-new-privileges:true
  cap_drop:
    - ALL
  logging:
    driver: json-file
    options:
      max-size: "20m"
      max-file: "5"
  networks:
    - internal

services:
  caddy:
    image: caddy:2.8-alpine
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
      - "443:443/udp"
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy_data:/data
      - caddy_config:/config
    environment:
      EZMD_DOMAIN: ${EZMD_DOMAIN:-localhost}
      EZMD_ACME_EMAIL: ${EZMD_ACME_EMAIL:-}
    networks:
      - internal
      - egress
    depends_on:
      api:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "wget", "-qO-", "http://127.0.0.1:2019/metrics"]
      interval: 30s
      timeout: 5s
      retries: 3
    cap_drop: [ALL]
    cap_add: [NET_BIND_SERVICE]
    security_opt: [no-new-privileges:true]
    logging:
      driver: json-file
      options: { max-size: "20m", max-file: "5" }

  api:
    <<: *common
    command: ["ezmd", "serve", "--host", "0.0.0.0", "--port", "8080", "--workers", "${EZMD_API_WORKERS:-2}"]
    expose: ["8080"]
    volumes:
      - state:/var/lib/ezmd
      - blobs:/var/lib/ezmd/blobs
      - models:/var/lib/ezmd/models:ro
    depends_on:
      redis:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/healthz',timeout=3).status==200 else 1)"]
      interval: 15s
      timeout: 5s
      retries: 5
      start_period: 30s
    deploy:
      resources:
        limits:
          cpus: "${EZMD_API_CPUS:-1.0}"
          memory: ${EZMD_API_MEM:-1g}

  worker-default:
    <<: *common
    image: ghcr.io/OWNER/ezmd:${EZMD_VERSION:-latest}-worker
    command: ["ezmd", "worker", "--queues", "default,web,docs", "--concurrency", "${EZMD_WORKER_DEFAULT_CONCURRENCY:-2}"]
    volumes:
      - blobs:/var/lib/ezmd/blobs
      - models:/var/lib/ezmd/models:ro
    depends_on:
      redis:
        condition: service_healthy
    networks:
      - internal
      - egress
    healthcheck:
      test: ["CMD", "ezmd", "worker", "--ping"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s
    security_opt:
      - no-new-privileges:true
      - seccomp:./seccomp-worker.json
    deploy:
      resources:
        limits:
          cpus: "${EZMD_WORKER_DEFAULT_CPUS:-3.0}"
          memory: ${EZMD_WORKER_DEFAULT_MEM:-4g}
        reservations:
          memory: 1g

  worker-media:
    <<: *common
    image: ghcr.io/OWNER/ezmd:${EZMD_VERSION:-latest}-media
    command: ["ezmd", "worker", "--queues", "media,ocr", "--concurrency", "${EZMD_WORKER_MEDIA_CONCURRENCY:-1}"]
    profiles: ["media"]
    volumes:
      - blobs:/var/lib/ezmd/blobs
      - models:/var/lib/ezmd/models
    depends_on:
      redis:
        condition: service_healthy
    networks:
      - internal
      - egress
    tmpfs:
      - /tmp:size=${EZMD_MEDIA_TMPFS_SIZE:-6g},mode=1777
    healthcheck:
      test: ["CMD", "ezmd", "worker", "--ping"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 180s
    security_opt:
      - no-new-privileges:true
      - seccomp:./seccomp-worker.json
    deploy:
      resources:
        limits:
          cpus: "${EZMD_WORKER_MEDIA_CPUS:-3.0}"
          memory: ${EZMD_WORKER_MEDIA_MEM:-6g}
        reservations:
          memory: 2g

  redis:
    image: redis:7.4-alpine
    restart: unless-stopped
    command: ["redis-server", "--save", "", "--appendonly", "no", "--maxmemory", "${EZMD_REDIS_MAXMEM:-256mb}", "--maxmemory-policy", "noeviction"]
    expose: ["6379"]
    networks: [internal]
    user: "999:999"
    read_only: true
    tmpfs: [/data]
    cap_drop: [ALL]
    security_opt: [no-new-privileges:true]
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 3s
      retries: 5
    deploy:
      resources:
        limits: { cpus: "0.5", memory: 384m }

  postgres:
    image: postgres:16-alpine
    profiles: ["postgres"]
    restart: unless-stopped
    environment:
      POSTGRES_DB: ezmd
      POSTGRES_USER: ezmd
      POSTGRES_PASSWORD: ${EZMD_PG_PASSWORD:?set EZMD_PG_PASSWORD}
    volumes: [pgdata:/var/lib/postgresql/data]
    networks: [internal]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ezmd"]
      interval: 10s
      timeout: 5s
      retries: 5
    deploy:
      resources:
        limits: { cpus: "1.0", memory: 1g }

  minio:
    image: minio/minio:RELEASE.2025-09-07T16-13-09Z
    profiles: ["minio"]
    restart: unless-stopped
    command: ["server", "/data", "--console-address", ":9001"]
    environment:
      MINIO_ROOT_USER: ${EZMD_S3_ACCESS_KEY:?set EZMD_S3_ACCESS_KEY}
      MINIO_ROOT_PASSWORD: ${EZMD_S3_SECRET_KEY:?set EZMD_S3_SECRET_KEY}
    volumes: [miniodata:/data]
    networks: [internal]
    healthcheck:
      test: ["CMD", "mc", "ready", "local"]
      interval: 15s
      timeout: 5s
      retries: 5

  model-init:
    image: ghcr.io/OWNER/ezmd:${EZMD_VERSION:-latest}-media
    profiles: ["media"]
    command: ["ezmd", "models", "pull", "--all-for-extras", "--cache", "/var/lib/ezmd/models"]
    env_file: .env
    user: "10001:10001"
    volumes: [models:/var/lib/ezmd/models]
    networks: [egress]
    restart: "no"

networks:
  internal:
    internal: true
  egress:

volumes:
  state:
  blobs:
  models:
  caddy_data:
  caddy_config:
  pgdata:
  miniodata:
```

Notes the agent must honor when writing this file:

- `internal` is an internal network: containers on it cannot reach the internet. Only `caddy`, the workers (which must fetch URLs), and `model-init` are also on `egress`. The `api` container is deliberately not on `egress`: it never fetches anything; fetches happen in workers. If the API needs Turnstile verification (public profile), it reaches `challenges.cloudflare.com` through a tiny `egress-proxy` service added by `docker-compose.public.yml` with an allowlist (4.12.1).
- `read_only: true` plus `tmpfs` for `/tmp` is mandatory on workers; converters that write scratch files use `EZMD_TMP=/tmp`.
- The `worker` command `ezmd worker` is the RQ worker entry point from Part 3.
- The model volume is read-only on `api` and `worker-default`; only `model-init` and `worker-media` (for first-run pulls when `EZMD_MODELS_AUTOPULL=true`) write it.
- `deploy.resources.limits` works with `docker compose` (not only Swarm) since Compose v2.

#### 4.9.3 `deploy/docker-compose.gpu.yml`

```yaml
# Usage: docker compose -f docker-compose.yml -f docker-compose.gpu.yml --profile media up -d
# Requires the NVIDIA Container Toolkit on the host.
services:
  worker-media:
    image: ghcr.io/OWNER/ezmd:${EZMD_VERSION:-latest}-media-cuda
    environment:
      EZMD_DEVICE: cuda
      EZMD_ASR_ENGINE: parakeet
      EZMD_OCR_ENGINE: paddleocr-vl
      NVIDIA_VISIBLE_DEVICES: ${EZMD_GPU_DEVICES:-all}
      NVIDIA_DRIVER_CAPABILITIES: compute,utility
    deploy:
      resources:
        limits:
          memory: ${EZMD_WORKER_MEDIA_MEM:-12g}
        reservations:
          devices:
            - driver: nvidia
              count: ${EZMD_GPU_COUNT:-1}
              capabilities: [gpu]
  model-init:
    image: ghcr.io/OWNER/ezmd:${EZMD_VERSION:-latest}-media-cuda
```

#### 4.9.4 `deploy/docker-compose.public.yml`

```yaml
# Public instance overlay. Usage on the VPS:
# docker compose -f docker-compose.yml -f docker-compose.public.yml --profile media up -d
services:
  api:
    environment:
      EZMD_PUBLIC_MODE: "true"
      EZMD_TURNSTILE_REQUIRED_FOR_FETCH: "true"
      EZMD_RETENTION_HOURS: "24"
      EZMD_ANON_MAX_UPLOAD_MB: "25"
      EZMD_ANON_MAX_HTML_MB: "10"
      EZMD_ANON_MAX_DURATION_S: "900"
      EZMD_ANON_RATELIMIT_MAX: "20"
      EZMD_ANON_RATELIMIT_WINDOW_S: "60"
      EZMD_ANON_CONCURRENCY: "1"
      EZMD_DISABLED_SOURCES: "youtube,tiktok,instagram,x,facebook"
      EZMD_FETCH_NODE_ENABLED: "true"
      EZMD_METRICS_ENABLED: "true"
      EZMD_TRUST_PROXY_HEADER: "CF-Connecting-IP"
      HTTPS_PROXY: "http://egress-proxy:3128"
    networks: [internal, egressproxy]
  worker-default:
    environment:
      HTTPS_PROXY: "http://egress-proxy:3128"
      HTTP_PROXY: "http://egress-proxy:3128"
      NO_PROXY: "redis,api,minio,localhost,127.0.0.1"
  worker-media:
    environment:
      HTTPS_PROXY: "http://egress-proxy:3128"
      HTTP_PROXY: "http://egress-proxy:3128"
      NO_PROXY: "redis,api,minio,localhost,127.0.0.1"
  egress-proxy:
    image: ubuntu/squid:6.1-24.04_edge
    restart: unless-stopped
    volumes:
      - ./squid.conf:/etc/squid/squid.conf:ro
    networks: [internal, egressproxy, egress]
    healthcheck:
      test: ["CMD-SHELL", "squidclient -h 127.0.0.1 mgr:info >/dev/null || exit 1"]
      interval: 30s
      timeout: 5s
      retries: 3
    deploy:
      resources:
        limits: { cpus: "0.5", memory: 256m }
networks:
  egressproxy:
    internal: true
```

The `squid.conf` is in 4.12.1. In public mode the workers are moved off the `egress` network in a second override step (`docker-compose.public.yml` cannot remove a network; the bootstrap script writes a `compose.override.yml` that sets `networks: [internal, egressproxy]` for the workers). Record this quirk in `deploy/README.md`.

#### 4.9.5 `deploy/docker-compose.pi.yml`

```yaml
# Fetch node for a Raspberry Pi 4/5 (arm64) at the owner's home.
# Outbound only. Reaches the instance over Tailscale. No ports published. No secrets baked into the image.
name: ezmd-fetch-node
services:
  fetch-node:
    image: ghcr.io/OWNER/ezmd:${EZMD_VERSION:-latest}-fetch
    restart: unless-stopped
    command: ["ezmd", "fetch-node", "run", "--concurrency", "${EZMD_FETCH_CONCURRENCY:-1}"]
    env_file: .env.pi
    environment:
      EZMD_FETCH_NODE_INSTANCE: ${EZMD_FETCH_NODE_INSTANCE:?e.g. http://ezmd-vps.tailnet-name.ts.net:8080}
      EZMD_FETCH_NODE_ID: ${EZMD_FETCH_NODE_ID:-pi-home}
      EZMD_FETCH_MAX_DURATION_S: ${EZMD_FETCH_MAX_DURATION_S:-3600}
      EZMD_FETCH_AUDIO_ONLY: "true"
      EZMD_FETCH_COOKIES_FILE: /run/secrets/cookies.txt
      EZMD_YTDLP_JS_RUNTIME: deno
      EZMD_TMP: /tmp
    user: "10001:10001"
    read_only: true
    tmpfs:
      - /tmp:size=${EZMD_PI_TMPFS_SIZE:-1500m},mode=1777
    volumes:
      - ./cookies.txt:/run/secrets/cookies.txt:ro
      - ytdlp_cache:/var/lib/ezmd/ytdlp
    cap_drop: [ALL]
    security_opt: [no-new-privileges:true]
    network_mode: "host"
    healthcheck:
      test: ["CMD", "ezmd", "fetch-node", "ping"]
      interval: 60s
      timeout: 10s
      retries: 5
      start_period: 60s
    deploy:
      resources:
        limits:
          cpus: "3.0"
          memory: 1500m
    logging:
      driver: json-file
      options: { max-size: "10m", max-file: "3" }

  watchtower:
    image: containrrr/watchtower:1.7.1
    restart: unless-stopped
    command: ["--cleanup", "--interval", "3600", "--label-enable"]
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
    labels:
      com.centurylinklabs.watchtower.enable: "false"

volumes:
  ytdlp_cache:
```

`network_mode: host` on the Pi is required so the container uses the host's Tailscale interface and the home LAN's residential egress; the Pi publishes no inbound ports, Tailscale ACLs (4.10.4) only allow the Pi to initiate to the VPS, and the VPS cannot initiate to the Pi. Add label `com.centurylinklabs.watchtower.enable=true` to `fetch-node` so it auto-updates; the token lives in `.env.pi` (mode 600), never in the image.

#### 4.9.6 `deploy/.env.example`

```bash
# ---- Required ----
EZMD_DOMAIN=ezmd.example.com           # Caddy obtains TLS for this. Use "localhost" for local HTTP.
EZMD_PUBLIC_URL=https://ezmd.example.com
EZMD_ACME_EMAIL=you@example.com         # Let's Encrypt contact. Empty = internal CA (localhost only).
EZMD_SECRET_KEY=change-me-64-random-chars   # Signs Turnstile JWTs, upload tokens, fetch-node tokens. `openssl rand -hex 32`.

# ---- Image ----
EZMD_VERSION=latest                      # Pin to a version in production, e.g. 1.4.2

# ---- Storage ----
EZMD_DB_URL=sqlite:////var/lib/ezmd/ezmd.db   # or postgresql+psycopg://ezmd:pw@postgres/ezmd (enable --profile postgres)
EZMD_PG_PASSWORD=                        # only with --profile postgres
EZMD_BLOB_BACKEND=fs                     # fs | s3
EZMD_BLOB_FS_ROOT=/var/lib/ezmd/blobs
EZMD_S3_ENDPOINT=http://minio:9000       # only with EZMD_BLOB_BACKEND=s3
EZMD_S3_BUCKET=ezmd
EZMD_S3_ACCESS_KEY=
EZMD_S3_SECRET_KEY=
EZMD_S3_REGION=us-east-1
EZMD_RETENTION_HOURS=24                  # results and uploads deleted after this. 0 = delete on first download.
EZMD_MODEL_CACHE=/var/lib/ezmd/models
EZMD_MODELS_AUTOPULL=false               # true lets worker-media pull missing models on first use

# ---- Queue ----
EZMD_REDIS_URL=redis://redis:6379/0
EZMD_QUEUE=rq                            # rq | inline (inline = no Redis, single process, for ezmd serve on a laptop)
EZMD_JOB_TIMEOUT_S=1800                  # hard kill for any job
EZMD_API_WORKERS=2
EZMD_WORKER_DEFAULT_CONCURRENCY=2
EZMD_WORKER_MEDIA_CONCURRENCY=1

# ---- Limits (apply to anonymous callers; API keys carry their own) ----
EZMD_ANON_MAX_UPLOAD_MB=200
EZMD_ANON_MAX_HTML_MB=10
EZMD_ANON_MAX_DURATION_S=10800           # 3h cobalt default; public instance uses 900
EZMD_ANON_MAX_PAGES=2000
EZMD_ANON_RATELIMIT_MAX=20
EZMD_ANON_RATELIMIT_WINDOW_S=60
EZMD_ANON_CONCURRENCY=1                  # running jobs per IP
EZMD_MAX_ARCHIVE_DEPTH=3                 # nested zip depth
EZMD_MAX_ARCHIVE_RATIO=100               # decompression ratio bomb guard
EZMD_MAX_ARCHIVE_ENTRIES=2000
EZMD_MAX_OUTPUT_MB=50

# ---- Auth ----
EZMD_API_KEYS_FILE=/var/lib/ezmd/keys.json   # cobalt-style per-key limits; see docs/abuse.md
EZMD_REQUIRE_API_KEY=false               # true = no anonymous access at all
EZMD_MCP_TOKEN=                          # bearer for /mcp when exposed; empty = /mcp disabled unless API key auth
EZMD_ADMIN_TOKEN=                        # for /admin/* (key management, queue stats). Empty = disabled.

# ---- Challenge ----
EZMD_TURNSTILE_SITEKEY=                  # Cloudflare Turnstile; empty = no challenge
EZMD_TURNSTILE_SECRET=
EZMD_TURNSTILE_REQUIRED_FOR_FETCH=false  # true on public instance: URL fetches need a Turnstile JWT
EZMD_TURNSTILE_JWT_TTL_S=120
EZMD_ALTCHA_HMAC_KEY=                    # self-host alternative: ALTCHA proof-of-work; set to enable
EZMD_ALTCHA_MAX_NUMBER=200000            # difficulty

# ---- Fetch policy ----
EZMD_ALLOW_PRIVATE_NETWORKS=false        # SSRF guard; never true on a public instance
EZMD_DISABLED_SOURCES=                   # comma list, e.g. youtube,tiktok,instagram,x
EZMD_FETCH_NODE_ENABLED=false            # accept claims from fetch nodes (public instance: true)
EZMD_FETCH_NODE_TOKENS=                  # comma list of node tokens; generate with `ezmd fetch-node token`
EZMD_FETCH_COOKIES_FILE=                 # self-host only: Netscape cookies for yt-dlp
EZMD_FETCH_PROXY=                        # self-host only: proxy URL for yt-dlp
EZMD_YTDLP_JS_RUNTIME=deno

# ---- Engines ----
EZMD_DEVICE=cpu                          # cpu | cuda | mps
EZMD_ASR_ENGINE=faster-whisper           # faster-whisper | parakeet | groq | deepgram
EZMD_ASR_MODEL=small                     # faster-whisper size; public CPU instance: small or base
EZMD_ASR_COMPUTE_TYPE=int8
EZMD_DIARIZATION=false                   # pyannote; needs the model pulled
EZMD_OCR_ENGINE=auto                     # auto | rapidocr | paddleocr-vl | off
EZMD_PDF_ENGINE=docling                  # docling | pypdf
EZMD_GROQ_API_KEY=                       # optional audio offload; see docs/ops.md
EZMD_GROQ_OFFLOAD_MIN_S=600              # route audio longer than this to Groq when key set

# ---- Public mode ----
EZMD_PUBLIC_MODE=false
EZMD_INSTANCE_NAME=
EZMD_SPONSOR_NAME=                       # shown in the footer: "Hosting by ..."
EZMD_SPONSOR_URL=
EZMD_SUPPORT_URL=                        # optional "Support" link; nothing is gated behind it
EZMD_DMCA_EMAIL=
EZMD_TRUST_PROXY_HEADER=                 # CF-Connecting-IP behind Cloudflare, X-Forwarded-For behind Caddy only
EZMD_TRUSTED_PROXIES=                    # CIDRs allowed to set that header; Cloudflare ranges are built in when header is CF-Connecting-IP

# ---- Observability ----
EZMD_LOG_LEVEL=info
EZMD_LOG_FORMAT=json                     # json | text
EZMD_LOG_REDACT=true                     # hashes IPs, strips query strings and file names from logs
EZMD_METRICS_ENABLED=false               # /metrics (Prometheus) on the internal port only
EZMD_METRICS_TOKEN=
EZMD_ALERT_WEBHOOK=                      # Discord/Slack webhook for alerts from the built-in checks
EZMD_ALERT_EMAIL=

# ---- Resources ----
EZMD_API_CPUS=1.0
EZMD_API_MEM=1g
EZMD_WORKER_DEFAULT_CPUS=3.0
EZMD_WORKER_DEFAULT_MEM=4g
EZMD_WORKER_MEDIA_CPUS=3.0
EZMD_WORKER_MEDIA_MEM=6g
EZMD_TMPFS_SIZE=2g
EZMD_MEDIA_TMPFS_SIZE=6g
EZMD_REDIS_MAXMEM=256mb
```

Every variable here must be read through one `Settings` class (pydantic-settings) in `packages/core`, and a test asserts that every variable in `.env.example` exists on `Settings` and vice versa, so the two cannot drift.

#### 4.9.7 `deploy/Caddyfile`

```caddyfile
{
  email {$EZMD_ACME_EMAIL}
  admin 127.0.0.1:2019
  servers {
    trusted_proxies static 173.245.48.0/20 103.21.244.0/22 103.22.200.0/22 103.31.4.0/22 141.101.64.0/18 108.162.192.0/18 190.93.240.0/20 188.114.96.0/20 197.234.240.0/22 198.41.128.0/17 162.158.0.0/15 104.16.0.0/13 104.24.0.0/14 172.64.0.0/13 131.0.72.0/22
    client_ip_headers CF-Connecting-IP X-Forwarded-For
  }
}

{$EZMD_DOMAIN} {
  encode zstd gzip

  header {
    Strict-Transport-Security "max-age=31536000; includeSubDomains"
    X-Content-Type-Options nosniff
    X-Frame-Options DENY
    Referrer-Policy no-referrer
    Permissions-Policy "camera=(), microphone=(), geolocation=()"
    Content-Security-Policy "default-src 'self'; script-src 'self' https://challenges.cloudflare.com; frame-src https://challenges.cloudflare.com; connect-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; worker-src 'self' blob:; object-src 'none'; base-uri 'none'; form-action 'self'"
    -Server
  }

  request_body {
    max_size 512MB
  }

  @static path /assets/* /icons/* /models/* /manifest.webmanifest /sw.js
  handle @static {
    header Cache-Control "public, max-age=31536000, immutable"
    reverse_proxy api:8080
  }

  @sse path /v1/jobs/*/events
  handle @sse {
    reverse_proxy api:8080 {
      flush_interval -1
      transport http {
        read_timeout 0
      }
    }
  }

  handle /metrics {
    respond 404
  }

  handle {
    reverse_proxy api:8080 {
      header_up X-Real-IP {client_ip}
      transport http {
        read_timeout 600s
      }
    }
  }

  log {
    output file /data/access.log {
      roll_size 50mb
      roll_keep 5
      roll_keep_for 168h
    }
    format filter {
      wrap json
      fields {
        request>headers>Cookie delete
        request>headers>Authorization delete
        request>remote_ip ip_mask {
          ipv4 24
          ipv6 48
        }
        request>client_ip ip_mask {
          ipv4 24
          ipv6 48
        }
        request>uri query {
          delete token
          delete key
        }
      }
    }
  }
}
```

When `EZMD_DOMAIN=localhost`, Caddy uses its internal CA automatically. The `/metrics` path is blocked at the edge; Prometheus scrapes the API on the internal network (4.10.5). Caddy's `sw.js` cache header must be overridden by the API to `no-cache` (Part 3 sets it); keep `/sw.js` out of the immutable list if that proves awkward.

#### 4.9.8 `deploy/bootstrap.sh`

```bash
#!/usr/bin/env bash
# One-command bootstrap for a clean Ubuntu 24.04 box (VPS or home server).
# Usage: curl -fsSL https://raw.githubusercontent.com/OWNER/ezmd/main/deploy/bootstrap.sh | sudo bash -s -- --domain ezmd.example.com --email you@example.com [--public] [--media] [--gpu]
set -euo pipefail

DOMAIN=""; EMAIL=""; PUBLIC=0; MEDIA=0; GPU=0; VERSION="latest"; INSTALL_DIR="/opt/ezmd"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --domain) DOMAIN="$2"; shift 2;;
    --email) EMAIL="$2"; shift 2;;
    --public) PUBLIC=1; shift;;
    --media) MEDIA=1; shift;;
    --gpu) GPU=1; MEDIA=1; shift;;
    --version) VERSION="$2"; shift 2;;
    --dir) INSTALL_DIR="$2"; shift 2;;
    *) echo "unknown arg $1"; exit 2;;
  esac
done
[[ -z "$DOMAIN" ]] && { echo "--domain required"; exit 2; }
[[ "$EUID" -ne 0 ]] && { echo "run as root"; exit 2; }
. /etc/os-release; [[ "$ID" == "ubuntu" && "${VERSION_ID%%.*}" -ge 24 ]] || echo "warning: tested on Ubuntu 24.04 only"

echo "==> system packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get install -y -q ca-certificates curl gnupg ufw fail2ban unattended-upgrades apt-listchanges jq git

echo "==> docker"
if ! command -v docker >/dev/null; then
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $VERSION_CODENAME stable" > /etc/apt/sources.list.d/docker.list
  apt-get update -q
  apt-get install -y -q docker-ce docker-ce-cli containerd.io docker-compose-plugin
fi
# Docker daemon hardening: no inter-container by default, log caps, live-restore, userns not enabled (compose sets uid 10001 explicitly)
cat > /etc/docker/daemon.json <<'EOF'
{ "icc": false, "live-restore": true, "no-new-privileges": true,
  "log-driver": "json-file", "log-opts": { "max-size": "20m", "max-file": "5" },
  "default-ulimits": { "nofile": { "Name": "nofile", "Hard": 65536, "Soft": 65536 } } }
EOF
systemctl restart docker

if [[ $GPU -eq 1 ]]; then
  echo "==> nvidia container toolkit"
  curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | gpg --dearmor -o /etc/apt/keyrings/nvidia-container-toolkit.gpg
  curl -fsSL https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | sed 's#deb https://#deb [signed-by=/etc/apt/keyrings/nvidia-container-toolkit.gpg] https://#' > /etc/apt/sources.list.d/nvidia-container-toolkit.list
  apt-get update -q && apt-get install -y -q nvidia-container-toolkit
  nvidia-ctk runtime configure --runtime=docker && systemctl restart docker
fi

echo "==> firewall"
ufw default deny incoming
ufw default allow outgoing
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw allow 443/udp
# Docker bypasses ufw for published ports; restrict published ports to Cloudflare when public.
if [[ $PUBLIC -eq 1 ]]; then
  cat > /etc/ufw/after.rules.ezmd <<'EOF'
# Only Cloudflare may reach 80/443 (DOCKER-USER chain is honored by Docker)
EOF
  CF4=$(curl -fsSL https://www.cloudflare.com/ips-v4)
  CF6=$(curl -fsSL https://www.cloudflare.com/ips-v6)
  iptables -N EZMD-CF 2>/dev/null || iptables -F EZMD-CF
  for r in $CF4; do iptables -A EZMD-CF -s "$r" -j RETURN; done
  iptables -A EZMD-CF -p tcp -m multiport --dports 80,443 -j DROP
  iptables -A EZMD-CF -p udp --dport 443 -j DROP
  iptables -I DOCKER-USER -i "$(ip route | awk '/default/ {print $5; exit}')" -j EZMD-CF
  ip6tables -N EZMD-CF 2>/dev/null || ip6tables -F EZMD-CF
  for r in $CF6; do ip6tables -A EZMD-CF -s "$r" -j RETURN; done
  ip6tables -A EZMD-CF -p tcp -m multiport --dports 80,443 -j DROP
  ip6tables -I DOCKER-USER -j EZMD-CF
  apt-get install -y -q iptables-persistent
  netfilter-persistent save
fi
ufw --force enable

echo "==> fail2ban"
cat > /etc/fail2ban/jail.d/ezmd.local <<'EOF'
[sshd]
enabled = true
maxretry = 4
bantime = 1h
findtime = 10m
EOF
systemctl enable --now fail2ban

echo "==> unattended upgrades"
cat > /etc/apt/apt.conf.d/20auto-upgrades <<'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
APT::Periodic::AutocleanInterval "7";
EOF
sed -i 's#//Unattended-Upgrade::Automatic-Reboot "false";#Unattended-Upgrade::Automatic-Reboot "true";\nUnattended-Upgrade::Automatic-Reboot-Time "04:30";#' /etc/apt/apt.conf.d/50unattended-upgrades

echo "==> sshd hardening"
mkdir -p /etc/ssh/sshd_config.d
cat > /etc/ssh/sshd_config.d/ezmd.conf <<'EOF'
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin prohibit-password
MaxAuthTries 4
X11Forwarding no
AllowAgentForwarding no
EOF
if [[ ! -s /root/.ssh/authorized_keys ]]; then echo "WARNING: no authorized_keys for root; not reloading sshd"; else systemctl reload ssh; fi

echo "==> ezmd"
mkdir -p "$INSTALL_DIR" && cd "$INSTALL_DIR"
if [[ ! -d .git ]]; then git clone --depth 1 https://github.com/OWNER/ezmd.git src; fi
cp -n src/deploy/docker-compose.yml src/deploy/docker-compose.gpu.yml src/deploy/docker-compose.public.yml \
      src/deploy/Caddyfile src/deploy/squid.conf src/deploy/seccomp-worker.json src/deploy/backup.sh src/deploy/restore.sh src/deploy/upgrade.sh . || true
if [[ ! -f .env ]]; then
  cp src/deploy/.env.example .env
  sed -i "s#^EZMD_DOMAIN=.*#EZMD_DOMAIN=$DOMAIN#; s#^EZMD_PUBLIC_URL=.*#EZMD_PUBLIC_URL=https://$DOMAIN#; s#^EZMD_ACME_EMAIL=.*#EZMD_ACME_EMAIL=$EMAIL#; s#^EZMD_VERSION=.*#EZMD_VERSION=$VERSION#" .env
  sed -i "s#^EZMD_SECRET_KEY=.*#EZMD_SECRET_KEY=$(openssl rand -hex 32)#; s#^EZMD_ADMIN_TOKEN=.*#EZMD_ADMIN_TOKEN=$(openssl rand -hex 24)#; s#^EZMD_METRICS_TOKEN=.*#EZMD_METRICS_TOKEN=$(openssl rand -hex 16)#" .env
  chmod 600 .env
fi
echo '[]' > keys.json.example

FILES=(-f docker-compose.yml)
PROFILES=()
[[ $MEDIA -eq 1 ]] && PROFILES+=(--profile media)
[[ $GPU -eq 1 ]] && FILES+=(-f docker-compose.gpu.yml)
if [[ $PUBLIC -eq 1 ]]; then
  FILES+=(-f docker-compose.public.yml)
  cat > compose.override.yml <<'EOF'
services:
  worker-default: { networks: [internal, egressproxy] }
  worker-media:   { networks: [internal, egressproxy] }
EOF
  FILES+=(-f compose.override.yml)
fi
printf 'COMPOSE_FILES="%s"\nCOMPOSE_PROFILES="%s"\n' "${FILES[*]}" "${PROFILES[*]}" > .ezmd-compose

docker compose "${FILES[@]}" "${PROFILES[@]}" pull
if [[ $MEDIA -eq 1 ]]; then docker compose "${FILES[@]}" "${PROFILES[@]}" run --rm model-init; fi
docker compose "${FILES[@]}" "${PROFILES[@]}" up -d

echo "==> systemd unit for restart on boot"
cat > /etc/systemd/system/ezmd.service <<EOF
[Unit]
Description=ezmd compose stack
After=docker.service
Requires=docker.service
[Service]
Type=oneshot
RemainAfterExit=true
WorkingDirectory=$INSTALL_DIR
EnvironmentFile=$INSTALL_DIR/.ezmd-compose
ExecStart=/bin/sh -c 'docker compose \$COMPOSE_FILES \$COMPOSE_PROFILES up -d'
ExecStop=/bin/sh -c 'docker compose \$COMPOSE_FILES \$COMPOSE_PROFILES down'
[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload && systemctl enable ezmd.service

echo "==> daily backup timer"
cat > /etc/systemd/system/ezmd-backup.service <<EOF
[Unit]
Description=ezmd backup
[Service]
Type=oneshot
WorkingDirectory=$INSTALL_DIR
ExecStart=$INSTALL_DIR/backup.sh
EOF
cat > /etc/systemd/system/ezmd-backup.timer <<'EOF'
[Unit]
Description=ezmd daily backup
[Timer]
OnCalendar=*-*-* 03:17:00
Persistent=true
[Install]
WantedBy=timers.target
EOF
chmod +x backup.sh restore.sh upgrade.sh
systemctl daemon-reload && systemctl enable --now ezmd-backup.timer

echo
echo "ezmd is starting at https://$DOMAIN"
echo "  Admin token and secrets are in $INSTALL_DIR/.env (mode 600)."
echo "  API keys: edit $INSTALL_DIR/keys.json (see docs/abuse.md), then: docker compose restart api"
echo "  Logs: cd $INSTALL_DIR && docker compose logs -f"
```

#### 4.9.9 Backup, restore, upgrade

State is tiny by design: the SQLite database (job metadata, API key usage counters), `keys.json`, `.env`, the Caddy data volume (certificates), and nothing else. Blobs are ephemeral (24-hour TTL) and are not backed up. Models are reproducible via `ezmd models pull`.

`deploy/backup.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
. ./.ezmd-compose
TS=$(date -u +%Y%m%dT%H%M%SZ); OUT=${EZMD_BACKUP_DIR:-/var/backups/ezmd}; mkdir -p "$OUT"; chmod 700 "$OUT"
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
# consistent SQLite snapshot through the api container (sqlite3 .backup); falls back to pg_dump when postgres profile is on
docker compose $COMPOSE_FILES $COMPOSE_PROFILES exec -T api ezmd admin db-backup --to /tmp/db.backup
docker compose $COMPOSE_FILES $COMPOSE_PROFILES cp api:/tmp/db.backup "$TMP/db.backup"
cp .env keys.json "$TMP/" 2>/dev/null || true
docker run --rm -v ezmd_caddy_data:/data:ro -v "$TMP":/out alpine tar czf /out/caddy_data.tgz -C /data .
tar czf "$OUT/ezmd-$TS.tgz" -C "$TMP" .
chmod 600 "$OUT/ezmd-$TS.tgz"
ls -1t "$OUT"/ezmd-*.tgz | tail -n +15 | xargs -r rm --   # keep 14
echo "backup written: $OUT/ezmd-$TS.tgz"
```

`deploy/restore.sh <backup.tgz>`: stops the stack, extracts `.env` and `keys.json` into the install dir (asks before overwriting `.env`), restores the Caddy volume with the inverse `tar`, starts `redis` and `api`, runs `ezmd admin db-restore --from`, then `up -d`. Prints what it restored.

`deploy/upgrade.sh [version]`:

1. Reads `.ezmd-compose`, runs `backup.sh`.
2. Sets `EZMD_VERSION` in `.env` to the requested version (or the latest tag from GHCR via `docker manifest inspect` if omitted), `docker compose pull`.
3. Runs `docker compose run --rm api ezmd admin migrate` (Alembic) and `model-init` if the media profile is on and the release notes JSON (`/releases/<version>.json` in the repo, fetched by the script) lists new models.
4. `docker compose up -d --remove-orphans`, waits for `/healthz` to return `ok` with the new version for 60 s, otherwise rolls back: restores the previous `EZMD_VERSION`, `up -d`, and prints the failure.
5. `docker image prune -f` for images older than two versions.

Upgrade policy for self-hosters, documented in `docs/self-host.md`: patch versions are safe to auto-update with Watchtower (`--label-enable` on `api` and workers); minor versions may add models or env vars and should go through `upgrade.sh`; major versions may change the API and are announced one minor release ahead with a deprecation warning in `/healthz`.

#### 4.9.10 Acceptance criteria

- `bootstrap.sh --domain localhost` on a fresh Ubuntu 24.04 VM (CI runs it in a nested Docker-in-Docker or on a `ubuntu-24.04` runner) yields `https://localhost/healthz` returning `{"status":"ok"}` within 5 minutes with the core profile, and the compose smoke corpus (4.14.3) converts.
- `docker compose config` validates with no warnings for every combination of overrides.
- `backup.sh` then `restore.sh` on a fresh volume set brings back API keys and certificates (integration test).
- Every container runs as non-root, read-only, with all capabilities dropped (test parses `docker inspect`).
- A worker container cannot reach `169.254.169.254`, `10.0.0.0/8`, or `redis` through a fetched URL (SSRF test from 4.14.5 runs inside the compose network).

### 4.10 Public instance runbook

Phase: 4. This is `docs/ops/runbook.md`. Everything here is executed by the owner, not by the agent, except where marked "agent": the agent writes the configuration files, scripts, and docs; the owner creates accounts and pays bills. The agent must produce every file referenced so the owner's work is clicking and pasting.

#### 4.10.1 Hetzner provisioning

1. Create a Hetzner Cloud project `ezmd-public`. Server: location Ashburn (`ash`), type dedicated-vCPU CCX33 (8 vCPU, 32 GB) or the 8-core/16 GB dedicated option available at order time; Ubuntu 24.04; add the owner's SSH key at creation; enable IPv4 and IPv6; attach to a Hetzner Cloud Firewall `ezmd-edge` with inbound rules: TCP 22 from the owner's Tailscale subnet only (after Tailscale is up; initially from the owner's current IP), TCP 80, TCP 443, UDP 443 from Cloudflare IP ranges only (paste both lists), and nothing else. Outbound: allow all.
2. Attach a 100 GB volume `ezmd-blobs` mounted at `/var/lib/docker/volumes` is not needed; use the server's local NVMe (80+ GB). Enable Hetzner backups only if the budget allows (20% surcharge); otherwise rely on `backup.sh` plus off-box copy (step 4).
3. First login as root, run `bootstrap.sh --domain ezmd.<domain> --email <email> --public --media`. The script handles ufw, fail2ban, unattended-upgrades, sshd, Docker, and the stack.
4. Off-box backup: install `rclone`, configure a Backblaze B2 or Hetzner Storage Box remote, and add to `ezmd-backup.service` an `ExecStartPost=rclone copy /var/backups/ezmd remote:ezmd-backups --max-age 2d`. Backups contain `.env` with secrets, so the bucket must be private and the rclone config mode 600.
5. Install Tailscale (`curl -fsSL https://tailscale.com/install.sh | sh && tailscale up --ssh`) and tag the node `tag:ezmd-vps`. After it is up, change the Hetzner firewall SSH rule to the Tailscale CGNAT range `100.64.0.0/10` only, or remove port 22 entirely and rely on Tailscale SSH.
6. Record the server's public IPv4 and IPv6 for Cloudflare DNS. Never publish them anywhere else; the instance must only be reachable through Cloudflare (the bootstrap `DOCKER-USER` rule enforces this on 80/443).

#### 4.10.2 Cloudflare setup

1. Add the zone (the domain) to a free Cloudflare account; move the nameservers. Create DNS `A` and `AAAA` records for `ezmd` pointing at the Hetzner IPs with proxy status "Proxied" (orange cloud). Set SSL/TLS mode to "Full (strict)"; Caddy holds a Let's Encrypt certificate obtained via the HTTP challenge, which works through Cloudflare's proxy (or, simpler and more robust, create a Cloudflare Origin CA certificate and mount it into Caddy; document both and default to Origin CA for the public instance since it avoids the ACME rate limits on redeploys). Enable "Always Use HTTPS", HSTS off at Cloudflare (Caddy sets it), minimum TLS 1.2, TLS 1.3 on, HTTP/3 on.
2. Turnstile: create a widget `ezmd-public`, type "Managed" with "Invisible" preferred (falls back to interactive on suspicious traffic), hostname `ezmd.<domain>`. Put the site key in `EZMD_TURNSTILE_SITEKEY` and the secret in `EZMD_TURNSTILE_SECRET`. Set `EZMD_TURNSTILE_REQUIRED_FOR_FETCH=true`. The flow (Part 3): the browser solves the widget, posts the token to `POST /v1/challenge`, receives a 120-second JWT, and sends it as `X-Ezmd-Challenge` on `POST /v1/convert` for URL sources. File uploads are not challenged (uploads are capped by size and rate instead).
3. WAF custom rules (Security > WAF > Custom rules), in order:
   - "Block non-API bots on convert": expression `(http.request.uri.path contains "/v1/convert" and cf.client.bot and not cf.verified_bot_category in {"Search Engine Crawler"})` action Block. (Verified search crawlers do not POST, so in practice this blocks known bad bots.)
   - "Challenge high threat": `(cf.threat_score gt 30 and http.request.uri.path contains "/v1/")` action Managed Challenge.
   - "Block oversized": `(http.request.uri.path eq "/v1/convert" and http.request.body.size gt 536870912)` action Block (belt and braces over Caddy's 512 MB).
   - "Block fetch-node paths at the edge": `(http.request.uri.path contains "/v1/fetch-node/")` action Block. Fetch-node traffic arrives over Tailscale on the API's internal port and never passes through Cloudflare, so any request to these paths from the public side is hostile.
   - Do not geo-block. Document that the project does not block countries.
4. Rate limiting rules (Security > WAF > Rate limiting rules; free plan allows one rule with a 10-second window, so set the critical one here and rely on the app for the rest):
   - "Convert burst": path `/v1/convert`, 10 requests per 10 seconds per IP, action Block for 60 s. The application enforces the cobalt-derived 20/60 s and per-key limits.
5. Cache rules: "Cache static": `(http.request.uri.path matches "^/(assets|icons|models)/")` eligible for cache, edge TTL 1 month, respect origin `immutable`. "Bypass API": `(http.request.uri.path contains "/v1/")` bypass cache. Default: cache nothing else (results must never be cached at the edge; Part 3 sets `Cache-Control: private, no-store` on `/v1/*`, and this rule is the second line).
6. Configuration rules: disable Rocket Loader, Email Obfuscation, and Mirage for the zone (they inject scripts and break CSP). Turn off "Browser Integrity Check" exceptions; keep it on by default.
7. Security settings: Bot Fight Mode on (free), "Challenge Passage" 30 minutes, Security Level Medium.
8. Notifications: enable "Origin error rate alert" and "SSL certificate expiry" to the owner's email.
9. Record the Cloudflare account email, zone ID, and Turnstile widget ID in the private ops notes (not in the repo).

#### 4.10.3 Fetch node: Pi image build and first boot

The fetch node runs `apps/fetch-node` on a Raspberry Pi 4 (4 GB) or Pi 5 at the owner's home. It claims fetch jobs from the instance over Tailscale, performs the platform fetch (captions first, then yt-dlp audio-only with the bgutil PO-token provider on the home residential IP), and uploads the small result (caption JSON or Opus audio) to the instance. Users never learn the home IP: the instance reaches the Pi only through Tailscale, the Pi has no published ports, and the Pi's HTTP calls to platforms carry no user-identifying data (the job carries only the target URL).

Image build (agent writes `deploy/pi/build.sh` and `deploy/pi/cloud-init.yaml`):

1. Use Raspberry Pi OS Lite 64-bit (Debian 12 based) via `rpi-imager` CLI or the official image URL. Customize with `cloud-init` style `user-data` (Pi OS supports `firstrun.sh`; the script generates it): hostname `ezmd-pi`, user `ezmd` with the owner's SSH public key, password login disabled, Wi-Fi off (Ethernet only), locale, timezone.
2. `firstrun.sh` installs Docker (`get.docker.com`), Tailscale, `unattended-upgrades`, enables `fail2ban` (SSH only), sets `dtoverlay=disable-wifi,disable-bt` in `/boot/firmware/config.txt`, mounts `/tmp` as tmpfs 1.5 GB, configures `journald` with `SystemMaxUse=200M`, and writes `/opt/ezmd-fetch/docker-compose.yml` (the pi compose from 4.9.5) and an empty `.env.pi` with mode 600.
3. Nothing secret is in the image. On first boot the owner SSHes in (over LAN), runs `sudo tailscale up --advertise-tags=tag:ezmd-pi --ssh`, authenticates in the browser, then fills `.env.pi` with `EZMD_FETCH_NODE_TOKEN` (generated on the VPS with `docker compose exec api ezmd fetch-node token --node-id pi-home`, which also appends it to `EZMD_FETCH_NODE_TOKENS` on the VPS) and `EZMD_FETCH_NODE_INSTANCE=http://ezmd-vps:8080` (Tailscale MagicDNS name; the API's internal port is reachable via Tailscale because `tailscaled` on the VPS exposes it through `tailscale serve --bg --tcp 8080 tcp://127.0.0.1:8080`, which is itself allowed only by ACL from `tag:ezmd-pi`). Note: the API container publishes 8080 only to `127.0.0.1` on the VPS for this purpose; add `ports: ["127.0.0.1:8080:8080"]` to the `api` service in `docker-compose.public.yml`.
4. `docker compose up -d` on the Pi. Verify with `docker compose logs -f fetch-node` that it reports "claimed 0 jobs, polling" and that the VPS `/admin/fetch-nodes` (admin token) lists `pi-home` as online.
5. Optional cookies: if the owner wants to supply a YouTube cookies file for the Pi (self-host rule applies here too, since the public instance's own fetch policy still forbids YouTube unless a fetch node is online and the owner has accepted the risk in `DECISIONS.md`), place it at `/opt/ezmd-fetch/cookies.txt` mode 600. Default: no cookies; captions and public audio only.
6. Power: a UPS HAT is optional; the node is best-effort. When it is offline the instance's capabilities report `fetch_node: offline` and URL fetches for the disabled sources return `fetch_blocked_by_platform` with the extension suggestion, which is the designed degraded mode.

#### 4.10.4 Tailscale ACLs

In the tailnet policy file (agent writes `deploy/tailscale/policy.hujson`):

```hujson
{
  "tagOwners": {
    "tag:ezmd-vps": ["autogroup:admin"],
    "tag:ezmd-pi":  ["autogroup:admin"]
  },
  "acls": [
    // Pi may reach only the API port on the VPS. Nothing else, in either direction.
    { "action": "accept", "src": ["tag:ezmd-pi"],  "dst": ["tag:ezmd-vps:8080"] },
    // Owner may SSH to both.
    { "action": "accept", "src": ["autogroup:admin"], "dst": ["tag:ezmd-vps:22,8080", "tag:ezmd-pi:22"] }
  ],
  "ssh": [
    { "action": "accept", "src": ["autogroup:admin"], "dst": ["tag:ezmd-vps", "tag:ezmd-pi"], "users": ["root", "ezmd", "autogroup:nonroot"] }
  ]
  // No nodeAttrs granting "funnel" to any tag. Funnel and `tailscale serve` must never be enabled on the Pi.
}
```

The VPS node runs `tailscale serve` for 8080 restricted by this ACL; the Pi node never serves. Enable key expiry disabled on both tagged nodes (tagged nodes do not expire by default). Turn on tailnet lock if the owner has a second signing device; otherwise document the risk.

#### 4.10.5 Monitoring

1. Metrics: the API exposes `/metrics` (Prometheus text format, `prometheus-fastapi-instrumentator` plus custom gauges) on the internal network with `EZMD_METRICS_TOKEN` as a bearer. Required series: `ezmd_jobs_total{source_type,status,client}`, `ezmd_job_duration_seconds{stage,source_type}` histogram, `ezmd_queue_depth{queue}`, `ezmd_queue_wait_seconds{queue}` histogram, `ezmd_rate_limited_total{reason}`, `ezmd_fetch_blocked_total{platform,strategy}`, `ezmd_fetch_node_online{node_id}`, `ezmd_blob_bytes`, `ezmd_model_loaded{engine}`, `ezmd_turnstile_verify_total{result}`, `ezmd_warnings_total{code}`, plus process metrics. Workers push to the API's `/internal/metrics` over the internal network every 15 s (RQ workers have no HTTP server); the API aggregates.
2. Stack: `deploy/docker-compose.monitoring.yml` adds `prometheus` (15-day retention, 2 GB cap, scrapes `api:8080/metrics` with the token, `caddy:2019/metrics`, `node-exporter`, `cadvisor`), `grafana` (anonymous disabled, admin password from `.env`, bound to `127.0.0.1:3000` and reached over Tailscale only), and `alertmanager`. Provision one Grafana dashboard JSON (`deploy/monitoring/grafana/ezmd.json`) with panels: jobs/min by type, p50/p95 duration by stage, queue depth and wait, rate-limited/min, fetch blocked by platform, fetch node online, CPU and memory per container, disk free, blob bytes, warnings by code.
3. Alert rules (`deploy/monitoring/alerts.yml`) routed to email and a Discord webhook via alertmanager:
   - `ApiDown`: `up{job="api"} == 0` for 2 m, critical.
   - `QueueBacklog`: `ezmd_queue_depth{queue="default"} > 50` for 10 m, warning; `> 200` for 5 m, critical.
   - `MediaQueueWait`: p95 `ezmd_queue_wait_seconds{queue="media"} > 600` for 15 m, warning.
   - `FetchNodeOffline`: `ezmd_fetch_node_online == 0` for 30 m, warning (expected occasionally; info-level after the first week).
   - `FetchBlockedSpike`: `rate(ezmd_fetch_blocked_total[15m]) > 0.2` for 30 m, warning (yt-dlp breakage signal).
   - `DiskLow`: `node_filesystem_avail_bytes{mountpoint="/"} / node_filesystem_size_bytes < 0.15`, critical.
   - `CpuSaturated`: node CPU idle < 10% for 20 m, warning.
   - `RateLimitFlood`: `rate(ezmd_rate_limited_total[5m]) > 5`, info (abuse signal).
   - `CertExpiry`: Caddy cert expiry < 14 d, warning.
   - `JobFailureRate`: failed/total over 30 m > 20% with total > 20, warning.
4. Uptime: an external check (UptimeRobot free, or Cloudflare's health check if on a paid plan) on `https://ezmd.<domain>/healthz` every 5 minutes, email and Discord on failure. This catches Cloudflare-side and DNS problems the internal stack cannot see.
5. Discord: a private channel with the webhook; alertmanager's Discord receiver (native since 0.25). Keep the webhook URL in `.env` only.
6. Weekly digest: a small `ezmd admin report --week` command prints jobs by type, top warning codes, fetch block rate, p95 durations, cost estimate, and is run by a systemd timer that posts it to the Discord channel. This is the owner's main feedback loop and the input for the sponsor application.

#### 4.10.6 Log retention and redaction

1. Application logs are JSON lines to stdout, captured by Docker's json-file driver with the 20 MB x 5 cap per container (about a week at expected volume). Caddy access logs roll at 50 MB, kept 5 files or 7 days. Nothing is shipped off-box in v1.
2. Redaction is on by default (`EZMD_LOG_REDACT=true`): client IPs are hashed with a daily rotating salt (HMAC of IP with `date + EZMD_SECRET_KEY`), so abuse correlation works within a day but logs cannot be joined across days or to a person; URLs are logged as scheme plus host plus path with the query string removed; uploaded file names are logged as their extension and size only; result bodies, text inputs, and captions are never logged; API keys appear as their first 6 characters; Turnstile tokens, JWTs, and node tokens are never logged.
3. Caddy's log filter (4.9.7) masks IPs to /24 and /48 and drops cookies and authorization headers.
4. A job record in SQLite keeps: job id, source type, host (not full URL), size, duration, stages timing, warning codes, client string, hashed IP, API key id, created and expires timestamps. It is deleted with the result at 24 hours by the reaper (Part 3). Aggregate counters (for the weekly report) are kept in a separate table with no per-job linkage.
5. Error reports with stack traces may contain file names; the error handler strips paths to basenames and redacts anything that looks like a URL query or a token before logging.
6. The Privacy page (4.13.2) states exactly this.

#### 4.10.7 Cost tracking and capacity math

Known numbers from the research, used as planning constants (record them in `docs/ops/capacity.md` and re-measure in the nightly fixture run):

- Docling CPU: ~3.1 s per PDF page. pypdf text-layer fallback: ~0.05 s per page. Trafilatura web page: ~0.3 s. DOCX via Docling: ~0.5 s per page. Repo packing: I/O bound, ~1 s per 1,000 files.
- faster-whisper `small` int8 on a modern x86 core: roughly 2 to 3x realtime single-threaded; `base` roughly 6 to 8x; with 3 threads `small` reaches roughly 5x. Plan on `small` at 4x realtime on the media worker's 3 cores: a 15-minute clip takes about 4 minutes.
- Groq whisper-large-v3-turbo: $0.04 per audio hour, 100 MB file cap, roughly 200x realtime.

Capacity on the 8-core box with the compose limits above (api 1 core, worker-default 3 cores with concurrency 2, worker-media 3 cores with concurrency 1, 1 core for Caddy, Redis, Squid, and the OS):

- Documents: a typical 10-page PDF is ~31 s of a core on Docling; two concurrent jobs on 3 cores give roughly 200 ten-page PDFs per hour, or about 2,000 pages per hour. Web pages: ~10,000 per hour (rate limits bind first).
- Media: at 4x realtime and concurrency 1, the media worker clears 4 audio hours per wall hour, i.e. 16 fifteen-minute clips per hour. A queue of 20 clips means an hour's wait, which is the `MediaQueueWait` alert threshold rationale.
- When to add Groq: the trigger is p95 media queue wait above 10 minutes for three days in a week, or more than 60 media jobs per day. At that point set `EZMD_GROQ_API_KEY` and `EZMD_GROQ_OFFLOAD_MIN_S=300`: clips over 5 minutes go to Groq, short clips stay local. Cost at 100 fifteen-minute clips a day is 25 audio hours, i.e. $1 per day, $30 per month, far cheaper than a GPU box. Groq is a sub-processor, so enabling it requires updating the Privacy page (the draft includes the clause, commented out) and the capabilities response (`asr_offload: groq`), and the UI shows "Transcribed with a hosted provider" in the warnings panel as an info-level notice for those jobs. Diarization is not available via Groq; such jobs lose speaker labels, reported as `warning: diarization_unavailable_offload`.
- Cost tracking: `ezmd admin report` sums Groq seconds billed (from the job table) and multiplies by the configured rate, adds the fixed monthly server cost from `EZMD_COST_SERVER_MONTHLY`, and prints cost per 1,000 jobs. The weekly Discord digest includes it. Hetzner bandwidth is 20 TB included; expected egress is text, under 50 GB per month; an alert fires at 5 TB per month measured by `node_network_transmit_bytes_total`.
- Sponsor application: once the instance shows 30 days of data (jobs per day, unique daily IPs, bandwidth, CPU hours), the owner applies to Hetzner's open source program, Cloudflare's Project Alexandria or OSS sponsorship, and GitHub Sponsors (organization tier). The `docs/ops/sponsor-pack.md` template is generated by `ezmd admin report --sponsor-pack` with the numbers filled in. Until a sponsor exists, the footer shows the "Support" link to GitHub Sponsors with the text "Nothing is gated; this keeps the public instance running." Donations alone are not expected to cover the box; the budget ceiling at which the owner downgrades the public instance to documents-and-web-only (media profile off) is written in `DECISIONS.md` and defaults to $80 per month of unsponsored spend.

### 4.11 Abuse prevention

Phase: 4 for the public instance; the mechanisms are built in Phase 1 (rate limiting, keys, size caps) and Phase 2 (duration caps, bomb protection). `docs/abuse.md` documents all of it for self-hosters.

#### 4.11.1 Limits (cobalt-derived defaults)

| Control | Anonymous | Free API key | Sponsor key | Where enforced |
|---|---|---|---|---|
| Requests per IP | 20 per 60 s | per key: 200 per 60 s | unlimited | API middleware (Redis sliding window) |
| Concurrent running jobs | 1 per IP | 3 per key | 10 | queue admission |
| Upload size | 25 MB public (200 MB self-host default) | 200 MB | 2 GB | Caddy `request_body`, API pre-check, multipart streaming abort |
| HTML fetch size | 10 MB | 25 MB | 100 MB | fetch chain, streaming abort |
| Audio or video duration | 15 min public (3 h self-host default) | 1 h | 6 h | ffprobe before transcribing; truncate and warn, do not reject, when within 2x; reject beyond |
| PDF pages | 300 public (2,000 self-host) | 2,000 | 10,000 | page count before layout engine |
| Archive entries, depth, ratio | 2,000 / 3 / 100x | same | same | archive walker |
| Output size | 50 MB | 50 MB | 200 MB | renderer; truncate with `warning: truncated` |
| Job wall time | 30 min | 30 min | 2 h | RQ job timeout plus a SIGKILL watchdog |
| URL fetch | Turnstile JWT required | no challenge | no challenge | API |
| Platform fetch (YouTube etc.) | fetch node only, else blocked | same | same | source policy |

Keys live in `keys.json` in cobalt's shape, loaded on start and on `SIGHUP` or `POST /admin/keys/reload`:

```json
[
  {
    "key": "b7b1b0a0-5d6e-4f0e-9e2b-2f0c0f6b1a11",
    "name": "obsidian-plugin-ci",
    "tier": "free",
    "limits": { "requests_per_window": 200, "window_s": 60, "concurrency": 3, "max_upload_mb": 200, "max_duration_s": 3600 },
    "ips": ["203.0.113.0/24"],
    "user_agents": ["ezmd-obsidian/*"],
    "allowed_sources": ["*"],
    "disabled_sources": [],
    "expires": "2027-01-01T00:00:00Z",
    "notes": "issued 2026-11-02 via email"
  }
]
```

Free keys are issued by the owner on request (a form on the docs site that opens a GitHub issue template; no automated issuance in v1 so there is no signup system to abuse). Keys are UUIDv4; the API stores only a SHA-256 of the key in the usage table.

#### 4.11.2 Turnstile JWT flow and the self-host alternative

1. The web UI loads the Turnstile widget only when `capabilities.challenge == "turnstile"`. On URL submit it obtains a token, posts it to `POST /v1/challenge`, and the API verifies with Cloudflare's siteverify (through the egress proxy) and returns a JWT signed with `EZMD_SECRET_KEY`, TTL 120 s, bound to the hashed client IP and a nonce. `POST /v1/convert` with a URL source requires the JWT in `X-Ezmd-Challenge`. One JWT is good for up to 5 convert calls (so multi-URL paste works) and is then revoked in Redis.
2. ALTCHA for self-hosters who do not want Cloudflare: when `EZMD_ALTCHA_HMAC_KEY` is set and Turnstile is not, `capabilities.challenge == "altcha"`, `GET /v1/challenge/altcha` returns an ALTCHA challenge (SHA-256, `maxnumber` from `EZMD_ALTCHA_MAX_NUMBER`), the `altcha` web component (MIT, 34 kB, vendored into `apps/web`) solves it in the browser in 1 to 3 s, and `POST /v1/challenge` accepts the ALTCHA payload in place of a Turnstile token and issues the same JWT. Anubis is documented as a reverse-proxy option in front of Caddy for operators who want site-wide proof-of-work; the project does not integrate it in code. The docs state plainly that proof-of-work blocks low-effort scrapers only and that API keys plus per-IP concurrency are the real controls.
3. Clients without a browser (CLI, SDK, Shortcut, MCP remote) cannot solve a challenge; they use an API key, or on the public instance fall into the `client` allowance: the API recognizes `client: ios-shortcut` and `User-Agent: ezmd-cli/*` and permits URL fetches without a JWT at a tighter per-IP limit (5 per 10 minutes). This is an explicit, documented soft spot; if abused, the owner flips `EZMD_CLIENT_ALLOWANCE=off` and those clients need keys.

#### 4.11.3 Queue fairness

1. Three RQ queues: `web` and `docs` (worker-default), `media` and `ocr` (worker-media). Admission control sits in the API before enqueue: a per-IP (or per-key) running-job counter in Redis with TTL equal to the job timeout; exceeding the concurrency returns 429 with `Retry-After` and the queue position of the caller's own running job, so the UI can say "your previous conversion is still running".
2. Weighted fairness inside a queue: RQ is FIFO, so fairness is implemented at enqueue time by sharding into priority sub-queues: `media-short` (under 5 min) is served before `media-long` by the worker's queue order (`ezmd worker --queues media-short,media-long`), which keeps a 3-hour self-host job from starving thirty 2-minute clips. Keyed jobs go to `*-keyed` sub-queues listed first. The worker command in compose must list queues in this order; the agent generates the list from one constant in `packages/core`.
3. Per-IP daily budget on the public instance: 60 media minutes and 500 document pages per hashed IP per rolling 24 hours, after which the API returns 429 with a message pointing to self-host. Enforced with Redis counters keyed by the daily IP hash.
4. Reaper: a scheduled RQ job every 5 minutes deletes results past `EZMD_RETENTION_HOURS`, kills jobs past wall time, and clears orphaned temp files.

#### 4.11.4 Size caps and bomb protection

1. Uploads stream to disk with a running byte counter; the request is aborted at the cap before the body is fully read (Starlette `request.stream()`), and the partial file is deleted.
2. Archives (zip, tar, 7z, and Office/EPUB containers, which are zips): entry count, nesting depth, and cumulative decompressed size are checked during extraction, never trusted from headers; extraction stops at `EZMD_MAX_ARCHIVE_RATIO` times the compressed size or `EZMD_MAX_ARCHIVE_ENTRIES`, emitting `warning: archive_truncated`. Path traversal entries (`../`, absolute, symlinks) are skipped with `warning: archive_entry_skipped`.
3. PDFs: page count via `pypdf` before any layout engine; a per-page time budget (10 s on CPU) with the engine run in a subprocess that is killed on overrun, emitting `warning: page_timeout` with the page list; object stream and XRef bombs are caught by the subprocess memory limit (`RLIMIT_AS` 2 GB per converter subprocess).
4. Images: `Pillow.Image.MAX_IMAGE_PIXELS` set to 50 MP; decompression bombs raise and produce `warning: image_too_large`.
5. Media: `ffprobe` first (with its own 20 s timeout); duration and stream count are checked before decoding; ffmpeg runs with `-t <cap>` so a mislabeled 10-hour file cannot run past the cap; ffmpeg and the ASR engine run under the converter subprocess limits.
6. Fetch: response size streamed with a cap, redirect count 5, each redirect re-checked by the SSRF guard (DNS resolved once, IP pinned, private and link-local ranges and the instance's own hosts refused), content-type sniffed by Magika on the first 1 MB, total fetch time 60 s.
7. Text inputs: 10 MB cap on `text` fields; token estimation is done on a sample for inputs over 1 MB to bound CPU.

#### 4.11.5 Blocklist and source policy

1. `EZMD_DISABLED_SOURCES` disables platform adapters by name; the public instance ships with `youtube,tiktok,instagram,x,facebook` disabled for direct fetch (fetch-node and extension paths remain). Each disabled source returns `fetch_blocked_by_policy` with the UI's suggestion text.
2. A pattern blocklist `deploy/blocklist.txt` (one regex per line, hot-reloaded) refuses URLs by pattern: known abuse targets (e.g. login pages, `/wp-login.php`, `/xmlrpc.php`, `/.env`), file-sharing hosts that have asked to be excluded, and anything the owner adds after an incident. Matches return 400 with `url_blocked_by_policy` and are counted in metrics.
3. User-agent and ASN heuristics: requests from known cloud ASNs with no API key are allowed but get `concurrency 1` and `requests 10 per 60 s` (half the anonymous allowance). ASN lookup via a bundled MaxMind GeoLite2-ASN database only if the owner accepts its license; otherwise skip this control (default: skipped; the Cloudflare `cf.client.bot` rule covers the worst of it).
4. Takedown blocklist: URLs or content hashes received through the DMCA process are added to `deploy/blocklist.txt` with a comment and date.

#### 4.11.6 Incident response checklist

`docs/ops/incidents.md`:

1. Detect: alert fires (RateLimitFlood, CpuSaturated, QueueBacklog, DiskLow), or a complaint arrives (DMCA email, platform contact, Hetzner abuse ticket).
2. Triage in 15 minutes: `ezmd admin top --last 1h` prints top hashed IPs, keys, source hosts, and client strings by job count and CPU seconds. Identify the pattern.
3. Contain: for an IP or key, `ezmd admin block --ip-hash H --hours 24` or `ezmd admin keys disable NAME`; for a source host, add a regex to `blocklist.txt`; for a flood, enable Cloudflare "Under Attack" mode for the zone (interactive challenge on every request) for up to an hour; for a runaway job, `ezmd admin jobs kill ID`; for disk, `ezmd admin reap --now`.
4. If the abuse is media-bound, temporarily set `EZMD_ANON_MAX_DURATION_S=300` and restart the API (no job loss; workers keep running).
5. If a platform or rights holder contacts the owner: acknowledge within 2 business days from the DMCA mailbox, disable the specific source or URL pattern immediately while reviewing, follow the takedown process (4.13.3), and record the event in the private incident log with date, request, action, and outcome.
6. If Hetzner sends an abuse ticket: respond within their deadline (usually 24 h), include what was done, and keep the ticket ID in the log.
7. Recover: remove temporary blocks after 24 to 72 hours unless repeated; return Cloudflare to normal security level; post a one-line note in the Discord channel.
8. Learn: if the incident revealed a missing control, open an issue tagged `abuse` with the proposed change; if it was a false positive on legitimate users, adjust the limit and note the change in CHANGELOG under "Operations".
9. Escalate to the human (this is the trigger for the agent, in the autonomous build, to stop and write a report rather than act): any legal correspondence, any Hetzner or Cloudflare account action, any event that would require spending money, any data exposure suspicion.

### 4.12 Security hardening

Phase: 1 for container hardening and CI scanning; Phase 4 for the VPS and Pi checklists (applied by bootstrap and the Pi image). `SECURITY.md` and `docs/security.md` carry the public versions.

#### 4.12.1 VPS checklist

Applied by `bootstrap.sh` where marked (B), by the owner where marked (O), verified by `ezmd admin audit-host` (a script that checks each item and prints OK/FAIL; agent writes it in `deploy/audit-host.sh`):

1. (B) SSH: key-only, no password, no root password login, `MaxAuthTries 4`, no agent or X11 forwarding. (O) After Tailscale: close port 22 at the Hetzner firewall and use Tailscale SSH.
2. (B) ufw: default deny inbound, allow 22 (until closed), 80, 443 TCP and UDP. (B) `DOCKER-USER` chain restricts 80/443 to Cloudflare ranges in public mode; a weekly timer `ezmd-cfips.timer` refreshes the ranges from `cloudflare.com/ips-v4` and `ips-v6`.
3. (B) fail2ban on sshd. (B) unattended-upgrades with automatic reboot at 04:30 and `live-restore` so containers survive the Docker daemon restart.
4. (B) Docker daemon: `icc: false`, `no-new-privileges: true`, log caps. Docker socket is not mounted into any container on the VPS (Watchtower is not used on the VPS; `upgrade.sh` is).
5. (compose) Every container: non-root uid 10001, `read_only`, `cap_drop: ALL` (Caddy adds `NET_BIND_SERVICE`), `no-new-privileges`, tmpfs scratch, memory and CPU limits, `pids_limit: 512` (add to the `x-common` anchor), healthchecks.
6. (compose) Workers run under the seccomp profile `deploy/seccomp-worker.json`: Docker's default profile with `ptrace`, `mount`, `umount2`, `pivot_root`, `kexec_load`, `reboot`, `swapon`, `init_module`, `finit_module`, `delete_module`, `bpf`, `perf_event_open`, `userfaultfd`, `unshare`, `setns`, `clone3` with new namespaces removed. Generate it by starting from the default profile JSON shipped in the moby repository and removing those names; test that ffmpeg, Docling, and faster-whisper still run under it in CI. AppArmor: Ubuntu's `docker-default` profile applies automatically; the compose file sets `apparmor:docker-default` explicitly on workers so it is visible.
7. (compose) Converter subprocesses inside the worker (Part 2 runs each engine in a subprocess) get `RLIMIT_AS` 2 GB, `RLIMIT_CPU` per job budget, `RLIMIT_NPROC` 64, `RLIMIT_FSIZE` 2 GB, umask 077, a fresh tmp dir deleted after, and no inherited environment beyond an allowlist (no `EZMD_*` secrets reach engine subprocesses; a test asserts the subprocess env).
8. (compose) Egress allowlist: in public mode, workers have no direct internet; all HTTP goes through Squid with this `deploy/squid.conf`:

```
http_port 3128
acl localnet src 172.16.0.0/12 10.0.0.0/8
acl SSL_ports port 443
acl Safe_ports port 80 443
acl CONNECT method CONNECT
# Deny private destinations even if DNS resolves there (defense in depth behind the app SSRF guard)
acl to_private dst 10.0.0.0/8 172.16.0.0/12 192.168.0.0/16 127.0.0.0/8 169.254.0.0/16 100.64.0.0/10 fc00::/7 fe80::/10 ::1/128
http_access deny to_private
http_access deny !Safe_ports
http_access deny CONNECT !SSL_ports
# Optional hostname allowlist for the api container (Turnstile verify, Groq); workers fetch arbitrary public hosts
acl api_src src 172.16.0.0/12
http_access allow localnet
http_access deny all
# No caching, no logging of URLs beyond host
cache deny all
logformat ezmd %ts.%03tu %>a %Ss/%03>Hs %<st %rm %rp://%rh %Sh/%<a
access_log stdio:/dev/stdout ezmd
forwarded_for delete
via off
request_header_access X-Forwarded-For deny all
dns_v4_first on
```

The app-level SSRF guard remains the primary control (it resolves once, pins the IP, and connects to the pinned IP with the Host header, which Squid cannot do), and Squid is the backstop for anything that escapes it (a library opening its own connection, for example).

9. (compose) Secrets: everything secret is in `.env` (mode 600, root-owned) and `keys.json` (mode 600); the images contain no secrets; `docker compose config` output is never pasted into issues (the `ezmd admin support-bundle` command produces a redacted bundle). No secret is passed as a command-line argument (visible in `ps`). `EZMD_SECRET_KEY` rotation is documented: rotating it invalidates outstanding challenge JWTs and fetch-node tokens only.
10. (CI) Trivy scans every image on every build for OS and library CVEs; `HIGH` and `CRITICAL` with a fix available fail the build; unfixed ones are reported and tracked in `SECURITY-EXCEPTIONS.md` with an expiry. `pip-audit` and `pnpm audit` run on lockfiles. An SBOM (CycloneDX) is generated per image with `syft` and attached to the GitHub release and the GHCR image as an attestation (`cosign attest`). Images are signed with `cosign` keyless (Sigstore, GitHub OIDC); the docs show how to verify.
11. (O) Hetzner project: 2FA on the account; a separate API token is not needed (no automation uses the Hetzner API). Cloudflare: 2FA; the Turnstile secret and Origin CA key are the only Cloudflare secrets on the box.
12. (compose) The admin API (`/admin/*`) is served only on the internal port, reachable via Tailscale, with `EZMD_ADMIN_TOKEN`. Caddy returns 404 for `/admin/*` and `/metrics` from the public side.
13. (app) CSP as in the Caddyfile; cookies are not used at all (no sessions); CORS allows the configured public origin and `moz-extension://` and `chrome-extension://` origins for the extension (Part 3 lists the exact header behavior).
14. (app) Dependencies are pinned with `uv.lock` and `pnpm-lock.yaml`; Renovate (4.15.7) updates them weekly with CI gates.

#### 4.12.2 Pi checklist

1. Image contains no secrets; `.env.pi` is created at first boot, mode 600, owned by `ezmd`.
2. SSH key-only, fail2ban, unattended-upgrades with reboot at 05:00, Wi-Fi and Bluetooth disabled in firmware config, no inbound ports open on the LAN beyond SSH (ufw: default deny inbound, allow 22 from the LAN subnet and from Tailscale).
3. Tailscale with tag `tag:ezmd-pi`, ACL allows only Pi to VPS:8080; Funnel and Serve never enabled; `tailscale set --auto-update`.
4. Container: non-root, read-only, caps dropped, tmpfs scratch 1.5 GB, memory limit 1.5 GB, `network_mode: host` is the one relaxation (needed for Tailscale and residential egress); Watchtower auto-updates the fetch-node image hourly from GHCR; the Docker socket is mounted read-only into Watchtower only.
5. The fetch node never writes fetched media to the SD card (tmpfs only), never stores results, and keeps only yt-dlp's cache of challenge solvers in a named volume.
6. The node authenticates to the instance with its token; the instance validates the node id, rate-limits claims, and only hands a node jobs whose source is in the node's `allowed_sources`. A compromised Pi can at worst return bad transcripts for jobs it claims; the instance treats node uploads as untrusted input (same size caps, same Magika sniff, same conversion pipeline).
7. The Pi has no copy of `EZMD_SECRET_KEY`, no API keys, no database access.
8. `ezmd fetch-node doctor` checks all of the above on the Pi and prints OK/FAIL.

#### 4.12.3 Threat model

| Asset | Threat | Mitigation |
|---|---|---|
| Users' uploaded files and results | Exposure to other users or the operator | Opaque 128-bit job ids; results fetched by id plus a per-job download token (Part 3); 24 h TTL reaper; no operator browsing tool; logs never contain content; blobs on an encrypted volume (Hetzner volumes are encrypted at rest) |
| Users' uploaded files and results | Retention beyond promise | Reaper every 5 min, `EZMD_RETENTION_HOURS=24` enforced in code and tested; backups exclude blobs |
| Server | SSRF via URL fetch to cloud metadata, Redis, internal services | DNS resolved once and IP pinned; private, link-local, loopback, CGNAT, and own-host ranges refused on every hop; API container has no egress; workers egress only through Squid, which also denies private destinations; `internal: true` Docker network |
| Server | Malicious document exploits a parser (PDF, image, Office, archive) | Each engine in a subprocess with rlimits and seccomp; read-only root FS; non-root; tmpfs scratch; Trivy-scanned base images; Pillow pixel cap; archive bomb limits |
| Server | Resource exhaustion (CPU, disk, memory) by many or large jobs | Rate limits, per-IP concurrency, size and duration caps, per-job wall time, container memory limits, tmpfs sizing, DiskLow alert, reaper |
| Server | SSH brute force, unpatched OS | Key-only SSH behind Tailscale, fail2ban, unattended-upgrades, ufw, Cloudflare-only on 80/443 |
| Owner's home network | Exposure of the home IP through the fetch node | Pi is outbound-only; reaches the VPS over Tailscale only; no ports published; users never receive a URL that resolves to the Pi; media fetched by the Pi is uploaded to the VPS, never served from the Pi |
| Owner's home network | Compromise of the Pi pivoting to the LAN | Pi on its own VLAN or guest network (documented recommendation); container hardened; no secrets beyond its own token; ACL prevents the VPS from initiating to the Pi |
| Platform relations | Datacenter-IP scraping of YouTube and others from the VPS | Public instance disables direct platform fetch; fetch moves to the Pi, extension, or Shortcut on the user's own IP; captions-first strategy minimizes media transfer |
| Legal posture | DMCA or ToS complaints | Published agent and process; no content retention past 24 h; no re-serving of media; `DISABLED_SOURCES` to turn off any platform on request; blocklist for specific URLs; incident log |
| API keys | Leak and misuse | Keys stored hashed; per-key IP and user-agent allowlists; per-key limits; `expires`; usage visible in `ezmd admin keys usage`; rotation by issuing a new key |
| Challenge system | Turnstile token replay or JWT forgery | Token verified once with Cloudflare and the JWT bound to hashed IP plus nonce with 120 s TTL and a use counter in Redis; HMAC with the server secret |
| Supply chain | Malicious or vulnerable dependency, model weights swapped | Lockfiles; Renovate with CI gates; pip-audit and pnpm audit; Trivy; SBOM; model registry pins Hugging Face revisions and SHA-256; license allowlist |
| Prompt injection | Converted content carries instructions to the consuming model | Injection scanner flags, never deletes; `agent` profile wraps body in a salted untrusted-content fence; MCP tool descriptions tell the model that content is data |
| Extension users | Extension exfiltrates browsing | Minimal permissions, `activeTab` only, no host permissions at rest, open source, no analytics, store privacy declarations |
| Operator | Account takeover (Hetzner, Cloudflare, GitHub, PyPI, npm) | 2FA everywhere; PyPI and npm trusted publishing (no long-lived tokens); GitHub environment protection on release; cosign keyless signing |
| Monitoring | Metrics or admin endpoints exposed | Internal network only; bearer tokens; Caddy 404s; Grafana bound to loopback, reached over Tailscale |

### 4.13 Legal and policy pages

Phase: 4 (must exist before the public launch; the pages are static routes in `apps/web` at `/terms`, `/privacy`, `/dmca`, `/acceptable-use`, served from `apps/web/src/legal/*.md` through the same Markdown renderer). Self-hosters get them with placeholders and a note that they are responsible for their own instance's terms. The draft text below is plain English and short. The owner must read it before launch; the agent must not change the substance without flagging it. Replace `OPERATOR`, `JURISDICTION`, and `DMCA_EMAIL` from `.env`.

#### 4.13.1 Terms of Service (draft)

> **Terms of Service for the ezmd public instance**
>
> Last updated: DATE.
>
> **What this is.** ezmd converts documents, web pages, media, and other inputs you provide into Markdown text. The public instance at EZMD_PUBLIC_URL is run by OPERATOR as a free service for the open-source project. The software is Apache-2.0 and you can run your own copy.
>
> **No account, no warranty.** You do not need an account. The service is provided as is, with no warranty of accuracy, availability, or fitness for any purpose. Converted output may be incomplete or wrong; the service reports what it could not read, but you are responsible for checking the output before relying on it.
>
> **Your content.** You keep all rights to what you submit and to the output. You confirm that you have the right to submit it and to produce a text version of it. Do not submit content you are not allowed to copy, content that is unlawful, or other people's personal data without a lawful basis.
>
> **Limits.** The service has rate limits, size and duration caps, and may refuse sources, URLs, or files at any time. It may be unavailable or change without notice. We may block abusive use.
>
> **Third-party platforms.** The service fetches public web pages on your behalf. It does not bypass logins, paywalls, DRM, or technical protection measures, and it does not fetch from platforms that have asked us not to. Fetching some sites may be against those sites' terms; you are responsible for your use.
>
> **Liability.** To the extent permitted by law, OPERATOR is not liable for any loss arising from your use of the service. The total liability of OPERATOR to you is zero, since the service is free.
>
> **Law.** These terms are governed by the laws of JURISDICTION. If a part of these terms is unenforceable, the rest stays in effect.
>
> **Contact.** DMCA_EMAIL.

#### 4.13.2 Privacy Policy (draft)

> **Privacy Policy for the ezmd public instance**
>
> Last updated: DATE.
>
> **Summary.** No accounts. No tracking scripts. Nothing you submit is kept for more than 24 hours. We do not read your content. We do not sell or share data.
>
> **What we process.** When you submit a URL, text, or file, we process it to produce Markdown. The input and the result are stored on our server under a random id, so you can download the result, and are deleted automatically 24 hours after the job was created, or earlier if the server needs the space. You can delete a result sooner with the "Delete now" button or `DELETE /v1/jobs/{id}`.
>
> **What we log.** For abuse prevention and capacity planning we log, per request: a one-way hash of your IP address that changes daily (so it cannot be linked to you across days), the type and size of the input, the host name of a fetched URL (not the full address), the time taken, warning codes, and which client you used (web, CLI, extension, shortcut). We do not log the content of what you submit or receive, file names, full URLs, or query strings. Logs are kept for 7 days on the server and are not sent anywhere else.
>
> **Cookies and storage.** We set no cookies. The web app stores your history and settings in your own browser's local storage; you can clear it with "Clear history". Cloudflare, which sits in front of our server for protection, may set its own technical cookie for bot challenges; see Cloudflare's privacy policy.
>
> **Third parties.** Our server is hosted by Hetzner Online GmbH in the United States (Ashburn, Virginia). Cloudflare, Inc. provides DNS, DDoS protection, and the Turnstile bot check; Turnstile processes your IP address and browser signals to decide whether you are a bot. [IF GROQ ENABLED: For audio longer than N minutes we send the audio to Groq, Inc. for transcription; Groq does not retain it after processing per their terms. Jobs that used this path say so in their warnings.] No other third party receives your data.
>
> **Browser extension and shortcuts.** The extension and shortcuts send only the page address or the media you chose to the instance you configured. They collect nothing else.
>
> **Your rights (GDPR, CCPA, and similar).** Because we hold no account data and delete content within 24 hours, there is usually nothing to access or erase after that time. If you believe we hold data about you, write to DMCA_EMAIL and we will respond within 30 days. The controller is OPERATOR, JURISDICTION. We do not have a representative in the EU; EU residents may contact us at the same address. We do not make automated decisions with legal effects about you.
>
> **Children.** The service is not directed at children under 13 (16 in the EU) and we do not knowingly process their data.
>
> **Changes.** We will post changes here with a new date.

#### 4.13.3 DMCA agent and takedown process (draft)

> **Copyright and takedown**
>
> The ezmd public instance converts content on your request and deletes it within 24 hours. We do not host, index, or publish content, and we do not re-serve media files. If you believe that the service has been used to infringe your copyright, or that a specific URL should not be convertible through this service, send a notice to our designated agent:
>
> OPERATOR, DMCA_EMAIL, POSTAL_ADDRESS.
>
> A notice should include: the work you own, the URL or job id involved, your contact details, a statement of good-faith belief that the use is unauthorized, a statement under penalty of perjury that you are the owner or authorized to act, and your signature. We will acknowledge within 2 business days, remove any stored result that matches (results are in any case deleted within 24 hours), add the URL pattern to our refusal list where appropriate, and reply with what we did. Repeated or clearly abusive notices may be published with personal data removed.
>
> **Platform operators.** If you run a platform and want ezmd's public instance to stop fetching from your domain, write to the same address; we will add your domain to the refusal list within 2 business days without requiring a legal notice. The self-hosted software remains available under the Apache-2.0 license and we do not control what others run.

The owner must register the DMCA agent with the US Copyright Office (small fee, online form) before launch; the runbook includes that step. Internal process: `docs/ops/takedown.md` describes the mailbox, the 2-day SLA, the blocklist edit, the incident log entry, and the escalation to counsel if a notice concerns the software rather than a specific use.

#### 4.13.4 Platform ToS stance (published in docs and summarized on the Acceptable Use page)

> ezmd's public instance fetches only from sources that allow automated public access (ordinary web pages, Reddit's JSON endpoints, Hacker News's API, Bluesky and Mastodon public APIs, podcast RSS feeds, SEC EDGAR, public Google Docs exports). It does not fetch from YouTube, TikTok, Instagram, X, or Facebook directly from the server. For those sites the browser extension and the mobile shortcuts fetch captions or media in your own browser, with your own session, and send only the text or audio to ezmd for conversion; whether that use is allowed depends on the platform's terms and your own account. The self-hosted software includes optional adapters for those platforms; they are disabled by default, require you to supply your own credentials or proxy, and are your responsibility to use lawfully. ezmd never bypasses DRM or paywalls.

#### 4.13.5 Acceptable Use (draft)

> Do not use the service to: convert content you have no right to copy; process other people's personal data without a lawful basis; attack, probe, or overload the service or any site it fetches from; circumvent rate limits, challenges, or source restrictions; use the service as a proxy for anything other than conversion; or submit content that is illegal where you or we are. We may block, rate-limit, or refuse any use at our discretion. If you are not sure, run your own instance.

#### 4.13.6 GDPR note (in docs for self-hosters)

> If you run a public instance in or for the EU, you are the controller. Set `EZMD_LOG_REDACT=true`, keep `EZMD_RETENTION_HOURS` at 24 or lower, publish your identity and contact on the Privacy page, list your hosting provider and any ASR offload provider as processors, and do not enable the Groq offload or any hosted engine without updating the page. ezmd stores no account data, so data subject requests are normally answered by pointing to the retention window.

---

## C. Quality, CI, release

### 4.14 Test strategy

Phase: 0 scaffolding, grows every phase. Tests live beside the code (`packages/*/tests`, `apps/*/tests`) and in `fixtures/`. `uv run pytest` at the root runs everything Python; `pnpm test` runs TypeScript. CI runs the unit and fixture tiers on every PR and the integration, load, and browser tiers on merge to `main` and nightly.

#### 4.14.1 Unit tests

- Every converter has unit tests for: happy path, empty input, truncated or corrupt input, the warnings it must emit, and profile rendering. Coverage gate: 85% lines on `packages/core`, 75% on converter packages, enforced with `coverage` and failing CI below the gate.
- Every public CLI command has a `typer.testing.CliRunner` test for `--help`, one success, one failure with the right exit code, and `--json` validity.
- The API has `httpx.AsyncClient` tests against the app with `EZMD_QUEUE=inline` for every route, every documented error code, rate limiting (with a fake clock), key loading, challenge JWTs (with a stubbed Turnstile verifier), SSE event ordering, and the reaper.
- The MCP server has tests using the MCP SDK's in-memory client for every tool, pagination round-trips, and the auth refusal.
- The SDK has Vitest tests with `msw` mocking the API from the OpenAPI examples.
- Property tests (Hypothesis) for the chunker (never splits a table or fence; chunks concatenate to the original), the frontmatter serializer (round-trips), the SSRF guard (random IPs classified correctly), and the archive walker (bomb limits hold for generated archives).

#### 4.14.2 Golden fixtures with thresholds

`fixtures/` holds the corpus (provenance rules in 4.14.7). Layout:

```
fixtures/
  manifest.yaml            # every fixture: path, source_type, license, origin, expected engine, thresholds
  docs/                    # pdf, docx, pptx, xlsx, odt, epub, ipynb, ...
  web/                     # saved HTML with the original URL noted (synthetic or CC-licensed)
  media/                   # short wav/mp3/mp4 (synthetic TTS or CC0), with reference transcripts
  images/                  # screenshots, charts, handwriting, receipts (synthetic), with reference text
  chat/                    # Slack/Discord/WhatsApp export samples (synthetic)
  social/                  # recorded JSON responses for Reddit/HN/Bluesky adapters (synthetic ids)
  code/                    # small repos
  email/                   # eml, mbox, msg (synthetic)
  data/                    # csv, json, parquet, sqlite
  security/                # zip bombs, malformed pdfs, oversized headers, SSRF URL lists
  extension/               # synthetic platform pages for the extension tests
  expected/<fixture-id>/{full,compact,rag,agent}.md + sidecar.json
```

The fixture runner (`ezmd fixtures run [--update] [--only ID]`) converts every fixture with every profile and compares against `expected/` using per-fixture thresholds from `manifest.yaml`:

- `exact: true` for deterministic converters (text, data, code, email, chat, social): byte-identical body required; the frontmatter `fetched` and `content_hash` are normalized.
- `structure_f1 >= 0.90` for document converters: headings, tables, and lists are extracted from both outputs and compared as sets with F1; `text_similarity >= 0.97` by normalized token overlap.
- `wer <= X` for media fixtures: WER against the reference transcript, with per-fixture X (e.g. 0.12 for clean TTS, 0.30 for noisy); segment timestamps within 1 s; speaker count within 1 when diarization is on.
- `cer <= X` for OCR fixtures.
- `warnings_contain: [codes]` for fixtures designed to trigger warnings (a PDF with two image-only pages must produce `pages_without_text: [3, 4]`). This is the test that enforces "no silent loss".
- `max_seconds` per fixture, measured and compared to a budget with 50% headroom; regressions beyond the budget fail the nightly run and warn on PRs.

`--update` rewrites `expected/` and must be paired with a human-readable diff in the PR; CI refuses a PR that changes `expected/` without a `fixture-update` label and a CHANGELOG entry. The nightly run (4.15.5) uploads a scorecard JSON that the docs site renders as the converter matrix badges.

#### 4.14.3 Integration (compose in CI)

A workflow job starts `deploy/docker-compose.yml` (core profile) on the runner with `EZMD_QUEUE=rq`, waits for `/healthz`, then runs `tests/integration/` which: converts the smoke corpus (one fixture per source family, 15 files) through the REST API using the Python client and the TS SDK; streams SSE and asserts stage order; downloads each format; exercises rate limiting (21st request in 60 s gets 429 with headers); verifies the reaper deletes a job after `EZMD_RETENTION_HOURS=0.01`; verifies `backup.sh`/`restore.sh`; runs the MCP server in remote mode against the stack; verifies that the worker cannot reach `redis:6379` or `169.254.169.254` through a fetched URL; and confirms that every container is non-root and read-only via `docker inspect`. Weekly, the same job runs with `--profile media` on a larger runner and converts the media smoke fixtures.

#### 4.14.4 Load test

`tests/load/k6-convert.js` (k6, run on merge to main against the compose stack, and manually against staging before Phase 4 launch):

```js
import http from "k6/http";
import { check, sleep } from "k6";
import { Trend } from "k6/metrics";

const jobWait = new Trend("job_wait_seconds", true);
const jobTotal = new Trend("job_total_seconds", true);

export const options = {
  scenarios: {
    docs:  { executor: "constant-arrival-rate", rate: 20, timeUnit: "1m", duration: "10m", preAllocatedVUs: 10, exec: "docs" },
    web:   { executor: "constant-arrival-rate", rate: 60, timeUnit: "1m", duration: "10m", preAllocatedVUs: 20, exec: "web" },
    burst: { executor: "ramping-arrival-rate", startRate: 0, timeUnit: "1s",
             stages: [{ target: 30, duration: "30s" }, { target: 0, duration: "30s" }],
             preAllocatedVUs: 50, exec: "anonWeb", startTime: "5m" },
  },
  thresholds: {
    "http_req_duration{name:submit}": ["p(95)<800"],
    "http_req_failed{name:submit}": ["rate<0.02"],
    "job_wait_seconds": ["p(95)<60"],
    "job_total_seconds{kind:web}": ["p(95)<15"],
    "job_total_seconds{kind:docs}": ["p(95)<120"],
    "http_reqs{status:429}": ["count>0"],   // the anonymous burst must trip rate limiting
  },
};

const BASE = __ENV.EZMD_URL || "http://localhost:8080";
const KEY = __ENV.EZMD_KEY || "";
const pdf = open("../../fixtures/docs/ten-pages.pdf", "b");

function authHeaders(extra) {
  const h = Object.assign({}, extra || {});
  if (KEY) h["Authorization"] = `Bearer ${KEY}`;
  return h;
}

function submitAndWait(body, headers, kind) {
  const t0 = Date.now();
  const r = http.post(`${BASE}/v1/convert`, body, { headers, tags: { name: "submit", kind } });
  if (r.status === 429) return;                     // expected for the burst scenario
  if (!check(r, { submitted: (x) => x.status === 202 })) return;
  const id = r.json("id");
  let status = "queued";
  let started = null;
  for (let i = 0; i < 180 && status !== "done" && status !== "failed"; i++) {
    sleep(1);
    const j = http.get(`${BASE}/v1/jobs/${id}`, { headers, tags: { name: "poll", kind } });
    status = j.json("status");
    if (!started && status === "running") started = Date.now();
  }
  if (started) jobWait.add((started - t0) / 1000, { kind });
  jobTotal.add((Date.now() - t0) / 1000, { kind });
  check(null, { done: () => status === "done" });
}

export function docs() {
  const fd = { file: http.file(pdf, "ten-pages.pdf", "application/pdf"), profile: "compact" };
  submitAndWait(fd, authHeaders(), "docs");
}

export function web() {
  const body = JSON.stringify({ url: `${BASE}/fixtures/web/article.html`, profile: "compact" });
  submitAndWait(body, authHeaders({ "Content-Type": "application/json" }), "web");
}

export function anonWeb() {
  // No key, no challenge JWT: exercises the anonymous limiter. Set EZMD_TURNSTILE_REQUIRED_FOR_FETCH=false in the test stack.
  const body = JSON.stringify({ url: `${BASE}/fixtures/web/article.html`, profile: "compact" });
  submitAndWait(body, { "Content-Type": "application/json" }, "web");
}
```

The API serves `fixtures/web/*` at `/fixtures/` only when `EZMD_SERVE_FIXTURES=true` (test mode). Targets: on the 8-core box, docs at 20 per minute and web at 60 per minute sustain with p95 submit under 800 ms and p95 queue wait under 60 s; the burst trips 429s and the API's p95 stays under 1 s throughout (the limiter must be cheap).

#### 4.14.5 Security tests

`tests/security/`, run on every PR (fast ones) and in integration (network ones):

1. SSRF: a table of 60 URLs (loopback in every notation, `0.0.0.0`, decimal and octal IPs, IPv6 mapped, link-local, CGNAT, `localhost` variants, DNS names resolving to private IPs via a test resolver, redirects from public to private, `file://`, `gopher://`, ports 6379 and 5432 on public hosts) must all be refused with `fetch_refused_private_network` or `fetch_refused_scheme`, and the integration variant confirms Squid also denies them.
2. Zip bombs: a 42.zip-style nested archive, a single-entry 10 GB zero file, a 100,000-entry zip, a tar with `../../etc/passwd` and absolute paths, a symlink loop: each must terminate within 10 s with the expected warning and under 512 MB RSS.
3. Malformed PDFs: fuzzed samples from the `security/` fixtures (generated with a PDF mutator over the fixture corpus; 200 files committed), each converted in the subprocess with limits: no worker crash, each produces either output or `warning: engine_failed` with a stub.
4. Oversized upload: a streaming 600 MB upload must be rejected at the cap with 413 before the body is fully read (assert elapsed time and no temp file left).
5. Rate limiting: 21st request in a window gets 429; per-IP concurrency 1 enforced; JWT replay beyond the use count rejected; expired JWT rejected; key with `ips` restriction rejected from another IP.
6. Injection: the `agent` profile wraps content in a fence whose tag includes a per-job random salt; a fixture containing a fake closing tag must not close the fence (the salt makes it unguessable; the test checks the real close tag is distinct).
7. Headers: CSP, HSTS, nosniff present; `Server` header removed; `/metrics` and `/admin` 404 from the public side.
8. Secrets in subprocess env: converter subprocesses see no `EZMD_*` secret variables.
9. Path traversal in MCP `convert_file` and in `ezmd batch --out`.
10. Dependency gates (4.15.3) count as security tests.

#### 4.14.6 Browser tests

Playwright in `apps/web/tests/` against the compose stack (or the inline server in PR CI): paste URL and convert; drop three files; paste image; switch profile without a new job; download each format; warnings panel suggestions; history persistence and clearing; dark mode toggle; keyboard-only flow; axe-core scan; no third-party requests; share-target flow (service worker intercept with a synthetic POST); and the in-browser Whisper path on a 10-second fixture (Chromium with WebGPU flags, skipped if unavailable). Extension tests use Playwright's persistent context with the unpacked extension against the `fixtures/extension/` pages. Mobile viewport (iPhone 13) runs the core flow.

#### 4.14.7 Fixture provenance rules

Written in `fixtures/README.md` and enforced by a CI check over `manifest.yaml`:

1. Every fixture has `origin` (one of `synthetic`, `cc0`, `cc-by`, `cc-by-sa`, `apache`, `mit`, `public-domain`, `own-work`) and `source` (a URL or "generated by `fixtures/gen/<script>`"). CC-BY and CC-BY-SA fixtures carry the attribution in `manifest.yaml` and in a `CREDITS.md` the docs render.
2. No fixture may contain commercial media, platform content (no real YouTube, TikTok, Instagram, X material, even short), copyrighted books or articles, or real personal data. Social adapter fixtures are recorded responses with ids, names, and text replaced by generated values.
3. Media fixtures are generated with open TTS (Piper, MIT) from public-domain or synthetic text, or are CC0 recordings (e.g. LibriVox excerpts, which are public domain, with the reader credited). Noise is added synthetically.
4. Images are rendered from synthetic documents or drawn with scripts; handwriting fixtures come from CC-licensed datasets with their license noted, or from the owner's own hand.
5. Chat exports are generated by `fixtures/gen/chat.py` from a seed with fake names and timestamps.
6. The CI check fails if a fixture lacks `origin`, if `origin` is not on the list, or if a file in `fixtures/` is not in the manifest.
7. Fixtures over 5 MB are stored with Git LFS; the total corpus stays under 500 MB.

### 4.15 CI workflows

Phase: 0 (ci.yml, licenses), 1 (images, release), 2 (nightly fixtures), ongoing (Renovate). All workflows pin actions by SHA in the real repo (the YAML below uses tags for readability; the agent must replace each `@vN` with `@<sha> # vN` before committing, and Renovate keeps them current). `OWNER` is replaced by the GitHub owner.

#### 4.15.1 `.github/workflows/ci.yml`

```yaml
name: ci
on:
  pull_request:
  push:
    branches: [main]
concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: true
permissions:
  contents: read
env:
  UV_CACHE_DIR: /tmp/.uv-cache
  PNPM_VERSION: "9"
jobs:
  python:
    name: python ${{ matrix.os }} / ${{ matrix.python }}
    runs-on: ${{ matrix.os }}
    strategy:
      fail-fast: false
      matrix:
        os: [ubuntu-24.04, ubuntu-24.04-arm, macos-14, windows-2022]
        python: ["3.12"]
        include:
          - os: ubuntu-24.04
            python: "3.13"
    steps:
      - uses: actions/checkout@v4
        with: { lfs: true }
      - uses: astral-sh/setup-uv@v5
        with: { enable-cache: true, cache-dependency-glob: "uv.lock" }
      - uses: actions/setup-python@v5
        with: { python-version: "${{ matrix.python }}" }
      - name: system deps
        if: runner.os == 'Linux'
        run: sudo apt-get update -q && sudo apt-get install -y -q ffmpeg pandoc libmagic1
      - name: system deps (macos)
        if: runner.os == 'macOS'
        run: brew install ffmpeg pandoc libmagic
      - name: system deps (windows)
        if: runner.os == 'Windows'
        run: choco install -y ffmpeg pandoc
      - run: uv sync --all-packages --extra docs --extra ocr --extra server --extra mcp --extra media
      - run: uv run ruff check . && uv run ruff format --check .
      - run: uv run mypy --strict packages/core packages/mcp apps/api apps/fetch-node
      - name: import time budget
        if: runner.os == 'Linux'
        run: uv run python -X importtime -c "import ezmd" 2> /tmp/imp.txt && uv run python scripts/check_import_time.py /tmp/imp.txt 400
      - run: uv run pytest -q -m "not integration and not media" --cov --cov-report=xml --cov-fail-under=80
      - name: media unit tests (small models)
        if: runner.os == 'Linux' && matrix.os == 'ubuntu-24.04'
        run: uv run ezmd models pull whisper-tiny silero-vad && uv run pytest -q -m media
      - name: fixtures (fast tier)
        if: runner.os == 'Linux'
        run: uv run ezmd fixtures run --tier fast --report /tmp/fixtures.json
      - uses: actions/upload-artifact@v4
        if: always()
        with: { name: fixtures-${{ matrix.os }}, path: /tmp/fixtures.json, if-no-files-found: ignore }
      - name: env example drift
        run: uv run python scripts/check_env_example.py deploy/.env.example
      - name: openapi export and lint
        if: runner.os == 'Linux'
        run: |
          uv run python scripts/export_openapi.py docs/api/openapi.json
          git diff --exit-code docs/api/openapi.json || (echo "openapi.json out of date; run scripts/export_openapi.py" && exit 1)
          npx --yes @stoplight/spectral-cli@6 lint docs/api/openapi.json --ruleset .spectral.yaml --fail-severity error

  typescript:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v4
        with: { version: "${{ env.PNPM_VERSION }}" }
      - uses: actions/setup-node@v4
        with: { node-version: "20", cache: pnpm }
      - run: pnpm install --frozen-lockfile
      - run: pnpm -r lint && pnpm -r typecheck
      - run: pnpm -r test
      - run: pnpm -r build
      - name: sdk types match openapi
        run: pnpm -F @ezmd/sdk gen && git diff --exit-code packages/sdk-ts/src/generated
      - name: bundle size
        run: pnpm -F @ezmd/sdk size && pnpm -F web size
      - name: extension lint
        run: pnpm -F extension lint:webext
      - name: mcp server.json
        run: npx --yes @modelcontextprotocol/publisher@latest validate packages/mcp/server.json || true

  licenses:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv sync --all-packages --all-extras
      - name: python license allowlist
        run: uv run pip-licenses --format=json --with-license-file --no-license-path > /tmp/pylic.json && uv run python scripts/check_licenses.py /tmp/pylic.json scripts/license-allowlist.toml
      - uses: pnpm/action-setup@v4
        with: { version: "${{ env.PNPM_VERSION }}" }
      - uses: actions/setup-node@v4
        with: { node-version: "20", cache: pnpm }
      - run: pnpm install --frozen-lockfile
      - name: node license allowlist
        run: npx --yes license-checker-rseidelsohn --json --production > /tmp/nodelic.json && uv run python scripts/check_licenses.py /tmp/nodelic.json scripts/license-allowlist.toml --node
      - name: model license allowlist
        run: uv run python scripts/check_model_licenses.py packages/core/src/ezmd/models/registry.toml scripts/license-allowlist.toml
      - name: fixture provenance
        run: uv run python scripts/check_fixtures.py fixtures/manifest.yaml

  audit:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv sync --all-packages --all-extras
      - run: uv run pip-audit --strict --ignore-vuln-file .pip-audit-ignore.toml
      - uses: pnpm/action-setup@v4
        with: { version: "${{ env.PNPM_VERSION }}" }
      - uses: actions/setup-node@v4
        with: { node-version: "20", cache: pnpm }
      - run: pnpm install --frozen-lockfile
      - run: pnpm audit --audit-level=high --prod

  images:
    needs: [python, typescript]
    runs-on: ubuntu-24.04
    permissions:
      contents: read
      packages: write
      id-token: write
      security-events: write
    strategy:
      matrix:
        target: [api, worker, worker-media, fetch-node]
    steps:
      - uses: actions/checkout@v4
      - uses: docker/setup-qemu-action@v3
      - uses: docker/setup-buildx-action@v3
      - uses: docker/login-action@v3
        if: github.event_name == 'push'
        with: { registry: ghcr.io, username: "${{ github.actor }}", password: "${{ secrets.GITHUB_TOKEN }}" }
      - id: meta
        uses: docker/metadata-action@v5
        with:
          images: ghcr.io/${{ github.repository }}
          flavor: |
            suffix=${{ matrix.target == 'api' && '' || format('-{0}', matrix.target) }}
          tags: |
            type=sha
            type=ref,event=branch
            type=raw,value=edge,enable={{is_default_branch}}
      - uses: docker/build-push-action@v6
        with:
          context: .
          target: ${{ matrix.target }}
          platforms: ${{ matrix.target == 'fetch-node' && 'linux/amd64,linux/arm64' || 'linux/amd64,linux/arm64' }}
          push: ${{ github.event_name == 'push' }}
          load: ${{ github.event_name != 'push' }}
          tags: ${{ steps.meta.outputs.tags }}
          labels: |
            ${{ steps.meta.outputs.labels }}
            io.modelcontextprotocol.server.name=io.github.OWNER/ezmd
            org.opencontainers.image.licenses=Apache-2.0
          cache-from: type=gha,scope=${{ matrix.target }}
          cache-to: type=gha,mode=max,scope=${{ matrix.target }}
          provenance: true
          sbom: true
      - name: trivy
        uses: aquasecurity/trivy-action@0.28.0
        with:
          image-ref: ghcr.io/${{ github.repository }}${{ matrix.target == 'api' && '' || format('-{0}', matrix.target) }}:sha-${{ github.sha }}
          format: sarif
          output: trivy-${{ matrix.target }}.sarif
          severity: HIGH,CRITICAL
          ignore-unfixed: true
          exit-code: "1"
          trivyignores: .trivyignore
      - uses: github/codeql-action/upload-sarif@v3
        if: always()
        with: { sarif_file: trivy-${{ matrix.target }}.sarif }
      - name: sbom
        uses: anchore/sbom-action@v0
        with:
          image: ghcr.io/${{ github.repository }}${{ matrix.target == 'api' && '' || format('-{0}', matrix.target) }}:sha-${{ github.sha }}
          format: cyclonedx-json
          artifact-name: sbom-${{ matrix.target }}.cdx.json
      - name: sign
        if: github.event_name == 'push'
        run: |
          curl -sSfL https://github.com/sigstore/cosign/releases/download/v2.4.1/cosign-linux-amd64 -o /usr/local/bin/cosign && chmod +x /usr/local/bin/cosign
          cosign sign --yes ghcr.io/${{ github.repository }}${{ matrix.target == 'api' && '' || format('-{0}', matrix.target) }}@${{ steps.build.outputs.digest }}

  integration:
    needs: [images]
    if: github.event_name == 'push'
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v4
        with: { lfs: true }
      - uses: astral-sh/setup-uv@v5
      - run: uv sync --all-packages --extra server
      - name: compose up
        working-directory: deploy
        run: |
          cp .env.example .env
          sed -i 's#^EZMD_DOMAIN=.*#EZMD_DOMAIN=localhost#; s#^EZMD_VERSION=.*#EZMD_VERSION=sha-${{ github.sha }}#; s#^EZMD_RETENTION_HOURS=.*#EZMD_RETENTION_HOURS=0.02#; s#^EZMD_SECRET_KEY=.*#EZMD_SECRET_KEY=$(openssl rand -hex 32)#' .env
          echo "EZMD_SERVE_FIXTURES=true" >> .env
          docker compose up -d --wait --wait-timeout 300
      - run: uv run pytest -q -m integration tests/integration --base-url https://localhost --insecure
      - name: security (network)
        run: uv run pytest -q tests/security -m network --base-url https://localhost --insecure
      - name: playwright
        run: |
          corepack enable && pnpm install --frozen-lockfile
          pnpm -F web exec playwright install --with-deps chromium firefox
          pnpm -F web test:e2e -- --base-url https://localhost
      - name: load (short)
        run: |
          curl -sSfL https://github.com/grafana/k6/releases/download/v0.54.0/k6-v0.54.0-linux-amd64.tar.gz | tar xz --strip-components=1
          EZMD_URL=https://localhost EZMD_KEY=$(cat deploy/ci-key.txt) ./k6 run --insecure-skip-tls-verify -e DURATION=2m tests/load/k6-convert.js
      - name: compose logs
        if: failure()
        working-directory: deploy
        run: docker compose logs --no-color > /tmp/compose.log; docker compose ps
      - uses: actions/upload-artifact@v4
        if: failure()
        with: { name: compose-logs, path: /tmp/compose.log }
```

Notes: `.pip-audit-ignore.toml` and `.trivyignore` carry only entries with an expiry comment and an issue link; a weekly check (`scripts/check_ignores_expiry.py` in the nightly workflow) fails when one expires. The `deploy/ci-key.txt` key is created by a step that writes `keys.json` before `compose up` with a test key; the agent adds that step. The `id: build` must be set on the build-push step for `steps.build.outputs.digest` to resolve.

#### 4.15.2 License allowlist (`scripts/license-allowlist.toml` and `scripts/check_licenses.py`)

```toml
# SPDX ids accepted in the default dependency tree (core and all extras except nonfree)
[allow]
licenses = [
  "Apache-2.0", "MIT", "BSD-2-Clause", "BSD-3-Clause", "ISC", "PSF-2.0", "Python-2.0",
  "MPL-2.0", "Unlicense", "0BSD", "CC0-1.0", "Zlib", "BSL-1.0", "HPND", "LGPL-2.1-only",
  "LGPL-2.1-or-later", "LGPL-3.0-only", "LGPL-3.0-or-later",   # dynamic linking only; see notes
]
# Model weight licenses accepted for default pulls
model_licenses = ["Apache-2.0", "MIT", "CC-BY-4.0", "CC0-1.0", "BSD-3-Clause"]

[deny]
licenses = ["GPL-2.0-only", "GPL-2.0-or-later", "GPL-3.0-only", "GPL-3.0-or-later", "AGPL-3.0-only",
            "AGPL-3.0-or-later", "SSPL-1.0", "CC-BY-NC-4.0", "CC-BY-NC-SA-4.0", "OpenRAIL-M", "BigScience-OpenRAIL-M",
            "Commons-Clause", "Elastic-2.0", "BUSL-1.1", "MinerU-License"]

# Packages allowed only inside the `nonfree` extra; the checker verifies they are not in any other extra's tree
[nonfree]
packages = ["pymupdf", "pymupdf4llm", "extract-msg", "olefile"]

# Known mislabeled packages: declared license text to accept as the given SPDX
[overrides]
"docutils" = "BSD-2-Clause"        # dual licensed; using BSD terms
"certifi" = "MPL-2.0"
"pillow" = "HPND"
"typing-extensions" = "PSF-2.0"

[notes]
lgpl = "LGPL deps are permitted when used as separately installed shared libraries or Python packages without modification; ship no static LGPL linking."
```

`check_licenses.py` reads the pip-licenses or license-checker JSON, normalizes each package's license to SPDX (handles "BSD License", "Apache Software License", "MIT License" strings and the `overrides` table), fails on any package in `deny`, fails on any license not in `allow` (prints the package, version, and license text snippet, so the fix is a decision and not a search), and for the Python tree verifies `nonfree` packages do not appear when installed with `uv sync --all-extras --no-extra nonfree`. `check_model_licenses.py` does the same over `registry.toml`, fails on any default-pull model whose license is not in `model_licenses`, and requires `gated = true` plus a `license_url` for anything else. Pandoc (GPL) is invoked as a separate executable and is not a Python dependency; the docs state this and the allowlist does not cover binaries, which are listed with their licenses in `docs/licenses.md`.

#### 4.15.3 Nightly fixtures (`.github/workflows/nightly.yml`)

```yaml
name: nightly
on:
  schedule: [{ cron: "23 4 * * *" }]
  workflow_dispatch:
permissions:
  contents: write
  issues: write
jobs:
  fixtures-full:
    runs-on: ubuntu-24.04
    timeout-minutes: 180
    steps:
      - uses: actions/checkout@v4
        with: { lfs: true }
      - uses: astral-sh/setup-uv@v5
      - run: sudo apt-get update -q && sudo apt-get install -y -q ffmpeg pandoc libmagic1
      - run: uv sync --all-packages --all-extras --no-extra nonfree
      - run: uv run ezmd models pull --all-for-extras
      - run: uv run ezmd fixtures run --tier full --report /tmp/fixtures.json --timings
      - name: compare against baseline and publish scorecard
        run: |
          uv run python scripts/fixture_scorecard.py /tmp/fixtures.json docs/data/scorecard.json --baseline docs/data/scorecard.json --fail-on-regression
      - name: commit scorecard
        if: success()
        run: |
          git config user.name ezmd-bot && git config user.email bot@users.noreply.github.com
          git add docs/data/scorecard.json && git commit -m "nightly: fixture scorecard $(date -u +%F)" || true
          git push
      - name: open issue on regression
        if: failure()
        uses: actions/github-script@v7
        with:
          script: |
            const fs = require('fs');
            const body = fs.existsSync('/tmp/regression.md') ? fs.readFileSync('/tmp/regression.md','utf8') : 'See workflow run.';
            await github.rest.issues.create({ owner: context.repo.owner, repo: context.repo.repo,
              title: `Nightly fixture regression ${new Date().toISOString().slice(0,10)}`, body, labels: ['regression','fixtures'] });
  ignores-expiry:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv run python scripts/check_ignores_expiry.py .pip-audit-ignore.toml .trivyignore SECURITY-EXCEPTIONS.md
  ytdlp-canary:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv sync --all-packages --extra fetch
      - name: check yt-dlp release lag and extractor self-test
        run: uv run python scripts/ytdlp_canary.py --max-lag-days 14
```

`ytdlp_canary.py` compares the pinned yt-dlp version with the latest release and runs yt-dlp's built-in extractor unit tests for the adapters ezmd uses (no network to platforms; the canary does not fetch real videos). A lag over 14 days opens a Renovate-style PR by bumping the pin.

#### 4.15.4 Release (`.github/workflows/release.yml`)

```yaml
name: release
on:
  push:
    tags: ["v*.*.*"]
permissions:
  contents: write
  packages: write
  id-token: write
jobs:
  verify:
    uses: ./.github/workflows/ci.yml
  pypi:
    needs: verify
    runs-on: ubuntu-24.04
    environment: release
    strategy:
      matrix:
        package: [packages/core, packages/mcp]
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv build --package $(basename ${{ matrix.package }}) --out-dir dist/
      - uses: pypa/gh-action-pypi-publish@release/v1
        with: { packages-dir: dist/ }      # trusted publishing; no token
  npm:
    needs: verify
    runs-on: ubuntu-24.04
    environment: release
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v4
        with: { version: "9" }
      - uses: actions/setup-node@v4
        with: { node-version: "20", registry-url: "https://registry.npmjs.org", cache: pnpm }
      - run: pnpm install --frozen-lockfile && pnpm -F @ezmd/sdk build
      - run: pnpm -F @ezmd/sdk publish --provenance --access public --no-git-checks
        env: { NODE_AUTH_TOKEN: "${{ secrets.NPM_TOKEN }}" }   # replace with npm trusted publishing once enabled on the package
  images:
    needs: verify
    runs-on: ubuntu-24.04
    strategy:
      matrix:
        target: [api, worker, worker-media, worker-media-cuda, fetch-node]
    steps:
      - uses: actions/checkout@v4
      - uses: docker/setup-qemu-action@v3
      - uses: docker/setup-buildx-action@v3
      - uses: docker/login-action@v3
        with: { registry: ghcr.io, username: "${{ github.actor }}", password: "${{ secrets.GITHUB_TOKEN }}" }
      - id: meta
        uses: docker/metadata-action@v5
        with:
          images: ghcr.io/${{ github.repository }}
          flavor: suffix=${{ matrix.target == 'api' && '' || format('-{0}', matrix.target) }}
          tags: |
            type=semver,pattern={{version}}
            type=semver,pattern={{major}}.{{minor}}
            type=raw,value=latest
      - id: build
        uses: docker/build-push-action@v6
        with:
          context: .
          target: ${{ matrix.target }}
          platforms: ${{ matrix.target == 'worker-media-cuda' && 'linux/amd64' || 'linux/amd64,linux/arm64' }}
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          labels: |
            ${{ steps.meta.outputs.labels }}
            io.modelcontextprotocol.server.name=io.github.OWNER/ezmd
          provenance: true
          sbom: true
      - run: |
          curl -sSfL https://github.com/sigstore/cosign/releases/download/v2.4.1/cosign-linux-amd64 -o /usr/local/bin/cosign && chmod +x /usr/local/bin/cosign
          cosign sign --yes ghcr.io/${{ github.repository }}${{ matrix.target == 'api' && '' || format('-{0}', matrix.target) }}@${{ steps.build.outputs.digest }}
  extension:
    needs: verify
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v4
        with: { version: "9" }
      - uses: actions/setup-node@v4
        with: { node-version: "20", cache: pnpm }
      - run: pnpm install --frozen-lockfile && pnpm -F extension build
      - run: cd apps/extension/dist && zip -r ../../../ezmd-extension-chrome-${{ github.ref_name }}.zip chrome && zip -r ../../../ezmd-extension-firefox-${{ github.ref_name }}.zip firefox
      - uses: actions/upload-artifact@v4
        with: { name: extension, path: ezmd-extension-*.zip }
  mcp-registry:
    needs: [pypi]
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v4
      - run: |
          curl -sSfL https://github.com/modelcontextprotocol/registry/releases/latest/download/mcp-publisher_linux_amd64.tar.gz | tar xz
          sed -i "s/\"version\": \".*\"/\"version\": \"${GITHUB_REF_NAME#v}\"/" packages/mcp/server.json
          ./mcp-publisher login github-oidc
          ./mcp-publisher publish packages/mcp/server.json
  github-release:
    needs: [pypi, npm, images, extension]
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }
      - uses: actions/download-artifact@v4
        with: { name: extension, path: dist/ }
      - name: changelog section
        run: uv run python scripts/changelog_section.py CHANGELOG.md "${GITHUB_REF_NAME#v}" > /tmp/notes.md || awk '/^## /{n++} n==1' CHANGELOG.md > /tmp/notes.md
      - uses: softprops/action-gh-release@v2
        with:
          body_path: /tmp/notes.md
          files: dist/*
          generate_release_notes: true
```

Release procedure (`docs/contributing/releasing.md`): bump versions in `packages/core/pyproject.toml`, `packages/mcp/pyproject.toml`, `packages/sdk-ts/package.json`, `apps/extension/manifest.json` with `scripts/bump_version.py X.Y.Z` (which also moves the CHANGELOG "Unreleased" section under the new version with the date), commit, tag `vX.Y.Z`, push the tag. Trusted publishing is configured on PyPI for both packages pointing at this workflow and the `release` environment; the environment requires the owner's approval for the first release of each major. Versions follow SemVer; the API path `/v1` changes only on a major.

#### 4.15.5 Dependency updates (`.github/renovate.json`)

```json
{
  "$schema": "https://docs.renovatebot.com/renovate-schema.json",
  "extends": ["config:recommended", ":semanticCommits", "helpers:pinGitHubActionDigests", "docker:pinDigests"],
  "schedule": ["before 6am on monday"],
  "timezone": "America/Chicago",
  "labels": ["dependencies"],
  "prConcurrentLimit": 6,
  "lockFileMaintenance": { "enabled": true, "schedule": ["before 6am on monday"] },
  "packageRules": [
    { "matchManagers": ["pep621", "pip_requirements"], "groupName": "python deps (minor/patch)", "matchUpdateTypes": ["minor", "patch"], "automerge": true, "automergeType": "pr", "platformAutomerge": true },
    { "matchManagers": ["npm"], "groupName": "node deps (minor/patch)", "matchUpdateTypes": ["minor", "patch"], "automerge": true, "platformAutomerge": true },
    { "matchManagers": ["github-actions"], "groupName": "github actions", "automerge": true, "platformAutomerge": true },
    { "matchManagers": ["dockerfile", "docker-compose"], "groupName": "base images", "automerge": true, "matchUpdateTypes": ["patch", "digest"] },
    { "matchUpdateTypes": ["major"], "automerge": false, "labels": ["dependencies", "major"] },
    { "matchPackageNames": ["yt-dlp"], "schedule": ["at any time"], "automerge": true, "labels": ["dependencies", "yt-dlp"] },
    { "matchPackageNames": ["docling", "faster-whisper", "ctranslate2", "torch", "transformers"], "automerge": false, "labels": ["dependencies", "engine"], "prBodyNotes": ["Engine update: run `ezmd fixtures run --tier full` locally and attach the scorecard diff."] }
  ],
  "vulnerabilityAlerts": { "enabled": true, "labels": ["security"], "schedule": ["at any time"], "automerge": true }
}
```

Auto-merge is gated on the full `ci.yml` passing (branch protection requires the `python`, `typescript`, `licenses`, `audit`, and `images` checks). Engine updates never auto-merge because they can shift fixture scores; the nightly run on the Renovate branch (enable Renovate's `"branchConcurrentLimit"` default and run `nightly.yml` on `workflow_dispatch` for engine PRs via a comment command documented in CONTRIBUTING) decides.

### 4.16 Documentation plan

Phase: 1 for README, CONTRIBUTING, SECURITY, CODE_OF_CONDUCT, and the docs skeleton; each later phase fills its pages. Docs site: MkDocs Material in `docs/`, built by `.github/workflows/docs.yml` on push to `main` and deployed to GitHub Pages at `docs.<domain>` (CNAME) with `mike` for versioned docs from the first tagged release. Plugins: `mkdocs-material`, `mkdocs-swagger-ui-tag`, `mkdocs-macros-plugin` (reads `docs/data/scorecard.json` for the converter matrix), `mkdocs-git-revision-date-localized-plugin`, `mkdocs-redirects`. Search is Material's built-in (client-side; no third-party search).

#### 4.16.1 README.md (root)

In this order, nothing else above the fold:

1. One-line description: "Convert anything (documents, web pages, video, audio, chat exports, code) to clean Markdown for AI tools. No silent loss. Apache-2.0."
2. Badges: PyPI version, npm version, GHCR image, CI status, nightly fixture score (from the scorecard JSON via shields endpoint), license, MCP Registry.
3. Demo GIF (recorded with `vhs` from a `.tape` file in `docs/assets/demo.tape` so it is reproducible): paste a URL in the CLI, see progress, see Markdown with a warning line.
4. "Try it": the public instance URL, with the retention sentence.
5. Quickstart: `uvx ezmd convert https://example.com`, `pip install ezmd`, `ezmd convert report.pdf --profile compact`, `ezmd batch ./docs --out ./md`.
6. Self-host one-liner: the `bootstrap.sh` curl command, and the three-line `docker compose` alternative.
7. Library usage: the five-line Python example with `on_progress` and warnings.
8. MCP config: the Claude Desktop JSON and the `claude mcp add` line.
9. What it converts: a compact table of families with a link to the matrix.
10. Output profiles: four bullets.
11. Why ezmd: five bullets mirroring the differentiators (no silent loss, permissive license, one box, output profiles, client-side fetch).
12. Browser extension and mobile: two lines with links.
13. Project status: link to STATUS.md and ROADMAP.md.
14. License (Apache-2.0), with the note that optional `nonfree` extras and some model weights carry their own licenses, listed in `docs/licenses.md`.

#### 4.16.2 Docs site structure (`docs/mkdocs.yml` nav)

- Getting started: Install (pip, uvx, Docker, extras matrix, system deps per OS), First conversion, Output profiles explained, Configuration (config.toml and env vars; the env table is generated from `Settings` by `scripts/gen_env_docs.py`).
- Self-host: Docker Compose (core, media, GPU, public overlay), bootstrap script, Upgrading and backups, Reverse proxy alternatives (Traefik, nginx snippets), Air-gapped install (model pulls offline via `ezmd models export`), Challenge options (Turnstile, ALTCHA, Anubis), API keys and limits, Monitoring, Hardening checklist.
- API: REST reference (Swagger UI from `openapi.json`), Jobs and SSE, Authentication and limits, Errors and warning codes (generated table from `packages/core` warning registry: code, severity, meaning, suggested action), Fetch-node protocol.
- Converters: Matrix with status badges (per family and format: Stable, Beta, Experimental, Planned; engine; extras needed; provenance features such as page markers, tracked changes, speaker labels; latest nightly scores), one page per family with what is preserved, known limitations, and the warnings it emits.
- Output format spec: frontmatter schema, body conventions (headings, tables, images, transcripts, page markers, footnotes), sidecar JSON schema, `rag` chunk format, `agent` fence, stability guarantees across versions.
- Interfaces: CLI reference (generated from typer with `typer docs`), Python library, MCP server, TypeScript SDK, Browser extension, iOS Shortcut and Android share, Obsidian plugin and other integrations.
- Fetch node: what it is, when it is needed, Pi setup, Tailscale ACLs, security properties.
- Operations (public instance): Runbook, Abuse controls, Incident response, Capacity and cost, Sponsor pack.
- Legal: Terms, Privacy, DMCA, Acceptable use, Platform stance, Model and dependency licenses.
- FAQ: "Why did my YouTube link fail?" (platform blocking explained in plain words, with the three fixes: upload the file, use the extension, use the shortcut), "Why is my PDF empty?" (OCR extra), "Is my data stored?", "Can I use this commercially?", "Why not just upload to ChatGPT?", "How do I pick an engine?" (`ezmd shadow-run`), "Why is the first run slow?" (model pull).
- Contributing: Development setup, Monorepo layout, Adding a converter (the registry contract, fixture requirements, warning codes), The council process, Fixture process, Releasing, Code of conduct.
- Changelog, Security policy, Status, Roadmap (rendered from the root files via symlinks or `mkdocs-include-markdown-plugin`).

#### 4.16.3 Root files

- `CHANGELOG.md`: Keep a Changelog format, sections Added, Changed, Fixed, Removed, Security, Operations (the last one for runbook-level changes such as limit changes on the public instance). "Unreleased" at top. Every PR touching behavior adds a line.
- `SECURITY.md`: supported versions (latest minor), how to report (a private GitHub security advisory, or email with a PGP key published in the file), response targets (acknowledge 3 days, fix or mitigation plan 14 days for high, 30 for others), scope (software and the public instance; the public instance's abuse limits are in scope for bypass reports, but volumetric testing against it is not permitted), safe harbor statement, and the link to `SECURITY-EXCEPTIONS.md`.
- `CODE_OF_CONDUCT.md`: Contributor Covenant 2.1 with the enforcement contact.
- `CONTRIBUTING.md`: setup (`uv sync --all-packages --all-extras`, `pnpm install`, `pre-commit install`), branch and PR conventions (conventional commits, one change per PR, CHANGELOG line, tests), the converter contract, and two processes that are specific to this project:
  - The council process: a converter or engine change that could alter output for existing fixtures requires a "council" review, which is a PR template section where the author pastes the fixture scorecard diff, the engine license check output, and answers four questions (what is preserved that was not before, what could be lost, which warnings change, what the token cost impact is). Two approvals are needed for engine swaps, one for converter fixes. The name comes from the practice of asking three reviewers with different persona hats (developer, legal or finance provenance, media) to each check one aspect; the template lists the hats.
  - The fixture process: how to add a fixture (provenance rules, manifest entry, expected outputs generated with `--update`, threshold choice with rationale), how to update expected outputs (label `fixture-update`, diff in PR, CHANGELOG line), how the nightly scorecard works, and the rule that a bug report about silent loss should become a fixture before it becomes a fix.
- `DECISIONS.md`: append-only ADR log; Part 1 starts it; this part adds entries for the extension tooling choice, Turnstile versus ALTCHA default, Origin CA versus ACME, the unsponsored budget ceiling, and the Groq offload trigger.
- `STATUS.md`: format in 4.17.8.
- `ROADMAP.md`: content in 4.17.

---

## D. Roadmap with phases and gates

### 4.17 ROADMAP.md

Write the following as `ROADMAP.md` at the repository root, verbatim in structure (the agent may add tasks but may not remove or reorder gates). Task IDs are `P<phase>-T<nn>`. Each task lists dependencies (`deps`), the acceptance criterion (`done when`), and where in the spec it is defined. Phase 0 is defined in Part 1 and repeated here only as IDs so later phases can depend on them.

#### 4.17.1 Phase 0: Foundation (Part 1)

Goal: a repo that builds, tests, and ships nothing user-visible yet.

| ID | Task | deps | done when |
|---|---|---|---|
| P0-T01 | Monorepo scaffold: `packages/core`, `packages/converters/*`, `packages/mcp`, `packages/sdk-ts`, `apps/*`, `deploy/`, `fixtures/`, `docs/`; uv workspace; pnpm workspace; root `CLAUDE.md`, `DECISIONS.md`, `ROADMAP.md`, `STATUS.md` | none | `uv sync --all-packages` and `pnpm install` succeed on Linux, macOS, Windows |
| P0-T02 | Core types: `Result`, `Warning`, `Provenance`, `Profile`, `Options`, `Progress`; frontmatter schema; sidecar schema; warning code registry with suggested actions | P0-T01 | schema round-trip tests pass; registry has at least the codes named in Parts 1 to 4 |
| P0-T03 | Converter registry and MIME routing with Magika plus libmagic; engine tiers; subprocess runner with rlimits | P0-T02 | a stub converter routes by MIME in tests; subprocess limits verified |
| P0-T04 | Profile renderers `full`, `compact`, `rag`, `agent` over the intermediate representation; chunker; token estimator | P0-T02 | property tests pass; `render` idempotence test passes |
| P0-T05 | Settings class, `.env.example` drift test, config.toml loader | P0-T01 | 4.9.6 drift test passes |
| P0-T06 | CI: `ci.yml` python and typescript jobs, licenses, audit; pre-commit; coverage gate | P0-T01 | green on main |
| P0-T07 | Fixture framework: manifest, runner, thresholds, provenance check; first 10 synthetic fixtures | P0-T04 | `ezmd fixtures run --tier fast` passes |
| P0-T08 | SSRF guard and fetch client with IP pinning | P0-T02 | 4.14.5 item 1 fast tier passes |

Gate G0: all P0 tasks done; CI green on all four OS targets; coverage at or above 80% on core; `STATUS.md` updated.

#### 4.17.2 Phase 1: Permissive core, CLI, library, MCP, UI v1, compose

Goal: `pip install ezmd` converts documents, web, code, email, data, and notebooks with provenance; the four surfaces exist; a self-hoster can run it.

| ID | Task | deps | done when |
|---|---|---|---|
| P1-T01 | Document converters: PDF (Docling default, pypdf fallback), DOCX with tracked changes and comments (Pandoc `--track-changes=all`), PPTX with notes, XLSX with formulas and all sheets, ODF, RTF, EPUB, iWork via Docling | G0 | fixtures per format pass thresholds; `pages_without_text` and `engine_downgraded` warnings verified |
| P1-T02 | Web converter: Trafilatura plus Defuddle-style rules, metadata, numbered link list, hidden-element stripping, injection scan | G0 | web fixtures pass; injection fixture flags without altering text |
| P1-T03 | Code converter: repo and directory packing with Secretlint-style secret scan, tree, per-file tokens, signatures-only mode; GitHub URL fetch | G0 | code fixtures pass; a planted secret is redacted and warned |
| P1-T04 | Email converters: EML, MBOX, recursive attachments; MSG via `nonfree` extra | P1-T01 | email fixtures pass; attachment conversion warnings verified |
| P1-T05 | Data converters: CSV, TSV, JSON, YAML, TOML, XML, Parquet, SQLite with the six-column rule and CSV sidecar | G0 | data fixtures exact-match |
| P1-T06 | Notebook, Markdown passthrough, plain text, archives (zip, tar, 7z) with bomb limits | G0 | archive bomb tests pass |
| P1-T07 | SEC EDGAR via edgartools; sanctioned public APIs stub (Reddit JSON, HN Algolia) behind a `social` family flag (full adapters in P3) | P1-T02 | EDGAR fixture passes |
| P1-T08 | Python library public API (4.3): `convert`, `convert_async`, `convert_many`, `Result` helpers, lazy engine loading, `unload_models` | P1-T01..T06 | 4.3.4 criteria |
| P1-T09 | CLI (4.2): `convert`, `batch`, `serve`, `doctor`, `capabilities`, `version`; config.toml; exit codes; completions | P1-T08 | 4.2.3 criteria |
| P1-T10 | API (Part 3): routes, SSE, SQLite, RQ and inline queue, blobs FS, reaper, keys.json, rate limiting, admin, metrics, OpenAPI annotations | P1-T08 | API tests pass; spectral clean |
| P1-T11 | MCP server (4.4): five tools, pagination, stdio and HTTP, auth, `server.json`, client docs | P1-T08, P1-T10 | 4.4.6 criteria |
| P1-T12 | TS SDK (4.5): generated types, client, Node helper, size gate | P1-T10 | 4.5.3 criteria |
| P1-T13 | Web UI v1 (4.1 steps 1 to 12): input box, progress, result, profiles, downloads, warnings, history, dark mode, accessibility | P1-T10, P1-T12 | 4.1.3 criteria except Whisper and share target |
| P1-T14 | Docker: multi-stage Dockerfile targets `api`, `worker`; compose core profile; Caddyfile; `.env.example`; bootstrap, backup, restore, upgrade scripts | P1-T10 | 4.9.10 criteria for the core profile |
| P1-T15 | Integration workflow (compose in CI), security tests fast and network tiers, Playwright suite | P1-T13, P1-T14 | integration job green |
| P1-T16 | Images workflow with Trivy, SBOM, cosign; release workflow (PyPI trusted publishing, npm, GHCR, GitHub release, MCP registry) | P1-T14 | a `v0.1.0-rc` tag publishes to TestPyPI and GHCR |
| P1-T17 | Docs skeleton: README, CONTRIBUTING with council and fixture process, SECURITY, CODE_OF_CONDUCT, MkDocs site with install, self-host, API, converters matrix (generated), output spec, MCP, CLI, library pages | P1-T09..T13 | docs build with no warnings; every README command runs |
| P1-T18 | `shadow-run` command: convert a user's documents with each available engine and score structure and text similarity against each other, print a table | P1-T01 | runs on the fixture corpus and prints a table |
| P1-T19 | Fixture corpus to at least 80 fixtures across families, with thresholds and CREDITS | P1-T01..T07 | provenance check passes; nightly scorecard produced |

Gate G1: all P1 tasks done; `v0.1.0` released to PyPI, npm, GHCR; fixture pass rate 100% on `exact` fixtures and at or above 95% on threshold fixtures; integration and Playwright green; `uvx ezmd-mcp` works in Claude Desktop (manual check recorded in STATUS.md); docs site live; STATUS.md updated.

#### 4.17.3 Phase 2: Media (ASR, OCR, diarization, in-browser Whisper)

Goal: audio, video files, images, and screen recordings convert locally with speaker labels and sparse timestamps; the public-instance capacity numbers are measured.

| ID | Task | deps | done when |
|---|---|---|---|
| P2-T01 | Model registry (`registry.toml`) with pinned revisions, SHA-256, licenses; `ezmd models pull/list/rm/export`; license gate | G1 | 4.2.2 item 6 criteria; model license check in CI |
| P2-T02 | ASR pipeline: ffmpeg decode to 16 kHz mono, Silero VAD, faster-whisper int8 (CPU) and Parakeet (GPU), hallucination de-loop and blocklist, sentence split, paragraphing by pause and speaker, sparse timestamps, chapters from platform markers or TreeSeg | P2-T01 | media fixtures meet WER thresholds; non-speech fixture produces no hallucinated text |
| P2-T03 | Diarization: pyannote community-1 with midpoint alignment; `exclusive` mode; `DIARIZATION` setting | P2-T02 | speaker-count fixture within tolerance |
| P2-T04 | Transcript template and SRT/VTT output; `segments` in sidecar; `.srt` download in UI | P2-T02 | SRT fixture exact-match |
| P2-T05 | OCR routing: RapidOCR (PP-OCR) CPU default, PaddleOCR-VL on GPU, zxing-cpp barcodes, Florence-2 captions optional, chart-to-table via VLM optional; page-level OCR fallback for PDFs with `pages_without_text` | P2-T01 | OCR fixtures meet CER thresholds; image-only PDF now yields text plus `ocr_confidence_low` where applicable |
| P2-T06 | Lecture and screen-recording fusion: SSIM slide detection, per-slide OCR, ASR alignment to slide intervals | P2-T02, P2-T05 | lecture fixture produces slide headings with timestamps |
| P2-T07 | Hosted ASR backends (Groq, Deepgram) as keyed options with the offload threshold and `diarization_unavailable_offload` warning | P2-T02 | stubbed backend tests pass; capabilities reports `asr_offload` |
| P2-T08 | `worker-media` image and compose media profile; GPU override; `model-init`; tmpfs sizing; seccomp profile verified with ffmpeg and torch | P2-T02, P2-T05 | compose media profile converts media smoke fixtures in the weekly integration run |
| P2-T09 | In-browser Whisper in the web UI (4.1 step 13) with `transcript_segments` input to the API | P2-T04 | Playwright WebGPU test passes or is skipped with reason; 10-second fixture transcribes |
| P2-T10 | `ezmd watch` and the stub-note-on-failure behavior; systemd and launchd docs | P1-T09 | watch test with a temp dir passes |
| P2-T11 | MCP `search_result` tool | P1-T11 | BM25 test over a long fixture passes |
| P2-T12 | Capacity measurement: `ezmd fixtures run --timings` on an 8-core runner; write `docs/ops/capacity.md` with measured seconds per page and realtime factors | P2-T08 | numbers in docs match the nightly timings within 25% |
| P2-T13 | Load test script and thresholds; run against the compose stack in integration | P1-T15, P2-T08 | k6 thresholds pass on the CI runner at reduced rates |

Gate G2: all P2 tasks done; `v0.2.0` released; media fixtures at or above 90% pass; `ezmd doctor` reports GPU correctly on a CUDA runner (or documented manual check); capacity doc written; STATUS.md updated.

#### 4.17.4 Phase 3: Social, chat, URL fetch chains, fetch node, extension, share sheet

Goal: the inputs no competitor handles (chat exports, social threads) and the client-side fetch paths that sidestep platform blocking.

| ID | Task | deps | done when |
|---|---|---|---|
| P3-T01 | Chat export normalizer: Slack folders with thread reconstruction via `thread_ts`, Discord (DiscordChatExporter JSON), WhatsApp txt, Telegram JSON, iMessage (imessage-exporter output), Teams; speaker, timestamp, thread parent, reactions, attachments | G2 | chat fixtures exact-match; Slack thread fixture reconstructs nesting |
| P3-T02 | Social adapters: Reddit `.json` with comment tree and rate limiting, HN Algolia, Bluesky public AppView, Mastodon public API; podcast RSS with `podcast:transcript` | P1-T07 | social fixtures (recorded responses) exact-match |
| P3-T03 | Captions-first video URL chain: YouTube caption tracks via Data API when a key is configured, platform caption endpoints, podcast transcripts; `fetch_blocked_by_platform` on failure with the suggestion text | P3-T02 | chain order tested with stubbed responses |
| P3-T04 | `[fetch]` extra: yt-dlp with Deno and bgutil PO-token provider, audio-only formats, avd-style mirror chain for short-form kept in a data file, cookies and proxy options; self-host only, disabled on public mode | P3-T03 | self-host fetch tests with stubbed yt-dlp pass; public mode refuses with `fetch_blocked_by_policy` |
| P3-T05 | Crawl4AI extra for JS-rendered pages and bounded crawls (`max_pages`, same-origin), fit-markdown | P1-T02 | JS fixture page converts; crawl bounded test passes |
| P3-T06 | Fetch-node protocol (Part 3) server side: claim, lease, upload, node registry, `allowed_sources`, metrics | P3-T04 | protocol tests pass; a simulated node completes a job |
| P3-T07 | `apps/fetch-node` loop, `ezmd fetch-node run/token/doctor/ping`, `fetch-node` image (amd64 and arm64), `docker-compose.pi.yml`, Pi build script and firstrun, Tailscale policy file | P3-T06 | arm64 image runs on a Pi 4 (manual, recorded) and completes a caption job against a staging instance |
| P3-T08 | Browser extension (4.6): plain URL path, YouTube captions and audio, generic video blob, MediaRecorder fallback, settings, Firefox build, privacy doc, store assets | P1-T12, P3-T06 | 4.6.4 criteria |
| P3-T09 | PWA manifest with share target, service worker shell cache, `/share` handling, install hint (4.7.2) | P1-T13 | share-target Playwright test passes |
| P3-T10 | iOS Shortcuts A and B, exported `.shortcut` files, docs with exact steps, `client: ios-shortcut` allowance in the API | P1-T10 | manual run on an iPhone recorded in STATUS.md; API allowance tests pass |
| P3-T11 | Notes-app converters: Evernote ENEX, Notion export zip, Google Keep Takeout, Apple Notes via ENEX | G2 | fixtures exact-match |
| P3-T12 | Specialized converters: ICS, HL7 v2, MusicXML, fonts via fontTools, 3D mesh metadata, USPTO and JATS via Docling, Google Workspace via Drive export (user token) | G2 | fixtures pass; each marked Beta in the matrix |
| P3-T13 | Warnings and suggestions for every fetch failure mode wired into UI, CLI, MCP, SDK errors | P3-T03 | the warning coverage test (4.1.3) still passes with new codes |

Gate G3: all P3 tasks done; `v0.3.0` released; extension passes `web-ext lint` and Chrome validation and is submitted to both stores (approval pending is acceptable); a fetch node completed a real captions job against staging from the Pi with the VPS making no platform request (verified from Squid logs); STATUS.md updated.

#### 4.17.5 Phase 4: Public instance launch

Goal: the free instance is live, protected, lawful, observable, and cheap.

| ID | Task | deps | done when |
|---|---|---|---|
| P4-T01 | Public compose overlay, Squid egress proxy, worker network override, API loopback port for Tailscale, `audit-host.sh` | G3 | compose config validates; audit script passes on a staging VM |
| P4-T02 | Challenge: Turnstile verify and JWT, ALTCHA alternative, client allowance, web UI integration | P1-T10 | challenge tests pass; Playwright with a Turnstile test key passes |
| P4-T03 | Abuse controls complete (4.11): per-IP daily budgets, sub-queues, blocklist hot reload, admin commands `top`, `block`, `keys`, `jobs kill`, `reap`, `report`, `support-bundle` | P4-T02 | security tests item 5 pass; admin command tests pass |
| P4-T04 | Monitoring stack: metrics, compose monitoring overlay, Grafana dashboard JSON, alert rules, Discord and email receivers, weekly digest timer | P2-T12 | alerts fire in a test by injecting metrics; dashboard imports cleanly |
| P4-T05 | Log redaction verified end to end; job table retention; privacy page matches behavior (test reads the page and asserts the stated fields are the only ones logged) | P4-T03 | redaction tests pass |
| P4-T06 | Legal pages in the web app with `.env` substitution; DMCA mailbox config; takedown doc; platform stance doc | P1-T13 | pages render; links in footer; owner sign-off recorded in DECISIONS.md |
| P4-T07 | Runbook (4.10) complete with Hetzner, Cloudflare (rules as copyable expressions), Tailscale policy, Pi first boot, monitoring, cost, sponsor pack generator | P4-T04 | a second person can follow it on a fresh account (owner dry run recorded) |
| P4-T08 | Staging instance on a small Hetzner box using the full public overlay; k6 load run at target rates; 72-hour soak with synthetic traffic | P4-T01..T05 | thresholds pass; no alert false positives during soak; memory stable |
| P4-T09 | Red-team pass: SSRF through every fetch path including the fetch node and the extension upload, bomb files through every converter, rate-limit bypass attempts (header spoofing, IPv6 rotation within a /64, key sharing), JWT replay, path traversal, CSP bypass attempts, metrics and admin exposure; findings fixed or recorded in SECURITY-EXCEPTIONS.md with expiry | P4-T08 | report in `docs/ops/redteam-<date>.md`; no open high findings |
| P4-T10 | Production cutover: DNS, Cloudflare rules applied, Origin CA, Pi connected, uptime check, backups to off-box storage verified by a restore drill | P4-T07, P4-T09 | `https://ezmd.<domain>/healthz` ok; restore drill recorded |
| P4-T11 | Launch content: README "Try it" live, docs FAQ on platform blocking, Show HN draft with the shadow-run benchmark story, Product Hunt not planned (research shows weak signal), r/LocalLLaMA and r/ObsidianMD posts drafted; MCP registry entry verified in Claude Desktop and Cursor | P4-T10 | drafts in `docs/launch/` reviewed by the owner |
| P4-T12 | Sponsor pack generator and applications drafted (Hetzner OSS, Cloudflare OSS, GitHub Sponsors org tier) to be sent after 30 days of data | P4-T04 | `ezmd admin report --sponsor-pack` produces the document |

Launch checklist (every line must be checked and dated in STATUS.md before DNS cutover):

1. `audit-host.sh` passes on the production box.
2. Every container non-root, read-only, caps dropped, seccomp on workers (`docker inspect` check).
3. SSRF suite passes against production from inside the network (via Tailscale).
4. Rate limits verified with a scripted burst from an external IP: 429 at the 21st request.
5. Turnstile verified in a real browser; ALTCHA path disabled in production.
6. Upload cap 25 MB, duration cap 15 min, page cap 300 verified with real requests.
7. Direct platform fetch disabled; a YouTube URL returns `fetch_blocked_by_policy` with the extension suggestion when the Pi is offline and succeeds via captions when it is online.
8. The Pi's public IP never appears in any response, log, or header (test: convert via the Pi and inspect every header and the sidecar).
9. Reaper verified: a job is gone 24 hours after creation (clock-skewed test on staging).
10. Backups run nightly and were restored once on staging.
11. Alerts reach email and Discord (test alert fired).
12. Uptime check active.
13. Terms, Privacy, DMCA, Acceptable Use published; DMCA agent registered with the US Copyright Office; mailbox monitored.
14. `EZMD_SPONSOR_NAME` set or the "Support" link present; nothing gated.
15. Cloudflare: proxied records only, Full strict TLS, WAF rules, rate rule, cache rules, Rocket Loader off.
16. Hetzner firewall: 80/443 from Cloudflare ranges only; 22 closed or Tailscale-only.
17. Budget ceiling and downgrade plan written in DECISIONS.md.
18. CHANGELOG has the release entry; `v1.0.0` tagged after one week of stable operation.

Gate G4: launch checklist complete; 7 days of operation with no critical alert; `v1.0.0` released; STATUS.md updated.

#### 4.17.6 Phase 5: Persona verticals and integrations

Goal: the features that make specific professions choose ezmd. Each is independent; order by observed demand from the weekly digest.

| ID | Task | deps | done when |
|---|---|---|---|
| P5-T01 | Finance mode: bank statement and invoice tables with per-row page references, totals reconciliation (rows sum to ending minus beginning balance), sign and date normalization, CSV and JSON sidecars, confidence flags; `--mode finance` | G4 | finance fixtures pass with reconciliation checks |
| P5-T02 | Legal mode: page:line anchors for transcripts and pleadings, Bates numbering passthrough, verbatim guarantee (no normalization beyond whitespace, enforced by a test that diffs extracted text against the engine's raw text), matter-folder batch with an audit log JSONL | G4 | legal fixtures pass; audit log test passes |
| P5-T03 | Accessibility output: heading hierarchy repair suggestions, alt text from captions, reading order report, scored against DAISY's twelve criteria on the accessibility fixtures | P2-T05 | score report generated; at least 10 of 12 criteria met on the fixture set |
| P5-T04 | Research extras: LaTeX math preservation via Marker as an optional `nonfree-rail` extra with license display, DOI and citekey frontmatter from Crossref lookups (opt-in network), Zotero-friendly export | G4 | math fixture passes with the extra; license gate shows the RAIL text |
| P5-T05 | Obsidian plugin (4.8 item 1) and submission | G4 | plugin installs from a release; converts a URL into the vault |
| P5-T06 | Raycast extension and Alfred workflow | G4 | published |
| P5-T07 | GitHub Action `ezmd-action` | G4 | marketplace listing live; used by this repo's docs build |
| P5-T08 | n8n and Zapier templates | G4 | templates in docs; one n8n template verified |
| P5-T09 | Desktop binary: PyInstaller single-file build of `ezmd serve` plus the web UI for macOS, Windows, Linux (air-gapped and non-technical personas); Tauri wrapper evaluated and decided in DECISIONS.md; code signing deferred until funded | G4 | binaries attached to the release; smoke test on each OS |
| P5-T10 | Channel and playlist batch for marketers via the extension (queue every video on a channel page) and the CLI with the fetch extra | P3-T08 | extension batch test passes |
| P5-T11 | Safari extension, only if sponsorship covers the Apple developer fee | P3-T08 | decision recorded |

Gate G5: not a hard gate; each task releases in a minor version with its own fixtures and docs page.

#### 4.17.7 Definition of done (whole project)

The project is done for the purposes of the autonomous build when all of the following hold:

1. Gates G0 through G4 passed and are recorded with dates in STATUS.md.
2. `v1.0.0` is on PyPI (`ezmd`, `ezmd-mcp`), npm (`@ezmd/sdk`), GHCR (five image targets, signed, with SBOMs), the MCP Registry, and GitHub Releases with extension zips.
3. The public instance is live behind Cloudflare, with the Pi fetch node connected, monitoring and alerting active, backups verified, and legal pages published.
4. The fixture corpus has at least 150 fixtures with provenance; the nightly scorecard shows 100% on exact fixtures and at or above 95% on threshold fixtures; no fixture triggers silent loss (every known loss has a warning code).
5. The converters matrix on the docs site reflects reality: every family shipped is marked with its status and scores; nothing is marked Stable without fixtures.
6. The threat model mitigations are implemented and tested; the red-team report has no open high findings.
7. Documentation covers every interface, every env var, every warning code, and every runbook step; every command in the README runs as written.
8. The final completion report (4.17.9) is written.

#### 4.17.8 STATUS.md protocol

The agent updates `STATUS.md` after every task, before starting the next. Format:

```markdown
# Status

Last updated: 2026-11-14T18:22Z by agent
Current phase: 2
Current task: P2-T05 (in progress)

## Gates
| Gate | Status | Date | Evidence |
|---|---|---|---|
| G0 | passed | 2026-10-20 | ci run #142, coverage 84% |
| G1 | passed | 2026-11-02 | v0.1.0, scorecard 97.1% |
| G2 | open | | |

## Tasks
| ID | Status | Date | Notes |
|---|---|---|---|
| P2-T01 | done | 2026-11-05 | 9 models in registry; license gate on |
| P2-T02 | done | 2026-11-09 | WER 0.09 on clean, 0.27 on noisy |
| P2-T03 | done | 2026-11-11 | |
| P2-T04 | done | 2026-11-12 | |
| P2-T05 | in progress | | RapidOCR routed; PaddleOCR-VL loader failing on arm64, see #88 |

## Fixture scorecard (latest nightly)
exact: 61/61, threshold: 52/54 (96.3%), media: 12/13, ocr: 7/9

## Blockers and human decisions needed
- Hetzner GPU not in budget; media stays CPU (decision D-014)

## Known limitations (running list, becomes part of the final report)
- Old scans under 150 dpi produce `ocr_confidence_low` on most pages
```

Rules: one commit per task that touches STATUS.md with message `status: P2-T05 done`; never mark a task done with failing tests; if blocked, write the blocker and move to the next unblocked task in the same phase; never skip a gate; if a gate cannot pass, write why under Blockers and stop for the human.

#### 4.17.9 Final completion report

When G4 passes (or when the agent must stop because a gate cannot pass), write `docs/reports/completion-<date>.md` and link it from STATUS.md, with these sections:

1. What shipped: versions, packages, images, interfaces, with links.
2. Fixture scores: the latest scorecard table by family, with the ten lowest-scoring fixtures and why.
3. Known limitations: the running list from STATUS.md, grouped by family, each with the warning code users will see and the planned fix or "no fix planned".
4. Security: red-team summary, open exceptions with expiry, threat model deltas.
5. Public instance: capacity measured, limits in force, current sponsor status, 30-day traffic if available.
6. Cost estimate: monthly server, Cloudflare, domain, Groq at observed volume, Pi power; projected at 10x traffic; the budget ceiling and the downgrade plan.
7. Next steps: the Phase 5 items ranked by evidence from the weekly digests, plus any P1 to P4 debt.
8. Decisions needed from the human: a short numbered list.

### 4.18 Risk register

Each risk has an owner (agent or human), a mitigation built into the plan, and an escalation trigger: the condition under which the agent stops acting on its own and writes the issue to STATUS.md under "Blockers and human decisions needed" for the human.

| # | Risk | Likelihood | Impact | Mitigation | Escalation trigger |
|---|---|---|---|---|---|
| 1 | Platform blocking of datacenter fetches (YouTube, TikTok, Instagram, X) makes URL conversion fail for the most common user intent | High, continuous | High | Captions-first chain; direct platform fetch off on the public box; fetch node on residential IP; extension and share sheet on the user's IP; explicit `fetch_blocked_by_platform` warning with the three fixes; `FetchBlockedSpike` alert | Fetch-node success rate below 50% for 7 days, or a platform contacts the owner |
| 2 | yt-dlp breakage cadence (extractor changes every few weeks, JS runtime and PO-token churn) | High | Medium | yt-dlp pinned but auto-bumped by Renovate at any time; nightly canary on release lag and extractor self-tests; adapter data file for mirror chains hot-swappable; fetch node auto-updates via Watchtower | Canary fails for 14 days with no upstream fix, or a fix needs a new system dependency on the Pi |
| 3 | CPU saturation on the 8-core box from media jobs | Medium | Medium | Duration cap 15 min, concurrency 1 per IP, media sub-queues, Groq offload trigger at p95 wait over 10 min for 3 days, `CpuSaturated` and `MediaQueueWait` alerts, downgrade plan to documents-only | Groq offload would exceed the budget ceiling, or alerts persist after offload |
| 4 | Legal takedown or cease-and-desist (DMCA, platform ToS, a Hamburg-style ruling against downloaders) | Low to medium | High | No retention past 24 h, text output only, no media re-serving, DMCA agent registered, 2-day takedown SLA, `DISABLED_SOURCES`, blocklist, no commercial media in fixtures or examples, platform stance published | Any legal correspondence at all: the agent never answers it; the human does |
| 5 | License drift in dependencies or model weights (a dep flips to AGPL or BUSL, a model is RAIL) | Medium | High for commercial users | License allowlist CI on every PR for Python, Node, and models; `nonfree` isolation test; model registry with SPDX and gate; Renovate PRs fail on license change | A core dependency with no permissive alternative changes license |
| 6 | Model download sizes and first-run slowness (gigabytes of weights; Pi and laptop users) | High | Medium | Core install with no torch; extras opt-in; `models pull` with size shown first; `model-init` in compose; `doctor` explains; whisper `small` default on CPU; in-browser Whisper for small files; `models export` for air-gap | None; this is a product constraint, not a decision point |
| 7 | Pi offline (power, ISP, Tailscale, SD card failure) | High, intermittent | Low | Designed degraded mode: capabilities report `fetch_node: offline`, URL fetches for platform sources fail fast with the extension suggestion; `FetchNodeOffline` alert downgraded to info after week one; tmpfs-only writes to spare the SD card; Watchtower keeps it current | Offline more than 7 consecutive days (the human decides whether to replace hardware or drop the node) |
| 8 | Cloudflare dependency (Turnstile, proxy, WAF; terms or free-tier changes) | Low | Medium | ALTCHA implemented and tested as a drop-in challenge; Caddy handles TLS itself; Cloudflare-only firewall rule is a script toggle; runbook has a "run without Cloudflare" section (open 80/443, switch `TRUST_PROXY_HEADER`, enable ALTCHA, accept reduced DDoS protection) | Cloudflare free tier no longer covers Turnstile or proxying for the zone |
| 9 | Abuse (scrapers using the instance as a proxy, bulk media floods, key sharing) | High | Medium | cobalt-derived limits, per-IP concurrency, daily budgets, Turnstile JWT, keys with IP and UA pinning, Cloudflare bot rules, blocklist, incident checklist, admin tooling | Hetzner abuse ticket, bandwidth over 5 TB per month, or an incident needing a spend decision |
| 10 | Fixture copyright (a contributor adds real platform content or a copyrighted document) | Medium | Medium | Provenance manifest required by CI; allowed origins list; no real platform content rule; LFS size cap; CREDITS page; PR template question; council review on fixtures | A takedown about fixtures, or a contributor disputes a removal |
| 11 | Scope creep (60-plus input types, five interfaces, verticals) | High | Medium | Phases with hard gates; Phase 5 is demand-ranked by the weekly digest; converter matrix marks Experimental honestly; "stub plus warning" is an acceptable v1 for long-tail types; the agent must not start a Phase N+1 task before gate N | The agent finds itself more than 30% over the phase's task count or a gate is 2 weeks late |
| 12 | Maintainer burnout (one owner, free public instance, platform churn, support load) | High over 12 months | High | Automation: Renovate auto-merge, nightly canaries, alerts only for actionable conditions, weekly digest instead of dashboards, documented runbook so a second maintainer can step in, budget ceiling and downgrade plan so the box can shrink without shame, "Support" link and sponsor applications, issue templates that route platform-blocking complaints to the FAQ | The weekly digest shows more than 5 hours of operator time in a week for 3 weeks, or the owner says so |

Every escalation trigger that fires during the autonomous build is written to STATUS.md immediately, with the risk number, what was observed, what the agent did within its authority, and the decision needed. The agent continues with unblocked work in the same phase; it does not pass a gate while a trigger is open.
