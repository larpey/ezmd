# intomd roadmap

Ordered phases with gates. Generated from docs/spec/part4.md section 4.17 and docs/spec/part1.md section 9. Tasks may be added; gates may not be removed or reordered. Spec references use the section numbers in docs/spec/.

## 4.17.1 Phase 0: Foundation (Part 1)

Goal: a repo that builds, tests, and ships nothing user-visible yet. Task list from docs/spec/part1.md section 9.

| ID | Task | deps | done when |
|---|---|---|---|
| P0-T01 | Name availability check | none | acceptance criteria in docs/spec/part1.md section 9, P0-T01 |
| P0-T02 | Repository scaffold | P0-T01 | acceptance criteria in docs/spec/part1.md section 9, P0-T02 |
| P0-T03 | Core IR | P0-T02 | acceptance criteria in docs/spec/part1.md section 9, P0-T03 |
| P0-T04 | Detection | P0-T03 | acceptance criteria in docs/spec/part1.md section 9, P0-T04 |
| P0-T05 | Inputs, registry, chains, sandbox, netguard | P0-T03, P0-T04 | acceptance criteria in docs/spec/part1.md section 9, P0-T05 |
| P0-T06 | Plain text and Markdown passthrough converters | P0-T05 | acceptance criteria in docs/spec/part1.md section 9, P0-T06 |
| P0-T07 | Profiles, renderer skeleton, scoring | P0-T05 | acceptance criteria in docs/spec/part1.md section 9, P0-T07 |
| P0-T08 | CLI | P0-T06, P0-T07 | acceptance criteria in docs/spec/part1.md section 9, P0-T08 |
| P0-T09 | API | P0-T07 | acceptance criteria in docs/spec/part1.md section 9, P0-T09 |
| P0-T10 | Web UI | P0-T09 | acceptance criteria in docs/spec/part1.md section 9, P0-T10 |
| P0-T11 | Docker and Compose | P0-T09, P0-T10 | acceptance criteria in docs/spec/part1.md section 9, P0-T11 |
| P0-T12 | CI and release workflow | P0-T11 | acceptance criteria in docs/spec/part1.md section 9, P0-T12 |
| P0-T13 | Docs skeleton and Phase 0 close | P0-T01..P0-T12 | acceptance criteria in docs/spec/part1.md section 9, P0-T13 |

Part 4 lists a shorter Phase 0 (P0-T01..P0-T08) whose content is covered by the Part 1 tasks; mapping: P4 T01 scaffold -> P1 T02; P4 T02 core types and warning registry -> P1 T03; P4 T03 registry, MIME routing, subprocess runner -> P1 T04, T05; P4 T04 profile renderers, chunker, token estimator -> P1 T07; P4 T05 settings and .env drift test -> P1 T09; P4 T06 CI -> P1 T12; P4 T07 fixture framework -> P1 T06, T07; P4 T08 SSRF guard -> P1 T05. Gate G0 applies to the Part 1 task list (D-0002).

Gate G0: all P0 tasks done; CI green on all four OS targets; coverage at or above 80% on core; `STATUS.md` updated.

## 4.17.2 Phase 1: Permissive core, CLI, library, MCP, UI v1, compose

Goal: `pip install intomd` converts documents, web, code, email, data, and notebooks with provenance; the four surfaces exist; a self-hoster can run it.

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

Gate G1: all P1 tasks done; `v0.1.0` released to PyPI, npm, GHCR; fixture pass rate 100% on `exact` fixtures and at or above 95% on threshold fixtures; integration and Playwright green; `uvx intomd-mcp` works in Claude Desktop (manual check recorded in STATUS.md); docs site live; STATUS.md updated.

## 4.17.3 Phase 2: Media (ASR, OCR, diarization, in-browser Whisper)

Goal: audio, video files, images, and screen recordings convert locally with speaker labels and sparse timestamps; the public-instance capacity numbers are measured.

| ID | Task | deps | done when |
|---|---|---|---|
| P2-T01 | Model registry (`registry.toml`) with pinned revisions, SHA-256, licenses; `intomd models pull/list/rm/export`; license gate | G1 | 4.2.2 item 6 criteria; model license check in CI |
| P2-T02 | ASR pipeline: ffmpeg decode to 16 kHz mono, Silero VAD, faster-whisper int8 (CPU) and Parakeet (GPU), hallucination de-loop and blocklist, sentence split, paragraphing by pause and speaker, sparse timestamps, chapters from platform markers or TreeSeg | P2-T01 | media fixtures meet WER thresholds; non-speech fixture produces no hallucinated text |
| P2-T03 | Diarization: pyannote community-1 with midpoint alignment; `exclusive` mode; `DIARIZATION` setting | P2-T02 | speaker-count fixture within tolerance |
| P2-T04 | Transcript template and SRT/VTT output; `segments` in sidecar; `.srt` download in UI | P2-T02 | SRT fixture exact-match |
| P2-T05 | OCR routing: RapidOCR (PP-OCR) CPU default, PaddleOCR-VL on GPU, zxing-cpp barcodes, Florence-2 captions optional, chart-to-table via VLM optional; page-level OCR fallback for PDFs with `pages_without_text` | P2-T01 | OCR fixtures meet CER thresholds; image-only PDF now yields text plus `ocr_confidence_low` where applicable |
| P2-T06 | Lecture and screen-recording fusion: SSIM slide detection, per-slide OCR, ASR alignment to slide intervals | P2-T02, P2-T05 | lecture fixture produces slide headings with timestamps |
| P2-T07 | Hosted ASR backends (Groq, Deepgram) as keyed options with the offload threshold and `diarization_unavailable_offload` warning | P2-T02 | stubbed backend tests pass; capabilities reports `asr_offload` |
| P2-T08 | `worker-media` image and compose media profile; GPU override; `model-init`; tmpfs sizing; seccomp profile verified with ffmpeg and torch | P2-T02, P2-T05 | compose media profile converts media smoke fixtures in the weekly integration run |
| P2-T09 | In-browser Whisper in the web UI (4.1 step 13) with `transcript_segments` input to the API | P2-T04 | Playwright WebGPU test passes or is skipped with reason; 10-second fixture transcribes |
| P2-T10 | `intomd watch` and the stub-note-on-failure behavior; systemd and launchd docs | P1-T09 | watch test with a temp dir passes |
| P2-T11 | MCP `search_result` tool | P1-T11 | BM25 test over a long fixture passes |
| P2-T12 | Capacity measurement: `intomd fixtures run --timings` on an 8-core runner; write `docs/ops/capacity.md` with measured seconds per page and realtime factors | P2-T08 | numbers in docs match the nightly timings within 25% |
| P2-T13 | Load test script and thresholds; run against the compose stack in integration | P1-T15, P2-T08 | k6 thresholds pass on the CI runner at reduced rates |

Gate G2: all P2 tasks done; `v0.2.0` released; media fixtures at or above 90% pass; `intomd doctor` reports GPU correctly on a CUDA runner (or documented manual check); capacity doc written; STATUS.md updated.

## 4.17.4 Phase 3: Social, chat, URL fetch chains, fetch node, extension, share sheet

Goal: the inputs no competitor handles (chat exports, social threads) and the client-side fetch paths that sidestep platform blocking.

| ID | Task | deps | done when |
|---|---|---|---|
| P3-T01 | Chat export normalizer: Slack folders with thread reconstruction via `thread_ts`, Discord (DiscordChatExporter JSON), WhatsApp txt, Telegram JSON, iMessage (imessage-exporter output), Teams; speaker, timestamp, thread parent, reactions, attachments | G2 | chat fixtures exact-match; Slack thread fixture reconstructs nesting |
| P3-T02 | Social adapters: Reddit `.json` with comment tree and rate limiting, HN Algolia, Bluesky public AppView, Mastodon public API; podcast RSS with `podcast:transcript` | P1-T07 | social fixtures (recorded responses) exact-match |
| P3-T03 | Captions-first video URL chain: YouTube caption tracks via Data API when a key is configured, platform caption endpoints, podcast transcripts; `fetch_blocked_by_platform` on failure with the suggestion text | P3-T02 | chain order tested with stubbed responses |
| P3-T04 | `[fetch]` extra: yt-dlp with Deno and bgutil PO-token provider, audio-only formats, avd-style mirror chain for short-form kept in a data file, cookies and proxy options; self-host only, disabled on public mode | P3-T03 | self-host fetch tests with stubbed yt-dlp pass; public mode refuses with `fetch_blocked_by_policy` |
| P3-T05 | Crawl4AI extra for JS-rendered pages and bounded crawls (`max_pages`, same-origin), fit-markdown | P1-T02 | JS fixture page converts; crawl bounded test passes |
| P3-T06 | Fetch-node protocol (Part 3) server side: claim, lease, upload, node registry, `allowed_sources`, metrics | P3-T04 | protocol tests pass; a simulated node completes a job |
| P3-T07 | `apps/fetch-node` loop, `intomd fetch-node run/token/doctor/ping`, `fetch-node` image (amd64 and arm64), `docker-compose.pi.yml`, Pi build script and firstrun, Tailscale policy file | P3-T06 | arm64 image runs on a Pi 4 (manual, recorded) and completes a caption job against a staging instance |
| P3-T08 | Browser extension (4.6): plain URL path, YouTube captions and audio, generic video blob, MediaRecorder fallback, settings, Firefox build, privacy doc, store assets | P1-T12, P3-T06 | 4.6.4 criteria |
| P3-T09 | PWA manifest with share target, service worker shell cache, `/share` handling, install hint (4.7.2) | P1-T13 | share-target Playwright test passes |
| P3-T10 | iOS Shortcuts A and B, exported `.shortcut` files, docs with exact steps, `client: ios-shortcut` allowance in the API | P1-T10 | manual run on an iPhone recorded in STATUS.md; API allowance tests pass |
| P3-T11 | Notes-app converters: Evernote ENEX, Notion export zip, Google Keep Takeout, Apple Notes via ENEX | G2 | fixtures exact-match |
| P3-T12 | Specialized converters: ICS, HL7 v2, MusicXML, fonts via fontTools, 3D mesh metadata, USPTO and JATS via Docling, Google Workspace via Drive export (user token) | G2 | fixtures pass; each marked Beta in the matrix |
| P3-T13 | Warnings and suggestions for every fetch failure mode wired into UI, CLI, MCP, SDK errors | P3-T03 | the warning coverage test (4.1.3) still passes with new codes |

Gate G3: all P3 tasks done; `v0.3.0` released; extension passes `web-ext lint` and Chrome validation and is submitted to both stores (approval pending is acceptable); a fetch node completed a real captions job against staging from the Pi with the VPS making no platform request (verified from Squid logs); STATUS.md updated.

## 4.17.5 Phase 4: Public instance launch

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
| P4-T10 | Production cutover: DNS, Cloudflare rules applied, Origin CA, Pi connected, uptime check, backups to off-box storage verified by a restore drill | P4-T07, P4-T09 | `https://intomd.<domain>/healthz` ok; restore drill recorded |
| P4-T11 | Launch content: README "Try it" live, docs FAQ on platform blocking, Show HN draft with the shadow-run benchmark story, Product Hunt not planned (research shows weak signal), r/LocalLLaMA and r/ObsidianMD posts drafted; MCP registry entry verified in Claude Desktop and Cursor | P4-T10 | drafts in `docs/launch/` reviewed by the owner |
| P4-T12 | Sponsor pack generator and applications drafted (Hetzner OSS, Cloudflare OSS, GitHub Sponsors org tier) to be sent after 30 days of data | P4-T04 | `intomd admin report --sponsor-pack` produces the document |

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
14. `INTOMD_SPONSOR_NAME` set or the "Support" link present; nothing gated.
15. Cloudflare: proxied records only, Full strict TLS, WAF rules, rate rule, cache rules, Rocket Loader off.
16. Hetzner firewall: 80/443 from Cloudflare ranges only; 22 closed or Tailscale-only.
17. Budget ceiling and downgrade plan written in DECISIONS.md.
18. CHANGELOG has the release entry; `v1.0.0` tagged after one week of stable operation.

Gate G4: launch checklist complete; 7 days of operation with no critical alert; `v1.0.0` released; STATUS.md updated.

## 4.17.6 Phase 5: Persona verticals and integrations

Goal: the features that make specific professions choose intomd. Each is independent; order by observed demand from the weekly digest.

| ID | Task | deps | done when |
|---|---|---|---|
| P5-T01 | Finance mode: bank statement and invoice tables with per-row page references, totals reconciliation (rows sum to ending minus beginning balance), sign and date normalization, CSV and JSON sidecars, confidence flags; `--mode finance` | G4 | finance fixtures pass with reconciliation checks |
| P5-T02 | Legal mode: page:line anchors for transcripts and pleadings, Bates numbering passthrough, verbatim guarantee (no normalization beyond whitespace, enforced by a test that diffs extracted text against the engine's raw text), matter-folder batch with an audit log JSONL | G4 | legal fixtures pass; audit log test passes |
| P5-T03 | Accessibility output: heading hierarchy repair suggestions, alt text from captions, reading order report, scored against DAISY's twelve criteria on the accessibility fixtures | P2-T05 | score report generated; at least 10 of 12 criteria met on the fixture set |
| P5-T04 | Research extras: LaTeX math preservation via Marker as an optional `nonfree-rail` extra with license display, DOI and citekey frontmatter from Crossref lookups (opt-in network), Zotero-friendly export | G4 | math fixture passes with the extra; license gate shows the RAIL text |
| P5-T05 | Obsidian plugin (4.8 item 1) and submission | G4 | plugin installs from a release; converts a URL into the vault |
| P5-T06 | Raycast extension and Alfred workflow | G4 | published |
| P5-T07 | GitHub Action `intomd-action` | G4 | marketplace listing live; used by this repo's docs build |
| P5-T08 | n8n and Zapier templates | G4 | templates in docs; one n8n template verified |
| P5-T09 | Desktop binary: PyInstaller single-file build of `intomd serve` plus the web UI for macOS, Windows, Linux (air-gapped and non-technical personas); Tauri wrapper evaluated and decided in DECISIONS.md; code signing deferred until funded | G4 | binaries attached to the release; smoke test on each OS |
| P5-T10 | Channel and playlist batch for marketers via the extension (queue every video on a channel page) and the CLI with the fetch extra | P3-T08 | extension batch test passes |
| P5-T11 | Safari extension, only if sponsorship covers the Apple developer fee | P3-T08 | decision recorded |

Gate G5: not a hard gate; each task releases in a minor version with its own fixtures and docs page.
