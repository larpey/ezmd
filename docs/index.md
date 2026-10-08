# ezmd

Convert anything (documents, web pages, data files, code, archives, and more) to clean Markdown for AI
tools. No silent loss. Apache-2.0.

ezmd turns an input into an intermediate representation (IR) and renders it as Markdown with YAML
frontmatter under one of four output profiles (`full`, `compact`, `rag`, `agent`), plus a JSON
sidecar with block provenance and an explicit list of warnings. When something cannot be converted,
ezmd says so in the warnings instead of dropping it quietly.

!!! note "Status: Phase 1, pre-release"
    Nothing is published yet (no PyPI or npm package, no container image, no public instance); install
    from source. Audio, video, OCR, email, and chat exports arrive in later phases; see the
    [roadmap](roadmap.md) and [status](status.md).

## What works today

| Area | Status |
|---|---|
| Converters: PDF, DOCX, PPTX, XLSX, ODF, RTF, legacy Office (LibreOffice), EPUB, notebooks, HTML, CSV, JSON, YAML, TOML, XML, SQLite, Parquet, source code and repositories, archives, SEC EDGAR, plain text, Markdown | Available; see the [converter matrix](converters/README.md) |
| CLI: `convert`, `batch`, `shadow-run`, `doctor`, `capabilities`, `detect`, `version`, `serve` | Available |
| Python library: `convert`, `convert_async`, `convert_many`, `Result` | Available |
| MCP server (stdio and streamable HTTP, local and remote modes) | Available |
| REST API with jobs, SSE progress, API keys, rate limits; web UI served by the API | Available |
| Docker Compose self-host stack with sandboxed workers, bootstrap, backup, and restore scripts | Available |
| Media (ASR, OCR), email, chat exports, browser extension, fetch node, public instance | Planned (Phases 2 to 4) |

## Where to go next

- [Install](install.md) and [First conversion](quickstart.md).
- [Output format](output-format.md): frontmatter, profiles, tables, footnotes, chunks.
- [CLI](cli.md), [Python library](library.md), [MCP server](mcp.md), [REST API](api.md).
- [Self-hosting](selfhost.md) and the [security model](security.md).
- [Converter matrix](converters/README.md) and [Writing a converter plugin](plugins.md).
- [Contributing](contributing.md) and [Licenses](licenses.md).
