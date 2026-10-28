# ezmd

Convert anything (documents, web pages, data files, code, archives, and more) to clean Markdown for AI
tools. Reports what it couldn't convert. Apache-2.0.

ezmd renders every input as Markdown with YAML frontmatter under one of four output profiles, plus a JSON
ledger with block provenance and an explicit list of warnings. When something cannot be converted, ezmd
says so instead of dropping it quietly.

```sh
pip install ezmd                  # or: uv tool install ezmd
ezmd convert report.pdf -o report.md
ezmd convert https://example.com
ezmd capabilities                 # what this install can convert, and which extras are missing
```

```python
import ezmd

result = ezmd.convert("report.pdf")
print(result.markdown)
```

Optional extras:

- `ezmd[docs]`: Docling layout analysis for PDFs (large; pulls torch).
- `ezmd[data]`: Parquet files (pyarrow).
- `ezmd[7z]`: 7z archives.
- `ezmd[mcp]`: the MCP server (`ezmd-mcp`) for Claude Desktop, Claude Code, Cursor and other MCP clients.
- `ezmd[all]`: all of the above.

This package is the core library and CLI; the built-in converters ship in
[`ezmd-converters`](https://pypi.org/project/ezmd-converters/), which installs with it.

Documentation, the converter matrix, the self-hosted API and the changelog:
<https://github.com/larpey/ezmd>.
