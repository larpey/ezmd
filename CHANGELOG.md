# Changelog

All notable changes are generated from Conventional Commits. This project uses semantic versioning.

## [Unreleased]

### Security
- LibreOffice's profile now disables active content (OLE, DDE) and Python, blocks untrusted links, never
  updates links, fields or charts, and never recalculates on load, so linked files and URLs and
  `WEBSERVICE()` are not fetched. `office.require_sandbox` (default on with `EZMD_REQUIRE_SANDBOX=1` or
  `EZMD_SERVER=1`) refuses to run LibreOffice without bubblewrap; local runs without it log a warning (D-0056).
- Archive and package limits now count every decompressed byte (skipped tar members, 7z entries in a solid
  block that are not kept, documents inside archives), refuse oversized zip directories before parsing
  them, DOCTYPE-check every XML-looking package part, and keep Docling offline even when `HF_HUB_OFFLINE=0`
  is inherited (D-0057).
- URL fetches refuse hostnames with a label over 63 octets, over 253 in total, or an empty label (before,
  `getaddrinfo` raised UnicodeError and the job failed with a 500); a trailing dot is normalized.
- Executables detected by Magika (`application/x-executable-elf`, Mach-O, COFF, DEX, Windows drivers,
  Python bytecode and the rest of Magika's executable group) are refused like libmagic's; Magika's archive
  labels need the archive's signature when libmagic disagrees (1 MiB of `a` is no longer an ISO image);
  Magika's ONNX session uses `EZMD_MAGIKA_THREADS` threads (default 1) (D-0058).

### Documentation
- Install docs no longer pin `0.1.0rc2`: pip and uv take the newest release candidate while no final exists.
- Linux: `ezmd[docs]` pulls about 6 GB of CUDA torch and NVIDIA wheels from PyPI, not 1.2 GB; the install
  page shows how to get CPU torch first with pip or `uv --torch-backend cpu` (D-0051).

### Fixed
- PDF text layers whose font size is carried by the text matrix (`1 Tf` with a scaled `Tm` or CTM) no
  longer split every word at ascenders and descenders into one-glyph lines and spurious N-column tables;
  rotated tables on upright pages keep whole lines too (D-0050).
- `pip install --pre ezmd` no longer resolves defusedxml 0.8.0rc2 or openpyxl 3.2.0b1: both are capped
  below the pre-released series, like httpx and lxml (D-0039).
- With the `docs` extra but no Docling models, PDFs no longer spend about 20 s importing torch before
  falling back: Docling is skipped up front and the result carries an `engine_fallback` warning naming the
  missing models and the download command. `ezmd doctor` checks the models (D-0052).
- `ezmd doctor` no longer shows ffmpeg as MISSING while the `media` extra is unreleased, and `--quiet`
  prints only problems.
- Web pages: Wikipedia articles are titled by their name, not the JSON-LD short description; og:title loses
  a trailing site name; MediaWiki references become footnotes (`[^n]`) instead of digits glued to the text;
  unresolved references keep their brackets; empty table rows (image-only infobox rows) are dropped (D-0053).
- A missing optional extra exits 2 (`extra_required`) for every input type; Parquet exited 1 and 7z 3.
  Unsupported types carry the stable code `unsupported_media_type` (exit 6) instead of being recognized by
  their message (D-0054).
- `ezmd batch` stops starting new files at the first failure (before, up to workers + 1 more converted)
  and shows how many were cancelled; `-q` also silences Docling's "Loading weights" progress bars;
  `ftp://` and other non-http URLs fail with an unsupported-scheme message (exit 2) instead of "no such
  file"; `-f zip` explains that zip is the API's bundle and what `--out` writes instead (D-0055).
- `@ezmd/sdk`: `@ezmd/sdk/node` has types under TypeScript's `moduleResolution: node10` (`typesVersions`);
  the package version is unchanged.

## [0.1.0-rc4] - 2026-10-13

Release candidate for the pre-0.1.0 test pass. The npm SDK stays at 0.1.0-rc.3 (unchanged).

### Added
- `ezmd --version` (and `-V`) prints the same line as `ezmd version`.

### Security
- API-key `allowed_sources` / `disabled_sources` now hold across redirects and converter-requested
  fetches; before, an open redirect on an allowed site could reach any public host (D-0043).
- A Turnstile challenge JWT covers at most 5 URL jobs, counted per nonce, instead of any number until it
  expired (docs/spec/part4.md 4.11.2; D-0043).

### Fixed
- The fetch worker finds `keys.json` keys: a file key with `residential_allowed` is no longer failed
  when a redirect lands on a residential-only host.

## [0.1.0-rc3] - 2026-10-09

Fixes from the pre-release audit (D-0039 to D-0042).

### Security
- Client-IP spoofing behind proxies is fixed: uvicorn no longer rewrites the peer from `X-Forwarded-For`;
  the API trusts only Caddy's `X-Real-IP` from the internal network (`EZMD_TRUST_PROXY_HEADER`,
  `EZMD_TRUSTED_PROXIES`), so a client can no longer pick the address that rate limits, quotas, Turnstile and
  API-key IP pinning use.
- Brotli-encoded responses are decompressed with a cap, like gzip and deflate (decompression bomb).
- MCP tool calls may set only whitelisted conversion options and may lower, never raise, the operator's
  limits (new `ezmd-mcp --max-*` flags).
- Pillow's pixel cap is set to 50 megapixels.

### Packaging
- `httpx` is capped below 1.0 and `httpcore` is declared, so `pip install --pre ezmd` no longer pulls an
  httpx pre-release that breaks URL conversion; `lxml` is capped below 7 for the same reason.
- LICENSE and NOTICE are included in every wheel and sdist.
- The `mcp` and `all` extras pin `ezmd-mcp` to the exact matching version.
- The license gate covers every extra except `nonfree`; NVIDIA's CUDA runtime wheels, pulled by torch on Linux
  through the `docs` extra, are a named, reviewed exception.

### Tests
- Golden checks add hard structural invariants (math, blockquotes, list nesting, table spans, links, exact
  numbers, key frontmatter fields) and per-fixture `must_contain`/`must_not_contain`; sidecar goldens are
  compared. CI gains an `extras` job that runs the 7z and data converters.

### Fixed
- `.mbox` detection no longer depends on the host's `mime.types` (a spurious `misnamed_file` warning on
  Ubuntu and macOS); SQLite's `dbstat` size column can be turned off with `data.sqlite_sizes = false`.
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
