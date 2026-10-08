# Plain text and Markdown

Package `intomd_converters.text`, converters `text.plain` and `text.markdown_passthrough` (family `text`).
These are the reference implementation for the converter contract; see [Writing a converter
plugin](../plugins.md).

## What is supported

| Converter | Inputs | What it preserves |
|---|---|---|
| `text.plain` | `text/plain`, and any other `text/*` type no more specific converter claims | Charset detection (BOMs, UTF-8, legacy single-byte encodings), setext-style headings, paragraphs with line provenance, hidden-character removal |
| `text.markdown_passthrough` | `text/markdown` | CommonMark plus tables, strikethrough, footnotes, task lists, and front matter; the `full` profile reproduces the structure |

Fallback chains: `text/plain` uses `text.plain`; `text/markdown` tries `text.markdown_passthrough`, then
`text.plain`.

## Fixtures

`fixtures/text/`: `markdown-kitchen-sink`, `plain-latin1`, `plain-utf8`, `plain-utf8-bom`. Thresholds are
0.95 for both converters (`fixtures/text/thresholds.toml`).

## Known limitations

- Plain text has no reliable structure, so only setext-style headings (a line underlined with `===` or
  `---`) become headings; everything else is paragraphs.
- Encoding detection on very short legacy-encoded files can guess wrong. If the output looks garbled,
  re-save the file as UTF-8 and convert it again.
