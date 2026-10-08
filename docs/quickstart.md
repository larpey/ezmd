# Quickstart

Phase 0 converts plain text and Markdown. Other formats are rejected as unsupported until their
families land (Phase 1 onward). intomd is not yet published to PyPI, so run it from a source checkout.

## CLI

```sh
git clone https://github.com/larpey/intomd && cd intomd
uv sync --all-packages --dev
uv run intomd convert notes.txt --profile compact
```

Output for a small `notes.txt`:

```markdown
---
title: "Field notes"
source: "notes.txt"
source_type: text
word_count: 7
tokens: {o200k_base: 10, cl100k_base: 10, claude_approx: 11}
content_hash: "sha256:f2b2..."
warnings: []
injection_risk: none
profile: compact
---
# Field notes

The depot opened at six.
```

Useful variations:

```sh
uv run intomd convert report.md -p rag -o out/            # writes out/report.md
uv run intomd convert report.md -o report.md --sidecar     # also writes report.intomd.json
uv run intomd convert report.md --json                     # machine-readable result on stdout
cat notes.txt | uv run intomd convert -                    # stdin
uv run intomd convert https://example.org/readme.txt       # URL, fetched through the SSRF guard
uv run intomd capabilities                                 # registered converters
```

Warnings go to stderr as `WARN [code] message` (silence them with `-q`). See the
[CLI reference](cli.md) for every option and the exit codes.

Planned: `uvx intomd` and `pip install intomd` once the package is published, and `intomd batch`
(Phase 1).

## Docker Compose

```sh
docker compose -f deploy/docker-compose.yml up -d --build
```

Then open http://localhost:8080 for the web UI. The same port serves the API. For TLS, secrets, and
every setting see [Self-hosting](selfhost.md).

## REST API

Upload a file. The response is `202` with the job and its links:

```sh
curl -s -F file=@notes.txt -F profile=compact http://localhost:8080/v1/convert
```

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

Poll the job, then fetch the result in any profile and format:

```sh
curl -s http://localhost:8080/v1/jobs/job_4fQ...
curl -s "http://localhost:8080/v1/jobs/job_4fQ.../result?profile=compact&format=md"
```

Or wait for the result in one request (up to 60 seconds):

```sh
curl -s -F file=@notes.txt "http://localhost:8080/v1/convert?wait=30&format=md"
```

Convert a URL with a JSON body:

```sh
curl -s -H 'Content-Type: application/json' \
  -d '{"url": "https://example.org/readme.txt", "profile": "full"}' \
  http://localhost:8080/v1/convert
```

Stream progress with server-sent events:

```sh
curl -N http://localhost:8080/v1/jobs/job_4fQ.../events
```

See [REST API](api.md) for jobs, events, options, and [Errors](errors.md) for error codes.
