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

## D-0017: Phase 0 close council — contract changes before v0.0.1
Date: 2026-10-08
Task: P0-T13
Status: accepted
Context: Council question: "Is the Phase 0 IR, registry, and API contract sufficient for Parts 2 to 4 without breaking changes? Name anything that must change now."
Positions:
- Architect: the block model holds, but the converter contract lacks a context (progress, deadline, child conversion, limits, partial documents); Provenance lacks `path`/`source_id`/char offsets that Part 2 makes mandatory; `truncated` is inferred from three hard-coded codes so `page_cap_reached` reports `truncated=false`; experimental converters cannot be excluded; duplicate warning spellings become a public contract; Metadata lacks typed encoding/language fields; the IR cache key ignores schema and converter versions.
- Skeptic/Security: ListItem nesting beyond 46 levels breaks serialization (a 50-deep `<ul>` or Reddit chain crashes the job); anonymous callers can set `prefer_residential`, which with DNS rebinding pivots the home fetch node into the owner's LAN; hostile HTML is parsed inside the egress-capable fetch worker; the child's FetchRequired url/residential flag is trusted; the agent fence close tag is matched case-sensitively and the default fence id is computable by the content author; the child's result file is read unbounded.
- User-advocate: frontmatter `source_type` leaks IR values (`markup`, `text`) outside the Part 3 enum; the pagination cursor is a heading anchor so headingless tails are unreachable and the API rejects `cursor`/flat `max_tokens`; `source_label` means three things; `column_types` is a comma string in attrs; the CLI exits 2 (bad arguments) for a usable result with an error warning; duplicate warning spellings.
Decision (adopted now):
1. IR: `Provenance.path`, `source_id`, `page_label`, `char_start`, `char_end`; `source_label` reserved for sheet/slide/chapter names. `Document.truncated`. `Table.column_types: list[ColumnType] | None`. `Metadata.encoding`, `encoding_confidence`, `languages`, `language_source`. Nesting depth capped at 32 (`MAX_NEST_DEPTH`): `finalize()` flattens deeper list items and emits `nesting_flattened`. `schema_version` becomes "1.1" (additive; readers accept "1" and "1.1").
2. Registry/converter contract: `ConvertContext` reachable as `options.ctx` with a no-op default (progress callback, `check_deadline()`, `convert_child()` sharing the parent deadline and attachment depth, limits); optional `Converter.limits` read with getattr. `ConvertOptions.experimental` (default True in self-host, set False by policy) excludes experimental converters; `experimental_disabled` error. `truncated` = OR over warnings whose code spec has `truncates=True`, plus `Document.truncated`.
3. Warning codes: duplicates merged onto Part 2 13.6 spellings with an alias table (old spellings still parse and normalize): fallback_engine_used/engine_downgraded -> engine_fallback; page_limit_reached -> page_cap_reached; hidden_sheets -> hidden_sheets_included; injection_pattern/possible_prompt_injection/injection_flagged -> injection_suspected; merged_cells_flattened/table_merged_cells_flattened -> merged_cells_flattened (Part 2 has none; keep one); encoding_guessed -> encoding_uncertain; truncated_max_tokens/output_truncated -> truncated (with detail.reason); unreadable_regions -> unreadable_region; removed_invisible_chars stays distinct only if a converter needs it, else alias to removed_hidden_elements.
4. FetchRequired gains `fetch_depth` (max 2). The parent re-validates any URL the child asks for with netguard and the platform policy, and never trusts the child's `residential` flag.
5. Renderer: frontmatter `source_type` maps every IR SourceType onto the Part 3 enum, amended with `text` and `markdown` (logged); opaque cursors (base64 of profile, unit index, renderer version) that can split inside a section, so walking every cursor rebuilds the body; the fence close tag is matched case-insensitively after NFKC; `agent_salt=random` is forced by the API in public mode.
6. API: `prefer_residential` ignored for anonymous callers (residential routing only for `residential_only` policy hosts or keyed callers with the residential permission); fetched bodies are always re-enqueued to `default` so parsing never happens in the egress worker; fetch-node claim response gains `platform` and `resolved_ip` (the node re-runs netguard itself, Phase 3); the child's result file is capped at 256 MB; keyed callers get their key's page limits, not the anonymous cap; `cursor` and flat profile keys (`max_tokens`, ...) accepted on `GET /result`; the dedup/IR-cache key includes `schema_version` and the converter id+version.
7. CLI: an error-severity warning on a usable result exits 3 (partial success), not 2 (Part 4 exit codes win over Part 2 13.6.3).
8. Ratified without new fields: chapters are Headings with time-range provenance until a `Chapter` block lands in P2-T02 (shape: title, start, end, title_source, children via parent_id); slide notes are Paragraph children with `attrs.slide_part="notes"`; hidden sheets are sheet Headings with `attrs.hidden="true"` plus `hidden_sheets_included`; chat messages use `Comment` (no Message block); per-segment ASR confidence uses `Provenance.confidence`.
Deferred (additive, later phases): TranscriptSegment cue kinds, ParagraphRole notes/verbatim, thematic-break and definition-list blocks, Image cover/decorative flags, `JobOut.warnings`, `GET /v1/warnings`, Windows POSIX limits, `APIKey.max_pages` UI.
Consequences: goldens regenerate (source_type, schema_version); every test updated; openapi.json regenerated.
Council: convened (3 reviewers), iteration 1 of 3.

## D-0018: Environment template lives at deploy/env.example
Date: 2026-10-08
Task: P0-T09
Status: accepted
Context: The owner's agent permission rules deny reading and writing `.env*` files (protecting real secrets). The spec names the template `deploy/.env.example`.
Decision: The template is `deploy/env.example` (no leading dot); compose docs, smoke.sh, the drift test, and docs reference it; operators still copy it to `deploy/.env`. The owner was told and can ask for the original name.
Alternatives: weaken the permission rule (owner's call, not the agent's).
Consequences: the settings drift test now runs instead of skipping.
Council: not convened.

## D-0019: Compose fixes found by the first CI smoke runs
Date: 2026-10-08
Task: P0-T11
Status: accepted
Decision: (1) The blobs volume mounts at `/var/lib/intomd-blobs` (`INTOMD_BLOB_FS_ROOT`) instead of inside the state volume: a volume nested in another volume makes every container start create the mountpoint in the shared parent, and concurrent starts fail with "file exists". (2) `deploy/env.example` keeps comments on their own lines: Compose's env-file parser returns `# comment` as the value of an empty variable, which crashed Settings validation; a test enforces this. (3) CI's smoke job sets `INTOMD_WORKER_DEFAULT_CPUS=1.5` for 2-CPU runners. (4) pandoc is dropped from CI installs until the Office converters need it (a stalled mirror download cost 11 minutes).
Consequences: local and CI smoke run against the real template.

## D-0020: Converter families self-register; parallel Phase 1 build on task branches
Date: 2026-10-08
Task: P1 (setup)
Status: accepted
Context: Phase 1 adds about ten converter families. A single shared `builtin_converters()` list, `DEFAULT_CHAINS` dict, and `fixtures/thresholds.toml` would make every family edit the same lines.
Decision: Each `intomd_converters.<family>` package exposes `converters()` (returning `Converter` or `intomd.registry.Unavailable` for missing extras, which capabilities lists with the reason) and `CHAINS`; families are discovered with pkgutil and a failing family is isolated. A mime may have a chain in only one family (enforced). Thresholds live in `fixtures/<family>/thresholds.toml`. Families are built in parallel by subagents in separate git worktrees on `task/P1-Txx-*` branches; each records its approach notes in `docs/decisions/P1-Txx.md`, which the orchestrator folds into this log at merge, and goldens get a Skeptic review at merge time.
Consequences: adding a family touches only its own package, fixtures directory, and optional-dependency group; `uv.lock` is regenerated at each merge.

## D-0021: Specialist converters outrank a pinned chain; textual mime equivalence
Date: 2026-10-08
Task: P1-T03
Status: accepted
Context: The code family found that a Rust/Kotlin/C# file that Magika labels `text/plain` never reached `code.source_file`, because the `text/plain` chain pins `text.plain`; and that `.ts` mapped to MPEG-TS via mimetypes, producing a spurious `misnamed_file`.
Decision: In `ConverterRegistry._ranked`, when a chain applies, any available converter outside the chain whose `can_handle` confidence is strictly greater than every chain member's goes first; the chain stays as the fallback. Detection maps .ts/.tsx/.mts/.cts to application/typescript and .js/.mjs/.cjs to application/javascript. `detect.is_textual()` treats text/*, JSON/XML/YAML/TOML, +json/+xml, and source-code mimes as one family for the declared-vs-detected and misnamed-file checks. Root ruff config excludes `fixtures/**/expected.*` (ruff was reformatting code fences in goldens). Tracked zero-byte junk files from shell redirects were removed and `tests/test_repo_hygiene.py` now fails on any empty tracked file.
Alternatives: add `code.source_file` to the text family's chain (couples two families); per-extension chains (chains are per mime).
Consequences: chains still fully decide order among their own members.

## D-0022: Full CLI (P1-T09)
Date: 2026-10-08
Task: P1-T09
Status: accepted
Decision: The CLI is a thin client over `intomd.library` (convert/batch/doctor/capabilities/version/detect/serve, config file with env and flag precedence, remote mode over REST, `--json` on failure). Interactive default profile is `compact` only when Markdown goes to a terminal; file and machine output default to `full` (part4 4.0 rule 3). Batch idempotency compares the input sha256 with the previous manifest line and the sidecar's `source_hash` (the spec's `content_hash` hashes the output, so it cannot be checked before converting). Exit code 3 = partial success (D-0017). Details and alternatives: `docs/decisions/P1-T09.md`.
Deferred: an `Options.engines` per-family preference so the config `[engines]` table applies per input (today `--engine` maps to a single forced converter).

## D-0023: API additions (P1-T10)
Date: 2026-10-08
Task: P1-T10
Status: accepted
Decision: REST options are derived from `intomd.library.Options` (client-settable subset plus hostile-input caps; server-controlled fields listed with reasons; a drift test fails on any unclassified field). API keys also load from `INTOMD_KEYS_FILE` (keys.json; HMAC-SHA256 with the pepper; per-key limits, IP/UA restrictions, expiry; hot reload keeps the last good file). Host-only `intomd-admin` CLI (keys, jobs, reap); no admin HTTP endpoints (part1 7.4). `/metrics` exists only when `INTOMD_METRICS_TOKEN` (16+ chars) is set and requires it as a bearer token; counters live in Redis so API and workers share them. `GET /v1/warnings` and `JobOut.warnings` added (deferred by D-0017). OpenAPI: operationId/summary/description/tag/security/error responses on every route; Spectral 6.15.0 clean; a Python lint test runs on every test run. Name `INTOMD_KEYS_FILE` (Part 4 says INTOMD_API_KEYS_FILE) kept for continuity. Details: `docs/decisions/P1-T10.md`.

## D-0024: MCP server (P1-T11); MIT-0 and MIT-CMU allowed; anchored ignore rules
Date: 2026-10-08
Task: P1-T11
Status: accepted
Decision: `intomd-mcp` on the official MCP Python SDK 2.x (MIT): five Phase 1 tools, job resources, a provenance prompt; local mode over `intomd.library`, remote mode over REST; default profile `agent`, max_tokens 8000 (cap 50000); pagination wraps the renderer's opaque cursor and reconstructs the body byte for byte; HTTP transport requires a bearer token and binds loopback; file tools accept absolute paths under allowed roots only (default: the working directory; the spec's "cwd plus home" is narrowed deliberately). Details: `docs/decisions/P1-T11.md`.
License policy: add MIT-0 (cffi, via mcp -> pyjwt[crypto] -> cryptography; strictly more permissive than MIT) and MIT-CMU (Pillow, via pikepdf; HPND-family, already allowed as HPND) to the default allowlist.
`.gitignore`: `data/`, `*.sqlite`, `*.db` are anchored to the repo root; unanchored they silently excluded `packages/mcp/tests/data/` and the data family's fixtures. The repo hygiene test skips when `git ls-files` cannot run (worktree mounted in a container).
Pending: mount `intomd_mcp.http.build_http_app` at `/mcp` in the API behind key auth (P1-T14/P4).

## D-0025: Code family (P1-T03) merged
Date: 2026-10-08
Task: P1-T03
Status: accepted
Decision: `code.source_file` (about 43 code mimes, chains `[code.source_file, text.plain]`, specialist ranking per D-0021) and `code.repo_pack` (zip/tar.gz repos, GitHub URLs via a codeload FetchRequired, gitignore, budget actions, signatures-only) with Secretlint-style secret redaction that preserves source line numbering. Sizes are source bytes; `packed_bytes` reports emitted size. Goldens: 8 fixtures, Skeptic-accepted after two review rounds (line numbering, byte counts). The sidecar `redactions` list (part2 8b.4) waits for the core `Document.sidecar_extra` hook. Details: `docs/decisions/P1-T03-code.md`.

## D-0026: Core renderer and IR changes requested by the converter families
Date: 2026-10-08
Task: P1-T01..P1-T06 (core support)
Status: accepted
Context: Skeptic reviews of the Phase 1 family goldens found defects that belong in core, not in converters.
Decision (additive IR, schema stays "1.1"):
- Render `Document.children` (archives, later email attachments) as `## <path>` sections after the parent body, headings shifted beneath, warnings merged with the child path, a sidecar `children` index; the child's title becomes the section heading.
- Definition lists: `ListBlock.attrs["kind"]="definition"` renders `**term**` plus 4-space-indented definition lines.
- `Document.sidecar_extra` for family-specific sidecar lists (e.g. code `redactions`); reserved keys rejected.
- `InlineSpan.change` (`insert`/`delete`, with author/id) renders in place: accepted by default, CriticMarkup on request.
- `Metadata.slides` and `Metadata.sheets`; ` (hidden)` suffix for hidden headings/slides; slide notes under a `Notes` heading one level below the slide; `Table.attrs["header_synthesized"]`.
- Hidden text from `removed_hidden_elements` `detail.hidden_text` is scanned for injection (findings tagged hidden) but never rendered; `counts.removed_nonprinting` reads warning detail, never element counts; `counts.furniture_removed` adds converter-reported `removed_running_header_footer` counts; `counts.links` includes inline links.
- Footnotes referenced before the first heading are defined at the end of the preamble.
- Pipe/KV table cells keep inline Markdown and are never line-start-escaped; minimal HTML tables keep cells plain text (part3 15 rule 3).
- Detection: Magika `ipynb`/`sqlite`/`parquet` labels and `.sqlite/.db/.parquet` extensions mapped; OOXML macro-enabled variants and text/rtf vs application/rtf are not "misnamed".
- When only Unavailable converters claim a mime, the error names the reason and what to install (`code` set to the reason's warning code when it is one).
- Fixture `requires`/`requires_modules` skip fixtures whose extras are missing.
- Frontmatter `source_type` enum amended with `archive` (as with `text` and `markdown`, D-0017).
- Token-budget pagination counts page 1's head blocks; Contents is dropped first when they alone exceed the budget.
Details: `docs/decisions/P1-core-renderer.md`.

## D-0027: PDF family (P1-T01 PDF part) merged
Date: 2026-10-08
Task: P1-T01
Status: accepted
Decision: Default engine `documents.pdfium_text` (pypdfium2, BSD-3/Apache-2.0: character boxes, font sizes, marked content) with headings from the structure tree, then the outline, then font size; running header/footer removal; two-column reading order; simple tables; links; forms. `documents.docling_pdf` in the `docs` extra (docling-slim, MIT) and Unavailable otherwise; it never downloads models without allow_network. pikepdf (MPL-2.0) sanitizes first (JS/actions/launch/embedded files/XFA stripped and reported; encrypted-with-user-password refused as `encrypted_no_password`, the more specific Part 2 code, instead of Part 1's `encrypted_content`; page cap truncation). Image-only pages report `pages_without_text` and `ocr_unavailable` until the Phase 2 OCR pipeline exists. The `docs` extra caps typer below 0.27 across the universal lock; accepted (docs/cli.md regenerated). pypdfium2's license metadata is free text, recorded as an override. 7 fixtures Skeptic-accepted. Details: `docs/decisions/P1-T01-pdf.md`.

## D-0028: Web page family (P1-T02) merged
Date: 2026-10-08
Task: P1-T02
Status: accepted
Decision: Chain `web.trafilatura` (Trafilatura 2.3.1, Apache-2.0, then each block rebuilt from the matched DOM element to restore code languages, list starts, spans, captions, footnotes, math), `web.rules` (Defuddle-style rules in Python), `web.html_raw` (full body, always warns). Fallback when Trafilatura keeps under 200 characters or under 25% of the page text unless it kept 90%+ of the page, with the reason in `detail`. Hidden content (CSS/aria/hidden/noscript/template/comments/zero-size/off-screen/white-on-white/stylesheet classes) removed and reported with `hidden_text` (including raw tag-character runs) for the renderer's injection scan; visible text never rewritten. Metadata precedence: JSON-LD, citation_*, og/twitter, Trafilatura, `<title>`/h1; canonical URL adopted only when same-origin. Paywall prompts removed; lazy images restored from data-src/srcset. jusText license override (BSD-2-Clause, verified). 12 fixtures Skeptic-accepted after two rounds. Details: `docs/decisions/P1-T02-web.md`.

## D-0029: Data family (P1-T05) merged
Date: 2026-10-08
Task: P1-T05
Status: accepted
Decision: `data.csv` (CSV/TSV, dialect sniffing checked against field-count consistency, BOM and charset handling, header detection, caps), `data.json` (JSON/JSONL, source number spellings, records tables when shared keys exceed 60%, `## Schema` then `## Data`), `data.yaml` (SafeLoader subclass; unknown and python tags become inert text with `yaml_unsafe_tags`; alias bombs bounded), `data.toml`, `data.xml` (defusedxml; DTD and entities stripped and reported; `## Structure` summary; records for elements repeated more than 5 times), `data.sqlite` (read-only immutable temp copy, query_only, trusted_schema off, statement timeout; schema, sample rows, per-column stats), `data.parquet` (pyarrow in the `data` extra; Unavailable otherwise), and a `data.connection_string` refusal stub. Source key order is preserved; scalar keys after nested sections get their own heading. Sampled tables never contain marker rows (attrs plus a note paragraph). YAML/TOML/XML keep their (sanitized) raw source in a `## Source` block. Four fixtures assert the exported CSV byte for byte. 14 fixtures (1.0 thresholds) Skeptic-accepted after two rounds. Details: `docs/decisions/P1-T05-data.md`.

## D-0030: Office family (P1-T01 Office part) merged
Date: 2026-10-08
Task: P1-T01
Status: accepted
Decision: Native lxml/openpyxl converters rather than pandoc (GPL, external) or python-docx/python-pptx (python-pptx pulls Pillow; neither is needed at runtime): `documents.docx` (tracked changes as in-place `InlineSpan.change` spans, TrackedChange blocks only for whole-paragraph changes, moves, and formatting changes; comments with replies; inferred headings; lists; merged-cell tables; footnotes/endnotes; text boxes; OMML to LaTeX; hidden and white-on-white text excluded and counted), `documents.pptx` (slides, notes, tables, charts as data tables, SmartArt, hidden slides), `documents.xlsx` (every sheet including hidden, cached values formatted with the cell's number format and `raw_value` kept, formulas on cells, column types, regions, merged cells, named ranges; header rows also detected from defined names, autofilters, and tables), `documents.odf`, `documents.rtf` (striprtf), `documents.libreoffice` for legacy formats via `soffice` in the sandbox (Unavailable with `libreoffice_missing` otherwise), `documents.iwork` (Unavailable). Every package goes through a shared sanitizer first (zip limits, encryption detection, macro/ActiveX/OLE removal, external relationship filtering, DOCTYPE refusal). No LibreOffice fixture yet: it needs soffice to generate (tracked for P1-T19; contract test skips it). 7 fixtures Skeptic-accepted after three rounds. Details: `docs/decisions/P1-T01-office.md`.

## D-0031: Ebooks, notebooks, archives (P1-T01 EPUB part, P1-T06) merged
Date: 2026-10-08
Task: P1-T06
Status: accepted
Decision: `documents.epub` (spine order, nav/NCX titles, linked EPUB3 footnotes including cross-file endnotes with their visible markers, images and captions, page-list page breaks and page count, Dublin Core metadata including editors, DRM detection that ignores font obfuscation, safe XML, zip limits; the cover goes to metadata, not a numbered figure), `documents.ipynb` (verbatim code cells, outputs fenced `output`, markdown cells through the shared parser with `$...$` math as InlineSpan.math, raw cells fenced by language name, DataFrame HTML as tables, images, output caps), `archives.archive` (zip, tar.*, single-file gz/bz2/xz; tree plus summary; convertible members converted through ConvertContext.convert_child into `Document.children`, rendered as `## <path>: <title>` sections; 500 MB / 10,000 entries / depth 3 / 100:1 ratio limits counted while streaming; unsafe paths, symlinks, encrypted entries refused; nothing written to disk), `archives.sevenzip` (py7zr in the `7z` extra; LGPL-2.1 used unmodified as a separate package, so allowed as an optional extra). An empty header cell renders as `col_N` per part3 15 (empty headers are made unique), without the synthesized note. 9 fixtures (7z one requires the extra) Skeptic-accepted after three rounds. Details: `docs/decisions/P1-T06-ebooks-archives.md`.

## D-0032: Competitive benchmark loop is a launch gate
Date: 2026-10-08
Task: P4-B01..P4-B04
Status: accepted (owner directive)
Context: The owner asked that benchmarking against the existing tools be part of the final development phase, iterating until intomd beats them all. The spec only mentions a shadow-run benchmark story in the launch content (P4-T11) and has no competitive benchmark or win criterion.
Decision: Add P4-B01 to P4-B04 (harness, corpora and metrics, iterate-to-win loop, published results) ahead of launch content, and add a benchmark gate to G4. "Beat" means at or above the best competitor's primary metric per category on a held-out split, ties within the 95% interval counting. Competitors run in isolated containers for measurement only and are never dependencies, so GPL/AGPL/RAIL tools (Marker, MinerU, pymupdf4llm, pandoc) can be measured without entering the default install. Paid APIs are benchmarked only after the owner approves the spend (human gate). The only allowed exemption is a category whose winner depends on a license intomd cannot ship by default, and only when intomd's opt-in extra matches it; exemptions are logged here with numbers and published.
Alternatives: benchmark only on the intomd fixture corpus (self-graded, not credible); require a win on every metric (speed vs. quality trade-offs make that unfalsifiable); start the loop in Phase 1 (competitors and our converters both change before launch; the shadow-run command from P1-T18 and the fixture scorer are the seed).
Consequences: launch waits on the loop. Scanned-PDF OCR and formula-heavy papers are the likeliest categories to need the exemption path, since the strongest tools there use GPL or RAIL-licensed models; the loop must try permissive models first. Results, including losses, are published in docs/benchmarks.md.
Council: not convened (owner directive; the win criterion and exemption rule are open to owner revision).

## D-0033: SEC EDGAR converter and social stubs (P1-T07) merged
Date: 2026-10-08
Task: P1-T07
Status: accepted
Decision: `specialized.edgar` is built directly on the documented EDGAR endpoints (Archives, filing index, data.sec.gov submissions, company_tickers.json, efts search) instead of edgartools: edgartools is MIT but hard-depends on Unidecode (GPL-2.0-or-later) and does its own HTTP outside netguard. It claims EDGAR URLs and saved filings at 0.95, emits one H2 per Part/Item, exact financial tables (spacer columns removed, `$(1,204)` kept whole), cover facts from `dei:`, and exhibits as a table (children with `edgar_exhibits=true`). Network only with `allow_network`, identity from `INTOMD_EDGAR_IDENTITY`, 5 req/s per process, no retry on 403/429. `netguard.fetch` sends that identity as the User-Agent to sec.gov and its subdomains (per hop, unless the caller set one), so library and API URL inputs are not refused. Reddit and HN stubs (`web.social_reddit`, `web.social_hn`) are Unavailable unless `INTOMD_ENABLE_SOCIAL` is set; full adapters are P3-T02. Details: docs/decisions/P1-T07.md.
Alternatives: edgartools (GPL transitive dependency, unguarded network); edgartools in the nonfree extra (loses EDGAR from the default install).
Consequences: 3 fixtures at 1.000 (threshold 0.95); the TVA filing is treated as a US Government work (17 USC 105, defensible, not settled; D-P1-T07-4). XBRL statement tables wait for the XBRL converter. CLI `--form`/`--year` need library support for bare tickers and are deferred; use a browse-edgar URL.
Council: not convened; independent Skeptic review rejected two goldens (Wingdings check box inside ix tags, dropped filer address block); both fixed in the converter.

## D-0034: Self-host scripts and signed release pipeline (P1-T14, P1-T16) merged; api image budget 600 MB
Date: 2026-10-08
Task: P1-T14, P1-T16
Status: accepted
Decision: `deploy/bootstrap.sh`, `backup.sh`, `restore.sh`, `upgrade.sh` (shared `lib.sh`, data work through `deploy/stackctl.py` in a one-off api container), tested end to end on Docker Desktop including a failed upgrade that rolls back to the pre-upgrade backup. `images.yml` pushes by digest, scans with Trivy (fixable HIGH/CRITICAL fail), attaches a syft SPDX SBOM, signs and attests with cosign keyless, then tags. `release.yml` validates tag and versions; `v*-rcN` goes to TestPyPI only; final tags publish to PyPI, npm, and the MCP registry under `environment: release` with OIDC only, and nothing publishes until the owner sets `INTOMD_PUBLISH_ENABLED=true` and configures reviewers (the run fails if the environment has none). The api image budget rises from 480 MB (D-0012) to 600 MB: the API loads the converter registry for `/v1/capabilities` and IR-cache keys, so it cannot drop converter dependencies today (556 MB after stripping numpy tests; worker 888 MB). Details: docs/decisions/P1-T14-T16.md (D-a to D-j).
Alternatives: drop converters from the api image (capabilities and dedup keys would be wrong); split converter metadata from the registry now (larger core change; tracked as a deferred request, about 100 MB saving).
Consequences: owner setup is required before any publish (GitHub environments with reviewers, PyPI/TestPyPI trusted publishers for intomd, intomd-converters, intomd-mcp, npm `@intomd` scope, the publish variable). Backups cover SQLite and the filesystem blob store only.
Council: not convened.

## D-0035: Email family `comms` (P1-T04) merged; native MSG reader on olefile
Date: 2026-10-08
Task: P1-T04
Status: accepted
Decision: `comms.eml` (stdlib email, policy.default; multipart/alternative prefers HTML through the web pipeline's full-body mode; forwarded messages and attachments through `ctx.convert_child` with depth, size, and count caps and a warning for every unconverted attachment), `comms.mbox` (stdlib mailbox, threads from References with a subject fallback, message cap), `comms.msg` native on olefile (BSD-2: property streams, recipients, transport headers, code pages, compressed RTF with HTML de-encapsulation, attachments, embedded messages). Part 2 of the spec makes olefile the default MSG path and extract-msg (GPL-3) an opt-in engine, so olefile leaves `[nonfree]` in the license allowlist and `comms.msg_extract` is the second, nonfree-only engine in the chain; Part 4 still names the extra `nonfree` and `intomd` now forwards it (never part of `all`). Shared changes: one line-joining routine (`intomd_converters/text/lines.py`) for text.plain and mail bodies (join on 60+ character wraps or a lowercase start; lists and indented code never joined; kept lines become a hard-break paragraph rendered with CommonMark backslash breaks); child documents shift headings uniformly; the RFC 5322 sniff in detection needs From plus Message-ID, Received, MIME-Version, or Return-Path and stronger evidence under text-like extensions. Details: docs/decisions/P1-T04-comms.md.
Alternatives: extract-msg as the only MSG engine (GPL, out of the default install); convert HTML bodies with `convert_child` (bodies would count toward attachment depth and lose quotes and signatures to Trafilatura).
Consequences: 9 fixtures at 1.000 (threshold 0.97). TNEF is warned, not decoded. Deferred core requests: Provenance.timestamp, compact profile dropping reply and signature roles, a signature role, List-Id `<` escaping.
Council: not convened; two independent Skeptic rounds (3 rejects, then 2 shared-code regressions and a truncation defect), all fixed in code.

## D-0036: Fixture corpus at 94 with provenance check and nightly scorecard (P1-T19); integration suite (P1-T15); docs (P1-T17)
Date: 2026-10-08
Task: P1-T15, P1-T17, P1-T19
Status: accepted
Decision: The golden corpus is 94 fixtures (85 outside email), all self-generated CC0 except two public-domain EDGAR recordings credited in CREDITS.md. `tools/check_fixture_provenance.py` runs in pytest and nightly; `tools/scorecard.py` writes the per-family and per-converter scorecard as a nightly artifact. Converter fixes exposed by the new fixtures went in with tests (cross-page PDF tables merge only bottom-to-top fragments with per-row page provenance, docx list starts, xlsx merged regions, web source order and layout-table unwrapping with a layout signal, notebook stream concatenation, ALL-CAPS headings and whitespace tables in plain text, MathML, gitignore negation). P1-T15 adds the integration workflow on the bootstrapped compose stack, fast and network security tiers, and a Playwright suite (with axe) that fails on any off-origin request; bugs it found are pinned by strict xfail markers until fixed. P1-T17 adds README, CONTRIBUTING, SECURITY, CODE_OF_CONDUCT, and a strict MkDocs site with a generated converters matrix and a test that runs every runnable README command.
Alternatives: count fixtures without independent review (rejected: two Skeptic reviews rejected 4 of 23 and flagged 6 risky heuristics, all fixed in code).
Consequences: the fixture count and converter matrix must be regenerated when fixtures change (drift tests enforce it). Deferred: render/tables._html does not fill missing cells (the xlsx converter works around it).
Council: not convened.

## D-0037: Rename intomd to ezmd before the first release
Date: 2026-10-08
Task: P1-T16
Status: accepted (owner decision)
Context: The owner found "intomd" generic (it names the category, not a product). Nothing had been published (the v0.1.0-rc1 run was cancelled before any upload), so a rename was still free.
Decision: Rename everything to ezmd ("easy md"): PyPI `ezmd`, `ezmd-converters`, `ezmd-mcp`; import packages `ezmd`, `ezmd_converters`, `ezmd_mcp`, `ezmd_api`, `ezmd_fetch_node`; CLI `ezmd`, `ezmd-mcp`, `ezmd-admin`, `ezmd-score`, `ezmd-golden`; env vars `EZMD_*`; npm `@ezmd/sdk`; images `ghcr.io/larpey/ezmd-*`; MCP name `io.github.larpey/ezmd`; repository `larpey/ezmd`. Checked on 2026-10-08: the PyPI names and the npm `@ezmd` scope were free; npm `ezmd` (unscoped) is a 2015 README previewer, which does not matter since the SDK is scoped; github.com/ezmd is an empty organization, so the repository lives under larpey; the only USPTO mark for EZMD (serial 87153758, health-information website) is dead/abandoned. Entries before this one keep the name intomd (append-only); fixture inputs that contained the old name were regenerated from their generators and every golden was regenerated, with a diff check showing only the name, version stamps, content hashes, and runtime fields changed.
Alternatives: keep intomd (clear but generic); n2md ("into" pun, reads as "N-format to md", collides with a Notion converter of the same name); omd (collides with the Checkmk `omd` command and crowded search); markitall (too close to Microsoft's MarkItDown).
Consequences: CI and image names change; old `INTOMD_*` variables are not read (no deployments exist yet). The npm `ezmd` org and the ezmd.dev domain should be registered by the owner to hold the name.
Council: not convened (owner decision).

## D-0038: Release candidates publish to PyPI as pre-releases; TestPyPI dropped
Date: 2026-10-08
Task: P1-T16
Status: accepted (owner decision)
Context: TestPyPI's `ezmd` belongs to another user (SiLeader, one 1.0.0 upload of an unrelated markdown formatter), so a release candidate cannot rehearse the real package name there. Real PyPI's `ezmd`, `ezmd-converters`, and `ezmd-mcp` are free.
Decision: `vX.Y.Z-rcN` tags publish to PyPI as PEP 440 pre-releases (pip and uv install them only with `--pre` or an exact pin) through the same `release` environment and owner approval as finals; npm and the MCP registry stay final-only. The `testpypi` job and environment are removed.
Alternatives: keep TestPyPI for the other two packages and publish `ezmd` only at the final (the main package would never be rehearsed and `pip install ezmd` from TestPyPI would fetch the other project).
Consequences: the first candidate claims all three PyPI names. PyPI versions are permanent, so a broken candidate is yanked and followed by the next rcN rather than replaced.
Council: not convened (owner decision).

## D-0039: Dependency caps for pre-release majors; LICENSE/NOTICE in dists; license gate covers extras
Date: 2026-10-09
Task: audit (fix-packaging)
Status: accepted
Context: the pre-release audit found `pip install --pre ezmd` resolved httpx 1.0.dev6, which dropped httpcore (imported by netguard), so URL conversion crashed; no wheel or sdist shipped LICENSE or NOTICE; the license gate exported the tree without extras although it claims to cover them.
Decision: httpx is capped `<1` everywhere and ezmd declares httpcore; any direct dependency with a pre-release of a new major is capped below it (lxml `<7`), enforced by tests/test_packaging.py. ezmd, ezmd-converters and ezmd-mcp carry committed copies of the root LICENSE and NOTICE (`license-files`), kept byte-identical by a test. The `mcp`/`all` extras pin `ezmd-mcp==V`. The gate runs over `--all-extras --no-extra nonfree`; NVIDIA CUDA runtime wheels pulled by torch on Linux via the `docs` extra are a named `[platform_runtime]` exception listed by exact package name (CPU-only torch cannot be expressed in PyPI metadata). CI runs `uv lock --check`. Details: docs/decisions/audit-fix-packaging.md.
Consequences: changing the platform_runtime list is a policy decision; a new NVIDIA package fails the gate until reviewed.
Council: not convened (audit fix).

## D-0040: The API derives client IPs only from Caddy's X-Real-IP on the internal network
Date: 2026-10-09
Task: audit (fix-security)
Status: accepted
Context: uvicorn ran with `--proxy-headers --forwarded-allow-ips "*"` and took the leftmost, client-supplied X-Forwarded-For entry, so behind Cloudflare a client could choose the IP used by rate limits, quotas, Turnstile binding and API-key IP pinning.
Decision: uvicorn runs with `--no-proxy-headers`. Caddy overwrites `X-Real-IP` with its trusted-proxy-aware `{client_ip}` on every `reverse_proxy` block (`trusted_proxies_strict`). Compose sets `EZMD_TRUST_PROXY_HEADER=X-Real-IP` and `EZMD_TRUSTED_PROXIES` to the private ranges; the API has no published port, so only containers on the internal network can reach it. Header values that are not valid IPs are ignored. The fetch-node CIDR check uses the same `client_ip()`.
Alternatives: pin Caddy's container IP (fragile across compose networks); keep proxy headers with a narrowed allow-list (uvicorn still trusts the whole XFF chain from that peer).
Same branch: brotli decoding is bounded with `output_buffer_limit`; MCP tool calls may set only whitelisted options and may only lower `ezmd-mcp --max-*` limits; Pillow `MAX_IMAGE_PIXELS` is 50 MP (spec part1 8.2).
Council: not convened (audit fix).

## D-0041: Golden fixtures pass only with no hard invariant failure; sidecars compared
Date: 2026-10-09
Task: audit (fix-tests)
Status: accepted
Context: the 0.95 similarity threshold passed a leaked hidden-injection paragraph, a downgraded `injection_risk`, dropped table spans, changed totals and removed links.
Decision: `ezmd.testing.invariants` adds exact checks against the golden (math, block counts, list nesting, table spans, link and image targets, numeric tokens by default, frontmatter warnings/injection_risk/truncated); meta.toml gains `must_contain`/`must_not_contain`; normalized `expected.sidecar.json` is compared exactly. CI gains an `extras` job (7z, data). Details: docs/decisions/audit-fix-tests.md.
Consequences: goldens were generated on Windows; a platform difference now fails CI and is treated as a real difference, not a reason to loosen.
Council: not convened (audit fix).

## D-0042: server.json lists no remote until the API mounts /mcp; doctor reads extras from metadata
Date: 2026-10-09
Task: audit (fix-docs)
Status: accepted
Context: server.json advertised `https://{host}/mcp`, which the API never mounts (D-0024 pending), and `ezmd doctor` recommended unpublished extras.
Decision: `remotes` is removed until apps/api mounts `/mcp` (a test ties the two together; deviates from part4 4.4.5 until then). Doctor reads published extras from the installed metadata and shows unpublished spec extras as coming later. `--engine pdf=docling` resolves by id parts; naming an unavailable converter names its extra. Release notes come from the exact changelog heading or `[Unreleased]`, else the release fails. Details: docs/decisions/audit-fix-docs.md.
Council: not convened (audit fix).

## D-0043: Key source restrictions are checked on every hop; a challenge JWT covers 5 URL jobs
Date: 2026-10-13
Task: audit (residual security items)
Status: accepted
Context: an API key's `allowed_sources` / `disabled_sources` were checked only on the submitted URL, so an open redirect on an allowed host reached any public host; converter-requested fetches (`follow_fetch_required`) skipped the check too. The Turnstile challenge JWT was accepted for any number of jobs until it expired, while part4 4.11.2 allows 5. The fetch worker looked up `residential_allowed` in the database only, so `keys.json` keys were failed on residential-only redirects.
Decision: `netguard.fetch` takes `host_allowed: Callable[[str], bool]` and calls it on each hop right after `validate_url`, raising `SourceNotAllowed` (`forbidden`) before any request to that host. The fetch worker builds it from the job's key (file or database; a missing or revoked key allows nothing) and applies it to `follow_fetch_required` URLs. The challenge JWT carries a nonce; each convert call spends one use with `gauge_incr("challenge:<nonce>", ttl + 5)` and more than `CHALLENGE_MAX_USES` (5) needs a new Turnstile token. Key lookup for the worker covers file keys.
Alternatives: re-check only the final URL after redirects (the request to the forbidden host has already been sent); bind the JWT to a job count in its claims (stateless but cannot be decremented).
Consequences: the residential fetch node does not apply the per-hop check yet; it gets the same rule with its Phase 3 redirect handling.
Council: not convened (audit fix).

## D-0044: Turnstile siteverify goes through a fixed-upstream Caddy relay; no verdict is a 503
Date: 2026-10-13
Task: audit (rc5 pre-release testing)
Status: accepted
Context: the compose `api` container sits only on the `internal` network (Part 1 section 8.1), so its siteverify POST to challenges.cloudflare.com could never connect. `verify_turnstile` turned the connection error into `False`, and every URL job on a Turnstile-enabled instance got `turnstile_failed` (403) as if the visitor had failed the challenge. Part 4 4.9.4 has the API reach Cloudflare through an `egress-proxy` (Squid) in a public overlay that does not exist yet.
Decision: Caddy, which already has egress, serves an internal-only site `http://:9180` that answers only `POST /turnstile/v0/siteverify` from private source addresses, caps the body at 16 KB, strips forwarding headers, and reverse-proxies to the single upstream `https://challenges.cloudflare.com` (TLS verified by Caddy). Port 9180 is never published and the site has no access log (the body carries the secret). New setting `EZMD_TURNSTILE_VERIFY_URL` (default: Cloudflare's URL, so non-compose installs are unchanged); compose sets it to `http://caddy:9180/turnstile/v0/siteverify`. `verify_turnstile` returns False only for a real verdict (`success: false` with visitor error codes; the JSON is read at any HTTP status because Cloudflare answers a bad secret with 400). A network error, a reply without a verdict, or `missing-input-secret`/`invalid-input-secret` raises `TurnstileUnavailable`, logged at ERROR (never with the secret), and the API answers the new code `turnstile_unavailable` (503, `Retry-After: 30`). Checked live: through the relay, Cloudflare's always-pass test secret verifies, the always-fail one returns False, and a bogus secret is `turnstile_unavailable`.
Alternatives: route siteverify through worker-fetch as an RQ job (the API would block on the fetch queue behind URL fetches of up to 120 s, and Redis plus a worker become hard dependencies of the challenge); give the API an iptables egress allow-list (the API would need root and CAP_NET_ADMIN at start and a route to the internet, which is more privilege on the public-facing container); the spec's Squid `egress-proxy` (one more service and image for one hostname; it can still be added for the public overlay, and the setting works with it).
Consequences: a self-host behind its own egress control must let Caddy reach challenges.cloudflare.com:443. The relay is reachable by every container on the compose networks, which only lets them ask Cloudflare to verify tokens. The TypeScript SDK's error-code union does not list `turnstile_unavailable` yet (packages/sdk-ts).
Council: not convened (audit fix).

## D-0045: ezmd RQ workers run with worker_ttl 45 s so /readyz's 60 s window holds when idle
Date: 2026-10-13
Task: audit (rc5 pre-release testing)
Status: accepted
Context: `/readyz` needs a worker heartbeat within 60 s (part1 7.3), but RQ's default `worker_ttl` is 420 s and an idle worker only beats when its blocking dequeue times out (`worker_ttl - 15` = 405 s). An idle, healthy stack answered 503 most of the time.
Decision: `ezmd_api.worker.build_worker` creates every worker with `worker_ttl=queue.WORKER_TTL_S` (45 s): idle workers beat every 30 s (dequeue timeout) and busy ones every 30 s (`job_monitoring_interval`), twice per window. The window stays the spec's 60 s (`queue.HEARTBEAT_MAX_AGE_S`). A test pins both cadences below the window and the worker key's expiry above it.
Alternatives: widen the readiness window to ~420 s (a dead worker would look ready for 7 minutes, and the spec says 60 s); a separate heartbeat thread (duplicates what RQ already does).
Consequences: each idle worker makes one BLPOP round trip to Redis every 30 s instead of every 405 s.
Council: not convened (audit fix).

## D-0046: The reaper reconciles active jobs with RQ every 30 s
Date: 2026-10-13
Task: audit (rc5 pre-release testing)
Status: accepted
Context: Redis runs without persistence (`--save '' --appendonly no`), so a Redis restart drops every RQ job while the database still says `queued`; the reaper only looked at fetching/converting/rendering rows, so those jobs stayed queued until retention and held their caller's concurrency slot. A worker that died mid-job left its row `converting` until the queue timeout plus 150 s grace (about 12.8 minutes on `default`).
Decision: `JobQueue.liveness(job_id, rq_job_id)` reports WAITING (queued/deferred/scheduled), RUNNING (started, and the RQ job's own heartbeat, which its worker refreshes every 30 s, is within 60 s), LOST (no such RQ job; finished, failed, stopped or canceled while the row is active; or started with a silent worker), or UNKNOWN (Redis unreachable: do nothing). `purge.reconcile_queue` runs on every reaper tick before `reap_stale`, over active non-residential rows unchanged for 60 s (so an enqueue or hand-off in flight is never judged): a LOST `queued` row is enqueued again, since no worker started it; any other LOST row fails with `internal_error` ("The worker running this job stopped before it finished"). Failing a row frees the slot, because admission counts active rows. Inline mode never reports LOST. `ezmd-admin reap` prints the count as `lost=`.
Alternatives: requeue started jobs too (a poison input that kills its worker would loop forever); shorten the stale grace instead (the stale path has to allow a job's full wall time); use RQ's StartedJobRegistry cleanup (it only moves RQ's own record and does not touch our rows).
Consequences: a job that crashes its worker reaches `failed` about 60-90 s after the last heartbeat. A requeued job keeps its id, so clients following it see it start late rather than fail.
Council: not convened (audit fix).

## D-0047: The conversion child relies on the container's cgroup pids limit, not RLIMIT_NPROC 64
Date: 2026-10-13
Task: audit (rc5 pre-release testing)
Status: accepted
Context: `isolation._apply_limits` set RLIMIT_NPROC to 64. The kernel counts that limit over every thread of the real uid on the whole host, and every ezmd container runs as 10001, so the API's uvicorn threads, the purge loop, other workers and other stacks all count against the child. numpy/OpenBLAS and ONNX Runtime (Magika) start a thread per host core; on a 24-core host the child failed while importing the converters (reproduced in the rc4 worker image with the `ezmdred` stack running; the same child converts with the fix).
Decision: when `/sys/fs/cgroup/pids.max` (v2) or `/sys/fs/cgroup/pids/pids.max` (v1) holds a number, the child sets no RLIMIT_NPROC: the per-container cgroup limit (compose `pids: 256`) is the fork-bomb cap and counts only that container. Without one (bare metal, or `pids.max` = `max`) the child sets RLIMIT_NPROC 4096 as a backstop. The child also defaults OMP_NUM_THREADS, OPENBLAS_NUM_THREADS and MKL_NUM_THREADS to 4 (an operator's values win), so the pools do not grow with the host's core count inside a 3-CPU, 256-pid container.
Alternatives: raise the fixed limit (any fixed value can be exhausted by other containers of the same uid); give each container its own uid (a larger compose change, and still host-wide per uid); count the uid's threads and add headroom (other containers' processes are not visible inside the pid namespace).
Consequences: a bare-metal worker whose user already has more than 4096 threads would still fail; ONNX Runtime's own intra-op pool is not governed by these variables (Magika's session options are core code).
Council: not convened (audit fix).

## D-0048: Inputs no converter can claim are refused with 415 before a job exists
Date: 2026-10-13
Task: audit (rc5 pre-release testing)
Status: accepted
Context: an upload whose detected type no converter handles (random binaries, `application/octet-stream`, images without an image converter) and real ELF binaries were accepted with 202 and then failed with 500 `conversion_failed`. Magika labels real ELF files `application/x-executable-elf`, which `ezmd.detect.EXECUTABLE_MIMES` does not list (checked with /bin/ls and libc in the rc4 image).
Decision: `ezmd_api.detection.detect_supported` (used for uploads, fetch-node media and fetched URL bodies) raises `Unsupported` when the type is executable (`detail.reason: executable`) or when the registry has neither a candidate (including experimental converters) nor a registered-but-unavailable converter for it (`no_converter`). Uploads answer 415 `unsupported_media_type` with `detail.mime` and `detail.reason`, and no job or blob is created; a fetched body fails its job with the same code (status 415 in the job error). Inputs a converter would claim but that turn out damaged still fail as `conversion_failed`.
Alternatives: extend the executable list in the API (it belongs in core detection; the no-converter rule already catches these types); keep accepting and fail later (the reported bug).
Consequences: the API image must register the same converters as the worker image, or an upload is refused that a worker could convert (both images install the same converter packages; extras that are missing register as unavailable, which still admits the input). Core follow-ups: add the Magika executable-group mimes (`application/x-executable-elf`, `application/x-mach-o`, `application/x-coff`, `application/x-android-dex`, `application/x-windows-driver`, ...) to EXECUTABLE_MIMES; Magika calls a megabyte of a single repeated byte an ISO image.
Council: not convened (audit fix).

## D-0049: Job-creation requests that create nothing give their rate-limit hits back
Date: 2026-10-13
Task: audit (rc5 pre-release testing)
Status: accepted
Context: `limit_job_creation` records the per-window and daily hits before the body is read, so an upload refused with 413, a request refused by concurrency admission (429), or a later window's 429 still used up the earlier window. A client retrying after `Retry-After` could lock itself out. `Retry-After` was also one second over the window (61 for 60 s): the reset was `int(oldest + window) + 1`.
Decision: `RateResult` carries the recorded hit (`key`, `member`) and the exact `reset_at`; `retry_after` is `ceil(reset_at - now)` and the reset epoch is its ceiling. `POST /v1/convert` refunds every hit the request recorded when it ends with `rate_limited`, `input_too_large` or `queue_unavailable` (the global active-job cap; the server's capacity, not the caller's use). Other errors (invalid options, blocked URLs, 415) still count, so the limit keeps bounding the work the instance spends on a caller.
Alternatives: check limits after reading the body (an anonymous client could then stream unlimited 200 MB bodies before being limited); peek without recording and record at the end (two concurrent requests could both pass).
Consequences: the memory backend's member is the hit's timestamp; two hits in the same `time.time()` tick refund either one, which is equivalent.
Council: not convened (audit fix).

## D-0050: Anonymous deduplication is scoped to the client IP hash in every mode
Date: 2026-10-13
Task: audit (rc5 red team, F2)
Status: accepted
Context: part1 7.1 forbids cross-IP dedup of anonymous requests only when `EZMD_PUBLIC_MODE=true`. With public mode off (the self-host default) an anonymous caller who submitted the same file or URL as another got that caller's finished job back: its id and display filename. Anonymous jobs are not bound to a caller and the id is the capability, so the second caller could read the result and `DELETE` the job (confirmed live by the red team from three IPs).
Decision: anonymous dedup always adds `client_ip_hash` to the lookup; keyed dedup stays scoped by key. `Idempotency-Key` was already scoped to the caller identity. This is stricter than the spec, which is recorded here; the spec's public-mode rule is a subset.
Alternatives: return a fresh job that reuses the cached IR (saves the conversion but needs a copy path for blobs; possible later); bind anonymous jobs to their IP for reads and deletes (breaks result links shared on purpose, which the threat model accepts).
Consequences: two anonymous users of a private instance who convert the same file each pay for the conversion.
Council: not convened (audit fix).

## D-0051: Admission is re-checked after the job row exists; anonymous jobs get a share of the cap; one upload slot per caller
Date: 2026-10-13
Task: audit (rc5 red team, uploads and rate limits)
Status: accepted
Context: `admit_job` counted active rows and the row was inserted later (after a multi-second blob write for large uploads), so a burst of parallel uploads from one IP was admitted as 2 jobs at `anon_concurrency=1` (confirmed live at N=8 and N=25); the same window existed for URL jobs and the global cap. Anonymous traffic alone could fill the global cap (default 6), so API keys got 503. Admission ran only after the whole body was parsed, so one caller could stream many large bodies at once.
Decision: (1) The row is inserted first, then `admit_job(created=True)` counts again with it included and the row is deleted when that refuses; two racing requests can both be refused, never both admitted. For uploads the input blob is written after admission and the row is removed if the write fails. A cheap pre-check still runs before the body is read. (2) Anonymous active jobs are capped at `EZMD_MAX_ACTIVE_ANON_JOBS` (default: the cap minus a third, at least one slot left for keys), 503 `queue_unavailable` beyond it. (3) Before the body is read a caller takes an upload slot (`gauge_incr` on `upload:<identity>`, at most its concurrency limit, released in `finally`, TTL 1 h as a crash bound); a second parallel upload is 429 without reading its body. 429 bodies carry `detail.reason`: `rate`, `concurrency` or `upload_in_progress`. The error code stays `rate_limited`: part1 7.5 lists the codes, and clients branch on `reason`.
Alternatives: a Redis slot released on every terminal transition (every state change in the API, workers, reaper and admin would have to release it exactly once; the row count is already the truth); a new `concurrency_limited` code (a contract change for a distinction `detail.reason` already makes).
Deferred: spooling uploads to a disk-backed volume and a global in-flight-bytes cap (the red team's OOM run did not reproduce: five 160 MB uploads peaked at 262 MiB of the api's 1 GiB).
Council: not convened (audit fix).
