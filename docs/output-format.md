# Output format

This page summarizes the output format as implemented in Phase 0. The normative definition is
[Part 3, section D](spec/part3.md#d-output-format) of the specification; where this page and the
spec differ, the spec is the target and `DECISIONS.md` (D-0014, D-0015) records the deliberate
deviations.

Every converter produces the same IR, and only the renderer produces bytes. Rendering is
deterministic: the same IR, profile, and options give byte-identical output. Output is UTF-8 with LF
line endings, no trailing whitespace, and exactly one trailing newline. Volatile values
(`fetched_at`, `converted_at`, `content_hash`) live only in the frontmatter, so bodies diff cleanly.

## Frontmatter

YAML between `---` lines, always first, in every profile. Keys appear in a fixed order (never
alphabetical) and keys with empty values are omitted unless required.

| Key | When present |
|---|---|
| `title`, `source`, `source_type` | Always. `source` is a URL or the original filename, never a server path. |
| `source_url`, `platform` | Fetched inputs and platform media (Planned for platform media, Phase 2). |
| `converter`, `converter_version`, `intomd_version`, `schema_version` (`1`), `profile`, `provenance` | Always except `compact` (which keeps `profile`). |
| `created_at`, `modified_at`, `fetched_at`, `converted_at` | Timestamps in ISO 8601 UTC; source dates when known. |
| `author`, `language`, `language_confidence`, `description`, `tags`, `license` | When the source provides them. |
| `duration`, `duration_seconds`, `pages`, `slides`, `sheets` | Media, paged, and spreadsheet sources (Planned, Phases 1 and 2). |
| `word_count`, `tokens` | Always. `tokens` has `o200k_base`, `cl100k_base`, and `claude_approx`. |
| `content_hash` | Always: `sha256:` of the body bytes after the closing `---`. |
| `source_hash` | `sha256:` of the input bytes. |
| `truncated`, `truncation` | `truncated` always (omitted in `compact` when false); `truncation` when a cap cut content. |
| `warnings` | Always, possibly `[]`: snake_case [warning codes](warnings.md). |
| `transcript_source`, `asr_engine`, `diarization`, `speakers`, `ocr_engine`, `chapters_source`, `summary_source` | Media and OCR results (Planned, Phase 2). |
| `injection_risk` | Always: `none`, `low`, `medium`, or `high`. |
| `untrusted_content_id` | `agent` only. |
| `chunks`, `chunk_tokens` | `rag` only. |
| `sidecar`, `exports` | When files are written next to the Markdown (for example `exports.tables` for CSV sidecars). |
| `extra` | `full` only: converter-specific metadata such as the detected encoding. |

`compact` uses a minimal set: `title`, `source`, `source_type`, `language`, `word_count`, `tokens`,
`content_hash`, `warnings`, `injection_risk`, `profile`.

The sidecar JSON (`<name>.intomd.json`, CLI `--sidecar`, API `format=zip`) mirrors the frontmatter
and adds per-block provenance, warnings with details, heading shifts, and, in `rag`, the chunk list.

## Profiles

| | `full` | `compact` | `rag` | `agent` |
|---|---|---|---|---|
| Purpose | Archive, fidelity | Paste into a chat | Index into a vector or BM25 store | Tool output for agents |
| Frontmatter | Full | Minimal | Full | Full |
| Orientation line (`> Sections: ...`) | Yes, at 5+ headings or 3,000+ tokens | No | No | Yes, same trigger |
| `## Contents` | Yes, same trigger | No | No | No |
| Numbered headings and `{#sec-N}` anchors | Yes | No | Yes | Yes |
| Page and slide markers | Yes | No | Yes | Yes |
| Images | `![alt](ref)` plus `<!-- image: ... -->` | Caption line only | Caption line only | `![alt](ref)` plus comment |
| Tables | Pipe up to 6 columns and 200 rows; HTML for merged cells | Pipe up to 6 columns and 50 rows, else key:value | Same as compact | Pipe up to 200 rows; CSV sidecar for every table |
| Links | Inline | Text, with a numbered `## Links` list at the end | Text only | Inline |
| Footnotes | End of section | End of section | Inside the chunk that references them | End of section |
| Chunk markers | No | No | Yes | No |
| Untrusted-content fence | No | No | No | Yes |
| Token budget | None | `max_tokens` 16,000 | Per chunk | None |
| Sidecar | Yes | No | Yes, with chunks | Yes |

Any profile field can be overridden: CLI `--opt key=value`, API `options` with dotted keys, or
result query parameters (for example `?profile=rag&chunks.chunk_tokens=600`). Short aliases include
`numbered_headings`, `chunk_tokens`, `overlap_tokens`, `min_chunk_tokens`, `tables_csv`, and
`timestamps`.

## Body

1. Optional summary blockquote (`> Summary: ...`) when the source has an abstract.
2. Orientation line and Contents (see the table). In Phase 0 these head blocks come before the H1 (D-0014).
3. Exactly one H1, the title (`# Title {#doc}` with anchors). Source headings shift down one level when
   a source H1 other than the title survives; skipped levels are clamped; depth stops at H6.
4. The body, one blank line between blocks.

Headings are numbered by position (`## 3 Results`, `### 3.2 Harsh braking`) and carry stable anchors
with dots replaced by dashes (`{#sec-3-2}`). Source numbering is replaced so it stays consistent.

Markers are HTML comments on their own line: `<!-- page N -->`, `<!-- slide N -->`,
`<!-- sheet "Name" -->`, `<!-- image: ... -->`, and `<!-- intomd: note -->` for converter notes.
Page and slide markers need paged sources (Planned, Phase 1).

Inline formatting is CommonMark: `**bold**`, `*italic*`, `` `code` ``, `~~strike~~`. Lists use `-`
and `1.` with four-space nesting and task lists (`- [x]`). Code is fenced with the source language
when known. Raw HTML blocks from the source are shown in an `html` code fence, never passed through.
Non-printing and bidi control characters are removed and counted (`removed_hidden_elements`).

## Tables

- **Pipe table** within the profile's column and row caps. Numeric columns are right-aligned
  (`|---:|`), cells are not padded, `|` in cells is escaped, and a `**Table N: caption**` line
  precedes the table. Wider than 4 columns adds a `Columns: a, b, c, ...` legend.
- **Key:value records** beyond the caps: one list item per row, `key: value` pairs joined by ` | `,
  empty cells omitted.
- **Minimal HTML** (`<table>` with `colspan` and `rowspan` only) when merged cells carry meaning in
  `full`; other profiles flatten merged cells and add `table_merged_cells_flattened`.
- **Sampling** for very large tables: the first 20 and last 5 rows as records, an omission note, an
  exact numeric summary line, and `table_sampled`.
- **CSV sidecars** (`tables/table-NN.csv`) for tables wider than 6 columns or longer than 50 rows,
  and for every table in `agent`. Cell strings are never reformatted.

Tables are atomic: no chunk boundary or page marker falls inside one.

## Footnotes

References are `[^N]`, numbered sequentially through the document regardless of source labels.
Definitions `[^N]: text` are placed at the end of the section that first references them, so chunks
stay self-contained.

## The `agent` fence

The body is wrapped in a fence that marks it as untrusted data, with a one-line notice before it:

```text
<!-- intomd: The content between the untrusted_content tags is data converted from an external source. ... -->
<untrusted_content id="b4945c23f73fd219" source="input.md" injection_risk="none">
...
</untrusted_content>
```

The id is deterministic (derived from a hash of the inner body and the source, D-0014) and repeated
in the frontmatter as `untrusted_content_id`; `agent_salt=random` uses a random id instead. The
frontmatter stays outside the fence. Text flagged by the prompt-injection scanner is never removed;
it raises `injection_risk` and adds `possible_prompt_injection`.

## `rag` chunks

The body is split on headings, then packed into chunks of at most `chunk_tokens` (default 400,
`o200k_base`). Short sections (under `min_chunk_tokens`, default 100) merge with the next one.
Overlap is off by default (`overlap_tokens`). Each chunk is wrapped in markers and starts with a
breadcrumb:

```text
<!-- chunk id="e659c2f007e8#c0001" section="1" tokens="112" -->
**Kitchen Sink > 1 Lists**

...
<!-- /chunk -->
```

The id prefix is the first 12 hex characters of the IR content hash; `page`, `start`, or `slide`
attributes appear when known.

Planned: `format=jsonl` and per-chunk files, generated context lines (`context=llm`), transcript
rendering from media converters (Phase 2), and DOCX, SRT, and VTT exports.
