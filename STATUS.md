# Status

Last updated: 2026-10-08 by agent
Current phase: 1
Current task: gate G1 owner steps (publish, Claude Desktop check, docs hosting); Phase 2 not started
Overall: 32 / 85 tasks done

## Phases
| Phase | Name | State | Tasks done | Tag |
|---|---|---|---|---|
| 0 | Foundation | done | 13/13 | v0.0.1 |
| 1 | Permissive core, CLI, library, MCP, UI v1, compose | in_progress | 19/19 | gate G1 pending |
| 2 | Media | pending | 0/13 | |
| 3 | Social, chat, fetch chains, fetch node, extension | pending | 0/13 | |
| 4 | Public instance launch | pending | 0/12 | |
| 5 | Persona verticals and integrations | pending | 0/11 | |

## Gates
| Gate | Status | Date | Evidence |
|---|---|---|---|
| G0 | passed | 2026-10-08 | CI run 37819863068 green on Linux/macOS/Windows; core coverage 91%, all packages 85.6% (Linux container); 13/13 tasks |
| G1 | blocked on owner | 2026-10-08 | Done: 19/19 P1 tasks; 94 fixtures pass (2 skip without py7zr/pyarrow); CI 37847449194 and integration (compose + Playwright) green on fa16fa8. Owner steps left: v0.1.0 publish to PyPI/npm/GHCR (setup in Blocked on human), `uvx ezmd-mcp` manual check in Claude Desktop, docs site hosting (GitHub Pages on a private repo needs a paid plan or a public repo). |
| G2 | open | | |
| G3 | open | | |
| G4 | open | | |

## Tasks
| ID | Task | State | Last commit | Notes |
|---|---|---|---|---|
| P0-T01 | Name availability check | done | | ezmd free on PyPI, npm, GitHub; ezmd.dev unregistered; D-0001 |
| P0-T02 | Repository scaffold | done | 73cb1fe | uv + pnpm workspaces; spec split into docs/spec |
| P0-T03 | Core IR | done | 013f5ed | IR schema 1.1 after council (D-0017); 181 warning codes + aliases |
| P0-T04 | Detection | done | ce1ef5d | Magika+libmagic; 10 MB detect well under 200 ms |
| P0-T05 | Inputs, registry, chains, sandbox, netguard | done | b7fcf01 | registry, chains, sandbox, netguard (39 SSRF tests), redaction, ConvertContext |
| P0-T06 | Plain text and Markdown passthrough converters | done | 714715b | text.plain, text.markdown_passthrough; 4 fixtures at 1.0 (threshold 0.95), Skeptic-reviewed |
| P0-T07 | Profiles, renderer skeleton, scoring | done | 6226b8e | 4 profiles; Harbor Lane example byte-identical; render+profiles cov 94% |
| P0-T08 | CLI | done | 590cab5 | convert/capabilities/detect/version/serve; exit codes per Part 4 |
| P0-T09 | API | done | 6e4a333 | FastAPI+RQ+SSE; 162 API tests; openapi.json committed |
| P0-T10 | Web UI | done | 5f7b1c2 | React UI + @ezmd/sdk (2.9 KB gz); 33 JS tests |
| P0-T11 | Docker and Compose | done | 0f7e0f9 | api 443 MB (budget 480, D-0012), worker 621 MB, fetch-node 164 MB; local smoke PASS |
| P0-T12 | CI and release workflow | done | 4baab0a | CI green on ubuntu 3.12/3.13, macOS, Windows + ts, licenses, audit, images, compose smoke (run 37819863068) |
| P0-T13 | Docs skeleton and Phase 0 close | done | 4baab0a | mkdocs --strict clean; council D-0017 applied; v0.0.1 |
| P1-T01 | Document converters: PDF (Docling default, pypdf fallback), DOCX with tracked changes and comments (Pandoc `--track-changes=all`), PPTX with notes, XLSX with formulas and all sheets, ODF, RTF, EPUB, iWork via Docling | done | 01c21de | PDF (pdfium text + Docling extra), Office (DOCX/PPTX/XLSX/ODF/RTF/LibreOffice), EPUB; D-0027, D-0030, D-0031 |
| P1-T02 | Web converter: Trafilatura plus Defuddle-style rules, metadata, numbered link list, hidden-element stripping, injection scan | done | f858b5f | Trafilatura + rules + raw; hidden-content stripping; 12 fixtures; D-0028 |
| P1-T03 | Code converter: repo and directory packing with Secretlint-style secret scan, tree, per-file tokens, signatures-only mode; GitHub URL fetch | done | 93d2557 | source files, repo packing, secret redaction; 8 fixtures; D-0025 |
| P1-T04 | Email converters: EML, MBOX, recursive attachments; MSG via `nonfree` extra | done | 2aef928 | EML, MBOX, native MSG on olefile; extract-msg nonfree; D-0035 |
| P1-T05 | Data converters: CSV, TSV, JSON, YAML, TOML, XML, Parquet, SQLite with the six-column rule and CSV sidecar | done | 6d422fe | CSV/JSON/YAML/TOML/XML/SQLite/Parquet; 14 fixtures exact; D-0029 |
| P1-T06 | Notebook, Markdown passthrough, plain text, archives (zip, tar, 7z) with bomb limits | done | cb0531d | notebooks, archives with bomb limits (markdown/plain from P0); D-0031 |
| P1-T07 | SEC EDGAR via edgartools; sanctioned public APIs stub (Reddit JSON, HN Algolia) behind a `social` family flag (full adapters in P3) | done | 4672985 | EDGAR on the endpoints directly (edgartools pulls GPL Unidecode); social stubs behind a flag; D-0033 |
| P1-T08 | Python library public API (4.3): `convert`, `convert_async`, `convert_many`, `Result` helpers, lazy engine loading, `unload_models` | done | 650c0d1 | ezmd.convert/convert_async/convert_many/Result/Options; light import |
| P1-T09 | CLI (4.2): `convert`, `batch`, `serve`, `doctor`, `capabilities`, `version`; config.toml; exit codes; completions | done | 5f9c6d4 | convert/batch/doctor/config/remote/completions; D-0022 |
| P1-T10 | API (Part 3): routes, SSE, SQLite, RQ and inline queue, blobs FS, reaper, keys.json, rate limiting, admin, metrics, OpenAPI annotations | done | 37f3761 | keys.json, ezmd-admin, /metrics, /v1/warnings, OpenAPI (Spectral clean); D-0023 |
| P1-T11 | MCP server (4.4): five tools, pagination, stdio and HTTP, auth, `server.json`, client docs | done | e17fe8d | MCP server, local+remote, paging, HTTP auth; D-0024 |
| P1-T12 | TS SDK (4.5): generated types, client, Node helper, size gate | done | e4f859a | OpenAPI-generated types with drift checks, events iterator, 3.4 KB gzipped |
| P1-T13 | Web UI v1 (4.1 steps 1 to 12): input box, progress, result, profiles, downloads, warnings, history, dark mode, accessibility | done | 52a9207 | server warning registry, zip-all, kept results, history, test ids; 90 KB gzipped |
| P1-T14 | Docker: multi-stage Dockerfile targets `api`, `worker`; compose core profile; Caddyfile; `.env.example`; bootstrap, backup, restore, upgrade scripts | done | 1c4e90e | bootstrap/backup/restore/upgrade tested on Docker, rollback verified; D-0034 |
| P1-T15 | Integration workflow (compose in CI), security tests fast and network tiers, Playwright suite | done | 224bd9c | integration workflow on compose, security tiers, Playwright with axe; D-0036 |
| P1-T16 | Images workflow with Trivy, SBOM, cosign; release workflow (PyPI trusted publishing, npm, GHCR, GitHub release, MCP registry) | done | 1c4e90e | digest push, Trivy, SBOM, cosign; OIDC publish gated on owner setup; D-0034 |
| P1-T17 | Docs skeleton: README, CONTRIBUTING with council and fixture process, SECURITY, CODE_OF_CONDUCT, MkDocs site with install, self-host, API, converters matrix (generated), output spec, MCP, CLI, library pages | done | 65d4324 | README, CONTRIBUTING, SECURITY, CoC, strict MkDocs, generated matrix; D-0036 |
| P1-T18 | `shadow-run` command: convert a user's documents with each available engine and score structure and text similarity against each other, print a table | done | 5a159e6 | every available engine per file, scored against the registry's choice |
| P1-T19 | Fixture corpus to at least 80 fixtures across families, with thresholds and CREDITS | done | ff11260 | 94 fixtures, provenance check, nightly scorecard; D-0036 |
| P2-T01 | Model registry (`registry.toml`) with pinned revisions, SHA-256, licenses; `ezmd models pull/list/rm/export`; license gate | pending | |  |
| P2-T02 | ASR pipeline: ffmpeg decode to 16 kHz mono, Silero VAD, faster-whisper int8 (CPU) and Parakeet (GPU), hallucination de-loop and blocklist, sentence split, paragraphing by pause and speaker, sparse timestamps, chapters from platform markers or TreeSeg | pending | |  |
| P2-T03 | Diarization: pyannote community-1 with midpoint alignment; `exclusive` mode; `DIARIZATION` setting | pending | |  |
| P2-T04 | Transcript template and SRT/VTT output; `segments` in sidecar; `.srt` download in UI | pending | |  |
| P2-T05 | OCR routing: RapidOCR (PP-OCR) CPU default, PaddleOCR-VL on GPU, zxing-cpp barcodes, Florence-2 captions optional, chart-to-table via VLM optional; page-level OCR fallback for PDFs with `pages_without_text` | pending | |  |
| P2-T06 | Lecture and screen-recording fusion: SSIM slide detection, per-slide OCR, ASR alignment to slide intervals | pending | |  |
| P2-T07 | Hosted ASR backends (Groq, Deepgram) as keyed options with the offload threshold and `diarization_unavailable_offload` warning | pending | |  |
| P2-T08 | `worker-media` image and compose media profile; GPU override; `model-init`; tmpfs sizing; seccomp profile verified with ffmpeg and torch | pending | |  |
| P2-T09 | In-browser Whisper in the web UI (4.1 step 13) with `transcript_segments` input to the API | pending | |  |
| P2-T10 | `ezmd watch` and the stub-note-on-failure behavior; systemd and launchd docs | pending | |  |
| P2-T11 | MCP `search_result` tool | pending | |  |
| P2-T12 | Capacity measurement: `ezmd fixtures run --timings` on an 8-core runner; write `docs/ops/capacity.md` with measured seconds per page and realtime factors | pending | |  |
| P2-T13 | Load test script and thresholds; run against the compose stack in integration | pending | |  |
| P3-T01 | Chat export normalizer: Slack folders with thread reconstruction via `thread_ts`, Discord (DiscordChatExporter JSON), WhatsApp txt, Telegram JSON, iMessage (imessage-exporter output), Teams; speaker, timestamp, thread parent, reactions, attachments | pending | |  |
| P3-T02 | Social adapters: Reddit `.json` with comment tree and rate limiting, HN Algolia, Bluesky public AppView, Mastodon public API; podcast RSS with `podcast:transcript` | pending | |  |
| P3-T03 | Captions-first video URL chain: YouTube caption tracks via Data API when a key is configured, platform caption endpoints, podcast transcripts; `fetch_blocked_by_platform` on failure with the suggestion text | pending | |  |
| P3-T04 | `[fetch]` extra: yt-dlp with Deno and bgutil PO-token provider, audio-only formats, avd-style mirror chain for short-form kept in a data file, cookies and proxy options; self-host only, disabled on public mode | pending | |  |
| P3-T05 | Crawl4AI extra for JS-rendered pages and bounded crawls (`max_pages`, same-origin), fit-markdown | pending | |  |
| P3-T06 | Fetch-node protocol (Part 3) server side: claim, lease, upload, node registry, `allowed_sources`, metrics | pending | |  |
| P3-T07 | `apps/fetch-node` loop, `ezmd fetch-node run/token/doctor/ping`, `fetch-node` image (amd64 and arm64), `docker-compose.pi.yml`, Pi build script and firstrun, Tailscale policy file | pending | |  |
| P3-T08 | Browser extension (4.6): plain URL path, YouTube captions and audio, generic video blob, MediaRecorder fallback, settings, Firefox build, privacy doc, store assets | pending | |  |
| P3-T09 | PWA manifest with share target, service worker shell cache, `/share` handling, install hint (4.7.2) | pending | |  |
| P3-T10 | iOS Shortcuts A and B, exported `.shortcut` files, docs with exact steps, `client: ios-shortcut` allowance in the API | pending | |  |
| P3-T11 | Notes-app converters: Evernote ENEX, Notion export zip, Google Keep Takeout, Apple Notes via ENEX | pending | |  |
| P3-T12 | Specialized converters: ICS, HL7 v2, MusicXML, fonts via fontTools, 3D mesh metadata, USPTO and JATS via Docling, Google Workspace via Drive export (user token) | pending | |  |
| P3-T13 | Warnings and suggestions for every fetch failure mode wired into UI, CLI, MCP, SDK errors | pending | |  |
| P4-T01 | Public compose overlay, Squid egress proxy, worker network override, API loopback port for Tailscale, `audit-host.sh` | pending | |  |
| P4-T02 | Challenge: Turnstile verify and JWT, ALTCHA alternative, client allowance, web UI integration | pending | |  |
| P4-T03 | Abuse controls complete (4.11): per-IP daily budgets, sub-queues, blocklist hot reload, admin commands `top`, `block`, `keys`, `jobs kill`, `reap`, `report`, `support-bundle` | pending | |  |
| P4-T04 | Monitoring stack: metrics, compose monitoring overlay, Grafana dashboard JSON, alert rules, Discord and email receivers, weekly digest timer | pending | |  |
| P4-T05 | Log redaction verified end to end; job table retention; privacy page matches behavior (test reads the page and asserts the stated fields are the only ones logged) | pending | |  |
| P4-T06 | Legal pages in the web app with `.env` substitution; DMCA mailbox config; takedown doc; platform stance doc | pending | |  |
| P4-T07 | Runbook (4.10) complete with Hetzner, Cloudflare (rules as copyable expressions), Tailscale policy, Pi first boot, monitoring, cost, sponsor pack generator | pending | |  |
| P4-T08 | Staging instance on a small Hetzner box using the full public overlay; k6 load run at target rates; 72-hour soak with synthetic traffic | pending | |  |
| P4-T09 | Red-team pass: SSRF through every fetch path including the fetch node and the extension upload, bomb files through every converter, rate-limit bypass attempts (header spoofing, IPv6 rotation within a /64, key sharing), JWT replay, path traversal, CSP bypass attempts, metrics and admin exposure; findings fixed or recorded in SECURITY-EXCEPTIONS.md with expiry | pending | |  |
| P4-T10 | Production cutover: DNS, Cloudflare rules applied, Origin CA, Pi connected, uptime check, backups to off-box storage verified by a restore drill | pending | |  |
| P4-B01 | Competitive benchmark harness (isolated competitor containers, pinned versions) | pending | |  |
| P4-B02 | Benchmark corpora and metrics, per-category scorecards | pending | |  |
| P4-B03 | Iterate to win on the held-out split (benchmark gate, D-0032) | pending | |  |
| P4-B04 | Publish docs/benchmarks.md with full results | pending | |  |
| P4-T11 | Launch content: README "Try it" live, docs FAQ on platform blocking, Show HN draft with the shadow-run benchmark story, Product Hunt not planned (research shows weak signal), r/LocalLLaMA and r/ObsidianMD posts drafted; MCP registry entry verified in Claude Desktop and Cursor | pending | |  |
| P4-T12 | Sponsor pack generator and applications drafted (Hetzner OSS, Cloudflare OSS, GitHub Sponsors org tier) to be sent after 30 days of data | pending | |  |
| P5-T01 | Finance mode: bank statement and invoice tables with per-row page references, totals reconciliation (rows sum to ending minus beginning balance), sign and date normalization, CSV and JSON sidecars, confidence flags; `--mode finance` | pending | |  |
| P5-T02 | Legal mode: page:line anchors for transcripts and pleadings, Bates numbering passthrough, verbatim guarantee (no normalization beyond whitespace, enforced by a test that diffs extracted text against the engine's raw text), matter-folder batch with an audit log JSONL | pending | |  |
| P5-T03 | Accessibility output: heading hierarchy repair suggestions, alt text from captions, reading order report, scored against DAISY's twelve criteria on the accessibility fixtures | pending | |  |
| P5-T04 | Research extras: LaTeX math preservation via Marker as an optional `nonfree-rail` extra with license display, DOI and citekey frontmatter from Crossref lookups (opt-in network), Zotero-friendly export | pending | |  |
| P5-T05 | Obsidian plugin (4.8 item 1) and submission | pending | |  |
| P5-T06 | Raycast extension and Alfred workflow | pending | |  |
| P5-T07 | GitHub Action `ezmd-action` | pending | |  |
| P5-T08 | n8n and Zapier templates | pending | |  |
| P5-T09 | Desktop binary: PyInstaller single-file build of `ezmd serve` plus the web UI for macOS, Windows, Linux (air-gapped and non-technical personas); Tauri wrapper evaluated and decided in DECISIONS.md; code signing deferred until funded | pending | |  |
| P5-T10 | Channel and playlist batch for marketers via the extension (queue every video on a channel page) and the CLI with the fetch extra | pending | |  |
| P5-T11 | Safari extension, only if sponsorship covers the Apple developer fee | pending | |  |

## Fixture scorecard (latest)
94 fixtures across 11 families (text, pdf, office, ebooks, archives, web, code, data, edgar, comms); all pass; 2 skip without optional extras (py7zr, pyarrow); provenance check 0 problems; per-converter table from `uv run python tools/scorecard.py` (nightly artifact) — 2026-10-08

## Phase 0 summary
Foundation complete and tagged v0.0.1 (2026-10-08). The project was renamed anymd -> ezmd (npm name taken; D-0001).
Shipped: the IR (schema 1.1) with 181 warning codes plus aliases; content detection (Magika + libmagic); a converter
registry with fallback chains, ConvertContext, and experimental gating; the subprocess sandbox; the SSRF guard with
DNS pinning; log redaction; plain-text and Markdown converters; four renderer profiles (Part 3 worked example
byte-identical), chunker, injection scanner, opaque pagination cursors; fixture scorer and golden tooling; the CLI;
the FastAPI/RQ API with SSE, rate limits, dedup, fetch-node endpoints and purge; the React web UI and @ezmd/sdk;
the multi-stage Docker image set and hardened compose stack (non-root, read-only, seccomp, no worker egress); CI,
nightly and release workflows; the MkDocs site. The close council (D-0017) changed the contract before any
converter depended on it and closed an anonymous residential-fetch pivot into the owner's LAN.
Known gaps carried into Phase 1: PyPI/npm publish (human gate); ezmd[server] extra and library `convert()`
public API (P1-T08); docx/zip export formats (501 today); in-browser Whisper, share target (later phases).

## Blocked on human
- (resolved 2026-10-08) GitHub token lacked the `workflow` scope; owner approved device login from phone.
- First publish of `ezmd` to PyPI and `@ezmd/sdk` to npm (irreversible name claim). Publishing is off until the owner: creates GitHub environments `release` (required reviewers, tags `v*`) and `testpypi`; adds PyPI and TestPyPI trusted publishers for ezmd, ezmd-converters, ezmd-mcp (workflow release.yml); creates the npm `@ezmd` scope with trusted publishing; sets repo variable `EZMD_PUBLISH_ENABLED=true` (D-0034).
- Public instance (Hetzner VPS, domain, Cloudflare) and the Raspberry Pi fetch node are Phase 3/4; the owner has a Pi available (2026-10-08).

## Experimental converters
| Converter | Reason | Fixture score | Doc link |
|---|---|---|---|

## Red team findings open
| ID | Severity | Attack | Task |
|---|---|---|---|

## Known limitations (running list)
- EDGAR: no XBRL statement tables yet; accession-only lookups assume the filer prefix is the CIK; CLI `--form`/`--year` deferred (library treats a bare ticker as a path).
- shadow-run: `--timeout` relies on converters checking their deadline.
- Web UI: no upload path for files over 8 MB yet; capabilities lack instance name, sponsor, docx export flag, and queue position.

## Deferred core change requests
- `render/tables._html` does not fill missing cells, so columns shift (xlsx works around it; from P1-T19).
- `--engine pdf=docling` does not resolve (docs use `--converter documents.docling_pdf`); compact frontmatter shows `warnings: []` while the CLI prints info warnings: check against spec (from P1-T17).
- `server` extra needs ezmd-api published; `iwork` extra not packaged (tests/test_extras_hints.py PENDING).
- Split converter metadata from the registry so the api image can drop about 100 MB of converter dependencies (from P1-T14).
- `Provenance.timestamp` (comms keeps it in `Heading.attrs`), compact profile dropping `reply_history`/`reply_header`/`signature` roles, a `signature` paragraph role (from P1-T04).
