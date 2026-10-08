# intomd

Convert anything into LLM-ready Markdown: documents, web pages, audio and video, chat exports, code,
data files, email, and more. intomd emits Markdown with YAML frontmatter under four output profiles
(`full`, `compact`, `rag`, `agent`), a JSON sidecar with page and block provenance, and an explicit
warnings list, so nothing is lost silently.

> Status: Phase 0 (foundation). Plain text and Markdown convert today; the converter families land in Phase 1.
> See [STATUS.md](STATUS.md) and [ROADMAP.md](ROADMAP.md).

## Quickstart

```sh
uvx intomd convert notes.md --profile compact      # once published; for now: uv run intomd convert ...
```

Self-host the API and web UI:

```sh
docker compose -f deploy/docker-compose.yml up -d --build
```

Then open http://localhost:8080.

## Documentation

- [docs/](docs/index.md): quickstart, self-host guide, API, CLI, output format, security
- [CONTRIBUTING.md](CONTRIBUTING.md)
- [SECURITY.md](SECURITY.md)

Apache-2.0. Default installs pull only permissively licensed code and model weights.
