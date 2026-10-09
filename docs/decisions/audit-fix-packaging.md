# Audit fix: packaging (dependency bounds, license files, license gate scope)

For the orchestrator to number and append to DECISIONS.md.

## 1. Cap direct dependencies that have a pre-release of a new major

`pip install --pre ezmd` (how the README installs the release candidates) lets any pre-release satisfy an
open `>=` bound. httpx 1.0.dev6 is on PyPI and its metadata is `truststore, typing-extensions`: it no longer
depends on httpcore, which `ezmd.core.netguard` imports directly. Before this change, `uv pip compile
--prerelease allow` over `httpx>=0.28` resolved `httpx==1.0.dev6` and no httpcore, so URL converts crashed
with `ModuleNotFoundError: httpcore`. After it, `httpx>=0.28,<1` plus `httpcore>=1.0.9,<2` resolves
`httpx==0.28.1` and `httpcore==1.0.9` (the locked versions).

Decision: every declaration of httpx is capped `<1`, and ezmd declares httpcore itself, since it imports it.
The other direct runtime dependencies of ezmd, ezmd-converters and ezmd-mcp were checked against the PyPI
JSON API on 2026-10-09; only lxml has a new-major pre-release (7.0.0b1), so it is capped `<7`. defusedxml
(0.8.0rc2) and openpyxl (3.2.0b1) have newer pre-releases inside their current major and are left open.
`tests/test_packaging.py` records the hazard list and fails if a declaration admits those majors, or if a
member imports httpcore without declaring it.

## 2. LICENSE and NOTICE in every published dist

hatchling only packs files inside the project directory, so the wheels and sdists had no license file.
ezmd, ezmd-converters and ezmd-mcp now carry committed copies of the root LICENSE and NOTICE and declare
`license-files = ["LICENSE", "NOTICE"]` (PEP 639; hatchling 1.26+ writes them to
`.dist-info/licenses/`). Copies were chosen over a build hook because they are visible and need no build
code; a test keeps them byte-identical to the root files, and a slow test builds each package and checks
the wheel and the sdist. apps/api and apps/fetch-node are not published (release.yml builds only the three)
and are unchanged. packages/sdk-ts already ships LICENSE (identical to the root, listed in `files`).

## 3. Exact ezmd-mcp pin in the ezmd extras

`ezmd[mcp]` and `ezmd[all]` pin `ezmd-mcp==V`, matching how ezmd pins ezmd-converters and ezmd-mcp pins
ezmd. The ezmd and ezmd-mcp pins are circular; pip and uv resolve exact pins both ways. `tools/bump_version.py`
maintains them, and with `--npm` also `packages/sdk-ts/src/version.ts`.

## 4. The license gate covers every extra except nonfree

`tools/license_allowlist.toml` and docs/licenses.md said the gate covers the default tree and every extra
except `nonfree`, but `tools/license_check.py` exported the tree without extras. It now runs `uv export
--all-extras --no-extra nonfree`, which adds 6 permissive packages with ambiguous metadata (verified against
their license files and added to `tools/license_overrides.toml`) and the NVIDIA CUDA runtime.

torch, pulled only by the `docs` extra (Docling), depends on 15 NVIDIA wheels on Linux (x86_64 and aarch64)
that are `LicenseRef-NVIDIA-Proprietary` or carry no license metadata. Two options were considered:

- (a) An explicit, named exception class `[platform_runtime]` in the allowlist, with a reason.
- (b) Make the `docs` extra pull CPU-only torch.

(b) does not work for published packages: the CPU wheels live on the PyTorch index, and PyPI metadata cannot
name another index. A `[tool.uv.sources]` index would change only the workspace lock, not what `pip install
ezmd[docs]` resolves, so the gate would be checking a tree no user gets. Chosen: (a). The libraries are GPU
runtime that torch loads dynamically. The user's resolver installs them from PyPI under NVIDIA's terms;
ezmd does not bundle or redistribute them, and the published worker image does not install `docs`. An
operator who builds a worker image with `EZMD_WORKER_EXTRAS=docs` gets them in that image under NVIDIA's
license. The exception lists packages by exact name, so a new NVIDIA wheel fails the gate until it is
reviewed. It does not add an NVIDIA license id to the allowlist, and a test fails if any listed package
enters the no-extras tree. The checker reports them with the verdict source `platform-runtime exception`.

## 5. `uv lock --check` in CI

CI sets `UV_FROZEN=1`, so a version bump committed without `uv lock` went unnoticed. The python job now runs
`uv lock --check` once (ubuntu, Python 3.12).
