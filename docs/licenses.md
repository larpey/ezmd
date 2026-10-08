# Licenses

intomd is Apache-2.0. A default install pulls only permissively licensed code and model weights.
Engines under other licenses are available only through named optional extras that you install on
purpose, and they tell you their license the first time they load.

## Policy

- The default dependency tree (the `intomd` core, `intomd-converters`, the API, and every extra
  except `nonfree`) may only contain licenses from the allowlist below.
- Denied licenses (GPL, AGPL, SSPL, non-commercial Creative Commons, OpenRAIL, Commons Clause,
  Elastic, BUSL, MinerU) never enter the default tree.
- Packages under denied licenses may ship only in a named extra, and the converter that needs them
  calls `intomd.core.licensing.notify_once("<extra>")` on first import. The notice is printed to
  stderr once per machine (a stamp file in the cache directory records it).
- Changing the allowlist is a policy decision logged in `DECISIONS.md`.
- The check runs in CI: `uv run python tools/license_check.py` for the Python tree (from `uv.lock`,
  all platforms) and `pnpm licenses list --json --prod | node tools/license_check.mjs` for the
  JavaScript tree. Per-package decisions live in `tools/license_overrides.toml`, each with a URL to the
  license file it was verified against.

## Allowlist

From `tools/license_allowlist.toml`:

| Category | SPDX ids |
|---|---|
| Allowed in the default tree | Apache-2.0, MIT, BSD-2-Clause, BSD-3-Clause, ISC, PSF-2.0, Python-2.0, CNRI-Python, MPL-2.0, Unlicense, 0BSD, CC0-1.0, Zlib, BSL-1.0, HPND, LGPL-2.1-only, LGPL-2.1-or-later, LGPL-3.0-only, LGPL-3.0-or-later |
| Model weights accepted for default pulls | Apache-2.0, MIT, CC-BY-4.0, CC0-1.0, BSD-3-Clause |
| Denied | GPL-2.0-only, GPL-2.0-or-later, GPL-3.0-only, GPL-3.0-or-later, AGPL-3.0-only, AGPL-3.0-or-later, SSPL-1.0, CC-BY-NC-4.0, CC-BY-NC-SA-4.0, OpenRAIL-M, BigScience-OpenRAIL-M, Commons-Clause, Elastic-2.0, BUSL-1.1, MinerU-License |
| Only inside the `nonfree` extra | pymupdf, pymupdf4llm, extract-msg, olefile |

LGPL dependencies are allowed only as separately installed shared libraries or unmodified Python
packages; nothing is statically linked.

### CNRI-Python

`regex`, pulled in by `tiktoken` for exact token counts, is licensed "Apache-2.0 AND CNRI-Python".
CNRI-Python (the OSI-approved CNRI Python 1.6 license) belongs to the permissive Python license
family that the allowlist already accepted through PSF-2.0 and Python-2.0, so it was added to the
allowlist (D-0011).

## Extras

Optional extras of `intomd-converters` (from source: `uv sync --all-packages --extra <name>`):

| Extra | What it adds | License |
|---|---|---|
| `docs` | Docling (`docling-slim`) for PDF layout, with CPU torch and OpenCV | MIT (Docling), BSD-3-Clause (torch), Apache-2.0 (OpenCV); about 1.2 GB |
| `data` | pyarrow, for Parquet | Apache-2.0 |
| `7z` | py7zr, for 7z archives | LGPL-2.1-or-later (dynamically imported, never bundled in images) |

The known non-permissive extras, each of which prints a one-time notice when used, are planned:

| Extra | License | Status |
|---|---|---|
| `pymupdf` | AGPL-3.0 | Planned |
| `extract-msg` | GPL-3.0 | Planned (Outlook `.msg`, P1-T04) |
| `chandra` | OpenRAIL-M (model weights) | Planned |
| `nonfree` | AGPL-3.0 / GPL-3.0 (bundles the copyleft engines) | Planned |

Network use of AGPL software can oblige you to publish your source. Read each license before
installing a non-permissive extra on a server.

## External programs

System executables are run as separate processes, not linked, and are outside the Python and
JavaScript checks. Phase 0 images include:

| Program | License | Image |
|---|---|---|
| libmagic | BSD-2-Clause | api, worker, fetch-node |
| pandoc | GPL-2.0-or-later | worker (not used by a converter yet) |
| iptables | GPL-2.0 | worker (optional egress allowlist) |
| tini | MIT | worker |

Planned additions with their families: ffmpeg (LGPL or GPL depending on the build, Phase 2),
tesseract (Apache-2.0), LibreOffice (MPL-2.0).
