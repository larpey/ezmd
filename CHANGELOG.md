# Changelog

All notable changes are generated from Conventional Commits. This project uses semantic versioning.

## [Unreleased]

Fixes from the pre-release audit.

### Security
- Client-IP spoofing behind proxies is fixed: a client can no longer pick the address that rate limits and logs use.
- Brotli-encoded responses are capped like gzip and deflate (decompression bomb).
- The MCP server accepts only a whitelist of conversion options from tool calls.
- Images are opened with a Pillow pixel cap.

### Packaging
- `httpx` is capped below 1.0, so `pip install --pre ezmd` no longer pulls an incompatible httpx pre-release.
- LICENSE and NOTICE are included in every wheel.
- Extras forward to `ezmd-converters` at the exact matching version.
- The license gate covers the optional extras too.

### Fixed
- `ezmd doctor` lists the published extras (`7z`, `data`, `docs`, `mcp`, `nonfree`) from the package metadata,
  detects them by their real requirements, and shows spec extras that are not published yet as coming in a
  later release instead of printing a pip command that fails.
- `ezmd serve` without the API no longer suggests `pip install ezmd-api` (not on PyPI); it points at Docker
  Compose self-hosting.
- `--engine pdf=docling` resolves to `documents.docling_pdf`; naming a converter whose extra is missing (with
  `--engine` or `--converter`) says which extra to install instead of `Unknown converter`.
- The Parquet "needs pyarrow" error no longer repeats its install hint; the 7z placeholder names
  `pip install 'ezmd[7z]'` without escaped brackets.
- Release notes come from the exact `## [<version>]` changelog heading (or `## [Unreleased]`); the release fails
  instead of publishing another version's notes.
- `packages/mcp/server.json` no longer advertises a hosted `/mcp` endpoint the API does not serve yet.

### Documentation
- README and docs describe what is published (PyPI pre-release, GHCR images; npm with 0.1.0) and recommend an
  exact version pin for the release candidate.
- Email (EML, MBOX, MSG) is listed as supported; repository packing is documented as `--converter
  code.repo_pack` or a GitHub URL (local `*.repo.zip` names are not picked automatically, directories are not
  an input).
- Converter options are documented with the working `--opt extra.pdf.<name>=...` form; the install guide has
  the Docling model download step (`docling-tools models download layout tableformer -o DIR`,
  `EZMD_DOCLING_ARTIFACTS=DIR`).

## [0.1.0-rc2] - 2026-10-08

Second release candidate. Published to PyPI as a pre-release.

### Fixed
- On Windows, `ezmd convert` crashed with `UnicodeEncodeError` when its output was piped or redirected
  (the stream used the legacy cp1252 code page). The CLI now writes UTF-8 to stdout and stderr.
- Parquet column statistics render zone-aware timestamps the same way on every pyarrow version.

### Changed
- Renamed from intomd to ezmd before the first release (D-0037).

## [0.1.0-rc1] - 2026-10-08

First release candidate (Phase 1). Published to PyPI as a pre-release.

### Added
- Converters: PDF (pypdfium2 text with structure-tree headings; Docling layout engine in the `docs` extra),
  DOCX with tracked changes and comments, PPTX with notes, XLSX with formulas and every sheet, ODF, RTF,
  EPUB, Jupyter notebooks, archives (zip, tar, 7z in the `7z` extra) with bomb limits, web pages
  (Trafilatura with hidden-content stripping), source files and repositories with secret redaction,
  CSV/TSV/JSON/YAML/TOML/XML/SQLite (Parquet in the `data` extra), email (EML, MBOX, native Outlook MSG),
  and SEC EDGAR filings.
- Interfaces: `ezmd` CLI (`convert`, `batch`, `doctor`, ~~`config`, `remote`~~, `shadow-run`; correction: the
  `config` and `remote` commands are not implemented yet: config is read from the config file and remote use is
  the `--remote` option), the Python library
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
