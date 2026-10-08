# Contributing to ezmd

Thanks for helping. This guide covers setup, conventions, the converter contract, and the two processes
specific to this project: the council and the fixture process. The build specification lives in
`docs/spec/` and the layout and commands in `CLAUDE.md`.

## Setup

```sh
git clone https://github.com/larpey/ezmd && cd ezmd
uv sync --all-packages          # Python workspace, with the dev tools
pnpm install                    # web UI, TypeScript SDK, extension (Node 22)
make gates                      # every CI gate, in CI order
```

On Windows or macOS, `bash tools/linux_gates.sh` runs the Python gates in a Linux container, which is
where the sandbox and resource-limit code paths really execute. Add `--extra docs`, `--extra data`, or
`--extra 7z` to `uv sync` to work on the converters that need them.

The individual gates:

```sh
uv run ruff check . && uv run ruff format --check .
uv run mypy --strict packages/core/src && uv run mypy apps/api/src packages/converters/src packages/mcp/src
uv run pytest packages apps tests -q
uv run pytest fixtures -q
uv run python tools/license_check.py
uv run mkdocs build --strict
```

## Branches, commits, pull requests

- Branch `task/<phase>-<id>-<slug>` from `main`; one change per pull request; squash merge after the gates
  pass.
- Conventional Commits with the path segment as scope, for example
  `feat(converters): add DOCX tracked changes`, and the roadmap task in the footer (`Task: P1-T01`).
- Every pull request that changes behavior adds a line to `CHANGELOG.md` under "Unreleased", and comes
  with tests.
- Non-trivial choices are recorded in `DECISIONS.md` (append-only); per-task approach notes go in
  `docs/decisions/<task>.md`.

## Adding a converter

- Implement the `Converter` protocol (`ezmd.registry`): a stable `id` (`family.engine`), `can_handle`
  that does no I/O, and `convert` that returns a finalized `Document` or raises `ConversionError`. A family
  is a subpackage of `ezmd_converters` exposing `converters()` and `CHAINS`; an engine whose optional
  dependency is missing is returned as `Unavailable(...)` with the extra that provides it.
- Every input is hostile: enforce the size, entry, and depth limits before handing bytes to an engine, and
  run external programs only through `ezmd.core.sandbox.run([...])` (a test forbids `subprocess`
  anywhere else).
- Every block carries `Provenance`. Every loss is a structured warning with a code from
  `packages/core/src/ezmd/warnings/codes.py` (severity, description, suggestion). Never return an empty
  document silently.
- Research first: before adding an engine, record its version, its LICENSE file (not the README), known
  issues, and the fallback in an approach note. Default dependencies must be on the allowlist in
  `tools/license_allowlist.toml` (MIT, Apache-2.0, BSD, ISC, PSF, MPL-2.0, and similar); copyleft or
  restricted engines are only allowed as named optional extras that print a one-time notice.
- Document the family in `docs/converters/<family>.md` (what is supported, options, warnings, known
  limitations), then run `uv run python tools/gen_converters_matrix.py` to regenerate the converter matrix
  and the docs navigation. A test fails when the matrix is stale.
- The contract test (`packages/core/tests/test_converter_contract.py`) runs against every converter.

Third-party converters can be packaged as plugins through the `ezmd.converters` entry point group; see
`docs/plugins.md`.

## The council process

A council is a review by three reviewers who each wear a different hat and check one aspect:

| Hat | Checks |
|---|---|
| Architect (developer) | Fit with the IR and registry, surface area, dependency weight, CPU-only operation, license compliance, whether the change will have to be undone later |
| Skeptic and security (provenance, legal) | What input breaks or hangs it, what an attacker can do, untested assumptions, whether a fixture threshold is being gamed, where the fixtures and engines come from and under what license |
| User advocate (media, end users) | What a lawyer, an accountant, a researcher, a RAG developer, and a non-technical user each lose or gain; whether failures are reported or silent; whether output stays readable and greppable |

A council is required for:

- an architectural change (new service, queue, or storage shape; changes to the IR, the API contract, or
  the security model);
- a converter or engine change that could alter output for existing fixtures;
- a converter whose first implementation misses its fixture threshold;
- each release.

The pull request carries a council section with:

1. the fixture scorecard diff (`uv run ezmd-score fixtures/<family>` before and after);
2. the license check output (`uv run python tools/license_check.py`);
3. answers to four questions: what is preserved that was not before, what could be lost, which warnings
   change, and what the token cost impact is.

Engine swaps need two approvals; converter fixes need one. Each reviewer writes a short position
(position, evidence, risks, recommendation); the decision and a summary of each position are logged in
`DECISIONS.md`. A council iterates at most three times on one problem. A converter that still misses its
threshold after that ships with `experimental = True`, an `experimental_converter` warning on every
result, and a "Known limitations" paragraph stating exactly what fails on which inputs.

## The fixture process

Golden fixtures are how this project proves it loses nothing silently. A bug report about silent loss
becomes a fixture before it becomes a fix.

### Adding a fixture

Each fixture is a directory `fixtures/<family>/<name>/` with `input.<ext>` (or `input.url` plus a frozen
`input.html`, so tests never touch the network), `expected.full.md`, `expected.sidecar.json`, and
`meta.toml`:

```toml
converter = "documents.docx"
notes = "tracked insertions and deletions, one comment, a footnote"

[provenance]
origin = "self-generated"   # self-generated | public-domain | cc0 | cc-by
license = "CC0-1.0"
source = ""                 # a URL when not self-generated
```

Provenance rules:

- Inputs must be self-generated (preferred: commit the generator as `fixtures/<family>/_generate.py`),
  public domain, CC0, or CC-BY. CC-BY fixtures carry the attribution in `meta.toml`.
- No commercial documents or media, no content scraped from platforms, and no personal data.
- Keep inputs small (under about 200 KB each).
- `meta.toml` without a valid `[provenance]` table fails the test run.

### Goldens

Generate the expected outputs from the converter, then review them:

```sh
uv run ezmd-golden fixtures/office/docx-review --write
uv run ezmd-score fixtures/office/docx-review
```

A golden is never committed on the converter's word alone. Review it against the input for every
heading, table, list, figure, footnote, comment, and tracked change that is missing, mislabeled,
reordered, or hallucinated. If it is wrong, fix the converter rather than accepting a bad golden. Hand
edits are allowed only with `hand_edited = true` and the reason in `meta.toml`. Before merge, an
independent Skeptic reviewer (not the author) repeats that comparison and must answer ACCEPT; on REJECT
the fixes are listed and the golden is reworked.

### Thresholds

The scorer combines headings (0.25), tables (0.25), text (0.30), and structure (0.20) into one score.
The default threshold is 0.85 (`fixtures/thresholds.toml`); per-converter thresholds live in
`fixtures/<family>/thresholds.toml` and may be raised for simple converters. A fixture's `meta.toml`
may only lower its threshold, and only with `threshold_reason` (for example a deliberately damaged scan).
Regardless of score, a fixture fails on an exception, on an empty document when the golden has content,
on an error-severity warning not listed in `expected_errors`, or on exceeding `max_seconds`.

### Updating goldens

A change that rewrites `expected.*` files states why in the pull request, includes the diff of the
goldens and the score before and after, adds a CHANGELOG line, and goes through the council when it
changes output for existing fixtures. The nightly workflow runs the full fixture suite against `main`; a
published nightly scorecard is planned.

## Security issues

Do not open public issues for vulnerabilities; see `SECURITY.md`.

## Code of conduct

Everyone taking part is expected to follow `CODE_OF_CONDUCT.md`.
