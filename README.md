# ezmd

Convert anything (documents, web pages, data files, code, archives, and more) to clean Markdown for AI
tools. No silent loss. Apache-2.0.

[![ci](https://github.com/larpey/ezmd/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/larpey/ezmd/actions/workflows/ci.yml)
[![license: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)

ezmd turns an input into an intermediate representation and renders it as Markdown with YAML
frontmatter under one of four output profiles, plus a JSON sidecar with block provenance and an explicit
list of warnings. When something cannot be converted, ezmd says so instead of dropping it quietly.

> **Status: Phase 1, pre-release.** The repository is private and nothing is published yet: there is no
> PyPI package, npm package, container image, or public instance. Install from source as shown below.
> Commands marked "after the first release" do not work yet. See [STATUS.md](STATUS.md) and
> [ROADMAP.md](ROADMAP.md).

## Install

From source (needs [uv](https://docs.astral.sh/uv/) and Python 3.12 or newer):

<!-- readme: skip (clones from the network) -->
```sh
git clone https://github.com/larpey/ezmd && cd ezmd
```

<!-- readme: skip (installs packages; the test environment is already synced) -->
```sh
uv sync --all-packages
uv sync --all-packages --extra docs          # optional: Docling for PDF layout (large, pulls torch)
uv sync --all-packages --extra data          # optional: pyarrow for Parquet
```

Check what is available on your machine (converters, extras, and system programs such as LibreOffice):

<!-- readme: run -->
```sh
uv run ezmd capabilities
uv run ezmd doctor
```

After the first release (not available yet):

<!-- readme: skip (not published yet) -->
```sh
pip install ezmd
uvx ezmd convert https://example.com
uvx ezmd-mcp
npm install @ezmd/sdk
```

## Quickstart

### CLI

<!-- readme: run -->
```sh
uv run ezmd convert fixtures/office/docx-review/input.docx --profile compact
uv run ezmd convert fixtures/pdf/born-digital-report/input.pdf --profile rag
uv run ezmd convert fixtures/text/markdown-kitchen-sink/input.md --json
uv run ezmd detect fixtures/pdf/born-digital-report/input.pdf
uv run ezmd batch fixtures/text --recursive --out out/text
```

Warnings go to stderr as `WARN [code] message`. `ezmd batch` skips unchanged inputs when run again. URLs
work too; they are fetched through an SSRF guard that refuses private and loopback addresses:

<!-- readme: skip (needs network access) -->
```sh
uv run ezmd convert https://example.com --profile compact
```

Every command and option is in the [CLI reference](docs/cli.md).

### Python library

<!-- readme: run -->
```python
import ezmd

result = ezmd.convert(
    "fixtures/office/docx-review/input.docx",
    profile="compact",
    on_progress=lambda p: print(p.stage, p.progress),
)
print(result.markdown)
for w in result.warnings:
    print(w.severity, w.kind, w.message)
print(len(result.chunks(chunk_tokens=200)), "rag chunks")  # other profiles render from the same conversion
```

`result.render("rag")` renders another profile without converting again. See [docs/library.md](docs/library.md).

### MCP server

From a source checkout, point your MCP client at `uv run ezmd-mcp`. Claude Code:

<!-- readme: skip (needs the Claude Code CLI) -->
```sh
claude mcp add ezmd -- uv --directory /path/to/ezmd run ezmd-mcp
```

Claude Desktop (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "ezmd": {
      "command": "uv",
      "args": ["--directory", "/path/to/ezmd", "run", "ezmd-mcp", "--allowed-dirs", "/Users/you/Documents"]
    }
  }
}
```

After the first release the command becomes `uvx ezmd-mcp`. Other clients, tools, and the HTTP
transport: [docs/mcp.md](docs/mcp.md).

### REST API and web UI

Run the API in-process (inline queue, no Redis), then convert with `curl`:

<!-- readme: skip (starts a long-running server) -->
```sh
uv run ezmd serve --port 8080
```

<!-- readme: skip (needs the server from the previous block) -->
```sh
curl -s -F file=@fixtures/text/plain-utf8/input.txt -F profile=compact "http://127.0.0.1:8080/v1/convert?wait=30&format=md"
```

The web UI is served at `/` once it is built (needs Node 22 and pnpm); then open http://127.0.0.1:8080:

<!-- readme: skip (installs Node packages from the network) -->
```sh
pnpm install && pnpm --filter @ezmd/web build
```

API reference: [docs/api.md](docs/api.md) and [docs/api/openapi.json](docs/api/openapi.json).

### Self-host with Docker

The Compose stack (Caddy, API, sandboxed workers, Redis) builds from this checkout:

<!-- readme: skip (needs Docker and builds images) -->
```sh
bash deploy/bootstrap.sh --plain-http --build
```

Then open http://localhost:8080. Prebuilt images on GHCR come with the first release. Everything else
(TLS, API keys, backups, upgrades, every environment variable): [docs/selfhost.md](docs/selfhost.md).

## What it converts

| Family | Formats |
|---|---|
| Documents | PDF (text layer by default; Docling layout with the `docs` extra), DOCX, PPTX, XLSX, ODF, RTF, legacy Office through LibreOffice |
| Ebooks and notebooks | EPUB, Jupyter notebooks |
| Web | HTML pages and URLs (Trafilatura, rules-based, raw) |
| Data | CSV, TSV, JSON, JSON Lines, YAML, TOML, XML, SQLite, Parquet (`data` extra), connection strings |
| Code | Source files, repositories and directories packed with a secret scan |
| Archives | ZIP, TAR, and compressed TAR with bomb limits; 7z with the `7z` extra |
| Specialized | SEC EDGAR filings |
| Text | Plain text, Markdown |

The full list, with engines, extras, status, fixture counts, and thresholds, is the generated
[converter matrix](docs/converters/README.md). Audio, video, OCR, email, and chat exports are on the
[roadmap](ROADMAP.md).

## Output profiles

- `full`: fidelity first; full frontmatter, numbered headings, page markers, and a JSON sidecar.
- `compact`: for pasting into a chat; minimal frontmatter, link list at the end, a 16,000-token budget.
- `rag`: for indexing; chunk markers with breadcrumbs, and the chunks in the sidecar.
- `agent`: tool output for agents; the body sits inside an untrusted-content fence.

Details: [docs/output-format.md](docs/output-format.md).

## Why ezmd

- No silent loss: every dropped or degraded element becomes a structured warning with a code and a suggestion.
- Permissive by default: the default install pulls only allowlisted licenses; anything else is an opt-in extra.
- One box: CLI, library, REST API, web UI, and MCP server share one conversion path, and the Compose stack runs on a single machine.
- Output profiles: one conversion renders as `full`, `compact`, `rag`, or `agent`.
- Hostile input is the default assumption: sandboxed workers, an SSRF guard, archive and size limits.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) (setup, the council process, the fixture process),
[SECURITY.md](SECURITY.md), and [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

## License

Apache-2.0 (see [LICENSE](LICENSE) and [NOTICE](NOTICE)). Optional extras (for example `7z`, and the
planned `nonfree` extra) and some model weights carry their own licenses; they are listed in
[docs/licenses.md](docs/licenses.md).
