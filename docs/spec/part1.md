# ezmd build specification

## Part 1: Mission, operating rules, foundation

This document is written for Claude Code. You are the sole engineer on this project. You will build it end to end without a human in the loop. Read all four parts before writing code. Part 1 (this file) defines the mission, how you operate, the core domain model, the converter and renderer interfaces, the job system and API contract, the security baseline, and Phase 0. Part 2 covers converter families. Part 3 covers the exact Markdown output format and profiles. Part 4 covers the fetch node, extension, MCP server, deployment, and the public instance.

Fixed decisions that all parts share are restated in section 1.3. Do not relitigate them.

---

## 1. Mission and definition of done

### 1.1 Mission

ezmd converts anything into LLM-ready Markdown: PDFs, Office documents, web pages, audio, video, social URLs, chat exports, code repositories, data files, email, notes-app exports, and specialized formats. It emits Markdown with YAML frontmatter under four output profiles (`full`, `compact`, `rag`, `agent`), an optional JSON sidecar with provenance, and an explicit warnings list so nothing is lost silently. It ships three ways: a free public instance with no accounts and no retention beyond 24 hours, a self-hostable Docker Compose stack that is identical in capability to the public instance, and an embeddable Python library plus CLI plus MCP server. Everything in the repo is Apache-2.0, and the default install pulls only permissively licensed code and model weights. The differentiators are not raw parsing quality (that is wrapped from Docling, Trafilatura, yt-dlp, faster-whisper and friends) but the things incumbents drop: heading hierarchy, tracked changes, comments, speaker labels, thread parents, page and bbox provenance on every block, spreadsheet formulas, a "what I could not read" report, token-aware profiles, and prompt-injection flagging.

### 1.2 Definition of done

The project is done when every item below is true. Do not report completion before then.

1. All phases in ROADMAP.md (Phase 0 through the final phase defined in Part 4) have state `done` in STATUS.md, or `shipped-experimental` with a documented limitation.
2. The fixture corpus in `fixtures/` passes its golden tests at or above the per-converter threshold recorded in `fixtures/thresholds.toml`. No converter is below threshold unless it is flagged `experimental`.
3. `docker compose -f deploy/compose.yml up` on a clean Linux x86_64 machine with Docker installed (no GPU, no prior state) brings up API, web UI, Redis, and a worker; uploading a PDF, a DOCX, a URL, and a 60-second MP3 through the UI each produce correct Markdown. A script `deploy/smoke.sh` automates this check and passes.
4. The public instance is deployed on the Hetzner Ashburn VPS, reachable over HTTPS with valid TLS, Turnstile active on link fetches, rate limits active, 24-hour purge job running, and `deploy/smoke.sh --remote <url>` passes against it.
5. The Raspberry Pi fetch node image builds, and a fetch node connected over Tailscale successfully claims and completes a residential fetch job end to end (verified at least once against a real short video URL from a sanctioned test source, logged in STATUS.md).
6. `docs/` contains: quickstart, self-host guide, API reference (generated from OpenAPI), CLI reference, library reference, MCP reference, extension guide, fetch node guide, output format reference, security and threat model, license policy, contributing guide.
7. CI is green on main: unit tests, golden tests, `ruff`, `mypy --strict` on `packages/core`, `pnpm lint`, `pnpm typecheck`, license allowlist check, `pip-audit`, `pnpm audit`, Docker image build for all services.
8. A release is tagged (`v0.1.0` or higher), the Python package is published to PyPI, the Docker images are published to GHCR with multi-arch (amd64, arm64) manifests, and the browser extension is built as an unsigned zip in release assets.
9. The Red team pass (section 2.3) has run against the public-facing phases and all `critical` and `high` findings are closed.
10. The final report (section 2.9) has been written to STATUS.md.

### 1.3 Fixed decisions (shared by all four parts)

- Working codename: **ezmd**. Python package `ezmd`, CLI `ezmd`, Docker image `ezmd`. The first task in ROADMAP.md is a name availability check (PyPI, npm, GitHub org, `.dev` and `.com` domain). If the name is taken on PyPI or npm, you pick another short name, record it in DECISIONS.md, and perform a global rename before any other task. Domain availability is informational only; do not purchase a domain (that is externally costly and requires the human).
- License: Apache-2.0 for everything in the repo. Default-install dependencies and weights must be one of: MIT, Apache-2.0, BSD-2/3, ISC, PSF, MPL-2.0 (unmodified), CC-BY-4.0. Forbidden in defaults: AGPL, GPL (any version), LGPL for statically linked code, SSPL, BSL, OpenRAIL-M and variants, CC-BY-NC, Qwen Research License, MinerU license, and any "custom terms" license. Forbidden licenses may appear only as clearly named optional extras (`pip install ezmd[chandra]`, `ezmd[pymupdf]`) that print the license name and a one-line summary on first use. CI enforces this with an allowlist in `tools/license_allowlist.toml`.
- Stack: Python 3.12 for core, converters, API, workers. TypeScript for the web UI (React + Vite, static build served by the API), the browser extension (MV3), and a thin JS SDK. FastAPI for HTTP. Redis + RQ for the job queue. SQLite by default for job metadata with a Postgres option via `EZMD_DATABASE_URL`. Local filesystem for blobs by default with S3-compatible (MinIO) option via `EZMD_BLOB_URL`. Magika + libmagic for content-type detection. uv for Python packaging, pnpm for JS. Docker Compose for self-host. Everything runs CPU-only by default; GPU is optional acceleration.
- Monorepo layout:

```
ezmd/
  packages/core/        # python lib: IR, converter registry, renderers, profiles
  packages/converters/  # one subpackage per converter family (documents, web, media, images, code, comms, data, notes, specialized)
  packages/mcp/         # MCP server
  packages/sdk-ts/      # thin TS client
  apps/api/             # FastAPI app + RQ workers
  apps/web/             # React UI
  apps/fetch-node/      # Raspberry Pi residential fetch worker
  apps/extension/       # browser extension (MV3)
  deploy/               # docker compose files, Caddy config, Tailscale notes, Pi image script
  fixtures/             # test corpus + golden outputs
  docs/
  DECISIONS.md, ROADMAP.md, STATUS.md, CLAUDE.md
```

- Architecture: the public VPS (Hetzner Ashburn) runs API, UI, queue, and converters. A Raspberry Pi at the owner's home runs `apps/fetch-node`, connects outbound-only to the VPS over Tailscale, polls the `fetch_residential` queue for jobs that need a residential IP (TikTok, YouTube, Instagram, etc.), downloads, extracts audio with ffmpeg, and uploads the audio back. The VPS never exposes the Pi. Fallback chain when no fetch node is online: platform captions endpoints, then mirror/embed endpoints, then yt-dlp with a PO-token sidecar, then `needs_user_action` asking the user to upload the file or use the extension.
- Output: Markdown with YAML frontmatter, four profiles, optional JSON sidecar. Part 3 is authoritative for format.
- Public instance: no accounts, no retention beyond 24 hours, per-IP rate limits, Cloudflare Turnstile (invisible) for link fetches, size and duration caps.

---

## 2. Operating rules for Claude Code (autonomous mode)

### 2.1 The loop

You run this loop until the definition of done is met.

1. Read `STATUS.md` and `ROADMAP.md`.
2. Pick the first task whose state is `pending` and whose `blocked_by` list is empty or all `done`. Phases are ordered; do not start a task from phase N+1 while any phase N task is `pending` or `in_progress`, unless phase N's remaining tasks are all `blocked` on an external event (which should be rare and logged).
3. Set the task to `in_progress` in STATUS.md and commit that change alone.
4. Run the research step (section 2.5) if the task involves a converter, an external integration, or an architectural choice.
5. Implement on a feature branch named `task/<phase>-<task-id>-<slug>`.
6. Run the quality gates (section 2.4). If a gate fails, fix and re-run. If a converter fails its fixture threshold, convene the council (section 2.3).
7. Update STATUS.md (state `done`, last commit hash, metrics), commit, merge to `main` with a fast-forward or squash merge, delete the branch.
8. Go to step 1.

Stop and ask the human only when a decision is both irreversible and externally costly. The exhaustive list of such decisions: spending money (buying a domain, upgrading a server plan, paying for an API), publishing a package name to PyPI or npm for the first time (name squatting is irreversible), publishing a browser extension to a store, deleting data that is not reproducible from the repo, and sending any email or message to a third party. For everything else, decide, log the decision in DECISIONS.md with rationale and the alternatives you rejected, and move on. If you are blocked on a human decision, write it in STATUS.md under `## Blocked on human`, mark the task `blocked`, and continue with other unblocked tasks. Only when nothing is unblocked do you stop and write the report.

### 2.2 DECISIONS.md format

Each entry is appended, never edited, in this form:

```markdown
## D-0042: Use pypdfium2 rather than pdfminer.six as the PDF text-layer fallback
Date: 2026-10-12
Task: P1-T07
Status: accepted
Context: Docling is the primary PDF engine. When Docling is unavailable or fails, we need a fast pure-text fallback.
Decision: pypdfium2 (BSD-3 / Apache-2.0 dual).
Alternatives: pdfminer.six (MIT, slow, no reading order), PyMuPDF (AGPL, forbidden in defaults), pdfplumber (MIT, built on pdfminer).
Rationale: pypdfium2 is 10x faster than pdfminer on the fixture corpus, is permissively licensed, and returns character bboxes needed for provenance.
Consequences: Add pypdfium2 to core extras [pdf]. Reading order is page-native only; no column detection in fallback.
Council: not convened (not architectural).
```

Approach notes (section 2.5) go under the task's decision entry as a `### Approach note` subsection.

### 2.3 Agent council pattern

Convene a council for (a) any architectural decision (new service, new queue, new storage shape, changes to the IR, changes to the API contract, changes to the security model) and (b) any converter whose first implementation fails its fixture threshold. Also convene one before tagging each release.

A council is three reviewer subagents, spawned in parallel, each given the same context bundle and one of three roles. Each writes a position of at most 400 words. You (the orchestrator) read all three, decide, and log the decision with a one-paragraph summary of each position in DECISIONS.md. Councils are limited to 3 iterations per problem; after the third, apply the time-and-budget rule (section 2.7).

Context bundle for every council member: the relevant section of this spec, the current DECISIONS.md entry for the task, the failing test output or the design question, the files changed on the branch (diff or paths), and `STATUS.md`.

Prompt template. Replace the bracketed fields. Send the same bundle to all three; only the ROLE block differs.

```
You are a reviewer on the ezmd project, an open-source "convert anything to LLM-ready Markdown" tool.
You are reviewing one decision or one failing component. You do not write code. You write a position.

ROLE: [Architect | Skeptic/Security | User-advocate]

[Architect]
You care about: fit with the existing IR and registry, minimal surface area, operational simplicity, ability to run CPU-only,
dependency weight, license compliance, and whether this decision will need to be undone in Phase 3 or later.
Call out any abstraction that is premature or any coupling that will hurt later.

[Skeptic/Security]
You care about: what breaks, what input makes this crash or hang, what an attacker can do with it, what is being assumed
without evidence, where the test is too easy, and whether the fixture threshold is being gamed. Assume every input is hostile.
Name at least one concrete failure case with a concrete input.

[User-advocate]
You care about: what a lawyer, an accountant, a researcher, a developer running RAG, and a non-technical person pasting a URL
each experience. Does the output lose structure they need? Is a failure reported or silent? Is the Markdown readable in a
chat window and greppable by an agent? Does this add a required step, an API key, or a GPU that most users do not have?

QUESTION: [the decision to make, or: "Converter X scores 0.71 on fixture set Y; threshold is 0.85. Diagnose and propose."]

CONTEXT:
[spec excerpt]
[DECISIONS.md entry]
[test output or design options]
[changed files]

Write your position in at most 400 words with these headings:
1. Position (one sentence)
2. Evidence (specific files, lines, inputs, or numbers)
3. Risks if we go the other way
4. Recommendation (concrete; if proposing a fix, name the function or module)
Do not hedge. Do not restate the question.
```

Red team subagent. Run before any public-facing phase ships (the API being reachable from the internet, the public instance, the extension, the MCP server over HTTP). The Red team gets the full repo, the threat model table (section 8), and this prompt:

```
You are the red team for ezmd. You have the full repository. Your job is to break it.
Enumerate attacks against: file upload, URL fetch, the job queue, the fetch-node protocol, the result endpoints,
the web UI, the MCP server, and the deploy configuration. For each attack: name it, give the exact payload or steps,
state the expected impact, and rate it critical/high/medium/low. Try at least: zip bomb, PDF with JS and embedded files,
DOCX with macros and external template, SVG with script, SSRF to 169.254.169.254 and to the Tailscale CIDR, DNS rebinding,
redirect chains to private IPs, a 10 GB Content-Length with a 1 KB body, slowloris on SSE, a forged fetch-node claim,
a result ID enumeration, path traversal in multipart filenames, a URL with credentials, a file whose magic says PNG but
whose extension says .py, a prompt-injection payload that tries to escape the agent-profile fence, and an RQ job
payload that is unpickled unsafely. Where you can, write a failing test under tests/security/ that demonstrates the issue.
Output: a table (attack, severity, reproduced yes/no, file:line, fix). Do not fix anything yourself.
```

Every `critical` and `high` finding becomes a task in STATUS.md that blocks the phase from shipping.

### 2.4 Quality gates

No task is `done` until all of these pass locally and in CI:

1. Unit tests: `uv run pytest packages apps -x -q` passes with no skips that are not marked with a reason.
2. Golden fixture tests: `uv run pytest fixtures -q` passes at the threshold for every converter the task touches. Thresholds live in `fixtures/thresholds.toml`.
3. Lint and types: `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy --strict packages/core`, `uv run mypy apps/api packages/converters packages/mcp` (non-strict but no errors), `pnpm -r lint`, `pnpm -r typecheck`.
4. License check: `uv run python tools/license_check.py` and `pnpm licenses list --json | node tools/license_check.mjs` pass against the allowlist.
5. Security audit: `uv run pip-audit` and `pnpm audit --audit-level=high` report no unresolved high or critical advisories (allowlist with expiry in `tools/audit_ignore.toml` if a fix is unavailable; each entry needs a DECISIONS.md reference).
6. STATUS.md updated with the task's state, last commit, and metrics.

Fixture scoring. Each fixture is a directory `fixtures/<family>/<name>/` containing `input.<ext>` (or `input.url` with a URL and a frozen `input.html` or `input.har` snapshot so tests never hit the network), `expected.full.md`, `expected.sidecar.json`, and `meta.toml` (converter id, threshold overrides, notes on what the fixture tests). The scorer in `packages/core/ezmd/testing/score.py` computes:

- `heading_score`: F1 over (level, normalized text) pairs of headings, plus a hierarchy consistency term (fraction of expected parent-child heading relationships preserved). Weight 0.25.
- `table_score`: for each expected table, best-match actual table by caption and shape; cell accuracy is exact-match after whitespace and number normalization; merged-cell info compared when present. Mean over tables. Weight 0.25. If no tables expected and none produced, score 1.0; if tables produced where none expected, penalize 0.1 per extra table.
- `text_score`: normalized Levenshtein similarity (rapidfuzz `ratio` / 100) over the concatenated paragraph text with whitespace collapsed and Unicode NFKC-normalized. Weight 0.30.
- `structure_score`: for each block type (list, code, image, footnote, equation, transcript segment, comment, tracked change, link), compare counts; score is `1 - min(1, |expected - actual| / max(expected, 1))` averaged across types that are present in expected. Weight 0.20.
- `overall` is the weighted sum. The threshold in `fixtures/thresholds.toml` is per converter id, defaulting to 0.85. Per-fixture overrides in `meta.toml` are allowed only downward with a reason (for example a deliberately broken scan).
- Hard failures regardless of score: any `Document` with zero blocks when the expected has more than zero; any exception; any warning of severity `error` not present in expected warnings; runtime exceeding the converter's `max_seconds` in `meta.toml`.

Golden review. Golden files are never committed from a converter's own output without review. When you generate a golden, spawn one Skeptic subagent with the input, the proposed golden, and the prompt: "Compare this proposed golden output to the input. List every heading, table, list, figure, footnote, speaker turn, comment, or tracked change in the input that is missing, mislabeled, reordered, or hallucinated in the golden. If the golden is acceptable, say ACCEPT and list what you checked. If not, say REJECT and list the fixes." Commit the golden only on ACCEPT; otherwise fix the converter or hand-edit the golden (hand edits are allowed and are noted in `meta.toml` under `hand_edited = true` with the reason).

### 2.5 Research-before-build rule

Before implementing any converter or any integration with an external library, service, or protocol, do a bounded research step: at most 20 minutes of wall time or 15 tool calls. Steps:

1. Web search for the library's current version, its license (verify the license file, not the README), and any license change in the last 12 months.
2. Read the library's docs for the specific API you will call.
3. Read the library's GitHub issues from the last 6 months filtered to "bug", "breaking", and the file type you care about. Note open issues that affect your use.
4. Check whether a fixture-like public sample exists that you can legally include in `fixtures/` (public domain, CC0, CC-BY, or generated by you). Never include commercial media or anything scraped from a platform in fixtures.
5. Write a 10-line approach note into the task's DECISIONS.md entry:

```
### Approach note
Library: docling 2.x (MIT), verified LICENSE file 2026-10-12.
Entry point: DocumentConverter(...).convert(path) -> ConversionResult; use .document.iterate_items() for blocks.
Known issues: #1234 (tables split across pages lose header), #1301 (hangs on PDFs with >2000 pages; set page limit).
Mitigations: cap pages at 500 by default (option), merge continued tables when caption absent and column count matches.
Provenance: Docling gives prov[].page_no and bbox in PDF coordinates; convert to top-left origin.
Fallback: pypdfium2 text layer, then OCR family.
License gate: none for defaults.
Fixtures: 3 public-domain PDFs (arXiv CC-BY paper, IRS form, scanned 1920s book page from Internet Archive).
Threshold: 0.85 (default). Expected weak spot: equations (Docling renders as images).
Time box: 1 day; if tables under 0.80 after council, ship experimental.
```

### 2.6 Dependency, license, security, commit, branch, and release rules

Dependency rule. Add a dependency only if it saves more than 200 lines of non-trivial code or provides a model or parser you cannot reasonably write. Every new dependency gets one line in the task's DECISIONS.md entry: name, version pin, license, size, why. Pin exact versions in lockfiles (`uv.lock`, `pnpm-lock.yaml`). Model weights are downloaded at first use into `EZMD_MODEL_DIR` (default `~/.cache/ezmd/models`), never bundled in the Python package, and the Docker images for self-host have a `-models` variant that pre-bakes the default CPU weights.

License rule. Restated: Apache-2.0 for the repo. Allowlist for defaults: MIT, Apache-2.0, BSD-2, BSD-3, ISC, PSF, MPL-2.0 unmodified, CC-BY-4.0. Forbidden in defaults: AGPL, GPL, LGPL static, SSPL, BSL, OpenRAIL-M, CC-BY-NC, Qwen Research License, MinerU license, custom terms. Forbidden licenses are allowed only in named extras, declared in `pyproject.toml` under `[project.optional-dependencies]` with a name that is the engine name (`chandra`, `pymupdf`, `extract-msg`), and the extra's converter module must call `ezmd.core.licensing.notify_once("<extra>")` on first import, which prints the license name and a URL to stderr once per machine (stamp file in the cache dir). `tools/license_check.py` walks `uv export --no-dev` for defaults and the per-extra resolution and fails if any package resolves to a license not on the allowlist for the default set. Packages with ambiguous metadata go in `tools/license_overrides.toml` with a link to the license file you verified.

Security rule. Section 8 is binding. In short: every input is hostile; workers are sandboxed; type is detected by magic; URL fetches go through the SSRF guard; no user string ever reaches a shell; secrets only from env; logs are redacted.

Commit conventions. Conventional Commits: `feat(converters/documents): add DOCX tracked changes`, `fix(api): reject multipart filenames with path separators`, `test(fixtures): add scanned PDF golden`, `chore(deps): bump docling to 2.x.y`, `docs(selfhost): add Postgres option`. Scope is the path segment under `packages/` or `apps/`. Body explains why, not what. Footer references the task: `Task: P1-T07`. Include the attribution lines the environment provides.

Branch strategy. Trunk-based. `main` is always green. Feature branches `task/<phase>-<task-id>-<slug>` are merged by you after gates pass (squash merge, commit message is the task summary). No long-lived branches. If a task takes more than one day, merge intermediate working slices behind a feature flag rather than keeping the branch open.

Releases. Tag `v0.0.x` after each phase completes (Phase 0 is `v0.0.1`). Tag `v0.1.0` when the definition of done is met. Tags are annotated, the message is the phase summary from STATUS.md, and the CI release workflow builds and publishes the Python package (to TestPyPI for `v0.0.x`, to PyPI for `v0.1.0` and later, the first PyPI publish is a human-gated decision), Docker images to GHCR, and the extension zip as a release asset. A changelog is generated from conventional commits into `CHANGELOG.md`.

### 2.7 Time and budget awareness

Prefer a working vertical slice over breadth. A converter that handles 80% of real inputs correctly and reports the other 20% as warnings ships; a converter that handles 95% but crashes on the rest does not. When a converter cannot reach threshold after 3 council iterations, ship it with `experimental = True` in its registration, a `warnings` entry of kind `experimental_converter` on every result, a paragraph in `docs/converters/<family>.md` under "Known limitations" stating exactly what fails and on what inputs, and move on. Record the decision. Revisit experimental converters only after all phases are complete and only if time remains.

Do not optimize before the fixture corpus passes. Do not build abstractions for a second use case that does not exist yet. Do not write docs for features that are not merged.

### 2.8 STATUS.md format

```markdown
# ezmd status

Last updated: 2026-10-12T18:40:00Z
Current phase: 1
Overall: 14 / 87 tasks done

## Phases
| Phase | Name | State | Tasks done | Tag |
|---|---|---|---|---|
| 0 | Foundation | done | 12/12 | v0.0.1 |
| 1 | Documents, web, code, data, email | in_progress | 2/19 | |
| 2 | Media | pending | 0/14 | |
...

## Tasks
| ID | Phase | Task | State | Blocked by | Last commit | Metrics | Notes |
|---|---|---|---|---|---|---|---|
| P0-T01 | 0 | Name availability check | done | | a1b2c3d | | ezmd free on PyPI, npm; GH org taken, using ezmd-dev |
| P1-T07 | 1 | PDF converter (Docling + pypdfium2 fallback) | in_progress | P1-T02 | | heading 0.91 table 0.78 text 0.96 overall 0.86 | council iter 1 on tables |
...

## Blocked on human
- (none)

## Experimental converters
| Converter | Reason | Fixture score | Doc link |
|---|---|---|---|

## Red team findings open
| ID | Severity | Attack | Task |
|---|---|---|---|
```

Task states: `pending`, `in_progress`, `done`, `blocked`, `shipped-experimental`, `dropped` (with reason in Notes and a DECISIONS.md entry).

### 2.9 Final report

When the definition of done is met, replace the top of STATUS.md with a `## Final report` section containing: one paragraph summary; a table of every converter with its family, engine, fixture score, threshold, and experimental flag; the public instance URL and the smoke test output; the list of human-gated decisions that were made or are still waiting; the list of experimental converters and dropped tasks with reasons; total commits, tests, and fixture count; the five highest-risk areas you would want a human to look at first; and the suggested next five tasks. Then stop.

---

## 3. CLAUDE.md

Place this file at the repo root verbatim (update the commands if the tooling changes, and log that change).

```markdown
# ezmd

Convert anything to LLM-ready Markdown. Apache-2.0. Python 3.12 core, TypeScript UI/extension.

## Read first
- `docs/spec/part1.md` through `part4.md`: the build specification. Part 1 section 2 contains the operating rules. Follow them.
- `STATUS.md`: current phase, task table, blockers. Update it after every task.
- `ROADMAP.md`: ordered phases and tasks with acceptance criteria.
- `DECISIONS.md`: append-only decision log. Every non-trivial choice goes here.

## Layout
- `packages/core/ezmd/`: IR (`ir.py`), registry (`registry.py`), renderers (`render/`), profiles (`profiles.py`), detection (`detect.py`), testing utilities (`testing/`).
- `packages/converters/ezmd_converters/<family>/`: one subpackage per family. Each converter is a class registered via the `ezmd.converters` entry point group.
- `apps/api/`: FastAPI app (`ezmd_api/`), RQ workers (`ezmd_api/worker.py`), job store, blob store.
- `apps/web/`: React + Vite. Built output is served by the API at `/`.
- `apps/fetch-node/`: residential fetch worker for Raspberry Pi.
- `apps/extension/`: MV3 browser extension.
- `packages/mcp/`: MCP server (stdio and streamable HTTP).
- `packages/sdk-ts/`: thin TypeScript client generated from OpenAPI plus hand-written helpers.
- `fixtures/<family>/<name>/`: input, expected outputs, meta.toml. Golden tests.
- `deploy/`: compose files, Caddyfile, Tailscale notes, Pi image script, smoke test.

## Commands
- Install: `uv sync --all-packages --all-extras --dev` and `pnpm install`
- Unit tests: `uv run pytest packages apps -x -q`
- Golden tests: `uv run pytest fixtures -q` (add `-k <converter>` to narrow)
- Score one fixture: `uv run ezmd-score fixtures/documents/arxiv-paper`
- Regenerate a golden (then get Skeptic review before committing): `uv run ezmd-golden fixtures/documents/arxiv-paper --write`
- Lint: `uv run ruff check . && uv run ruff format --check . && pnpm -r lint`
- Types: `uv run mypy --strict packages/core && uv run mypy apps/api packages/converters packages/mcp && pnpm -r typecheck`
- License check: `uv run python tools/license_check.py && pnpm licenses list --json | node tools/license_check.mjs`
- Audit: `uv run pip-audit && pnpm audit --audit-level=high`
- All gates: `make gates`
- Run API locally: `uv run uvicorn ezmd_api.main:app --reload --port 8000`
- Run worker locally: `uv run rq worker default media --url redis://localhost:6379`
- Run web dev server: `pnpm --filter web dev`
- Compose (CPU): `docker compose -f deploy/compose.yml up --build`
- Smoke test: `deploy/smoke.sh` (local) or `deploy/smoke.sh --remote https://host`
- CLI: `uv run ezmd convert <path-or-url> --profile compact`

## Conventions
- Conventional Commits with scope = path segment. Footer `Task: Pn-Tnn`.
- Trunk-based. Branch `task/<phase>-<id>-<slug>`, squash merge after gates pass.
- Types everywhere. `mypy --strict` on core is non-negotiable. Pydantic v2 models for IR and API schemas.
- No shell string interpolation of user data. Use `subprocess.run([...])` with list args and the sandbox wrapper `ezmd.core.sandbox.run`.
- Every converter returns a `Document` or raises `ConversionError`. Never return an empty Document silently; attach warnings.
- Every block carries `Provenance`. If you do not know the page or bbox, leave them None, but set `source`.
- Dependencies: allowlisted licenses only in defaults. See `tools/license_allowlist.toml`. Forbidden licenses go in named extras with `notify_once`.
- Fixtures must be public domain, CC0, CC-BY, or self-generated. No commercial media, no platform-scraped content.
- Never commit secrets. `.env.example` lists every env var with a comment.
- Research step and approach note before every converter or integration.
- Council (3 reviewers) for architectural decisions and failing converters. Red team before public-facing phases.
- Do not ask the human unless the decision is irreversible and externally costly.

## Spec pointer
The authoritative specification is `docs/spec/part1.md` to `docs/spec/part4.md`. When this file and the spec disagree, the spec wins; log the disagreement in DECISIONS.md and fix this file.
```

---

## 4. Core domain model (IR)

The intermediate representation lives in `packages/core/ezmd/ir.py`. Every converter produces a `Document`; every renderer consumes one. The IR is Pydantic v2 so it serializes to the JSON sidecar and validates on construction. It is deliberately flat: `Document.blocks` is an ordered list, and nesting is expressed through `parent_id` and, for lists, through `ListBlock.items` with nested `ListItem.children`. Keep it this way; a deep tree makes chunking and page-anchoring harder than it needs to be.

Design constraints you must preserve:

- Every block has a stable `id` (`b0001`, `b0002`, ... assigned in document order by `Document.finalize()`), a `provenance`, and an optional `parent_id`.
- Text content is plain Unicode. Inline formatting (bold, italic, links, inline code) is carried in `InlineSpan` runs on `Paragraph`, `Heading`, `TableCell`, `ListItem`, and `Quote` so renderers decide how to emit it. Converters that cannot recover inline formatting emit a single span.
- Nothing in the IR is Markdown. Converters never write `**` or `|`. Renderers do.
- Warnings are structured, never free text only.
- `Document.finalize()` assigns ids, computes element counts, and validates parent references. Converters call it before returning.

```python
"""ezmd.ir: the intermediate representation every converter produces and every renderer consumes.

Blocks are flat and ordered. Hierarchy is expressed via `parent_id` (sections, figures, slides)
and via explicit nesting inside ListBlock. Every block carries Provenance.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=False, validate_assignment=True)


# ---------------------------------------------------------------------------
# Provenance
# ---------------------------------------------------------------------------


class BBox(_Model):
    """Axis-aligned bounding box in page coordinates, origin top-left, units in points (PDF)
    or pixels (images). `page_width`/`page_height` allow normalization downstream."""

    x0: float
    y0: float
    x1: float
    y1: float
    page_width: float | None = None
    page_height: float | None = None

    @model_validator(mode="after")
    def _ordered(self) -> "BBox":
        if self.x1 < self.x0 or self.y1 < self.y0:
            raise ValueError("bbox coordinates must satisfy x0<=x1 and y0<=y1")
        return self


class Provenance(_Model):
    """Where a block came from. Every field is optional except `source`.

    source: canonical path or URL of the input this block was extracted from. For attachments
        and nested archives this is `<outer>!<inner path>`.
    source_page: 1-based page number (PDF, DOCX page estimate, PPTX slide index, XLSX sheet index).
    source_label: human label when page numbers are not numeric (sheet name, slide title, chapter id).
    bbox: layout box when the engine provides one.
    time_start / time_end: seconds into media for transcript-derived blocks.
    line_start / line_end: 1-based line numbers in text-like sources (code, plain text, transcripts with line structure).
    engine: converter id and engine that produced this block (for shadow-run comparisons).
    confidence: engine confidence in [0, 1] when available (OCR, ASR). None means unknown.
    """

    source: str
    source_page: int | None = None
    source_label: str | None = None
    bbox: BBox | None = None
    time_start: float | None = None
    time_end: float | None = None
    line_start: int | None = None
    line_end: int | None = None
    engine: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


# ---------------------------------------------------------------------------
# Inline content
# ---------------------------------------------------------------------------


class InlineStyle(StrEnum):
    BOLD = "bold"
    ITALIC = "italic"
    CODE = "code"
    STRIKE = "strike"
    UNDERLINE = "underline"
    SUPERSCRIPT = "superscript"
    SUBSCRIPT = "subscript"


class InlineSpan(_Model):
    """A run of text with uniform styling. `href` makes it a link; `footnote_ref` points at a
    Footnote block id; `math` holds LaTeX for inline equations (text is the fallback rendering)."""

    text: str
    styles: list[InlineStyle] = Field(default_factory=list)
    href: str | None = None
    footnote_ref: str | None = None
    math: str | None = None


def spans_text(spans: list[InlineSpan]) -> str:
    """Plain-text concatenation of spans. Used by scoring and by renderers that drop styling."""
    return "".join(s.text for s in spans)


# ---------------------------------------------------------------------------
# Blocks
# ---------------------------------------------------------------------------


class BlockBase(_Model):
    """Fields shared by every block. `id` is assigned by Document.finalize(); converters may leave it empty."""

    id: str = ""
    parent_id: str | None = None
    provenance: Provenance
    attrs: dict[str, str] = Field(default_factory=dict)
    """Free-form string attributes for converter-specific hints the renderer may use
    (for example `{"docling_label": "caption"}`). Never required for rendering."""


class Heading(BlockBase):
    type: Literal["heading"] = "heading"
    level: int = Field(ge=1, le=6)
    spans: list[InlineSpan]
    number: str | None = None
    """Section number if the source had one ("3.2"). Renderers may assign numbers when absent."""


class Paragraph(BlockBase):
    type: Literal["paragraph"] = "paragraph"
    spans: list[InlineSpan]
    role: Literal["body", "caption", "header", "footer", "page_number", "abstract", "title", "subtitle", "author", "date"] = "body"
    """Furniture roles (header, footer, page_number) let renderers drop repeated chrome."""


class TableCell(_Model):
    spans: list[InlineSpan]
    row: int
    col: int
    row_span: int = Field(default=1, ge=1)
    col_span: int = Field(default=1, ge=1)
    is_header: bool = False
    formula: str | None = None
    """Spreadsheet formula text when the source had one (XLSX). The spans hold the cached value."""
    raw_value: str | None = None
    """Unformatted value (for example the float behind a currency-formatted cell)."""
    bbox: BBox | None = None


class Table(BlockBase):
    type: Literal["table"] = "table"
    cells: list[TableCell]
    n_rows: int = Field(ge=0)
    n_cols: int = Field(ge=0)
    caption: list[InlineSpan] | None = None
    has_merged_cells: bool = False
    header_rows: int = 0
    """Number of leading rows that are headers. 0 means unknown or none."""
    continued_from: str | None = None
    """Block id of the previous fragment when a table spanned pages and the converter joined them."""

    @model_validator(mode="after")
    def _shape(self) -> "Table":
        for c in self.cells:
            if c.row + c.row_span > self.n_rows or c.col + c.col_span > self.n_cols:
                raise ValueError(f"cell at ({c.row},{c.col}) exceeds table shape {self.n_rows}x{self.n_cols}")
        self.has_merged_cells = self.has_merged_cells or any(c.row_span > 1 or c.col_span > 1 for c in self.cells)
        return self

    def grid(self) -> list[list[TableCell | None]]:
        """Materialize a row-major grid. Merged cells occupy their anchor position only."""
        g: list[list[TableCell | None]] = [[None] * self.n_cols for _ in range(self.n_rows)]
        for c in self.cells:
            g[c.row][c.col] = c
        return g


class ListItem(_Model):
    spans: list[InlineSpan]
    children: list["ListItem"] = Field(default_factory=list)
    checked: bool | None = None
    """Task-list state. None means not a task item."""
    provenance: Provenance | None = None


class ListBlock(BlockBase):
    type: Literal["list"] = "list"
    ordered: bool = False
    start: int = 1
    items: list[ListItem]


class CodeBlock(BlockBase):
    type: Literal["code"] = "code"
    code: str
    language: str | None = None
    filename: str | None = None
    """For repo packing: path of the file this code came from."""


class Image(BlockBase):
    type: Literal["image"] = "image"
    ref: str
    """Path or URL where the renderer can reference the image. Blob store key for extracted images."""
    alt: str | None = None
    caption: list[InlineSpan] | None = None
    generated_caption: str | None = None
    """VLM or OCR-derived description; renderers label it as generated."""
    ocr_text: str | None = None
    width: int | None = None
    height: int | None = None
    mime: str | None = None
    chart_data: Table | None = None
    """When a chart was converted to data, the extracted table."""


class Figure(BlockBase):
    """A grouping block: its children (image, caption paragraph, table) have parent_id == this id."""

    type: Literal["figure"] = "figure"
    label: str | None = None
    """'Figure 3', 'Table 2', 'Listing 1'."""


class Footnote(BlockBase):
    type: Literal["footnote"] = "footnote"
    marker: str
    """The visible marker ('1', 'a', '*')."""
    spans: list[InlineSpan]
    section_id: str | None = None
    """Heading block id of the section this footnote belongs to, so renderers can place it at section end."""


class Equation(BlockBase):
    type: Literal["equation"] = "equation"
    latex: str | None = None
    text: str | None = None
    """Fallback plain text when LaTeX could not be recovered."""
    label: str | None = None


class PageBreak(BlockBase):
    type: Literal["page_break"] = "page_break"
    page_number: int
    """The page that begins after this break (1-based)."""


class TranscriptSegment(BlockBase):
    """One ASR or caption segment. Converters emit these at engine granularity; the renderer merges
    into turns and paragraphs according to Part 3 rules."""

    type: Literal["transcript_segment"] = "transcript_segment"
    start: float
    end: float
    text: str
    speaker: str | None = None
    """Diarization label ('SPEAKER_00') or resolved name."""
    language: str | None = None
    words: list[tuple[str, float, float]] | None = None
    """Optional word-level timings (word, start, end). Kept for the sidecar only."""
    kind: Literal["speech", "music", "noise", "silence", "on_screen_text", "slide_change"] = "speech"


class Slide(BlockBase):
    """Grouping block for presentations. Children carry parent_id == this id. Notes are a Paragraph child
    with role='body' and attrs={'slide_part': 'notes'}."""

    type: Literal["slide"] = "slide"
    index: int
    title: str | None = None
    layout: str | None = None


class Comment(BlockBase):
    """A review comment (DOCX, PPTX, PDF annotation, Google Docs) anchored to a block or text range."""

    type: Literal["comment"] = "comment"
    author: str | None = None
    created: datetime | None = None
    spans: list[InlineSpan]
    anchor_block_id: str | None = None
    anchor_text: str | None = None
    reply_to: str | None = None
    """Comment block id this replies to."""
    resolved: bool | None = None


class TrackedChange(BlockBase):
    """A DOCX/ODT/Google Docs revision. The renderer decides how to show it per profile."""

    type: Literal["tracked_change"] = "tracked_change"
    change: Literal["insert", "delete", "format", "move"]
    author: str | None = None
    created: datetime | None = None
    spans: list[InlineSpan]
    anchor_block_id: str | None = None


class Link(BlockBase):
    """A standalone link worth listing (web page outbound links, references, 'Links' sections).
    Inline links live in InlineSpan.href; this block is for link lists and reference sections."""

    type: Literal["link"] = "link"
    href: str
    text: str | None = None
    rel: str | None = None


class Quote(BlockBase):
    type: Literal["quote"] = "quote"
    spans: list[InlineSpan]
    attribution: str | None = None
    depth: int = Field(default=1, ge=1)
    """Nesting depth for threaded content (email quotes, nested comments)."""


class Raw(BlockBase):
    """Content the converter could not map to another block. Renderers emit it in a fenced block
    labeled with `format` so nothing is lost. Use sparingly; prefer a Paragraph with a warning."""

    type: Literal["raw"] = "raw"
    format: str
    """'html', 'xml', 'latex', 'rtf', 'unknown', ..."""
    content: str


Block = Annotated[
    Union[
        Heading,
        Paragraph,
        Table,
        ListBlock,
        CodeBlock,
        Image,
        Figure,
        Footnote,
        Equation,
        PageBreak,
        TranscriptSegment,
        Slide,
        Comment,
        TrackedChange,
        Link,
        Quote,
        Raw,
    ],
    Field(discriminator="type"),
]


# ---------------------------------------------------------------------------
# Document-level metadata, warnings, metrics
# ---------------------------------------------------------------------------


class SourceType(StrEnum):
    PDF = "pdf"
    DOCX = "docx"
    PPTX = "pptx"
    XLSX = "xlsx"
    ODF = "odf"
    IWORK = "iwork"
    RTF = "rtf"
    EPUB = "epub"
    MARKUP = "markup"
    NOTEBOOK = "notebook"
    HTML = "html"
    WEB = "web"
    FEED = "feed"
    SOCIAL = "social"
    AUDIO = "audio"
    VIDEO = "video"
    MEDIA_URL = "media_url"
    IMAGE = "image"
    CODE = "code"
    REPO = "repo"
    OPENAPI = "openapi"
    EMAIL = "email"
    CHAT = "chat"
    DATA = "data"
    FINANCE_XML = "finance_xml"
    NOTES = "notes"
    CALENDAR = "calendar"
    ARCHIVE = "archive"
    TEXT = "text"
    OTHER = "other"


class Metadata(_Model):
    """Document-level metadata. Mirrors the frontmatter schema (Part 3) minus render-time fields."""

    title: str | None = None
    source: str
    source_type: SourceType
    mime: str | None = None
    author: str | None = None
    authors: list[str] = Field(default_factory=list)
    published: datetime | None = None
    modified: datetime | None = None
    fetched: datetime | None = None
    language: str | None = None
    """BCP-47."""
    license: str | None = None
    pages: int | None = None
    duration_seconds: float | None = None
    speakers: list[str] = Field(default_factory=list)
    description: str | None = None
    keywords: list[str] = Field(default_factory=list)
    canonical_url: str | None = None
    site_name: str | None = None
    extra: dict[str, str | int | float | bool | None] = Field(default_factory=dict)
    """Converter-specific scalar metadata (EXIF, email headers, repo stats). Rendered into frontmatter
    under `extra:` in the full profile only."""


class WarningKind(StrEnum):
    PAGES_WITHOUT_TEXT = "pages_without_text"
    UNREADABLE_REGION = "unreadable_region"
    OCR_CONFIDENCE_LOW = "ocr_confidence_low"
    ASR_CONFIDENCE_LOW = "asr_confidence_low"
    ASR_HALLUCINATION_FILTERED = "asr_hallucination_filtered"
    REMOVED_HIDDEN_ELEMENTS = "removed_hidden_elements"
    REMOVED_SCRIPT_OR_MACRO = "removed_script_or_macro"
    TABLE_STRUCTURE_UNCERTAIN = "table_structure_uncertain"
    MERGED_CELLS_FLATTENED = "merged_cells_flattened"
    EQUATION_AS_TEXT = "equation_as_text"
    IMAGE_SKIPPED = "image_skipped"
    ATTACHMENT_SKIPPED = "attachment_skipped"
    ATTACHMENT_FAILED = "attachment_failed"
    TRUNCATED = "truncated"
    PAGE_LIMIT_REACHED = "page_limit_reached"
    DURATION_LIMIT_REACHED = "duration_limit_reached"
    ENCRYPTED_CONTENT = "encrypted_content"
    UNSUPPORTED_FEATURE = "unsupported_feature"
    FALLBACK_ENGINE_USED = "fallback_engine_used"
    EXPERIMENTAL_CONVERTER = "experimental_converter"
    INJECTION_PATTERN = "injection_pattern"
    LANGUAGE_UNCERTAIN = "language_uncertain"
    FETCH_DEGRADED = "fetch_degraded"
    OTHER = "other"


class Warning(_Model):
    kind: WarningKind
    severity: Literal["info", "warning", "error"] = "warning"
    message: str
    """Human-readable, one sentence, no engine stack traces."""
    block_id: str | None = None
    page: int | None = None
    count: int | None = None
    detail: dict[str, str | int | float] = Field(default_factory=dict)


class ElementCounts(_Model):
    headings: int = 0
    paragraphs: int = 0
    tables: int = 0
    table_cells: int = 0
    lists: int = 0
    list_items: int = 0
    code_blocks: int = 0
    images: int = 0
    figures: int = 0
    footnotes: int = 0
    equations: int = 0
    page_breaks: int = 0
    transcript_segments: int = 0
    slides: int = 0
    comments: int = 0
    tracked_changes: int = 0
    links: int = 0
    quotes: int = 0
    raw: int = 0
    words: int = 0


class Metrics(_Model):
    duration_seconds: float = 0.0
    """Wall time of the conversion, excluding fetch."""
    fetch_seconds: float | None = None
    engine: str | None = None
    """Primary engine id, e.g. 'docling@2.14.0'."""
    engines_tried: list[str] = Field(default_factory=list)
    input_bytes: int | None = None
    estimated_tokens: int = 0
    """cl100k_base estimate of the plain text; renderers recompute for the rendered output."""
    counts: ElementCounts = Field(default_factory=ElementCounts)


# ---------------------------------------------------------------------------
# Document
# ---------------------------------------------------------------------------


class Document(_Model):
    """The unit of conversion. One input produces one Document. Attachments and archive members
    are separate Documents linked via `children`."""

    schema_version: Literal["1"] = "1"
    metadata: Metadata
    blocks: list[Block] = Field(default_factory=list)
    warnings: list[Warning] = Field(default_factory=list)
    children: list["Document"] = Field(default_factory=list)
    converter_id: str = ""
    content_hash: str = ""
    """sha256 of the finalized plain text; set by finalize()."""
    _finalized: bool = False

    def plain_text(self) -> str:
        """Concatenated plain text of all text-bearing blocks, in order. Used for hashing, token
        estimates, scoring, and injection scanning."""
        parts: list[str] = []
        for b in self.blocks:
            match b:
                case Heading() | Paragraph() | Quote() | Footnote() | TrackedChange() | Comment():
                    parts.append(spans_text(b.spans))
                case Table():
                    parts.append("\n".join(spans_text(c.spans) for c in b.cells))
                case ListBlock():
                    parts.extend(_list_text(b.items))
                case CodeBlock():
                    parts.append(b.code)
                case TranscriptSegment():
                    parts.append(b.text)
                case Image():
                    parts.append(b.generated_caption or b.alt or "")
                case Equation():
                    parts.append(b.latex or b.text or "")
                case Raw():
                    parts.append(b.content)
                case _:
                    pass
        return "\n".join(p for p in parts if p)

    def finalize(self) -> "Document":
        """Assign ids in document order, validate parent references, compute counts and hash.
        Idempotent. Converters must call this before returning."""
        for i, b in enumerate(self.blocks, start=1):
            if not b.id:
                b.id = f"b{i:04d}"
        ids = {b.id for b in self.blocks}
        if len(ids) != len(self.blocks):
            raise ValueError("duplicate block ids")
        for b in self.blocks:
            if b.parent_id is not None and b.parent_id not in ids:
                raise ValueError(f"block {b.id} references unknown parent {b.parent_id}")
        text = self.plain_text()
        self.content_hash = "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()
        for child in self.children:
            child.finalize()
        self._finalized = True
        return self

    def counts(self) -> ElementCounts:
        c = ElementCounts()
        for b in self.blocks:
            match b:
                case Heading():
                    c.headings += 1
                case Paragraph():
                    c.paragraphs += 1
                case Table():
                    c.tables += 1
                    c.table_cells += len(b.cells)
                case ListBlock():
                    c.lists += 1
                    c.list_items += _count_items(b.items)
                case CodeBlock():
                    c.code_blocks += 1
                case Image():
                    c.images += 1
                case Figure():
                    c.figures += 1
                case Footnote():
                    c.footnotes += 1
                case Equation():
                    c.equations += 1
                case PageBreak():
                    c.page_breaks += 1
                case TranscriptSegment():
                    c.transcript_segments += 1
                case Slide():
                    c.slides += 1
                case Comment():
                    c.comments += 1
                case TrackedChange():
                    c.tracked_changes += 1
                case Link():
                    c.links += 1
                case Quote():
                    c.quotes += 1
                case Raw():
                    c.raw += 1
        c.words = len(self.plain_text().split())
        return c

    def sections(self) -> list[tuple[Heading, list[Block]]]:
        """Group blocks under their preceding heading. Blocks before the first heading are grouped
        under a synthetic None heading, represented by a level-0 Heading with empty spans."""
        out: list[tuple[Heading, list[Block]]] = []
        current = Heading(level=1, spans=[], provenance=Provenance(source=self.metadata.source), id="b0000")
        current.level = 1
        bucket: list[Block] = []
        for b in self.blocks:
            if isinstance(b, Heading):
                out.append((current, bucket))
                current, bucket = b, []
            else:
                bucket.append(b)
        out.append((current, bucket))
        return out


def _list_text(items: list[ListItem]) -> list[str]:
    out: list[str] = []
    for it in items:
        out.append(spans_text(it.spans))
        out.extend(_list_text(it.children))
    return out


def _count_items(items: list[ListItem]) -> int:
    return sum(1 + _count_items(it.children) for it in items)


# ---------------------------------------------------------------------------
# ConversionResult
# ---------------------------------------------------------------------------


class ConversionResult(_Model):
    """What the pipeline returns to the job system and the CLI. Wraps the Document with run metrics."""

    document: Document
    warnings: list[Warning] = Field(default_factory=list)
    """Pipeline-level warnings (detection ambiguity, fallback engine used, limits hit). Document-level
    warnings live on document.warnings; renderers merge both."""
    metrics: Metrics = Field(default_factory=Metrics)
    truncated: bool = False
    """True when any cap (pages, duration, bytes, time) cut the input short. Also surfaced as a
    WarningKind.TRUNCATED warning with detail."""
    converter_id: str
    input_ref: "InputRefInfo"

    @property
    def all_warnings(self) -> list[Warning]:
        return [*self.warnings, *self.document.warnings]


class InputRefInfo(_Model):
    """Serializable summary of the InputRef that was converted (the InputRef itself may hold handles)."""

    kind: Literal["path", "bytes", "url", "residential_fetch"]
    display: str
    """Filename or URL for display and frontmatter."""
    mime: str | None = None
    size_bytes: int | None = None
    sha256: str | None = None
```

Notes for implementers:

- `Document.sections()` is what the `rag` chunker and the TOC generator use. Keep it stable.
- `Provenance.source` for a web fetch is the final URL after redirects; `Metadata.canonical_url` is the `<link rel=canonical>` if present.
- `TranscriptSegment.words` can be large. The sidecar serializer includes it only in the `full` profile; the renderer never emits it inline.
- `Raw` is a last resort. A converter that emits more than 10% of its blocks as `Raw` on a fixture fails the structural score and must be fixed or flagged experimental.

---

## 5. Converter interface and registry

Lives in `packages/core/ezmd/registry.py` and `packages/core/ezmd/inputs.py`.

### 5.1 InputRef

An `InputRef` abstracts over the four input modes. Converters never open files or sockets themselves; they ask the `InputRef` for bytes, a path, or a URL, and the `InputRef` enforces caps.

```python
"""ezmd.inputs: input abstraction over local files, uploaded bytes, URLs, and residential fetches."""

from __future__ import annotations

import hashlib
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Protocol

from ezmd.ir import InputRefInfo


class InputTooLarge(Exception):
    pass


class FetchRequired(Exception):
    """Raised by a converter when it needs the body of a URL that has not been fetched yet.
    The pipeline catches it and enqueues a fetch (ordinary or residential) before retrying."""

    def __init__(self, url: str, residential: bool, reason: str) -> None:
        super().__init__(reason)
        self.url = url
        self.residential = residential
        self.reason = reason


@dataclass(slots=True)
class Detected:
    """Content-type detection result. `mime` is authoritative; `magika_label` and `libmagic_mime`
    are kept for diagnostics. `confidence` is Magika's score, or 1.0 when libmagic and extension agree."""

    mime: str
    extension: str | None
    confidence: float
    magika_label: str | None = None
    libmagic_mime: str | None = None
    extension_mime: str | None = None


@dataclass(slots=True)
class InputRef:
    """One input to convert.

    kind:
      path: a local file (CLI, worker after upload materialization).
      bytes: in-memory upload (API). Materialized to a temp path on demand.
      url: a URL whose body has not been fetched, or has been fetched into `fetched_path`.
      residential_fetch: a URL that must be fetched by a fetch node; `fetched_path` is set once the
        node uploads the result (usually an audio file plus a metadata JSON).

    All byte access goes through `path()` or `read()` which enforce `max_bytes`.
    """

    kind: Literal["path", "bytes", "url", "residential_fetch"]
    display: str
    local_path: Path | None = None
    data: bytes | None = None
    url: str | None = None
    fetched_path: Path | None = None
    fetched_headers: dict[str, str] = field(default_factory=dict)
    fetch_meta: dict[str, object] = field(default_factory=dict)
    """Platform metadata from a fetch (title, uploader, duration, captions available, ...)."""
    declared_mime: str | None = None
    """Mime from the upload or the HTTP Content-Type. Advisory only; detection decides."""
    detected: Detected | None = None
    max_bytes: int = 100 * 1024 * 1024
    _tmpdir: tempfile.TemporaryDirectory[str] | None = field(default=None, repr=False)

    @classmethod
    def from_path(cls, p: Path, *, max_bytes: int | None = None) -> "InputRef":
        ref = cls(kind="path", display=p.name, local_path=p)
        if max_bytes is not None:
            ref.max_bytes = max_bytes
        return ref

    @classmethod
    def from_bytes(cls, data: bytes, *, filename: str, declared_mime: str | None = None, max_bytes: int | None = None) -> "InputRef":
        ref = cls(kind="bytes", display=filename, data=data, declared_mime=declared_mime)
        if max_bytes is not None:
            ref.max_bytes = max_bytes
        if len(data) > ref.max_bytes:
            raise InputTooLarge(f"{len(data)} bytes exceeds cap {ref.max_bytes}")
        return ref

    @classmethod
    def from_url(cls, url: str, *, residential: bool = False, max_bytes: int | None = None) -> "InputRef":
        ref = cls(kind="residential_fetch" if residential else "url", display=url, url=url)
        if max_bytes is not None:
            ref.max_bytes = max_bytes
        return ref

    @property
    def has_body(self) -> bool:
        return self.local_path is not None or self.data is not None or self.fetched_path is not None

    def path(self) -> Path:
        """A readable local path. Materializes bytes to a temp file on first call. Raises FetchRequired
        for URL kinds whose body is not present."""
        if self.local_path is not None:
            self._check_size(self.local_path.stat().st_size)
            return self.local_path
        if self.fetched_path is not None:
            self._check_size(self.fetched_path.stat().st_size)
            return self.fetched_path
        if self.data is not None:
            if self._tmpdir is None:
                self._tmpdir = tempfile.TemporaryDirectory(prefix="ezmd-")
                suffix = Path(self.display).suffix[:16]
                p = Path(self._tmpdir.name) / f"input{suffix}"
                p.write_bytes(self.data)
                self.local_path = p
            assert self.local_path is not None
            return self.local_path
        assert self.url is not None
        raise FetchRequired(self.url, residential=self.kind == "residential_fetch", reason="body not fetched")

    def read(self) -> bytes:
        if self.data is not None:
            return self.data
        p = self.path()
        return p.read_bytes()

    def sha256(self) -> str:
        h = hashlib.sha256()
        with self.path().open("rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()

    def info(self) -> InputRefInfo:
        size = None
        sha = None
        if self.has_body:
            size = self.path().stat().st_size
            sha = self.sha256()
        return InputRefInfo(
            kind=self.kind,
            display=self.display,
            mime=self.detected.mime if self.detected else self.declared_mime,
            size_bytes=size,
            sha256=sha,
        )

    def cleanup(self) -> None:
        if self._tmpdir is not None:
            self._tmpdir.cleanup()
            self._tmpdir = None
        if self.fetched_path is not None and self.fetched_path.exists() and self.kind in ("url", "residential_fetch"):
            shutil.rmtree(self.fetched_path.parent, ignore_errors=True)

    def _check_size(self, n: int) -> None:
        if n > self.max_bytes:
            raise InputTooLarge(f"{n} bytes exceeds cap {self.max_bytes}")


class Detector(Protocol):
    def detect(self, ref: InputRef) -> Detected: ...
```

Detection (`packages/core/ezmd/detect.py`): run Magika on the first 1 MiB plus the last 64 KiB, run libmagic on the same, map the extension. Resolution order: if Magika confidence is at least 0.9, use Magika; else if libmagic and extension agree, use that; else if libmagic returns something other than `application/octet-stream` or `text/plain`, use libmagic; else use the extension's mime; else `application/octet-stream`. Record all three in `Detected`. For URL inputs without a body, detection returns a synthetic `Detected(mime="text/x-uri", ...)` and the URL converters' `can_handle` inspect the host and path. The declared mime from an upload is never trusted on its own.

### 5.2 Converter protocol

```python
"""ezmd.registry: converter protocol, options, registry with priority resolution, fallback chains,
and entry-point plugin discovery."""

from __future__ import annotations

import importlib.metadata as md
import logging
import time
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from ezmd.inputs import FetchRequired, InputRef
from ezmd.ir import ConversionResult, Document, Metrics, Warning, WarningKind

log = logging.getLogger(__name__)


class ConversionError(Exception):
    """A converter could not produce a Document. `retryable_with_fallback` tells the registry whether
    to try the next converter in the chain. `user_message` is safe to show to end users."""

    def __init__(self, message: str, *, user_message: str | None = None, retryable_with_fallback: bool = True) -> None:
        super().__init__(message)
        self.user_message = user_message or "Conversion failed."
        self.retryable_with_fallback = retryable_with_fallback


@dataclass(slots=True)
class ConvertOptions:
    """Options every converter receives. Converters read what they need and ignore the rest.
    Family-specific options go in `extra` and are documented per converter in Part 2."""

    max_pages: int | None = 500
    max_duration_seconds: float | None = 3 * 3600
    max_seconds: float = 600.0
    """Wall-clock budget for this conversion. Converters check `deadline()` in long loops."""
    ocr: bool = True
    """Allow OCR fallback when a page has no text layer."""
    asr_model: str | None = None
    diarize: bool = True
    languages: list[str] = field(default_factory=list)
    """Hint list of BCP-47 codes; empty means auto-detect."""
    extract_images: bool = True
    image_dir: str | None = None
    """Where extracted images are written (blob store key prefix or local dir). None disables extraction."""
    follow_attachments: bool = True
    max_attachment_depth: int = 3
    allow_network: bool = False
    """Whether the converter may make outbound requests beyond the already-fetched input (web crawl, feed follow).
    Workers run with this False unless the job is a fetch job."""
    tracked_changes: bool = True
    comments: bool = True
    formulas: bool = True
    gpu: bool = False
    extra: dict[str, str | int | float | bool] = field(default_factory=dict)
    _started: float = field(default_factory=time.monotonic)

    def deadline(self) -> float:
        """Seconds remaining. Converters raise ConversionError(retryable_with_fallback=False) when <= 0."""
        return self.max_seconds - (time.monotonic() - self._started)


@runtime_checkable
class Converter(Protocol):
    """A converter turns one InputRef into one Document.

    id: stable identifier `family.engine`, e.g. `documents.docling_pdf`, `web.trafilatura`.
    family: one of documents, web, media, images, code, comms, data, notes, specialized, text.
    priority: tie-breaker when two converters return equal confidence; higher wins.
    experimental: when True, every result gets an EXPERIMENTAL_CONVERTER warning.
    requires_extras: pip extras needed; the registry skips converters whose imports fail and logs why.
    """

    id: str
    family: str
    priority: int
    experimental: bool
    requires_extras: tuple[str, ...]

    def can_handle(self, ref: InputRef) -> float:
        """Confidence in [0, 1] that this converter should handle `ref`. 0 means no. Use `ref.detected.mime`,
        `ref.display`, and `ref.url`. Must be cheap: no I/O beyond what is already loaded."""
        ...

    def convert(self, ref: InputRef, options: ConvertOptions) -> Document:
        """Produce a finalized Document or raise ConversionError. Must not catch BaseException.
        Must call `document.finalize()`. May raise FetchRequired for URL inputs without a body."""
        ...


@dataclass(slots=True)
class Registration:
    converter: Converter
    source: str
    """'builtin' or the entry point's distribution name."""
    import_error: str | None = None


class ConverterRegistry:
    """Holds converters, resolves the best one for an input, runs fallback chains.

    Resolution: all converters' `can_handle` are called; those returning > 0 are sorted by
    (confidence desc, priority desc, id asc). The pipeline tries them in that order until one succeeds
    or a ConversionError with retryable_with_fallback=False is raised. Explicit chains (section 5.3)
    can pin an order for a mime type and override confidence sorting.
    """

    ENTRY_POINT_GROUP = "ezmd.converters"

    def __init__(self) -> None:
        self._regs: dict[str, Registration] = {}
        self._chains: dict[str, list[str]] = {}

    def register(self, converter: Converter, *, source: str = "builtin") -> None:
        if converter.id in self._regs:
            raise ValueError(f"duplicate converter id {converter.id}")
        self._regs[converter.id] = Registration(converter=converter, source=source)

    def set_chain(self, mime: str, converter_ids: list[str]) -> None:
        """Pin the order of converters for a mime type. Unknown ids are ignored at resolve time with a log line."""
        self._chains[mime] = converter_ids

    def load_entry_points(self) -> None:
        """Discover third-party converters. Each entry point must resolve to a Converter class or a zero-arg
        factory. Failures are recorded, not raised, so one broken plugin cannot take down the registry."""
        for ep in md.entry_points(group=self.ENTRY_POINT_GROUP):
            try:
                obj = ep.load()
                conv = obj() if callable(obj) and not isinstance(obj, Converter) else obj
                if not isinstance(conv, Converter):
                    raise TypeError(f"{ep.name} did not produce a Converter")
                self.register(conv, source=ep.dist.name if ep.dist else ep.name)
            except Exception as e:  # noqa: BLE001 - plugin isolation
                log.warning("converter plugin %s failed to load: %s", ep.name, e)
                self._regs[f"broken.{ep.name}"] = Registration(converter=_Broken(ep.name), source=ep.name, import_error=str(e))

    def available(self) -> list[Converter]:
        return [r.converter for r in self._regs.values() if r.import_error is None]

    def get(self, converter_id: str) -> Converter:
        reg = self._regs[converter_id]
        if reg.import_error:
            raise KeyError(f"converter {converter_id} unavailable: {reg.import_error}")
        return reg.converter

    def candidates(self, ref: InputRef) -> list[tuple[float, Converter]]:
        mime = ref.detected.mime if ref.detected else None
        if mime and mime in self._chains:
            ordered: list[tuple[float, Converter]] = []
            for cid in self._chains[mime]:
                reg = self._regs.get(cid)
                if reg is None or reg.import_error:
                    log.info("chain for %s skips unavailable converter %s", mime, cid)
                    continue
                score = reg.converter.can_handle(ref)
                if score > 0:
                    ordered.append((score, reg.converter))
            if ordered:
                return ordered
        scored = [(c.can_handle(ref), c) for c in self.available()]
        scored = [(s, c) for s, c in scored if s > 0]
        scored.sort(key=lambda sc: (-sc[0], -sc[1].priority, sc[1].id))
        return scored

    def convert(self, ref: InputRef, options: ConvertOptions, *, converter_id: str | None = None) -> ConversionResult:
        """Run the resolution and fallback chain. Raises ConversionError if every candidate fails,
        with the last error's message and all tried ids in the message. Raises FetchRequired through."""
        if converter_id is not None:
            cands = [(1.0, self.get(converter_id))]
        else:
            cands = self.candidates(ref)
        if not cands:
            raise ConversionError(
                f"no converter for {ref.display} (mime={ref.detected.mime if ref.detected else None})",
                user_message="This file type is not supported yet.",
                retryable_with_fallback=False,
            )
        tried: list[str] = []
        pipeline_warnings: list[Warning] = []
        last: Exception | None = None
        for i, (_score, conv) in enumerate(cands):
            tried.append(conv.id)
            t0 = time.monotonic()
            try:
                doc = conv.convert(ref, options)
            except FetchRequired:
                raise
            except ConversionError as e:
                last = e
                log.info("converter %s failed on %s: %s", conv.id, ref.display, e)
                if not e.retryable_with_fallback:
                    break
                continue
            except Exception as e:  # noqa: BLE001 - engine bugs become fallbacks, not crashes
                last = e
                log.exception("converter %s crashed on %s", conv.id, ref.display)
                continue
            if not doc.blocks:
                last = ConversionError(f"{conv.id} produced an empty document")
                log.info("converter %s produced empty document for %s; trying next", conv.id, ref.display)
                continue
            if i > 0:
                pipeline_warnings.append(
                    Warning(
                        kind=WarningKind.FALLBACK_ENGINE_USED,
                        severity="info",
                        message=f"Primary converter failed; used {conv.id}.",
                        detail={"tried": ",".join(tried)},
                    )
                )
            if conv.experimental:
                pipeline_warnings.append(
                    Warning(kind=WarningKind.EXPERIMENTAL_CONVERTER, severity="info", message=f"{conv.id} is experimental; see docs for known limitations.")
                )
            truncated = any(w.kind in (WarningKind.TRUNCATED, WarningKind.PAGE_LIMIT_REACHED, WarningKind.DURATION_LIMIT_REACHED) for w in doc.warnings)
            metrics = Metrics(
                duration_seconds=time.monotonic() - t0,
                engine=conv.id,
                engines_tried=tried,
                input_bytes=ref.path().stat().st_size if ref.has_body else None,
                counts=doc.counts(),
            )
            doc.converter_id = conv.id
            return ConversionResult(
                document=doc,
                warnings=pipeline_warnings,
                metrics=metrics,
                truncated=truncated,
                converter_id=conv.id,
                input_ref=ref.info(),
            )
        msg = f"all converters failed for {ref.display}: tried {tried}; last error: {last}"
        user = last.user_message if isinstance(last, ConversionError) else "Conversion failed."
        raise ConversionError(msg, user_message=user, retryable_with_fallback=False)


class _Broken:
    """Placeholder so `GET /v1/capabilities` can list plugins that failed to import."""

    def __init__(self, name: str) -> None:
        self.id = f"broken.{name}"
        self.family = "broken"
        self.priority = -1
        self.experimental = True
        self.requires_extras: tuple[str, ...] = ()

    def can_handle(self, ref: InputRef) -> float:
        return 0.0

    def convert(self, ref: InputRef, options: ConvertOptions) -> Document:
        raise ConversionError("broken plugin", retryable_with_fallback=False)


_default: ConverterRegistry | None = None


def default_registry() -> ConverterRegistry:
    """Process-wide registry: builtins first, then entry points, then default chains."""
    global _default
    if _default is None:
        reg = ConverterRegistry()
        from ezmd.builtin import register_builtins  # local import avoids cycles

        register_builtins(reg)
        reg.load_entry_points()
        from ezmd.chains import DEFAULT_CHAINS

        for mime, ids in DEFAULT_CHAINS.items():
            reg.set_chain(mime, ids)
        _default = reg
    return _default
```

### 5.3 Fallback chains

`packages/core/ezmd/chains.py` holds `DEFAULT_CHAINS: dict[str, list[str]]`. Part 2 fills it per family. Phase 0 ships:

```python
DEFAULT_CHAINS: dict[str, list[str]] = {
    "text/plain": ["text.plain"],
    "text/markdown": ["text.markdown_passthrough", "text.plain"],
    # Filled by Part 2. Examples of the intended shape:
    # "application/pdf": ["documents.docling_pdf", "documents.pypdfium2_text", "images.ocr_pages"],
    # "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ["documents.docling_docx", "documents.pandoc_docx"],
    # "text/html": ["web.trafilatura", "web.readability", "web.html_raw"],
    # "audio/*": ["media.asr_local", "media.asr_hosted"],
}
```

Wildcard keys (`audio/*`) are matched after exact keys. The registry's `candidates` must implement the wildcard match (add it in Phase 0; the code above shows exact matching only).

### 5.4 Plugin packaging

Third parties register converters in their `pyproject.toml`:

```toml
[project.entry-points."ezmd.converters"]
my_format = "my_pkg.converter:MyConverter"
```

`ezmd capabilities` (CLI) and `GET /v1/capabilities` list every registered converter with id, family, source distribution, experimental flag, required extras, and whether it loaded. A plugin cookiecutter lives in `docs/plugins.md` with a 40-line example converter and a fixture layout.

### 5.5 Converter authoring checklist (enforced by a test in `packages/core/tests/test_converter_contract.py` that runs against every registered converter)

1. `id` matches `^[a-z]+\.[a-z0-9_]+$` and `family` is in the allowed set.
2. `can_handle` returns 0.0 for an `InputRef` with mime `application/x-ezmd-nothing` and completes in under 10 ms.
3. `convert` on an empty file raises `ConversionError` or returns a Document with at least one warning; it never returns an empty Document with no warnings.
4. `convert` on a 1-byte file does not raise anything other than `ConversionError`.
5. Every block in the returned Document has `provenance.source` set.
6. `finalize()` has been called (`content_hash` non-empty).
7. No block text contains U+0000 or unpaired surrogates.
8. The converter has at least one fixture directory under `fixtures/<family>/` referencing its id in `meta.toml`.

---

## 6. Renderer and profiles interface

Lives in `packages/core/ezmd/render/` and `packages/core/ezmd/profiles.py`. Part 3 defines the exact Markdown rules; Part 1 defines the interfaces and a skeleton that the plain-text converter in Phase 0 can round-trip through.

```python
"""ezmd.profiles: output profile configuration objects."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

ProfileName = Literal["full", "compact", "rag", "agent"]


@dataclass(frozen=True, slots=True)
class TableRules:
    max_pipe_columns: int = 6
    max_pipe_rows: int | None = None
    """None means unlimited. compact uses 50."""
    merged_cells: Literal["html", "flatten"] = "html"
    wide_fallback: Literal["kv", "transpose"] = "kv"
    csv_sidecar: bool = True
    pad_columns: bool = False


@dataclass(frozen=True, slots=True)
class ImageRules:
    mode: Literal["reference_and_caption", "caption_only", "reference_only"] = "reference_and_caption"
    chart_table: bool = True


@dataclass(frozen=True, slots=True)
class TranscriptRules:
    timestamps: Literal["per_turn", "per_paragraph", "per_chapter"] = "per_turn"
    paragraph_gap_seconds: float = 1.75
    chapters: bool = True
    non_speech_cues: bool = True
    style: Literal["verbatim", "clean"] = "clean"


@dataclass(frozen=True, slots=True)
class ChunkRules:
    enabled: bool = False
    chunk_tokens: int = 400
    overlap_tokens: int = 0
    table_chunk_tokens: int = 2048
    breadcrumb: bool = True
    context_line: bool = False
    """Optional LLM-generated context line; off by default (requires a model endpoint)."""


@dataclass(frozen=True, slots=True)
class Profile:
    name: ProfileName
    frontmatter: bool = True
    summary_blockquote: bool = True
    toc: Literal["auto", "always", "never"] = "auto"
    toc_min_headings: int = 5
    toc_min_tokens: int = 3000
    number_headings: bool = True
    page_markers: bool = True
    footnotes: Literal["section_end", "document_end", "inline", "drop"] = "section_end"
    tracked_changes: Literal["annotate", "accept", "reject", "drop"] = "annotate"
    comments: Literal["inline", "section_end", "drop"] = "inline"
    links: Literal["inline", "numbered_list", "text_only"] = "inline"
    furniture: Literal["drop", "keep"] = "drop"
    tables: TableRules = field(default_factory=TableRules)
    images: ImageRules = field(default_factory=ImageRules)
    transcript: TranscriptRules = field(default_factory=TranscriptRules)
    chunks: ChunkRules = field(default_factory=ChunkRules)
    untrusted_fence: bool = False
    section_ids: bool = False
    sidecar: bool = True
    include_extra_metadata: bool = False
    raw_blocks: Literal["fenced", "drop"] = "fenced"
    token_budget: int | None = None
    """If set, the renderer truncates body at a section boundary and sets truncated=true."""


FULL = Profile(name="full", include_extra_metadata=True)

COMPACT = Profile(
    name="compact",
    page_markers=False,
    footnotes="document_end",
    tracked_changes="accept",
    comments="drop",
    links="numbered_list",
    tables=TableRules(max_pipe_rows=50, merged_cells="flatten"),
    images=ImageRules(mode="caption_only"),
    transcript=TranscriptRules(timestamps="per_paragraph"),
    sidecar=False,
)

RAG = Profile(
    name="rag",
    summary_blockquote=False,
    toc="never",
    page_markers=False,
    footnotes="inline",
    tracked_changes="accept",
    comments="drop",
    links="text_only",
    images=ImageRules(mode="caption_only"),
    chunks=ChunkRules(enabled=True),
    section_ids=True,
)

AGENT = Profile(
    name="agent",
    images=ImageRules(mode="reference_only"),
    untrusted_fence=True,
    section_ids=True,
)

PROFILES: dict[str, Profile] = {"full": FULL, "compact": COMPACT, "rag": RAG, "agent": AGENT}


def get_profile(name: str, **overrides: object) -> Profile:
    """Look up a profile and apply scalar overrides (API query params and CLI flags map here).
    Nested rule overrides use dotted keys: chunks.chunk_tokens=512."""
    import dataclasses

    base = PROFILES[name]
    flat = {k: v for k, v in overrides.items() if "." not in k}
    nested: dict[str, dict[str, object]] = {}
    for k, v in overrides.items():
        if "." in k:
            group, attr = k.split(".", 1)
            nested.setdefault(group, {})[attr] = v
    p = dataclasses.replace(base, **flat)  # type: ignore[arg-type]
    for group, attrs in nested.items():
        sub = getattr(p, group)
        p = dataclasses.replace(p, **{group: dataclasses.replace(sub, **attrs)})  # type: ignore[arg-type]
    return p
```

```python
"""ezmd.render.base: renderer interface and skeleton. Part 3 specifies the Markdown rules that
MarkdownRenderer implements; this module defines the contract and the pieces every renderer shares."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from ezmd.ir import ConversionResult, Document, Warning
from ezmd.profiles import Profile


@dataclass(slots=True)
class Chunk:
    id: str
    text: str
    """Chunk body including its own heading context, excluding the HTML comment markers."""
    section_id: str | None
    breadcrumb: str
    tokens: int
    page_start: int | None
    page_end: int | None
    time_start: float | None
    time_end: float | None
    block_ids: list[str]


@dataclass(slots=True)
class Attachment:
    """A file the renderer produced alongside the Markdown (CSV sidecar for a table, extracted image)."""

    path: str
    """Relative path as referenced from the Markdown ('tables/table-03.csv')."""
    mime: str
    data: bytes


@dataclass(slots=True)
class RenderedOutput:
    markdown: str
    frontmatter: dict[str, object]
    sidecar: dict[str, object] | None
    chunks: list[Chunk]
    attachments: list[Attachment] = field(default_factory=list)
    tokens: int = 0
    """cl100k_base token count of `markdown`."""
    truncated: bool = False
    warnings: list[Warning] = field(default_factory=list)
    injection_risk: str = "none"
    """none | medium | high; computed by the injection scanner over the plain text."""


class Renderer(Protocol):
    format: str
    """'markdown', 'json', 'txt', 'docx'. Only 'markdown' and 'json' ship in Phase 0."""

    def render(self, result: ConversionResult, profile: Profile) -> RenderedOutput: ...


class TokenCounter(Protocol):
    def count(self, text: str) -> int: ...


class TiktokenCounter:
    """cl100k_base via tiktoken (MIT). Loaded lazily; falls back to len(text)//4 if the encoding
    cannot be loaded (offline first run)."""

    def __init__(self) -> None:
        self._enc: object | None = None

    def count(self, text: str) -> int:
        if self._enc is None:
            try:
                import tiktoken

                self._enc = tiktoken.get_encoding("cl100k_base")
            except Exception:  # noqa: BLE001
                self._enc = False
        if self._enc is False:
            return max(1, len(text) // 4)
        return len(self._enc.encode(text, disallowed_special=()))  # type: ignore[attr-defined]


class MarkdownRenderer:
    """Skeleton. Phase 0 implements: frontmatter, headings, paragraphs, code blocks, lists, page markers,
    raw blocks, warnings into frontmatter and sidecar, token count, and the agent-profile fence with a
    placeholder salt. Part 3 fills in tables, images, transcripts, footnotes, comments, tracked changes,
    TOC, numbering, chunking, link lists, and the injection scanner."""

    format = "markdown"

    def __init__(self, counter: TokenCounter | None = None) -> None:
        self.counter = counter or TiktokenCounter()

    def render(self, result: ConversionResult, profile: Profile) -> RenderedOutput:
        doc = result.document
        body_lines: list[str] = []
        for block in doc.blocks:
            emitted = self._render_block(block, profile)
            if emitted is not None:
                body_lines.append(emitted)
                body_lines.append("")
        body = "\n".join(body_lines).rstrip() + "\n"
        tokens = self.counter.count(body)
        fm = self._frontmatter(result, profile, tokens)
        parts: list[str] = []
        if profile.frontmatter:
            parts.append(self._dump_frontmatter(fm))
        if profile.untrusted_fence:
            salt = self._salt()
            parts.append(f'<untrusted_content id="{salt}" source="{doc.metadata.source}" injection_risk="none">')
            parts.append(body.rstrip())
            parts.append("</untrusted_content>")
            md = "\n".join(parts) + "\n"
        else:
            parts.append(body)
            md = "\n".join(parts)
        sidecar = self._sidecar(result, profile) if profile.sidecar else None
        return RenderedOutput(
            markdown=md,
            frontmatter=fm,
            sidecar=sidecar,
            chunks=[],
            tokens=self.counter.count(md),
            truncated=result.truncated,
            warnings=result.all_warnings,
        )

    def _render_block(self, block: object, profile: Profile) -> str | None:
        """Phase 0 covers the text-only block types. Part 3 replaces this dispatch with the full rule set.
        Unknown block types fall through to a fenced raw dump so nothing is silently lost."""
        from ezmd.ir import CodeBlock, Heading, ListBlock, PageBreak, Paragraph, Raw, spans_text

        match block:
            case Heading():
                return "#" * block.level + " " + spans_text(block.spans)
            case Paragraph():
                if block.role in ("header", "footer", "page_number") and profile.furniture == "drop":
                    return None
                return spans_text(block.spans)
            case CodeBlock():
                lang = block.language or ""
                fence = "```" if "```" not in block.code else "````"
                return f"{fence}{lang}\n{block.code}\n{fence}"
            case ListBlock():
                return self._render_list(block.items, block.ordered, block.start, 0)
            case PageBreak():
                return f"<!-- page {block.page_number} -->" if profile.page_markers else None
            case Raw():
                if profile.raw_blocks == "drop":
                    return None
                return f"```{block.format}\n{block.content}\n```"
            case _:
                return f"```ezmd-unrendered\n{type(block).__name__} {getattr(block, 'id', '')}\n```"

    def _render_list(self, items: list[object], ordered: bool, start: int, depth: int) -> str:
        from ezmd.ir import ListItem, spans_text

        out: list[str] = []
        n = start
        for it in items:
            assert isinstance(it, ListItem)
            marker = f"{n}." if ordered else "-"
            check = "" if it.checked is None else ("[x] " if it.checked else "[ ] ")
            out.append("  " * depth + f"{marker} {check}{spans_text(it.spans)}")
            if it.children:
                out.append(self._render_list(it.children, False, 1, depth + 1))
            n += 1
        return "\n".join(out)

    def _frontmatter(self, result: ConversionResult, profile: Profile, body_tokens: int) -> dict[str, object]:
        """Keys and order are specified in Part 3; Phase 0 emits this minimal set."""
        m = result.document.metadata
        fm: dict[str, object] = {
            "title": m.title,
            "source": m.source,
            "source_type": str(m.source_type),
            "fetched": m.fetched.isoformat() if m.fetched else None,
            "language": m.language,
            "words": result.metrics.counts.words,
            "tokens": body_tokens,
            "content_hash": result.document.content_hash,
            "converter": f"ezmd/{_version()} {result.converter_id}",
            "profile": profile.name,
            "truncated": result.truncated,
        }
        warnings = result.all_warnings
        if warnings:
            fm["warnings"] = [f"{w.kind}: {w.message}" for w in warnings]
        return {k: v for k, v in fm.items() if v is not None}

    def _dump_frontmatter(self, fm: dict[str, object]) -> str:
        import yaml

        return "---\n" + yaml.safe_dump(fm, sort_keys=False, allow_unicode=True, width=10_000).rstrip() + "\n---\n"

    def _sidecar(self, result: ConversionResult, profile: Profile) -> dict[str, object]:
        """Phase 0: full IR dump plus metrics. Part 3 defines the compact sections/tables/figures index."""
        return {
            "schema": "ezmd.sidecar/1",
            "profile": profile.name,
            "metrics": result.metrics.model_dump(mode="json"),
            "warnings": [w.model_dump(mode="json") for w in result.all_warnings],
            "document": result.document.model_dump(mode="json", exclude={"children"}),
        }

    def _salt(self) -> str:
        import secrets

        return secrets.token_hex(4)


class JsonRenderer:
    """Emits the sidecar structure as the primary output. Used by `format=json`."""

    format = "json"

    def render(self, result: ConversionResult, profile: Profile) -> RenderedOutput:
        import json

        md = MarkdownRenderer().render(result, profile)
        payload = {"markdown": md.markdown, "frontmatter": md.frontmatter, "sidecar": md.sidecar, "chunks": [c.__dict__ for c in md.chunks]}
        return RenderedOutput(
            markdown=json.dumps(payload, ensure_ascii=False, indent=2),
            frontmatter=md.frontmatter,
            sidecar=md.sidecar,
            chunks=md.chunks,
            tokens=md.tokens,
            truncated=md.truncated,
            warnings=md.warnings,
        )


def _version() -> str:
    try:
        import importlib.metadata as md

        return md.version("ezmd")
    except Exception:  # noqa: BLE001
        return "0.0.0"


RENDERERS: dict[str, type[Renderer]] = {"markdown": MarkdownRenderer, "json": JsonRenderer}
```

Renderer determinism rule: the body must be byte-identical for the same `Document` and `Profile`. The only nondeterministic value is the agent-profile salt, which is in the fence tag, not the body. `fetched` lives in frontmatter only. A test in Phase 0 renders the same Document twice and asserts equality of everything after the frontmatter block.

---

## 7. Job system and API contract

### 7.1 Job lifecycle

States: `queued`, `fetching`, `converting`, `rendering`, `done`, `failed`, `needs_user_action`, `expired`.

Transitions:

- `queued -> fetching` when the input is a URL (ordinary or residential).
- `queued -> converting` when the input has a body.
- `fetching -> converting` on fetch success; `fetching -> needs_user_action` when the fallback chain is exhausted (no fetch node online, captions unavailable, mirrors failed, yt-dlp blocked); `fetching -> failed` on a hard error (404, unsupported platform, SSRF block).
- `converting -> rendering` when a `ConversionResult` exists. Rendering runs for the requested profile immediately and caches the `ConversionResult` (pickled IR JSON in the blob store) so other profiles render on demand at `GET /result`.
- `rendering -> done`.
- Any state `-> failed` on exception; `-> expired` by the purge job after `EZMD_RETENTION_HOURS` (default 24).
- `needs_user_action -> queued` when the user uploads the file or the extension posts the fetched media to `POST /v1/jobs/{id}/supply`.

Job record (SQLite table `jobs`, SQLAlchemy model; Postgres via `EZMD_DATABASE_URL`):

| column | type | notes |
|---|---|---|
| id | text pk | `job_` + 22-char base62 from 16 random bytes |
| state | text | enum above |
| created_at, updated_at, expires_at | timestamp | |
| input_kind | text | path, bytes, url, residential_fetch |
| input_display | text | filename or URL (redacted of credentials) |
| input_sha256 | text nullable | content hash for idempotency |
| content_hash | text nullable | Document hash after conversion |
| mime | text nullable | |
| converter_id | text nullable | |
| profile | text | requested profile |
| options_json | text | ConvertOptions overrides |
| queue | text | default, media, fetch_residential |
| rq_job_id | text nullable | |
| progress | integer | 0..100 |
| stage_message | text | human-readable |
| error_code, error_message | text nullable | |
| needs_action | text nullable | JSON: `{"kind": "upload_file" | "use_extension", "accept": [...], "reason": "..."}` |
| blob_input, blob_ir, blob_result_prefix | text nullable | blob store keys |
| api_key_id | text nullable | |
| client_ip_hash | text | salted sha256 of the IP, for rate limit and abuse audit; raw IP never stored |
| metrics_json | text nullable | |
| warnings_count | integer | |
| truncated | boolean | |

Idempotency: `POST /v1/convert` computes sha256 of the uploaded body (or normalizes the URL: lowercase scheme and host, strip fragment, strip known tracking params `utm_*`, `fbclid`, `gclid`, `si`) and looks for a non-expired job with the same `input_sha256` (or normalized URL), the same `options_json`, and state `done`. If found, it returns that job id with HTTP 200 and `"deduplicated": true` instead of creating a new one. Clients can pass `Idempotency-Key` to override with their own key. Dedup never crosses API keys and never applies to anonymous requests from different `client_ip_hash` values when `EZMD_PUBLIC_MODE=true` (the public instance does not reveal that someone else converted the same file).

### 7.2 Queues

RQ queues on Redis:

- `default`: documents, web, code, data, email, images, notes, specialized. Worker timeout 600 s. Concurrency per worker container: 2.
- `media`: audio and video conversion (ASR, diarization). Worker timeout 3600 s. Concurrency 1 per container.
- `fetch_residential`: jobs needing a residential IP. No RQ worker consumes this queue on the VPS. Fetch nodes claim from it via `POST /v1/fetch-node/claim` (the API pops from the queue on the node's behalf; the node never talks to Redis). Jobs waiting longer than `EZMD_RESIDENTIAL_WAIT_SECONDS` (default 180) when no node has heartbeated in the last 60 s fall through to the next fallback immediately rather than waiting.
- `fetch`: ordinary URL fetches (web pages, direct file URLs, sanctioned APIs). Worker timeout 120 s. This is the only worker with outbound network beyond the allowlist; it runs the SSRF guard.

Job payloads enqueued to RQ contain only the job id. Workers load everything else from the job store. Never pickle `InputRef` or `Document` into RQ.

Progress: workers call `job_store.progress(job_id, pct, message)` at stage boundaries and, for long conversions, every 5 seconds or 5 pages. Progress writes also publish to Redis pub/sub channel `ezmd:job:{id}` so SSE connections get them without polling the DB.

### 7.3 REST API

Base path `/v1`. JSON unless noted. All responses include `X-Request-Id`. Errors use the schema in 7.5.

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/v1/convert` | optional API key; Turnstile token required for `url` inputs in public mode | Create a job from a file (multipart) or a URL (JSON) |
| GET | `/v1/jobs/{id}` | job id is the capability; optional API key | Job state and metadata |
| GET | `/v1/jobs/{id}/events` | same | SSE stream of progress and state changes |
| GET | `/v1/jobs/{id}/result` | same | Rendered output; `profile`, `format` query params |
| GET | `/v1/jobs/{id}/attachments/{path}` | same | CSV sidecars and extracted images |
| POST | `/v1/jobs/{id}/supply` | same | Client supplies a file or fetched media for a `needs_user_action` job |
| DELETE | `/v1/jobs/{id}` | same | Purge now |
| POST | `/v1/fetch-node/claim` | fetch-node secret | Claim the next residential fetch job |
| POST | `/v1/fetch-node/heartbeat` | fetch-node secret | Liveness and capabilities |
| POST | `/v1/fetch-node/upload` | fetch-node secret | Upload fetched media and metadata for a claimed job |
| POST | `/v1/fetch-node/fail` | fetch-node secret | Report a failed fetch with a reason code |
| GET | `/v1/capabilities` | none | Converters, profiles, formats, limits, whether a fetch node is online, extras installed |
| GET | `/healthz` | none | Liveness: 200 if the process is up |
| GET | `/readyz` | none | Readiness: 200 if Redis and DB are reachable and at least one worker heartbeated in 60 s |
| GET | `/openapi.json` | none | Generated schema |

`POST /v1/convert` (multipart):

```
POST /v1/convert
Content-Type: multipart/form-data; boundary=...
X-API-Key: ak_live_...            (optional)

--...
Content-Disposition: form-data; name="file"; filename="q3-fleet.pdf"
Content-Type: application/pdf

<bytes>
--...
Content-Disposition: form-data; name="options"
Content-Type: application/json

{"profile": "rag", "chunks.chunk_tokens": 512, "ocr": true, "max_pages": 200}
--...--
```

`POST /v1/convert` (JSON, URL input):

```json
{
  "url": "https://example.com/reports/q3-fleet.pdf",
  "profile": "compact",
  "options": {"max_pages": 100},
  "turnstile_token": "0.AbCd...",
  "prefer_residential": false
}
```

Response (202 Accepted; 200 when deduplicated):

```json
{
  "job": {
    "id": "job_7Kx2mQp9Lw3nRt5vYb8cDe",
    "state": "queued",
    "queue": "default",
    "created_at": "2026-10-12T18:40:00Z",
    "expires_at": "2026-10-13T18:40:00Z",
    "input": {"kind": "bytes", "display": "q3-fleet.pdf", "mime": "application/pdf", "size_bytes": 1834022},
    "profile": "rag",
    "progress": 0,
    "stage_message": "Queued"
  },
  "deduplicated": false,
  "links": {
    "self": "/v1/jobs/job_7Kx2mQp9Lw3nRt5vYb8cDe",
    "events": "/v1/jobs/job_7Kx2mQp9Lw3nRt5vYb8cDe/events",
    "result": "/v1/jobs/job_7Kx2mQp9Lw3nRt5vYb8cDe/result?profile=rag&format=md"
  }
}
```

Synchronous convenience: `POST /v1/convert?wait=30` blocks up to 30 seconds and returns the result body directly (with the job envelope in `X-Ezmd-Job` header) if the job finishes in time; otherwise returns the 202 envelope. Capped at 60 s. The CLI uses this for small files.

`GET /v1/jobs/{id}`:

```json
{
  "id": "job_7Kx2mQp9Lw3nRt5vYb8cDe",
  "state": "converting",
  "progress": 42,
  "stage_message": "Converting page 84 of 200",
  "queue": "default",
  "converter_id": "documents.docling_pdf",
  "created_at": "...", "updated_at": "...", "expires_at": "...",
  "input": {"kind": "bytes", "display": "q3-fleet.pdf", "mime": "application/pdf", "size_bytes": 1834022, "sha256": "..."},
  "profile": "rag",
  "warnings_count": 0,
  "truncated": false,
  "needs_action": null,
  "error": null
}
```

When `state == "needs_user_action"`:

```json
{
  "state": "needs_user_action",
  "needs_action": {
    "kind": "upload_file",
    "reason": "No residential fetch node is online and this platform blocks datacenter requests.",
    "accept": ["audio/*", "video/*"],
    "alternatives": ["use_extension"],
    "supply_url": "/v1/jobs/job_.../supply"
  }
}
```

`GET /v1/jobs/{id}/events` (SSE). Events: `progress` (`{"progress": 42, "stage_message": "..."}`), `state` (`{"state": "converting"}`), `warning` (a Warning JSON), `done` (`{"result_url": "..."}`), `failed` (error schema), `needs_user_action` (the needs_action object), and a comment line `: keepalive` every 15 s. The stream closes after `done`, `failed`, or `needs_user_action`. `Last-Event-ID` is honored for reconnects (events are numbered per job and buffered in Redis for the job's lifetime, capped at 500).

```
event: state
id: 3
data: {"state":"converting"}

event: progress
id: 4
data: {"progress":42,"stage_message":"Converting page 84 of 200"}

: keepalive

event: done
id: 9
data: {"result_url":"/v1/jobs/job_7Kx2mQp9Lw3nRt5vYb8cDe/result?profile=rag&format=md","tokens":10950,"warnings_count":2}
```

`GET /v1/jobs/{id}/result?profile=rag&format=md`:

- `profile`: `full` | `compact` | `rag` | `agent` (default: the job's requested profile). Dotted overrides allowed: `chunks.chunk_tokens=512`.
- `format`: `md` (default; `Content-Type: text/markdown; charset=utf-8`, headers `X-Markdown-Tokens`, `X-Ezmd-Truncated`, `X-Ezmd-Warnings`, `X-Ezmd-Injection-Risk`), `json` (the JsonRenderer payload: markdown, frontmatter, sidecar, chunks), `txt` (plain text body, no frontmatter), `docx` (Phase 5 in Part 2; 501 until then), `zip` (markdown plus sidecar plus attachments).
- Results for non-requested profiles are rendered on demand from the cached IR and cached per (job, profile, overrides hash) in the blob store.
- 409 if the job is not `done`; body includes the current state.

`POST /v1/jobs/{id}/supply` (multipart `file` or JSON `{"captions": [...], "meta": {...}}` from the extension). Transitions `needs_user_action -> queued` on the `media` or `default` queue as appropriate.

Fetch-node endpoints (details of the fetch protocol, including the platform dispatch table, are in Part 4; the contract is fixed here):

`POST /v1/fetch-node/claim`:

```json
{"node_id": "pi-home-1", "capabilities": ["yt-dlp", "ffmpeg", "deno"], "max_duration_seconds": 10800}
```

Response 200 with a job or 204 when the queue is empty:

```json
{
  "job_id": "job_...",
  "claim_token": "ct_...",
  "url": "https://www.tiktok.com/@.../video/...",
  "want": "audio",
  "max_bytes": 524288000,
  "max_duration_seconds": 3600,
  "upload_url": "/v1/fetch-node/upload",
  "claim_expires_at": "2026-10-12T18:50:00Z"
}
```

`POST /v1/fetch-node/upload` (multipart: `claim_token`, `media` file, `meta` JSON with title, uploader, duration, upload date, caption tracks if any, platform id). The API validates the claim token, stores the media in the blob store under the job, and enqueues the job on `media`. Claims expire after 10 minutes without an upload or heartbeat; the job returns to the queue once, then falls through the fallback chain.

`GET /v1/capabilities`:

```json
{
  "version": "0.1.0",
  "converters": [{"id": "documents.docling_pdf", "family": "documents", "mimes": ["application/pdf"], "experimental": false, "loaded": true, "extras": ["pdf"]}],
  "profiles": ["full", "compact", "rag", "agent"],
  "formats": ["md", "json", "txt", "zip"],
  "limits": {"max_upload_bytes": 26214400, "max_url_bytes": 10485760, "max_audio_seconds": 900, "max_pages": 200, "retention_hours": 24},
  "fetch_node_online": true,
  "residential_platforms": ["youtube", "tiktok", "instagram", "x"],
  "public_mode": true,
  "turnstile_site_key": "0x4AAAA..."
}
```

### 7.4 Auth model

- Public web UI: no accounts. File uploads need no token. URL inputs in `EZMD_PUBLIC_MODE=true` require a Turnstile token (invisible widget; the UI fetches one on page load and refreshes on expiry). The API verifies the token server-side with Cloudflare, then issues a short-lived (120 s) signed JWT in a cookie so one widget solve covers one job creation. When `EZMD_PUBLIC_MODE=false` (self-host default), Turnstile is off unless `EZMD_TURNSTILE_SECRET` is set.
- API keys: `X-API-Key: ak_<env>_<22 base62>`. Keys are created with the CLI `ezmd keys create --name ci --limit 1000/day --max-upload 100MB --allow-residential`, stored hashed (sha256 with pepper from env) in the `api_keys` table with per-key limits (requests per minute and per day, max upload bytes, max audio seconds, allowed families, residential allowed). Keyed requests skip Turnstile. A key can be marked `unlimited` (sponsor or owner key).
- Fetch nodes: `Authorization: Bearer <EZMD_FETCH_NODE_SECRET>` plus the request must arrive from the Tailscale interface (`EZMD_FETCH_NODE_CIDR`, default `100.64.0.0/10`). Both checks are required. Fetch-node endpoints are not mounted at all when `EZMD_FETCH_NODE_SECRET` is unset.
- Job access: the job id is an unguessable capability (128 bits). No enumeration endpoint exists. Keyed requests additionally require the key to match the key that created the job.
- Admin: `ezmd admin` CLI only, run on the host. No admin HTTP endpoints.

### 7.5 Error schema

```json
{
  "error": {
    "code": "input_too_large",
    "message": "Upload exceeds the 25 MB limit for anonymous requests.",
    "status": 413,
    "request_id": "req_...",
    "detail": {"limit_bytes": 26214400, "received_bytes": 31457280},
    "docs": "https://<host>/docs/errors#input_too_large"
  }
}
```

Error codes (HTTP status): `invalid_request` (400), `turnstile_required` (401), `turnstile_failed` (403), `unauthorized` (401), `forbidden` (403), `not_found` (404), `job_not_ready` (409), `input_too_large` (413), `unsupported_media_type` (415), `url_blocked` (422, SSRF or disallowed scheme), `platform_disabled` (422), `rate_limited` (429, with `Retry-After`), `conversion_failed` (500, with the converter's `user_message`), `fetch_failed` (502), `queue_unavailable` (503, with `Retry-After`), `timeout` (504).

Never include stack traces, file paths on the server, or engine internals in `message`. Log them with the request id.

### 7.6 Rate limits (defaults; all env-configurable)

Anonymous, per `client_ip_hash`: 20 job creations per minute, 200 per day, 10 concurrent active jobs, 40 result fetches per minute, 10 SSE connections. Keyed: per-key values. Fetch-node: 60 claims per minute per node. Limits are enforced with a Redis sliding window; responses include `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`.

---

## 8. Security baseline

Every input is hostile. The public instance and self-host get identical defaults; self-hosters may loosen limits via env, never the sandbox.

### 8.1 Sandboxed conversion workers

- Workers run in a separate container from the API. The container runs as a non-root user with a read-only root filesystem, a tmpfs at `/tmp` sized by `EZMD_WORKER_TMP_MB` (default 2048), `cap_drop: [ALL]`, `no-new-privileges`, the Docker default seccomp profile plus a custom profile in `deploy/seccomp-worker.json` that additionally denies `ptrace`, `mount`, `keyctl`, `bpf`, `userfaultfd`.
- Network: the `default` and `media` workers are on an internal compose network with no default route except to Redis, the API (for blob access), and an explicit egress allowlist resolved at container start (model download hosts `huggingface.co`, `cdn-lfs.huggingface.co`, and hosted ASR endpoints when configured). Enforced by `deploy/egress-allowlist.sh` with iptables inside the worker container entrypoint, or by Docker network policy when available. The `fetch` worker is the only one with general egress, and it runs the SSRF guard.
- Resource limits per job, enforced in the worker process with `resource.setrlimit` (RLIMIT_AS = `EZMD_JOB_MEM_MB`, default 4096 for default queue and 8192 for media; RLIMIT_CPU = job timeout; RLIMIT_NPROC = 64; RLIMIT_FSIZE = 2 GB) and at the container level with compose `mem_limit`, `pids_limit: 256`, `cpus`. Each conversion runs in a child process (`multiprocessing` with `spawn`) so a crashing or hanging engine kills only that child; the parent enforces the wall-clock timeout with SIGKILL after `max_seconds + 30`.
- External binaries (ffmpeg, pandoc, deno, yt-dlp, tesseract) are invoked via `ezmd.core.sandbox.run(argv: list[str], *, timeout, cwd, env_allowlist)` which uses `subprocess.run` with a list argv, `shell=False`, a minimal environment, `stdin=DEVNULL`, output caps (stdout and stderr truncated at 10 MB), and `timeout`. Where `bwrap` (bubblewrap) is available in the worker image, `sandbox.run` wraps the command with `bwrap --ro-bind /usr /usr --tmpfs /tmp --unshare-all --die-with-parent` plus a bind for the job's working directory only. ffmpeg is always run with `-nostdin -protocol_whitelist file,pipe` to disable network protocols.

### 8.2 Input validation

- Type by magic, never by extension (section 5.1). If the detected type and the declared type disagree, the detected type wins and a `Warning(kind=OTHER, message="Declared type ... did not match detected type ...")` is attached. A file whose detected type is executable (`application/x-executable`, `application/x-dosexec`, `application/x-mach-binary`, `application/x-sharedlib`) is rejected with `unsupported_media_type`.
- Multipart filenames: take the basename only, strip control characters and path separators, cap at 255 bytes, never use the user filename for a path on disk (use the job id).
- Size caps are enforced at three layers: Caddy `request_body max_size`, FastAPI streaming upload that aborts at `max_upload_bytes + 1`, and `InputRef.max_bytes`. `Content-Length` is advisory; the stream is counted.
- Archives (zip, tar, 7z, and container formats like DOCX, EPUB, ODF, IPYNB-in-zip): decompression limits enforced by the archive converter and by the Office converters before handing to engines. Limits: total uncompressed size `EZMD_ARCHIVE_MAX_BYTES` (default 500 MB), max entries 10,000, max nesting depth 3, compression ratio cap 100:1 per entry (abort if exceeded), no symlinks or absolute paths or `..` components extracted, no entries extracted to disk at all when not needed (stream members). Nested archives count against the parent's budget.
- PDF: before any engine sees the file, run `ezmd.core.sanitize.pdf` using pikepdf (MPL-2.0): remove `/OpenAction`, `/AA`, `/JavaScript`, `/JS`, `/Launch`, `/EmbeddedFiles` (recorded as `ATTACHMENT_SKIPPED` warnings with names), `/RichMedia`, `/XFA` (recorded as `UNSUPPORTED_FEATURE`), and encrypted files with a non-empty user password are rejected with `encrypted_content`. Save the sanitized copy and convert that. Page count is read here and `max_pages` applied by truncation of the sanitized copy.
- Office: DOCX/XLSX/PPTX are zip containers. Before parsing, inspect the manifest: remove `vbaProject.bin` and any `.bin` ActiveX parts and record `REMOVED_SCRIPT_OR_MACRO`; drop external relationships of type `oleObject`, `hyperlink` with `file:` scheme, and `attachedTemplate`; reject if the zip fails the archive limits. Legacy binary `.doc`/`.xls`/`.ppt` go through LibreOffice headless conversion to OOXML inside the sandbox first (LibreOffice is in the worker image with macros disabled via a locked-down `registrymodifications.xcu`).
- SVG: parsed with `defusedxml`; `<script>`, `on*` attributes, external `<use>`, `<foreignObject>`, and external entity references are stripped before rasterization or text extraction.
- HTML: parsed with a tolerant parser (lxml via Trafilatura or selectolax), never executed. JS rendering (Crawl4AI/Playwright) only in the fetch worker, with the browser's network restricted by the same SSRF guard through a proxy, no file access, and a 60 s budget.
- XML of any kind: `defusedxml` or lxml with `resolve_entities=False, no_network=True, huge_tree=False`.
- Images: Pillow with `MAX_IMAGE_PIXELS` set to 50 MP; decompression bomb errors become `conversion_failed`.
- Media: ffprobe first (sandboxed) to read duration and streams; reject if duration exceeds the cap or if no audio stream; re-encode to 16 kHz mono WAV in the sandbox before any ASR engine sees it.
- Text: NUL bytes stripped, invalid UTF-8 replaced, bidi override and non-printing format characters (U+200B..U+200F, U+202A..U+202E, U+2066..U+2069, U+FEFF, Unicode Tags block) removed from body text and counted in `REMOVED_HIDDEN_ELEMENTS`.

### 8.3 SSRF protection on URL fetch

Implemented once in `ezmd.core.netguard` and used by the fetch worker, the web converters, feed followers, and the extension's server-side relay.

1. Scheme allowlist: `http`, `https` only. Reject URLs with userinfo (`user:pass@`).
2. Host validation: reject IP literals in private, loopback, link-local, multicast, reserved, CGNAT (100.64.0.0/10, which is also the Tailscale range), and IPv6 ULA/link-local ranges. Reject `localhost`, `*.localhost`, `*.internal`, `*.local`, `*.arpa`, and the metadata hostnames (`metadata.google.internal`).
3. DNS: resolve once with a 3 s timeout, reject if any A/AAAA answer is in a blocked range, then pin: connect to the resolved IP with the original hostname for SNI and Host header. Use httpx with a custom transport that performs the connect to the pinned IP. Never let the HTTP client re-resolve (prevents DNS rebinding).
4. Redirects: follow at most 5, re-run steps 1 to 3 on every hop, drop `Authorization` and cookies across hosts.
5. Response: cap body at `max_url_bytes` (streamed, abort at cap + 1), total time 30 s (120 s in the fetch worker for media), reject `Content-Type` of executables.
6. Platform policy: a `platforms.toml` lists hosts that are `sanctioned`, `residential_only`, or `disabled`. `disabled` hosts return `platform_disabled` immediately. The public instance ships with a stricter `platforms.public.toml`.
7. Every fetch is logged with request id, redacted URL (userinfo removed, query params longer than 64 chars truncated), resolved IP, status, bytes, and duration.

Tests in `tests/security/test_netguard.py` cover: `http://169.254.169.254/`, `http://[::ffff:169.254.169.254]/`, `http://0x7f000001/`, `http://2130706433/`, `http://localhost.example.com/` (must resolve and be blocked only if it resolves private), a redirect from a public host to `http://127.0.0.1:6379/`, a hostname with two A records where one is private, and `http://100.100.100.100/`.

### 8.4 Application hardening

- No shell interpolation of user strings anywhere. `ruff` rule `S602`, `S603`, `S604`, `S605`, `S607` enabled via `flake8-bandit` in `ruff.toml`; `subprocess` is only imported in `ezmd.core.sandbox`. A grep test asserts this.
- Secrets only via env. `.env.example` documents every variable. The API refuses to start in public mode if `EZMD_JWT_SECRET` or `EZMD_KEY_PEPPER` is shorter than 32 bytes.
- Security headers on every response (set in the API, duplicated in the Caddyfile): `Content-Security-Policy: default-src 'self'; script-src 'self' https://challenges.cloudflare.com; frame-src https://challenges.cloudflare.com; img-src 'self' data: blob:; connect-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: no-referrer`, `X-Frame-Options: DENY`, `Permissions-Policy: camera=(), microphone=(), geolocation=()`, `Strict-Transport-Security: max-age=31536000; includeSubDomains` (Caddy), `Cross-Origin-Opener-Policy: same-origin`, `Cross-Origin-Resource-Policy: same-origin`.
- Result downloads are served with `Content-Disposition: attachment` for `format=zip` and with `Content-Type: text/markdown; charset=utf-8` and `X-Content-Type-Options: nosniff` for `md`; extracted images are re-encoded through Pillow before storage so no original bytes are served back.
- CORS: `EZMD_CORS_ORIGINS` (default: same-origin only; the extension uses its own origin and must be listed; the public instance lists the extension ids).
- Rate limiting as in 7.6. Additionally a global concurrency cap on active conversions (`EZMD_MAX_ACTIVE_JOBS`, default 2x worker slots) returning `queue_unavailable` with `Retry-After` when exceeded.
- Dependency audit in CI: `pip-audit` and `pnpm audit` on every PR and nightly; Dependabot or Renovate config for weekly bumps; a nightly workflow rebuilds images and runs the golden suite.
- Prompt-injection flagging: the injection scanner (defined in Part 3) runs over the plain text of every result, sets `injection_risk`, adds `INJECTION_PATTERN` warnings with the pattern name and a 60-char snippet, and the `agent` profile wraps the body in a session-salted `<untrusted_content id="<salt>">` fence. No profile ever removes flagged text. The fence salt is generated per render and is not derivable from the job id.
- Log redaction: a logging filter in `ezmd.core.logging` redacts `X-API-Key` values, `Authorization` headers, Turnstile tokens, claim tokens, URL userinfo, and any string matching the API key pattern. Logs never contain document content; converter debug logs that need content are gated behind `EZMD_DEBUG_CONTENT=1`, which the public instance never sets. Client IPs are stored only as salted hashes.
- Retention: a scheduled purge (RQ scheduler job every 10 minutes) deletes blobs and DB rows for jobs older than `EZMD_RETENTION_HOURS` (24). `DELETE /v1/jobs/{id}` purges immediately. Blob store keys are `jobs/{job_id}/...` so a job purge is a prefix delete.
- MCP server over HTTP requires a bearer token by default and binds to loopback unless `EZMD_MCP_BIND` is set. Stdio mode has no auth (local process).
- The extension sends only the fetched media or caption JSON plus the source URL to the API; it never sends cookies, page HTML beyond the article body it extracted, or any other tab data.

### 8.5 Threat model

| Threat | Asset | Attack vector | Controls | Residual risk |
|---|---|---|---|---|
| Malicious document executes code in worker | Worker host, other jobs | PDF JS, Office macros, OLE, engine parser bugs | Sanitize before parse; sandboxed child process; read-only FS; seccomp; no egress; non-root | Engine zero-day escapes to container; mitigated by cap_drop and resource limits, not eliminated |
| Decompression bomb | Worker memory and disk | Nested zip, PDF stream bomb, PNG bomb | Ratio and size caps; RLIMIT_AS; tmpfs size; Pillow pixel cap | Engine-internal allocation before our caps engage |
| Denial of service via slow or huge inputs | Public instance availability | 3-hour audio, 10k-page PDF, slow upload, SSE holding | Duration/page/byte caps; per-IP and global concurrency caps; streaming upload timeouts; SSE keepalive and max connections | Distributed abuse beyond Turnstile; respond with `DISABLED_SERVICES` and tighter caps |
| SSRF to internal services or cloud metadata | VPS, Redis, Tailscale network, Pi | URL input, redirect, DNS rebinding, HTML with remote resources | netguard with resolve-once pinning; scheme allowlist; private range block incl. CGNAT; redirects re-checked; converters run with `allow_network=False` | New private range or IPv6 transition trick; keep block list tested |
| Forged fetch node | Job content, residential egress | Stolen secret, spoofed claim | Shared secret plus Tailscale CIDR check; claim tokens per job; upload bound to claim; node never reachable inbound | Secret leak from the Pi; rotate via env, nodes re-enroll |
| Job result disclosure | User documents | Job id guessing, log leakage, shared cache | 128-bit ids; no enumeration; key-bound access for keyed jobs; no dedup across identities in public mode; content never logged; 24 h purge | Users sharing result links; documented |
| Prompt injection via converted content | Downstream agents | Hidden text, white-on-white, HTML comments, bidi tricks, instructions in docs | Hidden element removal with counts; injection scanner; salted fence in agent profile; never alter text | Scanner misses novel patterns; risk level is advisory |
| Supply chain | Everything | Compromised dependency, model weights, base image | Lockfiles with hashes; `pip-audit`/`pnpm audit`; pinned base images by digest; weights pinned by sha256 in `models.toml`; license allowlist doubles as an inventory | Upstream compromise within a pinned version; nightly audit |
| Abuse of public instance for illegal content or ToS violation | Operator liability | Fetching DRM or platform-blocked content | Platform policy file; residential fetch only for self-host nodes the operator owns; no media re-serving (text out only); DMCA contact; 24 h retention | Operator still receives complaints; `DISABLED_SERVICES` switch |
| Credential leakage in logs or errors | API keys, secrets | Exceptions with headers, URL userinfo | Redaction filter; error schema without internals; userinfo rejected at input | Third-party library logging raw requests; audited per library in research step |
| Path traversal | Worker FS, blob store | Multipart filename, archive member names, attachment paths | Basename only; job-id paths; archive member validation; blob keys built from ids only | None known |
| Unsafe deserialization | Worker | RQ payload tampering via Redis | RQ payload is only the job id; Redis is on the internal network with `requirepass`; IR is JSON, never pickle | Redis compromise equals full compromise; keep it internal |

---

## 9. Foundation build steps (Phase 0)

Phase 0 ends with a working vertical slice: a plain-text file goes from the web UI through the API and queue to a worker, is converted into the IR, rendered through the skeleton renderer, and comes back as Markdown with frontmatter, all inside Docker Compose, with every CI gate active. Everything after Phase 0 adds converters, renderer rules, and deployment targets to this skeleton.

Each task below lists acceptance criteria. Mark tasks `done` in STATUS.md only when every criterion holds.

### P0-T01 Name availability check

1. Check `ezmd` on PyPI (`https://pypi.org/pypi/ezmd/json` returns 404 means free), npm (`https://registry.npmjs.org/ezmd`), GitHub org (`https://github.com/ezmd` 404), and `ezmd.dev` / `ezmd.com` via RDAP (`https://rdap.org/domain/ezmd.dev`).
2. Record results in DECISIONS.md as D-0001. If PyPI or npm is taken, choose a new name (short, pronounceable, free on both), record it, and rename everywhere before continuing. Domain availability is recorded only; do not purchase.
3. Acceptance: D-0001 exists with the four results and the final name.

### P0-T02 Repository scaffold

1. Create the monorepo layout from 1.3. Root files: `pyproject.toml` (uv workspace with members `packages/*`, `apps/api`, `apps/fetch-node`, `packages/mcp`), `uv.lock`, `package.json` (pnpm workspace: `apps/web`, `apps/extension`, `packages/sdk-ts`), `pnpm-workspace.yaml`, `Makefile` (`gates`, `test`, `lint`, `fmt`, `golden`, `up`, `smoke`), `ruff.toml` (line length 120, rules `E,F,W,I,N,UP,B,S,C4,SIM,RUF`, bandit S rules enabled), `mypy.ini` (strict for `packages/core`), `.editorconfig`, `.gitignore`, `.env.example`, `LICENSE` (Apache-2.0), `NOTICE`, `README.md` (one screen: what it is, quickstart with `uvx ezmd convert`, compose one-liner, link to docs), `CLAUDE.md` (section 3), `DECISIONS.md`, `ROADMAP.md` (all phases and tasks from all four parts, with ids and blocked_by), `STATUS.md` (section 2.8 format, all tasks `pending`), `CHANGELOG.md`, `CONTRIBUTING.md`, `SECURITY.md` (disclosure address placeholder, supported versions), `CODE_OF_CONDUCT.md`.
2. Copy the four spec parts into `docs/spec/`.
3. `packages/core/pyproject.toml`: package `ezmd`, Python `>=3.12`, deps: `pydantic>=2`, `pyyaml`, `tiktoken`, `magika`, `python-magic`, `rapidfuzz`, `typer`, `rich`, `httpx`. Entry points: `ezmd = ezmd.cli:app`, `ezmd-score = ezmd.testing.cli:score`, `ezmd-golden = ezmd.testing.cli:golden`.
4. Acceptance: `uv sync --all-packages --dev` succeeds; `pnpm install` succeeds; `make gates` runs (it may fail on empty packages at this point, but each gate command executes); git initialized with `main`, first commit `chore: scaffold monorepo`.

### P0-T03 Core IR

1. Implement `packages/core/ezmd/ir.py` exactly as in section 4 (you may fix type errors mypy finds, logging each change in DECISIONS.md if it changes semantics).
2. Tests in `packages/core/tests/test_ir.py`: round-trip every block type through `model_dump_json` and `model_validate_json`; `finalize()` assigns ids, rejects duplicate ids and dangling parents; `Table` validator rejects out-of-shape cells and sets `has_merged_cells`; `plain_text()` ordering; `counts()` correctness on a synthetic document with every block type; `sections()` grouping with and without a leading heading.
3. Acceptance: tests pass; `mypy --strict packages/core` clean; coverage of `ir.py` at least 95%.

### P0-T04 Detection

1. Implement `packages/core/ezmd/detect.py` per 5.1 with Magika and libmagic. Magika model download at first use goes to `EZMD_MODEL_DIR`; the Docker image pre-bakes it.
2. Tests: a table of 20 small synthetic files (txt, md, csv, json, html, pdf header, zip, png, mp3 header, docx minimal, empty, random bytes, a `.py` file renamed `.png`, a PNG renamed `.py`) asserting the resolved mime and that the rename cases resolve by content.
3. Acceptance: tests pass; detection of a 10 MB file completes under 200 ms (test with a timer, skip in CI if the runner is slow but assert locally).

### P0-T05 Inputs, registry, chains, sandbox, netguard

1. Implement `inputs.py`, `registry.py`, `chains.py` per section 5, including wildcard chain matching and `FetchRequired` propagation.
2. Implement `ezmd/core/sandbox.py` (`run()` per 8.1, with bwrap when present) and `ezmd/core/netguard.py` per 8.3 (resolve-once pinned httpx transport, redirect re-validation, byte cap, platform policy loader).
3. Implement `ezmd/core/licensing.py` (`notify_once`) and `ezmd/core/logging.py` (redaction filter).
4. Tests: registry resolution order with three fake converters of differing confidence and priority; chain override; fallback on `ConversionError`, on crash, and on empty document; `retryable_with_fallback=False` stops the chain; `FetchRequired` passes through; broken entry point is isolated (simulate with a fake `entry_points`); converter contract test harness (5.5) runs against all registered converters; `sandbox.run` rejects a string argv, enforces timeout (sleep 5 with timeout 1), caps output; netguard tests from 8.3; redaction filter tests.
5. Acceptance: tests pass; mypy strict clean.

### P0-T06 Plain text and Markdown passthrough converters

1. `packages/converters/ezmd_converters/text/plain.py`: `text.plain` handles `text/plain` and any `text/*` not claimed at higher confidence. Decodes with charset detection (`charset-normalizer`, MIT), splits paragraphs on blank lines, detects simple heading conventions (a line underlined with `===` or `---`, or a line that is the only content and under 80 chars followed by a blank line is not a heading; only underline style is promoted), emits `Paragraph` blocks with line provenance, strips NUL and control characters with a warning count. Line numbers in provenance.
2. `text.markdown_passthrough`: `text/markdown` parsed with `markdown-it-py` (MIT) into the IR (headings, paragraphs, lists, code, quotes, links, images as `Image` with `ref`, tables as `Table`). This proves the IR can represent Markdown losslessly enough that rendering a Markdown input in the `full` profile reproduces its structure.
3. Register both in `ezmd/builtin.py` and the chains.
4. Fixtures: `fixtures/text/plain-utf8`, `fixtures/text/plain-latin1-with-bom`, `fixtures/text/markdown-kitchen-sink` (headings, nested lists, table, code, quote, image, footnote-style refs). Goldens generated, Skeptic-reviewed, committed with `meta.toml`.
5. Acceptance: fixtures pass at 0.95 (threshold override upward is allowed for trivial converters); contract test passes.

### P0-T07 Profiles, renderer skeleton, scoring

1. Implement `profiles.py` and `render/base.py` per section 6 plus `render/__init__.py` exposing `render(result, profile_name, format, **overrides)`.
2. Implement `testing/score.py` per 2.4 and the `ezmd-score` and `ezmd-golden` CLIs. `ezmd-golden --write` writes `expected.full.md` and `expected.sidecar.json` and prints a reminder that Skeptic review is required.
3. Implement the fixture pytest plugin `testing/pytest_fixtures.py` that discovers `fixtures/**/meta.toml`, parametrizes a test per fixture, converts, renders `full`, scores, and asserts the threshold from `fixtures/thresholds.toml` with `meta.toml` overrides, plus the hard-failure checks.
4. Determinism test: render twice, compare everything after the frontmatter.
5. Acceptance: `uv run pytest fixtures -q` passes for the three text fixtures; `ezmd-score` prints the four sub-scores and overall; mypy strict clean.

### P0-T08 CLI

1. `ezmd convert <path-or-url> [--profile full] [--format md] [--out path] [--sidecar] [--converter id] [--opt key=value]...`: local conversion through the registry and renderer. URLs in Phase 0 go through netguard to a temp file and then the registry (only text types will succeed until Part 2).
2. `ezmd capabilities`, `ezmd detect <path>`, `ezmd version`.
3. `ezmd serve` is a thin wrapper that runs the API with uvicorn (useful for self-host without compose).
4. Acceptance: `ezmd convert fixtures/text/markdown-kitchen-sink/input.md --profile compact` prints Markdown with frontmatter; exit code 2 on unsupported type with the `user_message`; `--help` output is checked into `docs/cli.md` by a generator script.

### P0-T09 API

1. `apps/api/ezmd_api/`: `main.py` (FastAPI app factory, middleware: request id, security headers, CORS, rate limit, redaction logging), `settings.py` (pydantic-settings, every `EZMD_*` var), `db.py` (SQLAlchemy 2 with SQLite default and Postgres option, Alembic migrations), `blobs.py` (local FS default, S3 via `boto3` optional extra `[s3]`), `jobs.py` (job store, state transitions, progress with pub/sub), `queue.py` (RQ enqueue helpers, queue routing by mime family), `routes/convert.py`, `routes/jobs.py` (get, events SSE, result, attachments, supply, delete), `routes/fetch_node.py` (claim, heartbeat, upload, fail; mounted only when secret set), `routes/meta.py` (capabilities, healthz, readyz), `errors.py` (schema 7.5), `auth.py` (API keys, Turnstile verification, fetch-node auth), `worker.py` (RQ worker entry with sandbox child-process execution, progress callbacks, result caching of the IR), `purge.py` (retention job), `static.py` (serve `apps/web/dist` at `/` with SPA fallback, cache headers).
2. Rate limiting via Redis sliding window per 7.6. Turnstile verification is implemented but disabled unless configured.
3. Tests with `httpx.AsyncClient` against the app with an in-memory SQLite and `fakeredis`: create job from multipart, poll, SSE receives `done`, result in all four profiles and `md`/`json`/`txt` formats, 409 before done, 413 over cap, 415 for executables, dedup returns the same job, error schema shape, security headers present, rate limit returns 429 with headers, fetch-node routes absent without secret and 401 with wrong secret, job purge deletes blobs.
4. OpenAPI generated and committed to `docs/api/openapi.json` with a test that fails if the committed file is stale.
5. Acceptance: tests pass; `uv run mypy apps/api` clean; `uvicorn ezmd_api.main:app` serves `/healthz` and `/v1/capabilities`.

### P0-T10 Web UI

1. `apps/web`: React 18 + Vite + TypeScript, no UI framework beyond a small CSS file (keep the dependency footprint minimal; Tailwind is acceptable if you want it). Pages: single page with a drop zone and URL field, profile selector, options drawer (max pages, OCR toggle), a job progress panel driven by SSE, a result view with tabs (Markdown rendered, raw, sidecar JSON, warnings), copy and download buttons, and a capabilities-driven list of supported inputs. Turnstile widget mounted only when `turnstile_site_key` is present in capabilities. Dark mode via `prefers-color-scheme`.
2. `packages/sdk-ts`: generated client from `docs/api/openapi.json` (`openapi-typescript` plus a 150-line hand-written wrapper with `convert()`, `waitForJob()` using SSE with polling fallback, `getResult()`). The web UI uses this SDK.
3. Tests: Vitest unit tests for the SDK wrapper (mocked fetch and EventSource); Playwright e2e test that uploads `fixtures/text/plain-utf8/input.txt` against the running API and asserts the Markdown appears.
4. Acceptance: `pnpm -r build` succeeds; `pnpm -r lint` and `typecheck` clean; e2e passes locally and in CI (CI runs the API with a worker and fakeredis-free real Redis service).

### P0-T11 Docker and Compose

1. `deploy/Dockerfile.api` (python:3.12-slim pinned by digest, uv install, non-root, builds web UI in a node stage and copies `dist`), `deploy/Dockerfile.worker` (same base plus libmagic, ffmpeg, pandoc, bubblewrap; model pre-bake stage for Magika; non-root, read-only FS compatible), `deploy/compose.yml` (services: `caddy`, `api`, `worker-default`, `worker-media`, `worker-fetch`, `redis` with `requirepass` and no host port, `purge` as a one-shot scheduler sidecar or in-API scheduler; internal network for workers with no default egress except allowlist; volumes for SQLite and blobs; healthchecks; `mem_limit`, `pids_limit`, `cap_drop`, `read_only`, `security_opt`), `deploy/compose.gpu.yml` override (adds the NVIDIA runtime to `worker-media`, used from Part 2), `deploy/Caddyfile` (TLS automatic when `EZMD_DOMAIN` set, otherwise plain HTTP on 8080; `request_body max_size`; security headers; `/v1/fetch-node/*` restricted to the Tailscale interface address), `deploy/seccomp-worker.json`, `deploy/egress-allowlist.sh`, `deploy/smoke.sh` (waits for `/readyz`, posts a text file, polls, asserts Markdown contains the expected heading, also tests `format=json`, exits non-zero on failure; `--remote` mode skips bring-up).
2. `.env.example` lists every variable with defaults and comments. `EZMD_PUBLIC_MODE=false` by default.
3. Acceptance: on a clean machine `docker compose -f deploy/compose.yml up --build -d && deploy/smoke.sh` passes; image sizes recorded in STATUS.md metrics (`api` under 400 MB, `worker` under 1.2 GB before any ML extras); `docker compose config` validates; the worker container has no route to the internet (test from inside with a curl to a public IP that must fail, included in smoke.sh).

### P0-T12 CI and release workflow

1. `.github/workflows/ci.yml`: on push to `main` and on PRs: matrix for Python 3.12 on ubuntu-latest; steps: uv sync, pnpm install, ruff, mypy, license check, pip-audit, pnpm audit, unit tests, fixture tests, web build and tests, docker build of all images (no push), compose smoke on the runner. Cache uv and pnpm stores and the Magika model.
2. `.github/workflows/nightly.yml`: rebuild images, run goldens, run `pip-audit`/`pnpm audit`, open an issue on failure.
3. `.github/workflows/release.yml`: on tag `v*`: build and push multi-arch images to GHCR (`ghcr.io/<org>/ezmd-api`, `ezmd-worker`, `ezmd-fetch-node` from Part 4), build the Python package with `uv build` and publish to TestPyPI for `v0.0.*` (PyPI for `v0.1.0+` is behind a manual environment approval, which is the human gate), attach the extension zip (from Part 4) and `CHANGELOG.md` section as release notes.
4. `tools/license_check.py`, `tools/license_check.mjs`, `tools/license_allowlist.toml`, `tools/license_overrides.toml`, `tools/audit_ignore.toml`.
5. Dependabot config for pip, npm, docker, and GitHub Actions, weekly.
6. Acceptance: CI green on `main`; a test tag `v0.0.1-rc1` on a branch triggers the release workflow through the image build step successfully (publishing steps may be dry-run with `if: false` until the human gate is cleared, logged in STATUS.md under Blocked on human).

### P0-T13 Docs skeleton and Phase 0 close

1. `docs/`: `index.md`, `quickstart.md` (CLI, compose, API curl examples), `selfhost.md` (env vars table generated from `settings.py`), `api.md` (rendered from OpenAPI with a short narrative), `cli.md` (generated), `output-format.md` (placeholder pointing at Part 3 until implemented), `security.md` (section 8 adapted for users, threat model table), `licenses.md` (policy, allowlist, extras), `plugins.md` (entry point how-to with the 40-line example), `converters/README.md` (table to be filled per family), `errors.md` (codes table).
2. `mkdocs.yml` with Material theme (MIT) building `docs/` to `site/`; CI builds docs and fails on warnings.
3. Council: convene the three-reviewer council on the question "Is the Phase 0 IR, registry, and API contract sufficient for Parts 2 to 4 without breaking changes? Name anything that must change now." Apply accepted changes, log D-entries.
4. Tag `v0.0.1`. Update STATUS.md phase table. Write a short Phase 0 summary in STATUS.md.
5. Acceptance: docs build clean; council logged; tag exists; STATUS.md shows Phase 0 `done` 13/13.

End of Part 1. Continue with Part 2 (converter families), Part 3 (output format and profiles), and Part 4 (fetch node, extension, MCP, deployment, public instance). ROADMAP.md must contain every task from all four parts before Phase 1 begins.
