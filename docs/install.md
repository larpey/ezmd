# Install

!!! note "Release candidate"
    `0.1.0rc2` is on PyPI as a pre-release (`ezmd`, `ezmd-converters`, `ezmd-mcp`), and signed container
    images tagged `0.1.0-rc2` are on GHCR. pip and uv skip pre-releases unless asked, so pin the exact version
    until `0.1.0` is final; after that, plain `pip install ezmd` works. The npm package `@ezmd/sdk` is
    published with `0.1.0`.

## From PyPI

Python 3.12 or newer. On Linux and macOS, also install libmagic (`apt install libmagic1`,
`brew install libmagic`); on Windows it comes from a wheel.

```sh
pip install ezmd==0.1.0rc2                   # library and CLI
uv tool install ezmd==0.1.0rc2               # or: the CLI as a uv tool
uvx ezmd==0.1.0rc2 convert https://example.com   # run without installing
uvx ezmd-mcp==0.1.0rc2                       # MCP server (see MCP server)
```

With an extra: `pip install "ezmd[docs]==0.1.0rc2"`. Once `0.1.0` is out, drop the `==0.1.0rc2`.

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
| `docs` | Docling layout analysis for PDF (headings, tables, reading order), CPU torch | about 1.2 GB | `uv sync --all-packages --extra docs` |
| `data` | pyarrow, for Parquet | 30 to 50 MB | `uv sync --all-packages --extra data` |
| `7z` | py7zr, for 7z archives (LGPL-2.1-or-later) | a few MB | `uv sync --all-packages --extra 7z` |
| `mcp` | the MCP server (`ezmd-mcp`) | small | installed by `uv sync --all-packages` |
| `nonfree` | extract-msg, a fallback reader for Outlook `.msg` (GPL-3.0; see [Licenses](licenses.md)) | small | `uv sync --all-packages --extra nonfree` |
| `all` | `docs`, `data`, `7z` and `mcp` (never `nonfree`) | | |

Without an extra, its converter is listed as unavailable with the reason, and inputs fall back to the
next converter in the chain (PDF uses the pypdfium2 text-layer engine and emits `engine_fallback`). See
which converters need which extra in the [converter matrix](converters/README.md), and the licenses in
[Licenses](licenses.md). The media, OCR, web and fetch extras in the spec come in later releases.

### Docling models (`docs` extra)

ezmd never lets Docling download models during a conversion (it sets `HF_HUB_OFFLINE=1`), so download the
layout and table models once and point ezmd at them:

```sh
docling-tools models download layout tableformer -o ~/.cache/ezmd/docling
export EZMD_DOCLING_ARTIFACTS=~/.cache/ezmd/docling     # Windows: set EZMD_DOCLING_ARTIFACTS=...
```

Without the models, Docling fails and PDFs fall back to the text-layer engine with an `engine_fallback`
warning. Details: [PDF converters](converters/pdf.md).

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
`ghcr.io/larpey/ezmd-fetch-node` (tags `0.1.0-rc1` and `0.1.0-rc2` today). The Compose stack can pull them
or build from the checkout; see [Self-hosting](selfhost.md):

```sh
bash deploy/bootstrap.sh --plain-http --version 0.1.0-rc2   # pull the release candidate images
bash deploy/bootstrap.sh --plain-http --build              # or build from this checkout
```

## TypeScript client

`npm install @ezmd/sdk` works once `0.1.0` is released; until then, build it from the checkout
(`pnpm install && pnpm --filter @ezmd/sdk build`).
