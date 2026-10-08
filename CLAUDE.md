# intomd

Convert anything to LLM-ready Markdown. Apache-2.0. Python 3.12 core, TypeScript UI/extension.

The spec was written under the codename "anymd"; the project is named intomd (DECISIONS.md D-0001). The copies in `docs/spec/` are already renamed.

## Read first
- `docs/spec/part1.md` through `part4.md`: the build specification (`docs/spec/README.md` has the reconciliation notes). Part 1 section 2 contains the operating rules. Follow them.
- `STATUS.md`: current phase, task table, blockers. Update it after every task.
- `ROADMAP.md`: ordered phases and tasks with acceptance criteria.
- `DECISIONS.md`: append-only decision log. Every non-trivial choice goes here. D-0002 records where the spec parts conflict and which one wins.

## Layout
- `packages/core/src/intomd/`: IR (`ir.py`), inputs (`inputs.py`), detection (`detect.py`), registry (`registry.py`), chains (`chains.py`), builtin registration (`builtin.py`), pipeline (`pipeline.py`), renderers (`render/`), profiles (`profiles.py`), warning codes (`warnings/codes.py`), security utilities (`core/`: sandbox, netguard, licensing, logging, textclean), CLI (`cli/`), testing utilities (`testing/`).
- `packages/converters/src/intomd_converters/<family>/`: one subpackage per family. Built-ins are listed in `intomd_converters.builtin_converters()`; third-party converters register via the `intomd.converters` entry point group.
- `apps/api/src/intomd_api/`: FastAPI app, RQ workers (`worker.py`), job store, blob store.
- `apps/web/`: React + Vite. Built output is served by the API at `/`.
- `apps/fetch-node/`: residential fetch worker for Raspberry Pi (Phase 3).
- `apps/extension/`: MV3 browser extension (Phase 3).
- `packages/mcp/`: MCP server (stdio and streamable HTTP, Phase 1).
- `packages/sdk-ts/`: thin TypeScript client (`@intomd/sdk`).
- `fixtures/<family>/<name>/`: input, expected outputs, meta.toml. Golden tests. `fixtures/thresholds.toml` holds per-converter thresholds.
- `deploy/`: `Dockerfile` (targets api, worker, fetch-node), `docker-compose*.yml`, Caddyfile, seccomp profile, smoke test.
- `tools/`: license and audit tooling.

## Commands
- Install: `uv sync --all-packages --dev` and `pnpm install`
- Unit tests: `uv run pytest packages apps tests -x -q`
- Golden tests: `uv run pytest fixtures -q` (add `-k <converter>` to narrow)
- Score one fixture: `uv run intomd-score fixtures/text/markdown-kitchen-sink`
- Regenerate a golden (then get Skeptic review before committing): `uv run intomd-golden fixtures/text/markdown-kitchen-sink --write`
- Lint: `uv run ruff check . && uv run ruff format --check . && pnpm -r lint`
- Types: `uv run mypy --strict packages/core/src && uv run mypy apps/api/src packages/converters/src packages/mcp/src && pnpm -r typecheck`
- License check: `uv run python tools/license_check.py && pnpm licenses list --json --prod | node tools/license_check.mjs`
- Audit: `uv run pip-audit && pnpm audit --audit-level=high`
- All gates: `make gates`
- Run API locally: `uv run uvicorn intomd_api.main:app --reload --port 8000`
- Run worker locally: `uv run rq worker default --url redis://localhost:6379`
- Run web dev server: `pnpm --filter @intomd/web dev`
- Compose (CPU): `docker compose -f deploy/docker-compose.yml up --build`
- Smoke test: `deploy/smoke.sh` (local) or `deploy/smoke.sh --remote https://host`
- CLI: `uv run intomd convert <path-or-url> --profile compact`

## Conventions
- Conventional Commits with scope = path segment. Footer `Task: Pn-Tnn`.
- Trunk-based. Branch `task/<phase>-<id>-<slug>`, squash merge after gates pass (Phase 0 was built in parallel on main; D-0008).
- Types everywhere. `mypy --strict` on core is non-negotiable. Pydantic v2 models for IR and API schemas.
- No shell string interpolation of user data. `subprocess` is imported only in `intomd.core.sandbox`; use `intomd.core.sandbox.run([...])` (a test enforces this).
- Every converter returns a `Document` or raises `ConversionError`. Never return an empty Document silently; attach warnings.
- Every block carries `Provenance`. If you do not know the page or bbox, leave them None, but set `source`.
- New warning codes go in `intomd/warnings/codes.py` with severity, description, and a user-facing suggestion.
- Dependencies: allowlisted licenses only in defaults. See `tools/license_allowlist.toml`. Forbidden licenses go in named extras with `notify_once`.
- Fixtures must be public domain, CC0, CC-BY, or self-generated, with `[provenance]` in meta.toml. No commercial media, no platform-scraped content.
- Never commit secrets. `deploy/env.example` lists every env var with a comment.
- Research step and approach note before every converter or integration.
- Council (3 reviewers) for architectural decisions and failing converters. Red team before public-facing phases.
- Do not ask the human unless the decision is irreversible and externally costly.

## Spec pointer
The authoritative specification is `docs/spec/part1.md` to `docs/spec/part4.md`. When this file and the spec disagree, the spec wins; log the disagreement in DECISIONS.md and fix this file.
