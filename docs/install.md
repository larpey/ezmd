# Install

## From PyPI

Python 3.12 or newer. On Linux and macOS, also install libmagic (`apt install libmagic1`,
`brew install libmagic`); on Windows it comes from a wheel.

```sh
pip install ezmd                             # library and CLI
uv tool install ezmd                         # or: the CLI as a uv tool
uvx ezmd convert https://example.com         # run without installing
uvx ezmd-mcp                                 # MCP server (see MCP server)
```

With an extra: `pip install "ezmd[data]"`. For `ezmd[docs]` on Linux, read
[Docling on Linux](#docling-on-linux-cpu-torch) first.

## From source

You need [uv](https://docs.astral.sh/uv/) and Python 3.12 or newer. On Linux and macOS, also install
libmagic (`apt install libmagic1`, `brew install libmagic`); on Windows it comes from a wheel.

```sh
git clone https://github.com/larpey/ezmd && cd ezmd
uv sync --all-packages
uv run ezmd version
```

`uv sync --all-packages` installs the core (`ezmd`), the built-in converters (`ezmd-converters`), the
API (`ezmd-api`), and the MCP server (`ezmd-mcp`) into `.venv`, with the development tools. Run any
command through `uv run`, for example `uv run ezmd convert report.pdf`.

For the web UI and the TypeScript SDK, also install Node 22 and pnpm, then `pnpm install`.

## Extras

Optional engines live in extras. From PyPI, install `ezmd[<extra>]`; from source, add them with `--extra`:

| Extra | Adds | Size | From source |
|---|---|---|---|
| `docs` | Docling layout analysis for PDF (headings, tables, reading order), torch | about 1.2 GB with CPU torch; about 6 GB on Linux with PyPI's default CUDA torch ([see below](#docling-on-linux-cpu-torch)) | `uv sync --all-packages --extra docs` |
| `data` | pyarrow, for Parquet | 30 to 50 MB | `uv sync --all-packages --extra data` |
| `7z` | py7zr, for 7z archives (LGPL-2.1-or-later) | a few MB | `uv sync --all-packages --extra 7z` |
| `mcp` | the MCP server (`ezmd-mcp`) | small | installed by `uv sync --all-packages` |
| `nonfree` | extract-msg, a fallback reader for Outlook `.msg` (GPL-3.0; see [Licenses](licenses.md)) | small | `uv sync --all-packages --extra nonfree` |
| `all` | `docs`, `data`, `7z` and `mcp` (never `nonfree`) | | |

Without an extra, its converter is listed as unavailable with the reason, and inputs fall back to the
next converter in the chain (PDF uses the pypdfium2 text-layer engine and emits `engine_fallback`). See
which converters need which extra in the [converter matrix](converters/README.md), and the licenses in
[Licenses](licenses.md). The media, OCR, web and fetch extras in the spec come in later releases.

### Docling on Linux: CPU torch

On Linux, PyPI's torch wheel is the CUDA build, and it pulls NVIDIA's CUDA runtime wheels: for
`ezmd[docs]` that is about 3.2 GB to download (2.4 GB of it NVIDIA libraries and triton) and about 6 GB
installed. ezmd runs Docling on the CPU, so you do not need them. Package metadata cannot point pip at
PyTorch's CPU index, so ask for the CPU build yourself:

```sh
# pip: install CPU torch from PyTorch's index first, then the extra (pip keeps the torch it has)
pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
pip install "ezmd[docs]"

# uv: one flag
uv pip install --torch-backend cpu "ezmd[docs]"
uv tool install --torch-backend cpu "ezmd[docs]"
```

Do not pass `--index-url https://download.pytorch.org/whl/cpu` to the `ezmd[docs]` install itself: that
index does not carry ezmd or Docling. On Windows and macOS, PyPI's torch is already the CPU build (about
1.2 GB for the whole extra). From source, `uv sync --extra docs` resolves the lock, which uses PyPI's torch.

### Docling models (`docs` extra)

ezmd never lets Docling download models during a conversion (it sets `HF_HUB_OFFLINE=1`), so download the
layout and table models once and point ezmd at them:

```sh
docling-tools models download layout tableformer -o ~/.cache/ezmd/docling
export EZMD_DOCLING_ARTIFACTS=~/.cache/ezmd/docling     # Windows: set EZMD_DOCLING_ARTIFACTS=...
```

Without the models, ezmd skips Docling before loading it (so no time is lost importing torch), converts
with the text-layer engine, and adds an `engine_fallback` warning that names the missing models and this
command. `ezmd doctor` shows a `docling models` row and exits 2 when the `docs` extra is installed without
them. Details: [PDF converters](converters/pdf.md).

## System programs

| Program | Needed for | Install |
|---|---|---|
| libmagic | content detection (with Magika) | `apt install libmagic1`, `brew install libmagic` |
| LibreOffice (`soffice`) | legacy `.doc`, `.xls`, `.ppt`, `.xlsb`, `.wpd` | your package manager, or set `LIBREOFFICE_PATH` |

## Check the installation

```sh
uv run ezmd doctor          # Python, extras, system programs, cache
uv run ezmd capabilities    # every converter, loaded or unavailable with the reason
```

## Docker

Signed images for each release are on GHCR: `ghcr.io/larpey/ezmd-api`, `ghcr.io/larpey/ezmd-worker`, and
`ghcr.io/larpey/ezmd-fetch-node`, tagged with the release version (`X.Y.Z`, or `X.Y.Z-rcN` for a
candidate). The Compose stack can pull them or build from the checkout; see [Self-hosting](selfhost.md):

```sh
bash deploy/bootstrap.sh --plain-http --version <tag>       # pull published images
bash deploy/bootstrap.sh --plain-http --build              # or build from this checkout
```

## TypeScript client

`npm install @ezmd/sdk` works once `0.1.0` is released; until then, build it from the checkout
(`pnpm install && pnpm --filter @ezmd/sdk build`).
