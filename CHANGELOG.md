# Changelog

All notable changes are generated from Conventional Commits. This project uses semantic versioning.

## [0.1.0-rc1] - 2026-10-08

First release candidate (Phase 1). Published to TestPyPI only.

### Added
- Converters: PDF (pypdfium2 text with structure-tree headings; Docling layout engine in the `docs` extra),
  DOCX with tracked changes and comments, PPTX with notes, XLSX with formulas and every sheet, ODF, RTF,
  EPUB, Jupyter notebooks, archives (zip, tar, 7z in the `7z` extra) with bomb limits, web pages
  (Trafilatura with hidden-content stripping), source files and repositories with secret redaction,
  CSV/TSV/JSON/YAML/TOML/XML/SQLite (Parquet in the `data` extra), email (EML, MBOX, native Outlook MSG),
  and SEC EDGAR filings.
- Interfaces: `ezmd` CLI (`convert`, `batch`, `doctor`, `config`, `remote`, `shadow-run`), the Python library
  (`ezmd.convert`, `convert_async`, `convert_many`), the MCP server `ezmd-mcp` (stdio and streamable HTTP),
  the HTTP API with SSE progress, the web UI, and the `@ezmd/sdk` TypeScript client.
- Self-hosting: Docker Compose stack with bootstrap, backup, restore and upgrade scripts; images scanned with
  Trivy, shipped with SPDX SBOMs and signed with cosign.
- 94 golden fixtures with provenance checks, a nightly scorecard, integration tests on the compose stack, and a
  Playwright suite with accessibility checks.

### Security
- SSRF guard on every fetch (blocked ranges, IPv4-mapped addresses, internal service ports, per-hop checks),
  sandboxed external tools, hidden-text and prompt-injection scanning in the renderer.

## [0.0.1] - 2026-10-08

### Added
- Phase 0 foundation: IR, detection, converter registry with fallback chains, sandbox, SSRF guard,
  plain text and Markdown converters, renderer profiles, fixture scorer, CLI, API, web UI, Docker Compose, CI.
