# First conversion

These examples run from a source checkout (see [Install](install.md)) and use files from `fixtures/`, so
you can paste them as they are.

## CLI

```sh
uv run intomd convert fixtures/office/docx-review/input.docx --profile compact
```

```markdown
---
title: "Quarterly Review Memo"
source: "input.docx"
source_type: docx
word_count: 85
tokens: {o200k_base: 126, cl100k_base: 127, claude_approx: 136}
content_hash: "sha256:2e76c6e4..."
warnings: []
injection_risk: none
profile: compact
---
# Quarterly Review Memo

*Draft for the budget committee*

## Summary

The committee approved the annual budget after a short debate.
...
```

Warnings go to stderr, one per line, so stdout stays clean Markdown:

```text
WARN [tracked_changes_present] The source contains tracked changes; they were resolved.
WARN [comments_present] The source contains review comments; they were omitted.
```

Useful variations:

```sh
uv run intomd convert report.pdf -p rag -o out/             # writes out/<title>.md
uv run intomd convert report.pdf -o report.md --sidecar      # also writes report.intomd.json
uv run intomd convert report.pdf --json                      # one JSON object on stdout
uv run intomd convert report.pdf --converter documents.docling_pdf   # force a converter (docs extra)
cat notes.txt | uv run intomd convert -                      # stdin
uv run intomd convert https://example.com                    # URL, fetched through the SSRF guard
uv run intomd batch ./reports --recursive --out ./md         # many files; unchanged ones are skipped
uv run intomd shadow-run report.pdf                          # compare every engine that handles a file
```

Exit codes and every option are in the [CLI reference](cli.md). The output profiles are
explained in [Output format](output-format.md).

## Python

```python
import intomd

result = intomd.convert("fixtures/office/docx-review/input.docx", profile="compact")
print(result.markdown)
for w in result.warnings:
    print(w.severity, w.kind, w.message)
```

More in [Python library](library.md).

## REST API

Start the API in-process (inline queue, no Redis or Docker needed):

```sh
uv run intomd serve --port 8080
```

Upload a file and wait up to 30 seconds for the result:

```sh
curl -s -F file=@fixtures/text/plain-utf8/input.txt -F profile=compact "http://127.0.0.1:8080/v1/convert?wait=30&format=md"
```

Without `wait`, the response is `202` with the job and its links:

```json
{
  "job": {"id": "job_4fQ...", "state": "queued", "progress": 0, "profile": "compact", "...": "..."},
  "deduplicated": false,
  "links": {
    "self": "/v1/jobs/job_4fQ...",
    "events": "/v1/jobs/job_4fQ.../events",
    "result": "/v1/jobs/job_4fQ.../result?profile=compact&format=md"
  }
}
```

Poll the job, stream progress, then fetch the result in any profile and format:

```sh
curl -s http://127.0.0.1:8080/v1/jobs/job_4fQ...
curl -N http://127.0.0.1:8080/v1/jobs/job_4fQ.../events
curl -s "http://127.0.0.1:8080/v1/jobs/job_4fQ.../result?profile=rag&format=md"
```

Convert a URL with a JSON body:

```sh
curl -s -H 'Content-Type: application/json' \
  -d '{"url": "https://example.com", "profile": "full"}' \
  http://127.0.0.1:8080/v1/convert
```

See [REST API](api.md) for jobs, events, and options, and [Errors](errors.md) for error codes.

## Web UI

`intomd serve` and the Compose stack serve the web UI at `/` once it is built:

```sh
pnpm install && pnpm --filter @intomd/web build
uv run intomd serve --port 8080
```

Then open http://127.0.0.1:8080: paste a link, drop a file, or paste text.

## MCP

```sh
claude mcp add intomd -- uv --directory /path/to/intomd run intomd-mcp
```

Other clients: [MCP server](mcp.md).

## Docker Compose

```sh
bash deploy/bootstrap.sh --plain-http --build
```

Then open http://localhost:8080. TLS, API keys, backups, and every setting: [Self-hosting](selfhost.md).
