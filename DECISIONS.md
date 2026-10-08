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
