# MCP server

`ezmd-mcp` exposes ezmd to any [Model Context Protocol](https://modelcontextprotocol.io) client. It is
a thin client: in **local mode** (the default) it calls the ezmd library in-process; in **remote mode**
(`--remote URL`) it forwards to an ezmd instance over the REST API. It never contains conversion logic of
its own.

```bash
uvx ezmd-mcp                       # stdio, local mode
```

!!! note "Before the first release"
    `ezmd-mcp` is not on PyPI yet, so `uvx ezmd-mcp` does not work. From a source checkout (see
    [Install](install.md)), replace `uvx ezmd-mcp` in every example below with
    `uv --directory /path/to/ezmd run ezmd-mcp`; in JSON configs that is
    `"command": "uv", "args": ["--directory", "/path/to/ezmd", "run", "ezmd-mcp", ...]`. For example:

    ```bash
    claude mcp add ezmd -- uv --directory /path/to/ezmd run ezmd-mcp
    ```

## Client configuration

### Claude Desktop

`claude_desktop_config.json` (Settings, Developer, Edit Config):

```json
{
  "mcpServers": {
    "ezmd": {
      "command": "uvx",
      "args": ["ezmd-mcp", "--allowed-dirs", "/Users/you/Documents"],
      "env": { "EZMD_PROFILE": "agent" }
    }
  }
}
```

Claude Desktop starts servers from an arbitrary working directory, so pass `--allowed-dirs` for the folders
you want `convert_file` to read.

### Claude Code

```bash
claude mcp add ezmd -- uvx ezmd-mcp
# a remote instance over streamable HTTP:
claude mcp add --transport http ezmd https://ezmd.example/mcp --header "Authorization: Bearer $EZMD_API_KEY"
```

or commit a project-scoped `.mcp.json`:

```json
{
  "mcpServers": {
    "ezmd": { "command": "uvx", "args": ["ezmd-mcp"] }
  }
}
```

Claude Code starts the server in the project directory, which is the default allowed root.

### Cursor

`.cursor/mcp.json` in the project (or `~/.cursor/mcp.json` globally):

```json
{
  "mcpServers": {
    "ezmd": { "command": "uvx", "args": ["ezmd-mcp", "--allowed-dirs", "${workspaceFolder}"] }
  }
}
```

### Windsurf

`~/.codeium/windsurf/mcp_config.json`:

```json
{
  "mcpServers": {
    "ezmd": { "command": "uvx", "args": ["ezmd-mcp", "--allowed-dirs", "/path/to/project"] }
  }
}
```

### VS Code (GitHub Copilot agent mode)

`.vscode/mcp.json` in the workspace:

```json
{
  "servers": {
    "ezmd": {
      "type": "stdio",
      "command": "uvx",
      "args": ["ezmd-mcp", "--allowed-dirs", "${workspaceFolder}"]
    }
  }
}
```

### Any other client

stdio: run `uvx ezmd-mcp` (or `ezmd-mcp` after `pip install ezmd-mcp`) as the server command.
Streamable HTTP: start `ezmd-mcp --transport http` and point the client at `http://127.0.0.1:8765/mcp`
with the header `Authorization: Bearer <token>`.

### A remote instance from a stdio client

```json
{
  "mcpServers": {
    "ezmd": {
      "command": "uvx",
      "args": ["ezmd-mcp", "--remote", "https://ezmd.example"],
      "env": { "EZMD_API_KEY": "imd_..." }
    }
  }
}
```

The server sends `User-Agent: ezmd-mcp/<version>` and `X-API-Key`. Remote mode never falls back to local
conversion.

## Tools

All tools accept `profile` (`full`, `compact`, `rag`, `agent`; default `agent`) and `max_tokens` (default
8000, range 256 to 50000) where relevant, and return a structured object plus a text block.

| Tool | Arguments | Notes |
| --- | --- | --- |
| `convert_url` | `url`, `profile?`, `max_tokens?`, `options?` | http and https only. The fetch goes through the SSRF guard: private, loopback, link-local and metadata addresses are refused with `fetch_refused_private_network`, other schemes with `fetch_refused_scheme`. |
| `convert_file` | `path` or `data_url`, `profile?`, `max_tokens?`, `options?` | `path` must be absolute and inside an allowed directory. `data_url` is a `data:<mime>;base64,...` URL under 1 MB for clients without a filesystem. |
| `convert_text` | `text`, `source_hint?`, `profile?`, `max_tokens?` | `source_hint` is a MIME type or extension used to break ties; detection still runs on the content. |
| `get_job` | `job_id`, `cursor?`, `max_tokens?`, `profile?` | Returns `{status: "running"}` while a remote job runs, else the page at `cursor` (page 1 without one). |
| `list_capabilities` | none | Converters (with the extra a missing one needs), profiles, formats, limits, whether fetching is allowed, and the allowed directories in local mode. |

`options` takes an allowlist of the library's conversion options, because tool arguments come from
the model and the model reads untrusted documents:

- output options: `ocr`, `asr_model`, `diarize`, `languages`, `extract_images`, `tracked_changes`,
  `comments`, `formulas`, `render` (dotted profile overrides such as `{"chunks.chunk_tokens": 512}`);
- limits, which a tool call may only lower: `max_pages`, `max_bytes`, `max_seconds`,
  `max_duration_seconds`. The ceilings are the operator's `--max-*` flags (below); a higher value, or
  `null` (unlimited), is rejected with `invalid_request`;
- refused with `invalid_request`: `extra` (family engine settings such as archive caps), `converter`,
  `experimental`, and any unknown key.

`allow_private_networks` is refused unless the server was started with `--allow-private-networks`,
so a document cannot talk the model into fetching intranet URLs. `list_capabilities` reports the
ceilings under `limits` and the settable keys under `tool_options`. In remote mode the instance's own
REST option rules apply.

`search_result` (BM25 search inside a result) arrives in Phase 2.

### Result shape

```json
{
  "job_id": "local_...", "status": "done", "title": "...", "source": "...", "profile": "agent",
  "tokens_total": 81200, "pages_total": 11, "pages_total_estimated": true, "page": 1,
  "next_cursor": "eyJ...", "warnings": [{"code": "pages_without_text", "severity": "warning",
  "message": "...", "suggestion": "..."}], "frontmatter": {"...": "..."},
  "sections": [{"id": "sec-1", "heading": "Introduction", "level": 2, "tokens": 640}],
  "content": "..."
}
```

`sections` appears on page 1 only. `pages_total` is exact on the last page and an estimate before it
(`pages_total_estimated`). `over_budget: true` appears when even the smallest possible page exceeds
`max_tokens` (page 1 of a document whose contents list alone is larger than the budget).

### Pagination

Large results are never returned in one piece. The text block of each page (frontmatter on page 1, the
body, and a one-line footer naming the next cursor) is at most `max_tokens` o200k tokens. Pages split on
section boundaries first and never inside a table or code block. To read on, call
`get_job(job_id, cursor=next_cursor)` with the `next_cursor` from the tool result. The cursor is opaque; it
binds the job, the profile and the page number, and a cursor from another job or profile is rejected with
`cursor_invalid`. Concatenating every page's `content` (without the agent fence and the continuation
comment) reproduces the unpaged body byte for byte.

### Warnings and errors

Partial success is a normal result (`isError: false`) with a `warnings` array: the renderer's warnings
verbatim, each with the same suggested action the web UI shows. `isError: true` is reserved for hard
failures (unsupported type, refused fetch, size cap, path outside the allowed directories, unknown job,
bad cursor); its text is `Error <code>: <message> Suggested action: <suggestion>` and its structured content
is `{"error": {"code", "message", "suggestion"}}`. Stack traces and server paths never reach the client;
unexpected exceptions are logged to stderr and reported as `internal_error`.

### Resources and prompt

- `ezmd://jobs/{id}`: the full Markdown of a job (default profile, unpaged).
- `ezmd://jobs/{id}/sidecar`: the sidecar JSON (sections, tables, provenance, warnings).
- Prompt `summarize_with_provenance(job_id?)`: summarize while citing section ids and page markers.

Local jobs live in memory (the 32 most recent) for the life of the server process.

## Transports and security

- **stdio** (default): no authentication; the server is a local child process of the client. stdout
  carries only the MCP protocol; logs go to stderr.
- **Streamable HTTP**: `ezmd-mcp --transport http [--host H] [--port P] [--token T]`. It binds
  `127.0.0.1:8765` unless `--host` or `EZMD_MCP_BIND` says otherwise. A bearer token is checked on every
  request (`401` without it). Without `--token`/`EZMD_MCP_TOKEN` on a loopback host the server generates
  one and prints it to stderr; binding a non-loopback host without an explicit token refuses to start.
  `--no-auth` is accepted on loopback hosts only. Tokens must be at least 16 characters.
- **SSE** is not implemented: it is deprecated in the MCP specification in favour of streamable HTTP.
- **Files**: `convert_file` reads only regular files under the allowed directories (default: the working
  directory; set `--allowed-dirs` or `EZMD_MCP_ALLOWED_DIRS`). Paths must be absolute, may not contain
  `..`, are resolved with symlinks followed before the check, and `/etc`, `/proc`, `/sys`, `/dev`, `/boot`,
  `/root` and `/run` are always refused.
- **URLs**: fetched by the library with the same SSRF guard as the server (resolve-once pinning, redirects
  re-checked, private ranges blocked).
- **Content**: the default `agent` profile wraps converted text in an `<untrusted_content>` fence and flags
  suspected prompt injection as a warning; the text itself is never altered or removed.

The API container mounts the same HTTP app at `/mcp` behind its API-key middleware
(`ezmd_mcp.http.build_http_app(server, token=None)`), so a remote instance is one URL for REST and MCP.

## Options and environment

| Flag | Environment | Default | Meaning |
| --- | --- | --- | --- |
| `--profile` | `EZMD_PROFILE` | `agent` | Default profile for every tool |
| `--allowed-dirs DIR...` | `EZMD_MCP_ALLOWED_DIRS` (OS path separator) | working directory | Roots `convert_file` may read |
| `--remote URL` | `EZMD_REMOTE` | none | Forward to an ezmd instance |
| `--api-key KEY` | `EZMD_API_KEY` | none | Sent as `X-API-Key` in remote mode |
| `--wait-seconds S` | `EZMD_MCP_WAIT_SECONDS` | `120` | Remote: wait this long before returning `status: running` |
| `--transport` | | `stdio` | `stdio` or `http` |
| `--host` | `EZMD_MCP_BIND` | `127.0.0.1` | HTTP bind host |
| `--port` | `EZMD_MCP_PORT` | `8765` | HTTP port |
| `--token` | `EZMD_MCP_TOKEN` | generated (loopback) | HTTP bearer token |
| `--no-auth` | | off | HTTP without a token (loopback only) |
| `--allow-private-networks` | | off | Let tool calls set `options.allow_private_networks` |
| `--max-bytes N` | | `104857600` | Local mode: input size ceiling for tool calls |
| `--max-seconds S` | | `600` | Local mode: per-conversion time ceiling |
| `--max-pages N` | | `500` | Local mode: page ceiling |
| `--max-duration-seconds S` | | `10800` | Local mode: audio/video duration ceiling |
| `--log-level` | | `WARNING` | stderr log level |

## Registry

The package is listed in the official MCP registry as `io.github.larpey/ezmd` (`packages/mcp/server.json`,
validated against the registry schema in the test suite and with `mcp-publisher validate` in CI).
