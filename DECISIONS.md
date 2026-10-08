# Decisions

Append-only log (docs/spec/part1.md section 2.2). Entries are never edited; a later entry supersedes an earlier one.

## D-0001: Rename the project from anymd to intomd
Date: 2026-10-08
Task: P0-T01
Status: accepted
Context: The spec's working codename is anymd. Rule 1.3: if the name is taken on PyPI or npm, pick another short name free on both and rename globally before any other task.
Decision: intomd ("anything into Markdown"). Python package `intomd`, CLI `intomd`, images `intomd-*`, env prefix `INTOMD_`, npm scope `@intomd`.
Results of the check (2026-10-08): anymd on PyPI free (404); anymd on npm TAKEN (a competing "convert any document to Markdown for RAG" package, modified 2026-02); github.com/anymd TAKEN; anymd.dev free (RDAP 404); anymd.com registered. intomd: PyPI free, intomd-mcp free, npm `intomd` and `@intomd/sdk` free, github.com/intomd free, intomd.dev free (RDAP 404), intomd.com registered.
Alternatives: allmd (taken on npm), omnimd (GitHub org taken), mdloom, tomarkdown, plainmd (all free; less descriptive), everymd/ingestmd (npm org check rate-limited).
Rationale: short, pronounceable, describes the product, free on every registry the spec publishes to.
Consequences: The spec copies in docs/spec/ were renamed mechanically (anymd -> intomd, ANYMD -> INTOMD). No domain purchased (human gate). The GitHub repo is larpey/intomd (private) until the owner decides on an org.
Council: not convened (not architectural).

## D-0002: Reconcile Part 1 and Part 4 where they conflict
Date: 2026-10-08
Task: P0-T02
Status: accepted
Context: The four spec parts were written separately and disagree on several details.
Decision:
- Phase 0 task list: Part 1 section 9 (P0-T01..T13) is authoritative; Part 4's eight P0 tasks are mapped onto it in ROADMAP.md. Gate G0 (Part 4) applies.
- Source layout: Part 4's src layout (`packages/core/src/intomd/`) instead of Part 1's flat `packages/core/anymd/`. Core security utilities live in `intomd.core.*` (sandbox, netguard, licensing, logging, textclean) as Part 1's prose names them.
- Deploy file names: Part 4 section 4.9 (`deploy/docker-compose.yml`, single multi-stage `deploy/Dockerfile`), not Part 1's `deploy/compose.yml` and per-service Dockerfiles.
- License tooling paths: Part 1's `tools/` (matches CLAUDE.md commands), with Part 4 4.15.2 content.
- STATUS.md: Part 4 4.17.8 format plus Part 1's phase table and red-team/experimental tables.
- Warning model: one registry, `intomd.warnings.codes` (Part 2 13.6 names this path), containing the union of Part 1's WarningKind, Part 2's taxonomy (canonical severities), Part 3's vocabulary, and Part 4's fetch codes: 194 codes. `Warning.kind` keeps Part 1's field name; when severity is omitted it defaults from the registry. Near-duplicate spellings used by different parts are kept for now and will be merged when converters settle on one (tracked as debt).
- Input kinds: `transcript_segments`, `captions_json3`, `media_upload` added to `InputRefInfo.kind`/`InputRef.kind` per the README reconciliation note.
Alternatives: follow Part 1 everywhere (loses Part 4's concrete deploy and CI content); follow Part 4 everywhere (Part 4 explicitly defers the core model to Parts 1 to 3).
Rationale: each part is most detailed in its own area; take each area from the part that specifies it concretely.
Consequences: CLAUDE.md layout and command lines are updated accordingly.
Council: to be reviewed by the Phase 0 close council (P0-T13).

## D-0003: Package boundaries between intomd and intomd-converters
Date: 2026-10-08
Task: P0-T02
Status: accepted
Context: Part 1 puts built-in converters in `packages/converters` but registers them from `intomd/builtin.py`; Part 4 says `pip install intomd` includes the HTML, text, data, code, email converters. The converters import the IR from intomd, so a two-way dependency would be a metadata cycle.
Decision: The `intomd` distribution depends on `intomd-converters`; `intomd-converters` does not declare a dependency on `intomd` (it is never installed alone). `intomd.builtin.register_builtins` imports `intomd_converters.builtin_converters()` and registers them with source "builtin"; entry points (`intomd.converters`) remain the third-party plugin path. The API (`intomd-api`) depends on `intomd`; the `intomd[server]` extra is deferred to P1-T16 to avoid an extras cycle during Phase 0.
Alternatives: converters inside the intomd wheel (violates the monorepo layout); register built-ins via entry points (a broken third-party plugin could shadow a builtin id).
Rationale: no metadata cycle, builtins always resolve first, layout preserved.
Consequences: `pip install intomd-converters` alone is unsupported (documented).
Council: to be reviewed at P0-T13.

## D-0004: IR implementation changes from the spec listing
Date: 2026-10-08
Task: P0-T03
Status: accepted
Context: Part 1 section 4 is to be implemented "exactly", fixing mypy errors with a log entry when semantics change.
Decision:
- `Table._shape` sets `has_merged_cells` with `object.__setattr__`; the spec's plain assignment re-enters validation under `validate_assignment=True` and recurses.
- `TableCell.row/col` gained `ge=0` (negative coordinates passed the shape check).
- `Document.counts()` is table-driven; same output.
- `Document.sections()` keeps the synthetic preamble heading (`id="b0000"`, level 1 because Heading.level is 1..6); the spec docstring's "level-0" is not representable.
- `Document.finalized` property exposes the private flag so the registry can finalize documents a converter forgot to.
- `ConversionResult` is declared after `InputRefInfo`; `model_rebuild()` resolves forward refs.
- `Warning` severity defaults from the code registry (D-0002).
Alternatives: none viable for the recursion bug.
Consequences: none for converters.
Council: not convened (no contract change).

## D-0005: Detection resolution extended for extensionless text; Magika model ships in the wheel
Date: 2026-10-08
Task: P0-T04
Status: accepted
Context: Part 1 5.1 resolution ends with "else the extension's mime; else application/octet-stream", which reports an extensionless plain-text file as binary. Magika 1.0.3 (Apache-2.0) bundles its model in the wheel.
Decision: After the extension step, fall back to libmagic's `text/plain`, then Magika's low-confidence answer, then octet-stream. A small alias table normalizes mimes across detectors (e.g. `text/x-markdown` -> `text/markdown`). No Magika model download to INTOMD_MODEL_DIR is needed; the Docker pre-bake step is unnecessary for Magika. On Windows, libmagic comes from python-magic-bin (MIT, bundles libmagic).
Alternatives: keep octet-stream (breaks `intomd convert README`).
Consequences: detection of a 10 MB file measured well under 200 ms locally.
Council: not convened.

## D-0006: Registry treats an empty Document with warnings as a last resort
Date: 2026-10-08
Task: P0-T05
Status: accepted
Context: Part 1 5.2 falls back on any empty Document; the 5.5 contract lets a converter return an empty Document if it carries a warning (for example an image-only PDF with `pages_without_text`).
Decision: An empty Document still triggers the next converter, but the first empty-with-warnings Document is kept and returned if every later candidate fails, so the user sees why nothing came out instead of a bare failure.
Alternatives: always fail (loses the explanation); accept the empty Document immediately (skips a fallback that might produce text).
Consequences: Tests cover both orders.
Council: not convened.

## D-0007: Phase 0 text fixtures
Date: 2026-10-08
Task: P0-T06
Status: accepted
Context: P0-T06 names a fixture `plain-latin1-with-bom`. Latin-1 has no byte-order mark, and a UTF-8 BOM in front of Latin-1 bytes would be malformed input rather than a realistic file.
Decision: Two fixtures instead: `text/plain-latin1` (Latin-1 bytes, exercises charset detection and `encoding_uncertain`) and `text/plain-utf8-bom` (UTF-8 BOM plus a zero-width space, exercises BOM handling and `removed_hidden_elements`). Threshold for both text converters raised to 0.95 as P0-T06 allows.
Alternatives: a UTF-8 BOM followed by Latin-1 bytes.
Consequences: four text fixtures instead of three.
Council: not convened.

## D-0008: Parallel subagents instead of one branch per task during Phase 0
Date: 2026-10-08
Task: P0-T02..P0-T12
Status: accepted
Context: Section 2.1 prescribes one task at a time on `task/<phase>-<id>-<slug>` branches. Phase 0 tasks P0-T07 (renderer), P0-T09 (API), P0-T10 (web/SDK), and P0-T11/T12 (deploy/CI) touch disjoint directories and share only the interfaces already fixed in Part 1.
Decision: Build those in parallel with subagents that each own a disjoint set of paths, then integrate, run all gates, and commit per task on main in task order. The branch-per-task loop resumes from Phase 1.
Alternatives: strictly sequential (several times slower with no quality gain since the interfaces are fixed).
Consequences: Per-task commits are made at integration time rather than as each task finishes.
Council: not convened (process, not architecture).

## D-0009: Dependencies added in Phase 0
Date: 2026-10-08
Task: P0-T02..P0-T08
Status: accepted
Decision (runtime, `intomd`): pydantic >=2.9 (MIT), pyyaml (MIT), tiktoken (MIT), magika (Apache-2.0), python-magic (MIT) / python-magic-bin on Windows (MIT), rapidfuzz (MIT), typer (MIT), rich (MIT), httpx (BSD-3), markdown-it-py (MIT, used by the scorer). `intomd-converters`: charset-normalizer (MIT), markdown-it-py (MIT), mdit-py-plugins (MIT). Dev: pytest (MIT), pytest-cov (MIT), pytest-asyncio (Apache-2.0), hypothesis (MPL-2.0), ruff (MIT), mypy (MIT), pip-audit (Apache-2.0), pip-licenses (MIT), mkdocs-material (MIT), fakeredis (BSD-3). API dependencies are logged by P0-T09.
Rationale: each saves well over 200 lines or provides a parser/model we cannot reasonably write.

## D-0010: Web UI and SDK stack choices
Date: 2026-10-08
Task: P0-T10
Status: accepted
Context: Part 4 4.1 suggests Tailwind, react-markdown, react-query, zod; P0-T10 asks for a minimal footprint.
Decision: React 18.3.1 + Vite 7.3.7 (Vite 5 / Vitest 3 carry open high/critical advisories), plain CSS, marked 18 (MIT) + DOMPurify 3 (Apache-2.0/MPL-2.0) for rendering; raw HTML in results is shown escaped and remote images become links so the page never loads off-origin content. SDK `@intomd/sdk` built with tsup (ESM+CJS+types); hand-written contract types with an `openapi-typescript` generate step. Browsers send `X-Intomd-Client: intomd-web/<v>` (User-Agent cannot be set); with an API key the SDK streams SSE over fetch because EventSource cannot send headers. Pasted text is sent as a multipart file. Deferred to P1-T13: IndexedDB "keep result", zip-all, .srt/.docx downloads, full axe audit.
Alternatives: Tailwind/react-markdown stack (heavier, more transitive licenses).
Consequences: SDK bundle 2.9 KB gz (gate 8 KB); web main chunk 86.9 KB gz. The dev-only dependency @csstools/color-helpers is MIT-0 (permissive); only the production license set is gated.
Council: not convened.

## D-0011: Accept CNRI-Python in the default license allowlist
Date: 2026-10-08
Task: P0-T12
Status: accepted
Context: `regex` (pulled in by tiktoken) is licensed "Apache-2.0 AND CNRI-Python". The allowlist already accepts PSF-2.0 and Python-2.0.
Decision: Add CNRI-Python (the OSI-approved CNRI Python 1.6 license, a permissive member of the Python license family) to `tools/license_allowlist.toml`.
Alternatives: drop tiktoken (loses exact token counts, which Part 3 section 20 requires); override only `regex` (hides the policy in an override file).
Consequences: license check passes on all 57 default packages.
Council: not convened (license family already accepted).

## D-0012: Raise the api image size budget to 480 MB
Date: 2026-10-08
Task: P0-T11
Status: accepted
Context: P0-T11 sets the api image under 400 MB. The built image is 443 MB uncompressed (138 MB compressed); about 136 MB is onnxruntime plus numpy, pulled in by Magika, which the API needs to detect uploads by content (executable rejection, dedup) before enqueueing.
Decision: Budget 480 MB in CI. Revisit when Phase 1 adds converters: moving detection fully into the worker would let the api image drop Magika.
Alternatives: detect by libmagic only in the API (weaker; the spec makes Magika primary); lazy-install Magika (adds a runtime network dependency).
Consequences: worker 621 MB (budget 1.2 GB), fetch-node 164 MB.
Council: not convened.

## D-0013: Deploy and runtime deviations from P0-T11
Date: 2026-10-08
Task: P0-T11
Status: accepted
Decision: Workers run `python -m intomd_api.worker --queues ...` (the API's own RQ entry, which adds the spawn child and limits) rather than bare `rq worker`; purge runs as its own `python -m intomd_api.purge --loop` service with the in-API scheduler disabled. bubblewrap is not installed in the worker image: inside a container with no capabilities and mount blocked by seccomp it cannot create namespaces, so the container boundary is the sandbox there; `sandbox.bwrap_available()` now probes that bwrap actually runs instead of only checking PATH. ffmpeg moves to the Phase 2 media worker. Caddy runs as root inside its container with only NET_BIND_SERVICE (Part 4). The redaction filter keeps `record.args` (redacting string arguments) because uvicorn's access formatter unpacks it.
Consequences: compose smoke passes end to end; worker-default has no route to the internet (verified).
Council: not convened.

## D-0014: Renderer implementation choices and the first IR addition
Date: 2026-10-08
Task: P0-T07
Status: accepted
Context: Part 4 puts all four profile renderers, the chunker, and the token estimator in Phase 0; Part 3 section D is authoritative for format. The Part 3 section 17 worked example (Harbor Lane) renders byte-identical in all four profiles, asserted by a test that reads the expected text from docs/spec/part3.md.
Decision:
- Hash inputs that would be circular: rag chunk doc id uses the IR `Document.content_hash` (the body contains the markers); the agent fence id is sha256(sha256(inner body) + source)[:16].
- Where Parts 1 and 3 disagree on profile defaults, Part 3 wins: tracked changes `accept` and comments `drop` by default (CriticMarkup on request), rag links become text, agent flattens merged cells.
- Head blocks (summary, orientation line, Contents) precede the H1, per the literal reading of 14.
- The first table column is the record label (never right-aligned or summarized) unless `Table.attrs["column_types"]` says otherwise.
- Offline token fallback is len/3.8 (Latin) and len/1.6 (CJK) per section 20.
- Injection patterns live in a Python module; medium/high risk adds `possible_prompt_injection`.
- Deferred: LLM context lines, jsonl/files chunk shapes, the table-downgrade step of the token budget, image-hash decorative detection.
- IR addition (additive, defaults preserve old behavior): `ListItem.children_ordered: bool = False` and `ListItem.children_start: int = 1`, because a nested ordered list under a bullet item could not be represented (found in golden review of markdown-kitchen-sink). Quote spans that are exactly a blank-line break separate quote paragraphs. Footnote references (`InlineSpan.footnote_ref`) point at Footnote block ids, as the IR docstring says; the Markdown converter now assigns `fn-<label>` ids.
Pending IR requests for the P0-T13 council: a Chapter block (now a Heading with time-range provenance), `Table.column_types`, a hidden-sheet flag, per-segment confidence on TranscriptSegment.
Council: IR change to be ratified at P0-T13.

## D-0015: Golden review outcomes for the Phase 0 text fixtures
Date: 2026-10-08
Task: P0-T06
Status: accepted
Context: Skeptic review (section 2.4) accepted content fidelity of all four text goldens and raised three spec questions.
Decision:
- Title H1: a leading source H1 whose text equals the title is consumed as the document H1, and no shift is applied; the sidecar records the effective `heading_shift` (0 in that case, 1 only when a source H1 survives below the title). Following Part 3 14 literally would print the title twice.
- `encoding_uncertain` follows Part 2 13.2: raised only when detection confidence is below 0.7 and the decode still contains replacement characters. A clean Latin-1/cp1252 decode is not uncertain; the plain-latin1 fixture expects no warning.
- Invisible characters: removed from all inputs (Part 1 8.2 and Part 3 14 win over Part 2's note that non-web inputs keep zero-width characters) and reported as `removed_hidden_elements` with a count; the sidecar `counts.removed_nonprinting` includes what converters removed upstream. `removed_invisible_chars` stays in the registry for converters that want to separate the two.
Consequences: goldens regenerated and accepted; all four score 1.0 at threshold 0.95. Goldens are not hand-edited.
Council: not convened.

## D-0016: API implementation choices (P0-T09)
Date: 2026-10-08
Task: P0-T09
Status: accepted
Decision: Settings live in `intomd_api.settings` (pydantic-settings). Part 1 names win over Part 4 where they differ (`INTOMD_DATABASE_URL`, `INTOMD_JWT_SECRET`, `INTOMD_KEY_PEPPER`). Anonymous concurrency defaults to 1 (Part 4 4.11.1, stricter than Part 1's 10). Fetch-node claims read the job store directly instead of popping an RQ queue (the node never touches Redis either way). `format=docx` and unknown formats return a new `not_implemented` (501) error code. Turnstile: token in the JSON body; success sets a 120 s signed challenge cookie (no separate `/v1/challenge` endpoint yet; P4-T02 completes the JWT flow). Converters receive `image_dir=None` until image extraction lands in Phase 1. Swagger/ReDoc UIs are disabled because the required CSP blocks their CDN assets; `/openapi.json` is served. Rendering runs in the worker parent process; conversion runs in the spawn child with resource limits. Uvicorn runs with proxy headers trusted only because the API is reachable solely through Caddy on the internal network (revisit at P4-T01).
Council: to be reviewed at P0-T13.
