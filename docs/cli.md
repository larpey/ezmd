# CLI reference

Generated from the `intomd` typer app by `tools/gen_cli_doc.py`; do not edit by hand.
In a source checkout run commands as `uv run intomd ...`.

## intomd

```text
Usage: intomd [OPTIONS] COMMAND [ARGS]...

  Convert anything to LLM-ready Markdown.

Options:
  --install-completion  Install completion for the current shell.
  --show-completion     Show completion for the current shell, to copy it or customize the
                        installation.
  -h, --help            Show this message and exit.

Commands:
  convert       Convert one input to Markdown (stdout, or a file with --out).
  batch         Convert many files; unchanged inputs are skipped on re-runs.
  doctor        Check the environment: Python, extras, ffmpeg, pandoc, models, cache, Redis.
  capabilities  List converters (loaded or unavailable, with the reason).
  detect        Show the detected content type of a file (always JSON).
  version       Print the version, commit, and build date.
  serve         Run the HTTP API and web UI in-process (inline queue without Redis).
```

## intomd convert

```text
Usage: intomd convert [OPTIONS] {source}

  Convert one input to Markdown (stdout, or a file with --out).

Arguments:
  source  File path, http(s) URL, or '-' for stdin.  [required]

Options:
  -p, --profile <str>       full | compact | rag | agent [default: auto]
  -o, --out <path>          Output file, or directory for <title>.md.
  -f, --format <str>        md | txt | json [default: md]
  --sidecar / --no-sidecar  Write <name>.intomd.json beside --out.
  --engine <str>            Engine as family=name, e.g. pdf=docling.
  --converter <str>         Force a converter id.
  --lang <str>              Language hint(s), e.g. en or en,de.
  --remote <str>            Convert on this intomd instance.
  --opt <str>               key=value converter or profile option.
  --json                    One JSON object on stdout.
  -q, --quiet               No progress or warnings on stderr.
  -h, --help                Show this message and exit.
```

## intomd batch

```text
Usage: intomd batch [OPTIONS] {inputs}

  Convert many files; unchanged inputs are skipped on re-runs.

Arguments:
  inputs  Directory or glob (quote globs).  [required]

Options:
  -o, --out <path>           Output directory (mirrors the input tree).
  -r, --recursive            Descend into subdirectories.
  -w, --workers <int range>  Worker processes.  [x>=1]
  -p, --profile <str>        full | compact | rag | agent
  -f, --format <str>         md | txt | json
  --continue-on-error        Keep going after a failure.
  --manifest <path>          [default: <out>/manifest.jsonl]
  --sidecar / --no-sidecar   Write sidecars.
  --opt <str>                key=value converter or profile option.
  --json                     Summary JSON on stdout.
  -q, --quiet                No progress or table on stderr.
  -h, --help                 Show this message and exit.
```

## intomd doctor

```text
Usage: intomd doctor [OPTIONS]

  Check the environment: Python, extras, ffmpeg, pandoc, models, cache, Redis.

Options:
  --json       Checks as JSON on stdout.
  -q, --quiet  Print only problems.
  -h, --help   Show this message and exit.
```

## intomd capabilities

```text
Usage: intomd capabilities [OPTIONS]

  List converters (loaded or unavailable, with the reason).

Options:
  --remote <str>  Ask this intomd instance instead.
  --json          As JSON.
  -h, --help      Show this message and exit.
```

## intomd detect

```text
Usage: intomd detect [OPTIONS] {path}

  Show the detected content type of a file (always JSON).

Arguments:
  path  File to inspect.  [required]

Options:
  -h, --help  Show this message and exit.
```

## intomd version

```text
Usage: intomd version [OPTIONS]

  Print the version, commit, and build date.

Options:
  --json      As JSON.
  -h, --help  Show this message and exit.
```

## intomd serve

```text
Usage: intomd serve [OPTIONS]

  Run the HTTP API and web UI in-process (inline queue without Redis).

Options:
  --host <str>             Bind address.  [default: 127.0.0.1]
  --port <int>             Port.  [default: 8080]
  --i-know-this-is-public  Allow binding non-loopback.
  -h, --help               Show this message and exit.
```

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Success. |
| 1 | Generic failure (the converter failed). |
| 2 | Bad arguments, missing file, or missing dependency. |
| 3 | Partial success: a usable result with an error warning, or batch failures with --continue-on-error. |
| 4 | The fetch was blocked by platform policy (residential-only host or fetch required). |
| 5 | Input too large. |
| 6 | Unsupported input type. |
| 130 | Interrupted. |

`--opt key=value` is repeatable. A `ConvertOptions` field name (such as `max_pages` or `ocr`) sets
that converter option, `extra.<key>` sets a family-specific converter option, and any other key is
a profile override (for example `--opt chunk_tokens=600` or `--opt tables.max_pipe_rows=100`).
See [Output format](output-format.md) for the profile options.
