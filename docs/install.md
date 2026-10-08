# Install

!!! note "Pre-release"
    intomd is not published yet: there is no PyPI package, npm package, or container image. Install from
    source. The commands under [After the first release](#after-the-first-release) are what the
    published packages will use.

## From source

You need [uv](https://docs.astral.sh/uv/) and Python 3.12 or newer. On Linux and macOS, also install
libmagic (`apt install libmagic1`, `brew install libmagic`); on Windows it comes from a wheel.

```sh
git clone https://github.com/larpey/intomd && cd intomd
uv sync --all-packages
uv run intomd version
```

`uv sync --all-packages` installs the core (`intomd`), the built-in converters (`intomd-converters`), the
API (`intomd-api`), and the MCP server (`intomd-mcp`) into `.venv`, with the development tools. Run any
command through `uv run`, for example `uv run intomd convert report.pdf`.

For the web UI and the TypeScript SDK, also install Node 22 and pnpm, then `pnpm install`.

## Extras

Optional engines live in extras of `intomd-converters`. From source, add them with `--extra`:

| Extra | Adds | Size | Command |
|---|---|---|---|
| `docs` | Docling layout analysis for PDF (headings, tables, reading order), CPU torch | about 1.2 GB | `uv sync --all-packages --extra docs` |
| `data` | pyarrow, for Parquet | 30 to 50 MB | `uv sync --all-packages --extra data` |
| `7z` | py7zr, for 7z archives (LGPL-2.1-or-later) | a few MB | `uv sync --all-packages --extra 7z` |

Without an extra, its converter is listed as unavailable with the reason, and inputs fall back to the
next converter in the chain (PDF uses the pypdfium2 text-layer engine and emits `engine_fallback`). See
which converters need which extra in the [converter matrix](converters/README.md), and the licenses in
[Licenses](licenses.md).

## System programs

| Program | Needed for | Install |
|---|---|---|
| libmagic | content detection (with Magika) | `apt install libmagic1`, `brew install libmagic` |
| LibreOffice (`soffice`) | legacy `.doc`, `.xls`, `.ppt`, `.xlsb`, `.wpd` | your package manager, or set `LIBREOFFICE_PATH` |

## Check the installation

```sh
uv run intomd doctor          # Python, extras, system programs, cache
uv run intomd capabilities    # every converter, loaded or unavailable with the reason
```

## Docker

The Compose stack builds from the checkout; see [Self-hosting](selfhost.md):

```sh
bash deploy/bootstrap.sh --plain-http --build
```

## After the first release

These commands do not work yet:

```sh
pip install intomd                       # library and CLI
uvx intomd convert https://example.com   # run without installing
uvx intomd-mcp                           # MCP server
npm install @intomd/sdk                  # TypeScript client
```

The published images will be `ghcr.io/larpey/intomd-api`, `-worker`, and `-fetch-node`.
