# Converter matrix

Built-in converters, as listed by `intomd capabilities` and `GET /v1/capabilities`. Status levels
are Stable, Beta, Experimental, and Planned.

| Converter | Family | Mime types | Status | Notes |
|---|---|---|---|---|
| `text.plain` | text | `text/plain`, and any other `text/*` not claimed by a more specific converter | Stable | Charset detection, setext headings, paragraph provenance by line, hidden-character removal |
| `text.markdown_passthrough` | text | `text/markdown` | Stable | CommonMark plus tables, strikethrough, footnotes, task lists, front matter; reproduces structure in the `full` profile |

Fallback chains (`intomd.chains`): `text/plain` uses `text.plain`; `text/markdown` tries
`text.markdown_passthrough`, then `text.plain`.

More families arrive in Phase 1: documents (PDF, Office, EPUB), web pages, code, data files, email,
notebooks, and archives, followed by media and OCR in Phase 2. Each family will get its own page here
with what it preserves, its known limitations, and the warnings it emits. To add your own, see
[Writing a converter plugin](../plugins.md).
