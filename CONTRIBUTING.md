# Contributing to intomd

Thanks for helping. The short version:

1. Read `CLAUDE.md` (layout, commands, conventions) and the spec in `docs/spec/`.
2. Install: `uv sync --all-packages --dev` and `pnpm install`.
3. Run the gates before opening a PR: `make gates`.
4. Commits follow Conventional Commits with the path segment as scope, for example
   `feat(converters): add DOCX tracked changes`. Reference the roadmap task in the footer (`Task: P1-T01`).

## Adding a converter

- Implement the `Converter` protocol (`intomd.registry`): stable `id` (`family.engine`), `can_handle` that
  does no I/O, `convert` that returns a finalized `Document` or raises `ConversionError`.
- Every block carries `Provenance`. Every loss is a structured warning from `intomd/warnings/codes.py`.
- Add at least one fixture under `fixtures/<family>/<name>/` with `meta.toml` (including `[provenance]`).
  Fixtures must be self-generated, public domain, CC0, or CC-BY. No commercial or platform-scraped content.
- Goldens are generated with `uv run intomd-golden <fixture> --write` and reviewed before they are committed.
- The converter contract test (`packages/core/tests/test_converter_contract.py`) runs against every converter.

## Licenses

Default dependencies must be MIT, Apache-2.0, BSD-2/3, ISC, PSF, MPL-2.0, or CC-BY-4.0. Copyleft engines
are only allowed as named optional extras. CI enforces this (`tools/license_check.py`).

## Decisions and councils

Architectural decisions are logged in `DECISIONS.md` (append-only). Contested design questions and
converters that miss their fixture threshold go to a three-reviewer council (Architect, Skeptic/Security,
User-advocate); see docs/spec/part1.md section 2.3.
