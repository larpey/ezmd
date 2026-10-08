# Ebooks and notebooks

Package `intomd_converters.ebooks`, converter family `documents` (spec: docs/spec/part2.md section 4).
Markdown and plain text are handled by the [text family](README.md).

| Converter | Mime types | Status | Engine |
|---|---|---|---|
| `documents.epub` | `application/epub+zip`; a zip named `.epub` or whose first member is the `mimetype` entry | Stable | stdlib `zipfile` + `lxml` (BSD-3-Clause), default install |
| `documents.ipynb` | `application/x-ipynb+json`; JSON that Magika labels `ipynb`, or a `.ipynb` file detected as JSON/text | Stable | stdlib `json`, the text family's Markdown parser |

Fallback chain: `application/epub+zip` tries `documents.epub`, then `archives.archive` (which lists the zip
when the EPUB converter rejects a file that detection called EPUB).

## EPUB 2 and 3

What is preserved:

- Reading order from the OPF spine. `linear="no"` items (endnotes, answer keys) follow at the end under a
  "Non-linear content" heading; when they hold only footnote bodies (an endnotes file) the headings are
  dropped and only the notes remain, so no hollow sections appear. Set `text.epub_nonlinear=false` to leave
  them out.
- Chapter headings from the TOC (EPUB 3 `nav.xhtml` with `epub:type="toc"`, else the EPUB 2 NCX). A TOC title
  is inserted before a chapter only when the chapter does not already start with a heading of the same text,
  so titles are never duplicated. Chapters with no TOC entry get no synthetic heading (fragmented books with
  one file per paragraph read as one chapter). Synthetic headings carry `attrs.origin = "toc"`.
- Headings, paragraphs, bold/italic/code/strike/super/subscript, links, lists (nested, ordered with `start`),
  tables (`colspan`/`rowspan`, `<thead>`/`<th>` header rows, captions), `<pre>` code (with `language-*`
  classes), block quotes, definition lists, MathML as an Equation with its `alttext`.
- Footnotes: EPUB 3 `epub:type="noteref"` links (and `role="doc-noteref"`) become footnote references that
  point at Footnote blocks built from `epub:type="footnote|endnote|rearnote"` (or `role="doc-footnote"`)
  elements, including notes in another file of the book. The note body is removed from the text flow.
- Images become Image blocks with their `alt` text and `figcaption`. The cover (`properties="cover-image"` or
  `<meta name="cover">`) is recorded as `metadata.extra.cover_image`, not as an Image block, so it is not a
  numbered figure, and it is not repeated where a cover page shows it. Image references are
  `images/<basename>`; the bytes (cover included) are written there when `ConvertOptions.image_dir` is set and
  `extract_images` is on.
- Print page numbers from the EPUB 3 `page-list` nav (or the NCX `pageList`): a PageBreak at each anchor,
  `provenance.source_page` (or `page_label` for non-numeric labels) on the blocks that follow,
  `metadata.pages` = the number of distinct page labels, and `metadata.extra.has_print_pages = true`.
- Metadata: `dc:title`, authors (`dc:creator` with role `aut` or no role); editors go to
  `metadata.extra.editors` and other roles to `metadata.extra.contributors` ("Name (role)"); `dc:language`
  (`language_source = "declared"`), `dc:date`, `dc:description`; `dc:identifier`, `dc:publisher`, and the
  EPUB version in `metadata.extra`.
- Provenance: every block has `path` = the chapter's zip path plus the nearest ancestor `id`
  (`OEBPS/text/chapter3.xhtml#sec2`).

Security: the container is read under the archive limits (500 MB total, 10,000 entries, 100:1 ratio per
entry; see [archives](archives.md)); a book that breaks them is refused with `archive_bomb_suspected`.
XHTML, OPF, NCX, and container XML are parsed with lxml with `resolve_entities=False`, `no_network=True`,
`load_dtd=False`, `huge_tree=False` (no XXE, no entity expansion). Chapters that are not well-formed XML
(HTML entities such as `&nbsp;`) are re-parsed with lxml's HTML parser, also without network access.
Scripts, styles, `<nav>`, and hidden elements (`hidden`, `aria-hidden="true"`, `display:none`) are dropped
and counted in `removed_hidden_elements`.

## Jupyter notebooks

- Markdown cells go through the text family's Markdown parser (`parse_markdown`); footnote ids are made
  unique per cell. TeX math is recovered afterwards: `$...$` becomes an inline math span and a paragraph that
  is only `$$...$$` becomes an Equation. `attachment:` images resolve to `images/cell<i>-<name>` (written when `image_dir` is set).
- Code cells become CodeBlocks in the kernel language, with the source verbatim (only a trailing newline
  is trimmed) (`metadata.kernelspec.language`, then
  `language_info.name`, default `python`), with `attrs.execution_count`.
- Outputs (`text.notebook_outputs`: `all` default, `text`, `off`): stream output and `text/plain` results are
  CodeBlocks fenced `output` (`attrs.role = "output"`, `attrs.stream`); error tracebacks are ANSI-stripped
  CodeBlocks fenced `output` with `attrs.role = "error"`; with `all`, rich results prefer `text/markdown`
  (Markdown parser), then `text/html` (tables such as pandas DataFrames through the XHTML walker), then
  PNG/JPEG/GIF/SVG images (Image blocks with `attrs.role = "output"`), then `text/plain`.
- Each output is capped at `text.notebook_max_output_chars` (5,000) characters with a truncation marker and
  a `truncated` warning (`detail.reason = "notebook_output"`).
- Raw cells become Raw blocks fenced with a language name derived from their `format`/`raw_mimetype`
  (`text/x-rst` becomes `rst`, `text/latex` becomes `latex`, unknown becomes `text`).
- Cells tagged `hide-cell`/`remove-cell` are left out only with `text.notebook_honor_tags=true`, and the
  count is reported in `removed_hidden_elements`.
- Notebooks older than nbformat 4 (or with no `cells` list) are read best-effort with `notebook_invalid`.
- Provenance: `path` = `cells[i]` or `cells[i].outputs[j]`, `source_id` = the cell id, and `line_start`/
  `line_end` within the cell for code and Markdown.

## Options

`ConvertOptions.extra` keys: `text.epub_nonlinear` (true), `text.notebook_outputs` (`all`),
`text.notebook_max_output_chars` (5000), `text.notebook_honor_tags` (false), and the archive limits
`specialized.archive_max_total` / `archive_max_entry` / `archive_max_entries` that also bound EPUB containers.

## Warnings

`epub_mimetype_missing` (info), `drm_protected` (error; DRM-encrypted chapters are skipped, and a stub
explains an entirely locked book; font obfuscation in `encryption.xml` is not DRM), `archive_bomb_suspected`
(error), `missing_resource` (a spine chapter is missing), `removed_hidden_elements` (info),
`extraction_empty`, `notebook_invalid`, `truncated` (notebook output cap), `image_too_large` (a notebook
image over 20 MB of base64).

## Known limitations

- The XHTML walker is local to this family until the shared HTML-to-IR module from the web family (P1-T02)
  lands; CSS-based hiding beyond inline `display:none`/`visibility:hidden` is not detected.
- EPUB 2 anchor-based footnotes (plain `#fn1` links to a short paragraph) are not yet detected; they stay
  as normal paragraphs and links.
- Only the first TOC entry of each file becomes a synthetic heading; deeper TOC entries rely on the
  chapter's own headings.
- HTML tables whose header row has an empty cell (a pandas index column) get
  `Table.attrs.header_synthesized = "true"`; the renderer names such columns itself.
- Notebook `text/latex` outputs and widget outputs are not rendered. Math recovery runs after Markdown
  parsing, so a backslash escape or an underscore pair inside `$...$` may already have been consumed.
- `ruff format .` also formats ````python` fences inside committed `expected.full.md` goldens, so the
  notebook fixture uses ruff-style code; verbatim code is asserted in the unit tests instead.
- Notebook detection depends on the extension until core detection maps Magika's `ipynb` label to
  `application/x-ipynb+json` (requested); until then every notebook also carries `misnamed_file`.

## Planned (not in this release)

MOBI/AZW/AZW3/KFX/CHM via Calibre `ebook-convert` (`calibre_missing` when absent), FB2, LaTeX (Pandoc or
the builtin parser), reStructuredText (docutils), AsciiDoc, Org, Textile, and MediaWiki (Pandoc when
present, `markup_partial` otherwise), HTML files/MHTML/webarchive (web family module in file mode).
