# PDF converters

Family `documents`, package `ezmd_converters.pdf`. Mime `application/pdf` (also `.pdf` files whose detected
type is something else, at lower confidence). Chain: `documents.docling_pdf` then `documents.pdfium_text`.

| Converter | Engine | Install | Notes |
|---|---|---|---|
| `documents.docling_pdf` | Docling (MIT), docling-parse backend, layout + TableFormer models | `pip install 'ezmd[docs]'` (torch, ~1.2 GB) | Default when installed. Registered `unavailable` otherwise. |
| `documents.pdfium_text` | pypdfium2 (BSD-3-Clause / Apache-2.0) text layer + layout heuristics | default | Always available; emits `engine_fallback` when Docling is not installed. |

## Pipeline (both engines)

1. **Sanitize** with pikepdf (MPL-2.0) before any engine sees the bytes (spec part1 8.2): remove `/OpenAction`,
   `/AA`, JavaScript (name tree, `/JS`, JavaScript actions), `/Launch` and other active actions (`/SubmitForm`,
   `/ImportData`, `/GoToR`, `/GoToE`, `/Rendition`, ...), multimedia annotations (`/RichMedia`, `/Movie`,
   `/Sound`, `/Screen`, `/3D`), `/EmbeddedFiles` and file-attachment annotations (one `attachment_skipped`
   warning per name), and `/XFA` (`unsupported_feature`). Counts go in `removed_script_or_macro`.
2. **Encryption**: tries the empty user password, then `pdf.password`, then `pdf.password_file` lines (at most 50
   candidates, never logged). A file that stays locked becomes the stub paragraph "Encrypted PDF; no valid
   password supplied" with `encrypted_no_password` (error). Owner-password (copy-restricted) files are converted
   with `copy_restricted_ignored` (info). The sanitized copy is saved unencrypted in a private temp dir.
3. **Page cap**: the sanitized copy is truncated to `min(max_pages, pdf.max_pages)` pages; `page_cap_reached`,
   `truncated: true`.
4. **Metadata**: Info/XMP title, author, subject, keywords, creation/modification dates, `/Lang`, tagged flag,
   page count. `extra`: `pdf_pages_converted`, `pdf_tagged`, `pdf_page_modes` (counts of born_digital / hybrid /
   scanned), `pdf_pages_without_text`, `pdf_heading_source`, `pdf_running_headers`, `pdf_engine`.
5. **Scan classifier** (every page, not a 12-page sample: the pdfium pass is cheap): characters and image-area
   fraction per page. Pages with fewer than 20 characters are listed in `pages_without_text` (warning). With
   `pdf.ocr=auto` (default) pages without text that contain images go to the OCR hook; until the OCR pipeline
   ships (P2-T05) they get the stub paragraph "Page N has no text layer; OCR not installed" and
   `ocr_unavailable`. A page where more than 5 percent of glyphs are private-use counts as having no text.
6. **Headings**: structure tree (tagged PDF, `H1`..`H6`/`H`/`Title` via `/RoleMap`, mapped through marked-content
   ids) first, then the outline (bookmarks) by title, then font size (sizes at least 1.15x the body size, largest
   first). When the tree disagrees with font sizes on more than 30 percent of headings,
   `heading_source_structure_tree` (info). Tagged files with an empty/unusable tree: `structure_tree_unusable`.
   Docling's section headers are re-leveled with the same map (Docling's layout model does not infer hierarchy).
7. **Forms**: AcroForm fields become a `Form fields` heading + table (Field, Type, Value, Page); checkboxes
   `[x]`/`[ ]`, signatures `(signed)`/`(unsigned)`, push buttons skipped.
8. Every block carries `source_page` and a top-left-origin `bbox` in points with `page_width`/`page_height`
   (PageBreak has page only). `PageBreak` precedes every page (renders as `<!-- page N -->`).

## Text-layer engine (`documents.pdfium_text`)

Characters (box, font size, weight/name for bold, marked-content id, link target) are grouped into lines; a
horizontal gap over 1.2 em splits a baseline (columns, cells). Coordinates honor `/Rotate` and the crop box.
Then: running headers/footers (lines in the top/bottom 8 percent whose digit-normalized text repeats on at least
half the pages) are removed with `removed_running_header_footer`; tables are detected best-effort (two or more
consecutive rows of short cells in consistent columns; bold first row is the header); column gutters are found
by the x position crossed by the fewest lines, and full-width lines split the page into bands read left column
then right column (`reading_order_uncertain` when the content stream was interleaved); lines are joined into
paragraphs by spacing, size, and indent; bullet and numbered lines become lists (nesting by indent); line-end
hyphens are joined when the joined word appears elsewhere in the document (`pdf.dehyphenate`); ligatures are
NFKC-expanded; URI link annotations become inline links (http, https, mailto only).

## Docling engine (`documents.docling_pdf`)

`DocumentConverter` with `PdfPipelineOptions(do_ocr=False, do_table_structure=True)`, run in page batches of
`pdf.batch_pages` with a deadline check and `publish_partial` between batches. Items map to Heading, Paragraph,
List (nesting from the item depth), Table (row/col spans, header rows, caption), CodeBlock, Equation (LaTeX text;
empty formulas warn `equation_unrecognized`), Footnote, caption paragraphs. Page headers/footers (furniture) are
dropped and counted. Pictures are counted in `pdf_pictures` (no image payloads yet).
Models are never downloaded during conversion unless `allow_network` is true (`HF_HUB_OFFLINE=1` is set before
Docling loads). Pre-fetch with `docling-tools models download layout tableformer -o DIR` and set
`EZMD_DOCLING_ARTIFACTS=DIR` (`docling-tools` is installed with the `docs` extra; see
[Install](../install.md#docling-models-docs-extra)). Any Docling error is retryable, so the registry falls back to the text-layer
engine (`engine_fallback`). `EZMD_PDF_ENGINE=pdfium` (or `pypdf`) or `pdf.engine=pdfium` skips Docling.

## Options (`ConvertOptions.extra`, CLI `--opt extra.pdf.<name>=...`)

From the CLI, pass each option as `--opt extra.pdf.<name>=<value>`, for example
`ezmd convert report.pdf --opt extra.pdf.engine=pdfium --opt extra.pdf.max_pages=20`. There are no
`--pdf.<name>` flags. `--engine pdf=docling` (or `--converter documents.docling_pdf`) forces the Docling
engine and, without the `docs` extra, fails with the install command.

| Option | Values (default first) | |
|---|---|---|
| `pdf.engine` | `docling`, `pdfium` (`pypdf` is an alias) | also `EZMD_PDF_ENGINE` |
| `pdf.ocr` | `auto`, `force`, `off` | `off` when `ConvertOptions.ocr` is false |
| `pdf.max_pages` | int | can only lower `ConvertOptions.max_pages` (default 500; spec local cap 2000) |
| `pdf.batch_pages` | 25 | Docling batch size |
| `pdf.password`, `pdf.password_file` | | never logged |
| `pdf.forms` | `table`, `inline`, `off` | `inline` currently behaves like `table` |
| `pdf.keep_running_headers` | false | |
| `pdf.dehyphenate` | true | |
| `pdf.structure_tree` | `prefer`, `ignore`, `only` | |
| `pdf.page_markers` | true | |
| `pdf.images` | `extract`, `skip`, `caption` | accepted; image extraction is not implemented yet |

## Warnings

`encrypted_no_password`, `copy_restricted_ignored`, `attachment_skipped`, `removed_script_or_macro`,
`unsupported_feature` (XFA), `page_cap_reached`, `pages_without_text`, `ocr_unavailable`, `engine_fallback`,
`reading_order_uncertain`, `heading_source_structure_tree`, `structure_tree_unusable`,
`removed_running_header_footer`, `equation_unrecognized` (Docling), `removed_hidden_elements`, `timeout_partial`,
`extraction_empty`.

## Known limitations

- Text-layer engine: tables are heuristic (no ruling lines, no merged cells, no tables spanning pages /
  `table_rejoined`); headings come only from tree/outline/size (bold body-size headings are paragraphs);
  footnotes, equations, figures, and captions are plain paragraphs; internal `/Dest` links are dropped.
- No image extraction (`Image` blocks) in either engine yet; `pdf.images` is accepted but ignored.
- `pdf.page_range`, `pdf.academic` (DOI/arXiv/citations), `pdf.forms=inline`, and embedded-file conversion as
  child documents are not implemented; embedded files are removed by sanitization (part1 8.2 wins over part2
  1c step 14).
- OCR is a hook only (`ezmd_converters.pdf.ocr.ocr_page`), live when `ezmd.ocr.pipeline` exists (Phase 2).
- Per-page decisions are summarized as counts in `metadata.extra` (Metadata has no nested dicts).
- Docling engine is tested against synthetic fixtures only and only when the `docs` extra and models are present.
