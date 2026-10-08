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

- Plain text has no reliable structure. Headings are recognised only when a line is underlined with `===`
  or `---`, or when a short ALL-CAPS line (3+ words or a trailing colon, no sentence punctuation) stands
  alone between blank lines. Blocks indented 4+ spaces are code unless they read as a quoted passage or a
  sub-list. Runs of 3+ lines whose columns line up on 2+ space gaps become a table.
- Numbered outlines (`1.`, `2.1`) keep one item per line (hard line breaks) but do not become nested lists.
  Whitespace tables with a ragged or missing column, or with fewer than 3 lines, stay as lines of text.
- Markdown: Obsidian wikilinks (`[[Page]]`) and embeds (`![[file]]`) stay literal text. Callouts
  (`> [!warning] Title`) render as a labelled quote with the title on its own line. Table column
  alignment is not carried over: left-aligned (`:--`) is the default anyway, and numeric columns are
  right-aligned by inference.
- Encoding detection on very short legacy-encoded files can guess wrong. If the output looks garbled,
  re-save the file as UTF-8 and convert it again.
