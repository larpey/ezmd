# intomd-mcp

<!-- mcp-name: io.github.larpey/intomd -->

An [MCP](https://modelcontextprotocol.io) server for [intomd](https://github.com/larpey/intomd): convert
files, URLs and pasted text to LLM-ready Markdown from Claude Desktop, Claude Code, Cursor, VS Code and any
other MCP client. Results are paginated to your token budget, carry section ids and page markers for
citations, and report every warning (skipped pages, truncated tables, suspected prompt injection) instead
of dropping content silently.

```bash
uvx intomd-mcp                      # stdio, converts in-process
uvx intomd-mcp --allowed-dirs ~/docs
uvx intomd-mcp --remote https://intomd.example   # forward to an instance; INTOMD_API_KEY is sent as X-API-Key
uvx intomd-mcp --transport http --port 8765      # streamable HTTP on 127.0.0.1, bearer token required
```

## Tools

| Tool | What it does |
| --- | --- |
| `convert_url(url, profile?, max_tokens?, options?)` | Fetch (through the SSRF guard) and convert an http(s) URL. |
| `convert_file(path? \| data_url?, profile?, max_tokens?, options?)` | Convert a local file inside the allowed directories, or a base64 `data:` URL under 1 MB. |
| `convert_text(text, source_hint?, profile?, max_tokens?)` | Convert pasted text, HTML, Markdown, CSV, JSON. |
| `get_job(job_id, cursor?, max_tokens?, profile?)` | Job status, or the page at `cursor`: the pagination endpoint for every convert tool. |
| `list_capabilities()` | Supported types, missing extras, limits, whether fetching is allowed. |

Every result has `job_id, title, source, tokens_total, pages_total, page, next_cursor, warnings,
frontmatter, content` (page 1 adds `sections`). The default profile is `agent` (untrusted-content fence,
section ids); `max_tokens` defaults to 8000 and is capped at 50000. Resources `intomd://jobs/{id}` and
`intomd://jobs/{id}/sidecar` expose the full Markdown and sidecar JSON; the prompt
`summarize_with_provenance` asks the model to cite section ids and pages.

See [docs/mcp.md](https://github.com/larpey/intomd/blob/main/docs/mcp.md) for client configuration,
security notes and every option. Apache-2.0.
