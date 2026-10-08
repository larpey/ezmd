# intomd

Convert anything (documents, web pages, video, audio, chat exports, code) to clean Markdown for AI
tools. No silent loss. Apache-2.0.

intomd turns an input into an intermediate representation (IR) and renders it as Markdown with YAML
frontmatter under one of four output profiles (`full`, `compact`, `rag`, `agent`), plus a JSON
sidecar with block provenance and an explicit list of warnings. When something cannot be converted,
intomd says so in the warnings instead of dropping it quietly.

!!! note "Status: Phase 0 (foundation)"
    Today intomd converts plain text and Markdown through the CLI, the REST API, and the web UI.
    Document, web, media, OCR, and the other converter families arrive from Phase 1 onward. Pages
    in these docs mark anything not yet available as "Planned (Phase N)".

## What works today

| Area | Status |
|---|---|
| CLI: `convert`, `capabilities`, `detect`, `version`, `serve` | Available |
| Converters: `text.plain`, `text.markdown_passthrough` | Stable |
| Output profiles `full`, `compact`, `rag`, `agent`; formats `md`, `json`, `txt`, `zip` | Available |
| REST API with jobs, SSE progress, rate limits, error schema | Available |
| Web UI served by the API | Available |
| Docker Compose self-host stack with sandboxed workers | Available |
| SSRF-guarded URL fetching | Available (only text and Markdown URLs convert) |
| PDF, Office, HTML, media, OCR, archives, email, and other families | Planned (Phase 1 onward) |
| MCP server, Python library docs, TypeScript SDK docs | Planned (Phase 1) |
| Browser extension, fetch node, public instance | Planned (Phases 3 and 4) |

## Where to go next

- [Quickstart](quickstart.md): the CLI, the compose stack, and the API in a few commands.
- [Self-hosting](selfhost.md): compose services and every environment variable.
- [REST API](api.md) and [Errors](errors.md).
- [Output format](output-format.md): frontmatter, profiles, tables, footnotes, chunks.
- [Security](security.md): the sandbox, input validation, SSRF guard, and threat model.
- [Writing a converter plugin](plugins.md).
- [Licenses](licenses.md): the dependency license policy.
