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
  convert       Convert one input to Markdown.
  capabilities  List registered converters and whether they loaded.
  detect        Show the detected content type of a file.
  version       Print the intomd version.
  serve         Run the HTTP API and web UI in-process (inline queue when Redis is not...
```

## intomd convert

```text
Usage: intomd convert [OPTIONS] {source}

  Convert one input to Markdown.

Arguments:
  source  File path, URL, or '-' for stdin.  [required]

Options:
  -p, --profile <str>       full | compact | rag | agent  [default: full]
  -f, --format <str>        md | json | txt  [default: md]
  -o, --out <path>          Output file or directory.
  --sidecar / --no-sidecar  Write <name>.intomd.json beside --out.  [default: no-sidecar]
  --converter <str>         Force a converter id.
  --opt <str>               key=value converter or profile option.
  --json                    Machine-readable result on stdout.
  -q, --quiet               No warnings on stderr.
  -h, --help                Show this message and exit.
```

## intomd capabilities

```text
Usage: intomd capabilities [OPTIONS]

  List registered converters and whether they loaded.

Options:
  --json
  -h, --help  Show this message and exit.
```

## intomd detect

```text
Usage: intomd detect [OPTIONS] {path}

  Show the detected content type of a file.

Arguments:
  path  [required]

Options:
  -h, --help  Show this message and exit.
```

## intomd version

```text
Usage: intomd version [OPTIONS]

  Print the intomd version.

Options:
  -h, --help  Show this message and exit.
```

## intomd serve

```text
Usage: intomd serve [OPTIONS]

  Run the HTTP API and web UI in-process (inline queue when Redis is not configured).

Options:
  --host <str>             [default: 127.0.0.1]
  --port <int>             [default: 8080]
  --i-know-this-is-public  Allow binding non-loopback.
  -h, --help               Show this message and exit.
```

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Success. |
| 1 | Generic failure (the converter failed). |
| 2 | Bad arguments, missing file or dependency, or a result with an error-severity warning. |
| 4 | The fetch was blocked by platform policy (residential-only host or fetch required). |
| 5 | Input too large. |
| 6 | Unsupported input type. |
| 130 | Interrupted. |

`--opt key=value` is repeatable. A `ConvertOptions` field name (such as `max_pages` or `ocr`) sets
that converter option, `extra.<key>` sets a family-specific converter option, and any other key is
a profile override (for example `--opt chunk_tokens=600` or `--opt tables.max_pipe_rows=100`).
See [Output format](output-format.md) for the profile options.
