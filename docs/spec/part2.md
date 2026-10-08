## Part 2: Converter families

This part specifies every converter family in `packages/converters/`. Part 1 defines the `Converter` protocol, the IR (`Document` and its blocks), the registry, the output profiles, and the test harness. Part 3 defines the media pipeline (audio, video, transcription) and the OCR pipeline (image OCR, VLM OCR, chart-to-table). Part 2 does not restate those; where a document converter needs OCR or transcription it calls `intomd.ocr.pipeline` or `intomd.media.pipeline` through the interfaces Part 3 defines and otherwise treats them as black boxes.

### Conventions used in every family section

1. Package path: `packages/converters/<family>/` containing `pyproject.toml`, `src/intomd_<family>/`, and `tests/`. The package registers its converters under the entry point group `intomd.converters`, one entry per `Converter` class, e.g. `pdf = intomd_pdf:PdfConverter`.
2. Each `Converter` implements `can_handle(input: InputRef) -> float` (0.0 to 1.0) and `convert(input: InputRef, options: ConvertOptions) -> Document`. `InputRef` carries the detected MIME type, extension, URL (if any), byte length, and a lazily opened stream. Confidence rules: 1.0 for an exact MIME match from Magika, 0.9 for extension match, 0.7 for URL-pattern match, 0.3 for "I could try" sniffing, 0.0 never.
3. Every emitted block carries a `Provenance` object. The fields in play for Part 2 are `page` (1-based int), `bbox` (x0, y0, x1, y1 in PDF points, origin top-left, normalized by the IR to 0 to 1 floats), `path` (source-relative path or JSON pointer or sheet!cell), `timestamp` (seconds float, used by transcripts and chat), `source_id` (message id, post id, commit sha, etc.), and `line` (1-based line for text-ish inputs). A section below names which fields are mandatory for that family; the fixture scorer treats missing mandatory fields as a provenance-completeness failure.
4. Warnings use the taxonomy in section 13. A converter appends `Warning(code, message, provenance)` to `Document.warnings`. A converter never raises on partial failure; it raises `ConversionError` only when it produced no blocks at all, and the registry then falls back to the next candidate converter or to the stub note defined in Part 1.
5. Options: every converter accepts the shared `ConvertOptions` (profile, max_bytes, timeout_s, language_hint, experimental) plus family-specific options listed under heading (h). Family options are declared as a pydantic model `<Family>Options` nested at `options.pdf`, `options.office`, etc., so the CLI exposes them as `--pdf.ocr=force`.
6. Fixture layout: `fixtures/<family>/<case>/input.*`, `expected.md`, `expected.json`, `meta.yaml`. `meta.yaml` keys: `threshold` (object with the five scores), `notes`, `source`, `license`, `experimental` (bool), `requires` (list of optional extras or system binaries; the harness skips the case when they are absent and reports it as skipped, never as passed). Fixtures must be self-authored, public domain, CC-BY, or generated synthetically with a script committed under `fixtures/_gen/`. Never commit commercial media or copyrighted text longer than fair-use excerpts.
7. Acceptance scoring (from Part 1): `heading_retention` (fraction of expected headings present with the correct level), `table_cell_accuracy` (fraction of expected cells whose normalized text matches), `text_similarity` (normalized Levenshtein ratio on whitespace-collapsed, punctuation-normalized text), `element_counts` (per-block-type count within tolerance), `provenance_completeness` (fraction of blocks carrying the mandatory provenance fields). Thresholds given in each section are minimums; the harness fails the case if any score is below its minimum.
8. Golden workflow: run `intomd fixtures regen <family>/<case>`, which writes `expected.md` and `expected.json`, then run the Skeptic subagent (Part 1, `tools/skeptic`) which opens the input and the output side by side and must sign `meta.yaml` with `reviewed_by: skeptic` and `reviewed_at` before the commit hook allows the fixture to land. A fixture without a skeptic signature fails CI.
9. Phases: Phase 1 is the permissive document, web, code, and email core. Phase 2 is media. Phase 3 is social, chat exports, and URL fetching that needs Crawl4AI or credentials. Phase 4 is the public instance (no converter work). Phase 5 is persona verticals. Each section states its phase; sub-features may be split across phases and are marked.

---

## 1. documents/pdf

### 1a. Scope and input matrix

| Input | Detection | Route |
|---|---|---|
| `.pdf`, `application/pdf` | Magika `pdf`, magic bytes `%PDF-` | this converter |
| `.pdf` with no extractable text on sampled pages | post-detection scan classifier (1c step 4) | OCR pipeline per page, results merged back here |
| `.pdf` with AcroForm or XFA fields | `/AcroForm` in trailer | form extraction path (1c step 9) |
| Encrypted `.pdf` | `/Encrypt` in trailer | password path (1c step 3) |
| PDF/A, tagged PDF (`/MarkInfo /Marked true`) | trailer flags | structure-tree reuse (1c step 5) |
| `https://...pdf` and any URL whose response is `application/pdf` | web/pages hands off | this converter |
| PDF portfolios and embedded files (`/EmbeddedFiles`) | name tree | each embedded file is a child `Document` converted through the registry |

Not in scope: PDF generation, PDF editing, redaction. Scanned pages are in scope only through the OCR pipeline.

### 1b. Library and fallback chain

1. Primary: Docling (MIT) `DocumentConverter` with `PdfPipelineOptions`. Docling's default PDF backend is `docling-parse` (MIT); use it. Do not enable Docling's `pypdfium2` backend by default (pypdfium2 is BSD-3/Apache dual, acceptable, but docling-parse gives better bbox fidelity). Docling default layout and table models are Apache-2.0 / CDLA-permissive-2.0 and are the only weights the default install pulls.
2. Fallback when Docling raises or times out on a page batch: `pypdf` (BSD-3) text extraction per page, emitted as `Paragraph` blocks with `page` provenance only and warning `engine_fallback`. This path never produces tables or headings; the warning text must say so.
3. Optional extras, never default: `intomd[pymupdf]` (AGPL, `pymupdf4llm`) as a fast path for born-digital PDFs when the user has accepted the license; `intomd[marker]` (code Apache-2.0, Surya weights OpenRAIL-M) for academic math; `intomd[mineru]` (MinerU custom terms). Each extra registers a converter with `can_handle` returning 0.95 only when `options.pdf.engine` names it explicitly or `INTOMD_PDF_ENGINE` is set; otherwise 0.0. The `shadow-run` command in Part 1 may invoke all installed engines for comparison.
4. Scanned pages: the OCR pipeline (Part 3). Default engine PaddleOCR-VL (Apache); CPU-light mode uses RapidOCR or Tesseract. The PDF converter does not import OCR engines directly; it calls `intomd.ocr.pipeline.ocr_page(image, hints)` and receives IR blocks with bboxes.
5. Forms: `pypdf` for AcroForm fields (BSD-3). XFA forms: extract the XFA datasets XML with `pypdf`, parse with stdlib `xml.etree`, emit a key-value table, and warn `xfa_partial`.
6. Encrypted: `pypdf` with `cryptography` (Apache/BSD) for AES.

### 1c. Build steps

1. Create `packages/converters/pdf/` with `PdfConverter`. `can_handle` returns 1.0 on `application/pdf`, 0.9 on `.pdf` extension with a non-PDF MIME (Magika sometimes reports `unknown` for malformed PDFs), 0.0 otherwise.
2. Open with `pypdf.PdfReader` first (cheap) to read the trailer: page count, `/Encrypt`, `/AcroForm`, `/MarkInfo`, `/Metadata` (XMP), `/Info` (title, author, creation date), `/Outlines` (bookmarks), `/EmbeddedFiles`. Store in `Document.metadata`. If page count exceeds `options.pdf.max_pages` (default 2000), truncate and set `Document.truncated = True` with warning `page_cap_reached`.
3. Password handling: if encrypted, try the empty user password, then `options.pdf.password`, then `options.pdf.password_file` entries line by line. On failure emit a stub `Document` with one `Paragraph` reading "Encrypted PDF; no valid password supplied" and warning `encrypted_no_password`; do not retry more than 50 passwords; never log passwords. Owner-password-only PDFs (openable, copy-restricted) are opened and converted with warning `copy_restricted_ignored` so the user knows the producer set a restriction flag.
4. Scan classification per page: sample up to 12 pages (first 4, last 2, 6 evenly spaced). For each sampled page compute `chars_per_page` via `pypdf` text extraction and `image_area_fraction` from the page's XObject images. Classify: `born_digital` if chars >= 200 and image fraction < 0.9; `scanned` if chars < 20 and image fraction > 0.5; `hybrid` otherwise. If `options.pdf.ocr == "off"`, never OCR; `"force"` OCRs every page; `"auto"` (default) OCRs pages classified `scanned` and, in `hybrid`, OCRs only pages whose own text is under 20 chars. Record the per-page decision in `Document.metadata["pdf"]["page_modes"]`.
5. Tagged PDF structure reuse: if `/MarkInfo /Marked true` and a `/StructTreeRoot` exists, walk the structure tree with `pypdf` and build a heading-level map (`H1`..`H6`, `P`, `Table`, `TH`, `TD`, `L`, `LI`, `Figure`, `Caption`, `Note`) keyed by marked-content IDs. After Docling runs, if Docling's heading levels disagree with the structure tree on more than 30 percent of headings, prefer the structure tree (authors' intent beats layout inference) and warn `heading_source_structure_tree`. If the structure tree is present but empty or malformed (common with auto-tagged output), ignore it and warn `structure_tree_unusable`.
6. Run Docling in page batches of `options.pdf.batch_pages` (default 25) using `page_range` so a 1,500-page filing does not hold the whole layout result in memory. Each batch runs under its own timeout slice (section 13). Merge batch results in order. Headings that Docling splits across a batch boundary are rejoined when the last block of batch N and the first block of batch N+1 are both `Heading` with identical text.
7. Map Docling items to IR: `SectionHeaderItem` to `Heading(level)` where level comes from Docling's `level` attribute, clamped 1..6; `TextItem` to `Paragraph`; `ListItem` groups to `List(ordered, items)` preserving nesting from Docling's parent chain; `TableItem` to `Table` with `cells[r][c]` and `row_span`/`col_span` from Docling's `TableCell` so merged cells survive; `PictureItem` to `Figure(image, caption)` when a caption item is attached, else `Image`; `CodeItem` to `Code(language=None)`; `FormulaItem` to `Equation(latex)`; `FootnoteItem` to `Footnote(id, text)`; running headers and footers (`PageHeaderItem`, `PageFooterItem`) are dropped from the body and stored in `Document.metadata["pdf"]["running_headers"]` with a count, and the converter emits one warning `removed_running_header_footer` with the count. Every block gets `Provenance(page=item.prov[0].page_no, bbox=item.prov[0].bbox normalized)`.
8. Page markers: emit `PageBreak(page=N)` before the first block of each page. The Markdown renderer (Part 1) turns these into `<!-- page N -->`. The first page gets a marker too so page 1 is grep-able.
9. Forms: when `/AcroForm` exists, read every field (`pypdf` `get_fields()`), including nested kids and radio groups, and emit a `Table` with columns `Field`, `Type`, `Value`, `Page` under a `Heading(level=2, text="Form fields")` appended after the body. Checkbox values normalize to `[x]`/`[ ]`. Signature fields emit `Value = "(signed)"` or `"(unsigned)"` by presence of `/V`. If `options.pdf.forms == "inline"` (experimental), additionally place each field value as a `Paragraph` at its widget bbox position within the page flow, sorted by y then x.
10. Multi-column handling: Docling's layout model handles columns; verify by a reading-order sanity check: for each page, if more than 40 percent of adjacent paragraph pairs have the second block's bbox entirely to the left and above the first (a sign of interleaving), re-run that page with Docling's `force_backend_text=False` and the OCR pipeline's layout-only mode, keep the better of the two by a monotonic-y score, and warn `reading_order_uncertain` on that page. Resumes and newsletters are the test targets.
11. Academic path: when `Document.metadata` suggests a paper (DOI in XMP or text matching `10\.\d{4,9}/`, or `arXiv:` in the first page), set `pipeline_options.do_formula_enrichment=True` so Docling emits LaTeX for formulas, enable `do_picture_classification` so figures get a type, and run citation detection: numeric `[12]`, author-year `(Smith et al., 2021)`, and a trailing `References` section parsed into a `List` of `Paragraph` entries each carrying `metadata.citation_key` (first author surname + year). Also extract DOI, arXiv id, title, authors, abstract into frontmatter fields `doi`, `arxiv_id`, `authors`, `abstract`. Figures with captions become `Figure(caption=...)` and the caption text is also searched for `Figure N` to set `metadata.figure_number`. Equation blocks that Docling returns as images with no LaTeX are kept as `Image` with warning `equation_unrecognized` and, when `intomd[marker]` is installed and the user opted in, re-run through Marker for that page only.
12. Footnotes: Docling marks footnotes when its layout model labels them. Additionally, for born-digital pages, detect superscript runs (font size under 70 percent of body median and raised baseline) that match a block at the page bottom starting with the same number; emit `Footnote(id, text)` and insert the `[^id]` reference into the paragraph text. Place footnotes at the end of the section in which they are referenced (renderer rule from Part 1).
13. Images: write each `Image`/`Figure` payload to the output asset store as `images/p{page}-{idx}.png` (Part 1 asset API). Default `options.pdf.images = "extract"`; `"skip"` emits an `Image` with no payload and `alt` only; `"caption"` additionally runs the OCR pipeline's captioner (Part 3) when installed.
14. Embedded files: for each entry in `/EmbeddedFiles`, convert through the registry as a child document and attach under `Heading(level=2, text="Attachment: <name>")`, respecting the archive depth and size rules in section 12 (archives).
15. Large-file streaming: never read the whole file into memory for files over 50 MB; use `pypdf` with a seekable stream and Docling page ranges. Emit blocks per batch to the `Document` builder so a cancelled job still yields partial output with `truncated=True`.
16. Finalize: compute `Document.metadata["pages"]`, `pages_without_text` (list), `ocr_pages` (list), and run the warning aggregation. Return.

### 1d. IR blocks and provenance

Emits: `Heading`, `Paragraph`, `Table` (with spans), `List`, `Code`, `Image`, `Figure`, `Footnote`, `Equation`, `PageBreak`, `Link` (from annotation `/Link` with `/URI`), `Raw` only for XFA residue. Mandatory provenance: `page` on every block, `bbox` on every block except `PageBreak`. `Footnote` additionally carries `page` of the note body. Form field rows carry `page` of the widget.

### 1e. Known failure modes to test

1. Multi-column resumes and two-column academic papers interleaving lines (reading order).
2. Running headers and footers leaking into the body, or a real heading being dropped as a running header because it repeats (e.g. chapter title on every page: keep it once, drop repeats).
3. Tables spanning page breaks producing two tables; rejoin when the column count and header row match and warn `table_rejoined`.
4. Merged header cells flattened to duplicates.
5. Scanned pages returning empty text with no warning (the silent-loss case from the research). The test asserts `pages_without_text` is non-empty and a warning exists when OCR is off.
6. Equations rendered as garbage glyphs; the fixture asserts an `Equation` block with LaTeX or an `equation_unrecognized` warning, never a `Paragraph` of symbols.
7. Hyphenation across line breaks (`infor-\nmation`); dehyphenate when the joined word appears in the document elsewhere or passes a wordlist check; otherwise keep the hyphen.
8. Ligatures (`ﬁ`, `ﬂ`) and private-use glyphs from subsetted fonts; NFKC-normalize, and if more than 5 percent of characters on a page are private-use, treat the page as scanned.
9. Rotated pages and landscape tables; honor `/Rotate`.
10. Text boxes and sidebars (resume skills sections) skipped; the fixture checks that sidebar text is present.
11. Bank statement page-break phantom rows (section 12 covers reconciliation; the PDF fixture here just checks no duplicated row at a page boundary).
12. Password-protected and owner-restricted files.
13. 1,000-plus page documents completing under the per-page time budget with batches.
14. PDFs with a bogus structure tree (auto-tagged by a scanner) producing wrong heading levels.
15. Links: anchors inside the document (`/Dest`) become `Link(target="#heading-slug")`, external become absolute URLs.

### 1f. Fixtures (minimum)

1. `pdf/born-digital-report`: a 12-page synthetic report generated with ReportLab (BSD): H1 to H3, nested lists, two tables (one with a merged header), one figure with caption, footnotes, running header and footer, page numbers.
2. `pdf/two-column-paper`: synthetic two-column paper with an abstract, numbered equations in LaTeX via matplotlib mathtext rendered as vector text, numeric citations, references section, DOI in XMP.
3. `pdf/resume-two-column`: CC-BY resume template with a sidebar skills column, icon glyphs, and a text box.
4. `pdf/scanned-letter`: a 3-page typed letter rendered to 300 dpi PNG and wrapped as image-only PDF (page 2 slightly skewed 2 degrees). `requires: [ocr]`.
5. `pdf/hybrid-contract`: 6 pages where pages 1 to 4 are born-digital and pages 5 and 6 are scanned signature pages.
6. `pdf/acroform-application`: a filled AcroForm with text, checkbox, radio, dropdown, and an unsigned signature field.
7. `pdf/encrypted-user-password`: AES-256 encrypted with user password `fixture`; `meta.yaml` carries the password under `options.pdf.password`.
8. `pdf/tagged-pdfa`: PDF/A-2a with a correct structure tree whose heading levels differ from visual sizes (H2 rendered larger than H1) to verify tree precedence.
9. `pdf/table-across-pages`: a 40-row table split across three pages with the header repeated on each page.
10. `pdf/long-500-pages`: generated 500-page document to test batching and timeout; threshold on text_similarity only, with a wall-clock budget in `meta.yaml`.
11. `pdf/portfolio-with-attachments`: a PDF with one embedded CSV and one embedded DOCX.

### 1g. Acceptance thresholds

Born-digital fixtures: heading_retention 0.90, table_cell_accuracy 0.92, text_similarity 0.97, element_counts within 10 percent, provenance_completeness 1.0. Scanned fixtures (`requires: [ocr]`): heading_retention 0.70, table_cell_accuracy 0.80, text_similarity 0.93, provenance_completeness 1.0. Two-column paper: additionally at least 90 percent of expected `Equation` blocks present with LaTeX that normalizes (whitespace, `\left`/`\right` removal) to the expected string.

### 1h. Options

`options.pdf`: `engine` (`docling` default, `pypdf`, `pymupdf`, `marker`, `mineru`), `ocr` (`auto` default, `force`, `off`), `ocr_languages` (list, default from `language_hint`), `max_pages` (2000), `batch_pages` (25), `page_range` (e.g. `1-10,15`), `password`, `password_file`, `forms` (`table` default, `inline`, `off`), `images` (`extract` default, `skip`, `caption`), `keep_running_headers` (false), `academic` (`auto` default, `on`, `off`), `dehyphenate` (true), `structure_tree` (`prefer` default, `ignore`, `only`), `page_markers` (true).

### 1i. Phase

Phase 1 for born-digital, forms, encrypted, tagged, batching, and the scan classifier with the `pages_without_text` warning. The OCR hand-off becomes live in Phase 2 when the OCR pipeline ships; until then `ocr=auto` on a scanned page emits the stub paragraph "Page N has no text layer; OCR not installed" and warning `ocr_unavailable`. Academic citation and figure numbering: Phase 1. Marker and MinerU extras: Phase 2. Bank-statement and legal provenance modes: Phase 5 (section 12).

---

## 2. documents/office

### 2a. Scope and input matrix

| Input | Extensions / MIME | Path |
|---|---|---|
| Word (OOXML) | `.docx`, `.docm`, `.dotx`; `application/vnd.openxmlformats-officedocument.wordprocessingml.document` | native DOCX path |
| Word legacy, RTF, OpenDocument text | `.doc`, `.dot`, `.rtf`, `.odt`, `.wpd` | LibreOffice headless to DOCX, then native path |
| PowerPoint | `.pptx`, `.pptm`, `.potx` | native PPTX path |
| PowerPoint legacy, ODP | `.ppt`, `.pps`, `.odp` | LibreOffice to PPTX |
| Excel | `.xlsx`, `.xlsm`, `.xltx` | native XLSX path |
| Excel legacy, ODS, binary | `.xls`, `.xlsb`, `.ods` | `.xls` via `xlrd` (BSD) for cell values; `.xlsb` and `.ods` via LibreOffice to XLSX |
| iWork | `.pages`, `.numbers`, `.key` (zip or package directory) | Docling `format-iwork` extra |
| Delimited | `.csv`, `.tsv`, `.txt` with delimiter sniff, `text/csv` | native CSV path |

### 2b. Libraries and fallback chain (license in parentheses)

1. DOCX: `python-docx` (MIT) for the document body, styles, numbering, tables, headers/footers, images; direct `lxml` (BSD) access to `word/document.xml`, `word/comments.xml`, `word/footnotes.xml`, `word/endnotes.xml` for tracked changes (`w:ins`, `w:del`, `w:moveFrom`, `w:moveTo`, `w:rPrChange`), comments, and footnotes, because python-docx does not expose them. Fallback: Docling DOCX backend (MIT) when the lxml path raises on a malformed package; warn `engine_fallback` and note that tracked changes were not extracted. Pandoc (GPL) is an optional shell-out: if `pandoc` is on PATH and `options.office.engine == "pandoc"`, run `pandoc --track-changes=all -t json` and map its AST; never link or vendor it.
2. DOC/RTF/ODT/WPD: `soffice --headless --convert-to docx` (LibreOffice is MPL-2.0, shelled out, never linked). If LibreOffice is absent: RTF falls back to `striprtf` (BSD) plain text with warning `engine_fallback`; ODT falls back to a native `content.xml` parser (stdlib zip + lxml) that handles headings (`text:h` with `text:outline-level`), paragraphs, lists, tables, and images; DOC falls back to `olefile` (BSD) WordDocument stream text extraction, paragraphs only, warning `legacy_text_only`.
3. PPTX: `python-pptx` (MIT). Charts: read `ppt/charts/chartN.xml` via lxml for series and categories (python-pptx exposes `chart.plots[].categories` and `series.values`). Fallback: Docling PPTX backend.
4. XLSX: `openpyxl` (MIT) with `read_only=True` for values and a second `load_workbook(data_only=False)` pass for formulas when requested. `.xls`: `xlrd` (BSD) 2.x handles only `.xls`. Fallback: `pandas` (BSD) `read_excel` for values only with warning.
5. CSV/TSV: stdlib `csv` with `csv.Sniffer`, `charset-normalizer` (MIT) for encoding, `pandas` optional for type inference of numeric columns.
6. iWork: Docling with `intomd[iwork]` extra which installs `docling[format-iwork]`. When absent, iWork packages that contain a `preview.pdf` or `QuickLook/Preview.pdf` are routed to the PDF converter with warning `iwork_preview_fallback`.

### 2c. Build steps

DOCX path:

1. Open the package with `zipfile`; verify `[Content_Types].xml` and `word/document.xml` exist, else `ConversionError`.
2. Read `docProps/core.xml` (title, creator, created, modified, revision) and `docProps/app.xml` (pages, words) into metadata.
3. Build a style map: for each paragraph style in `word/styles.xml`, resolve the `w:outlineLvl` through the `basedOn` chain. Headings map by: `Heading N` or `heading N` built-in names to level N; any style with `outlineLvl` k to level k+1; `Title` to level 1 and `Subtitle` to a `Paragraph` with `metadata.role="subtitle"`; otherwise, if a style has no outline level but its font size is at least 1.3x the Normal size and bold, treat it as a heading at a level inferred by rank of distinct sizes (largest = 1), warn `heading_inferred_from_formatting` once. Direct formatting (a bold 18pt paragraph in Normal style) follows the same size-rank rule only when `options.office.infer_headings=true` (default true).
4. Walk `w:body` in document order. For each `w:p`: resolve style, numbering (`w:numPr` with `w:ilvl` and `w:numId` to `word/numbering.xml` to decide ordered vs bullet and nesting level), and runs. Runs inside `w:ins` become `TrackedChange(kind="insert", author, date, text)`; inside `w:del` become `TrackedChange(kind="delete", ...)` using `w:delText`; `w:moveFrom`/`w:moveTo` become `kind="move_from"/"move_to"`; `w:rPrChange` is formatting-only and is recorded as `kind="format"` with no text replacement. The IR `Paragraph` holds inline children including `TrackedChange` so the renderer can produce `{++inserted++}` and `{--deleted--}` (CriticMarkup) in `full` profile, or accept/reject per `options.office.track_changes`. Default is `all` (keep both, mark them). `accept` applies insertions and drops deletions; `reject` does the opposite. Never default to `accept`: that is the Pandoc silent-loss trap.
5. Comments: parse `word/comments.xml` (and `word/commentsExtended.xml` for replies and resolved status, `word/commentsIds.xml` where present). Anchor each `w:commentRangeStart`/`End` pair to the text span it covers and emit `Comment(id, author, date, text, anchor_text, resolved, parent_id)`. The renderer places comments as footnote-style callouts `[^c3]` after the anchored paragraph in `full`, omits them in `compact` unless `include_comments=true`. Default `include_comments=true` in `full` and `agent`, `false` in `compact` and `rag`.
6. Footnotes and endnotes: `word/footnotes.xml`, `word/endnotes.xml`; emit `Footnote(id, text, kind)` and inject `[^id]` references at the `w:footnoteReference` position.
7. Tables: for each `w:tbl`, build the grid. Handle `w:gridSpan` (horizontal merge) and `w:vMerge` (`restart` begins a vertical merge, continuation cells without `w:val` extend it) into `row_span`/`col_span`. Nested tables become `Table` blocks inside the cell's block list; the renderer flattens nested tables to HTML in `full` and to a placeholder `[nested table: see sidecar]` in `compact`. Detect header rows via `w:tblHeader` or first-row bold-all; set `Table.header_rows`.
8. Headers and footers: parse `word/header*.xml` and `word/footer*.xml`, dedupe by text, store in `metadata.office.headers`/`footers`, and emit one `Paragraph` each with `metadata.role="header"` at the top of the document only when `options.office.include_headers_footers=true` (default false). Page numbers fields (`PAGE`) are rendered as `{page}`.
9. Images: `w:drawing` and legacy `w:pict` with `v:imagedata`; resolve the relationship to `word/media/*`; write to assets; emit `Image(alt=wp:docPr/@descr or @title)`. Inline images stay inline in the paragraph; anchored (floating) images are emitted as a standalone `Image` block after the anchoring paragraph. Captions: a following paragraph with style `Caption` or starting with `Figure N` or `Table N` attaches to the preceding `Image`/`Table`.
10. Fields: `w:fldSimple` and `w:instrText` for `HYPERLINK` become `Link`; `TOC` fields are dropped from the body and replaced by nothing (the renderer builds its own TOC); `REF`, `SEQ`, `DATE` fields render their cached result text.
11. Text boxes (`w:txbxContent`, `mc:AlternateContent`): extract their paragraphs and emit them after the anchoring paragraph with `metadata.role="textbox"`; count them and warn `textbox_content_relocated` when any exist. This covers the resume sidebar case.
12. Equations: `m:oMath` converted to LaTeX via a small OMML-to-LaTeX walker (implement the common subset: fractions, superscripts, subscripts, radicals, sums, Greek, matrices; unsupported nodes fall back to the plain text and warn `equation_partial`). Emit `Equation`.
13. Hidden text (`w:vanish`) and white-on-white text: excluded from the body, counted, warning `removed_hidden_elements` with the count. Never silently include it (prompt-injection hygiene) and never silently drop it (fidelity): the count goes to the sidecar with the text under `hidden_text` when `options.office.keep_hidden=true`.
14. Provenance: `path` is the body-order index `body[123]` plus `para_id` from `w14:paraId` when present; `page` is unknown for DOCX (OOXML has no page concept) unless `options.office.render_pages=true`, which runs LibreOffice to PDF and maps paragraphs to pages by text alignment, warning `pages_estimated`.
15. Document properties with custom XML (`customXml/`) are skipped unless `options.office.include_custom_xml=true`, in which case they become `Raw`.

PPTX path:

16. Open with `python-pptx`. Read presentation metadata and slide size.
17. For each slide in `prs.slides` order (this is the physical order; hidden slides have `slide._element.get("show") == "0"`; include them with `metadata.hidden=true` and warn `hidden_slides_included` with a count, or skip when `options.office.include_hidden_slides=false`).
18. Emit `Slide(number=N, title=<title placeholder text or first title-styled shape>, layout=<layout name>)` as a container block. Inside it, walk shapes sorted by top then left (reading order approximation), recursing into group shapes. Placeholder type decides role: `TITLE`/`CENTER_TITLE` to `Heading(level=2)` under the slide (slide title is always H2; the deck title from the first slide's title is H1), `SUBTITLE` to `Paragraph(role="subtitle")`, `BODY`/`OBJECT` text frames to `List` or `Paragraph` by paragraph level (`paragraph.level` gives bullet nesting), `TABLE` to `Table` with `cell.is_merge_origin`/`is_spanned` mapped to spans, `PICTURE` to `Image(alt=shape.name or descr)`, `CHART` to `Table` built from chart XML with a caption `Chart: <chart title>` and `metadata.chart_type`, SmartArt (`dgm:` relationships) to `List` built from the data model's `dgm:pt` text nodes in tree order, with warning `smartart_flattened`.
19. Speaker notes: `slide.has_notes_slide` then `notes_slide.notes_text_frame.text`; emit `Paragraph(role="notes")` grouped under `Heading(level=3, text="Notes")` inside the slide when `options.office.include_notes=true` (default true). Many decks hold the actual content in the notes.
20. Slide comments: `ppt/comments/modernComment_*.xml` or `ppt/comments/comment*.xml`; emit `Comment` anchored to the slide.
21. Section headers (`p14:section`) become `Heading(level=1)` separators between slides when present.
22. Provenance: `page` = slide number, `path` = `slide{N}/shape{id}`, `bbox` from shape `left/top/width/height` normalized by slide size.
23. Images: export to assets as `slide{N}-{shape}.png`; if `options.office.ocr_images=true`, run the OCR pipeline on each picture (lecture decks with text-in-image) and attach the text as `Image.ocr_text`.

XLSX path:

24. Open with `openpyxl` `read_only=True, data_only=True`. Enumerate `wb.worksheets` in workbook order. For each sheet record `sheet_state` (`visible`, `hidden`, `veryHidden`); include hidden sheets with `metadata.hidden=true` and warn `hidden_sheets_included` listing names, unless `options.office.include_hidden_sheets=false`.
25. Determine the used range from `ws.calculate_dimension()`; for `read_only` sheets with bogus dimensions, scan rows until 50 consecutive empty rows. Apply `options.office.max_rows` (default 10,000 per sheet) and `max_cols` (256) with `truncated=true` and warning `row_cap_reached` naming the sheet.
26. Header detection: a row is the header if it is the first non-empty row and either all its non-empty cells are strings while the next row contains at least one number or date, or it is bold throughout (requires the non-read-only pass; do this only when the sheet has under 2,000 rows). Otherwise emit synthetic headers `A`, `B`, `C`. Record `header_row` in table metadata. Multi-row headers (two string rows followed by data) are joined with ` / `.
27. Emit one `Heading(level=2, text=sheet name)` then one `Table` per contiguous data region. Region detection: split on 2 or more fully empty rows or columns; each region becomes its own table with a caption `Region <n> (A1:F30)`. Merged cells from `ws.merged_cells.ranges` map to spans.
28. Values: dates become ISO 8601 (`YYYY-MM-DD` or full timestamp when a time component exists); numbers keep the cell's number format category only in sidecar (`metadata.number_format`); percent-formatted cells render as `12.5%`; currency formats render the raw number with the currency symbol detected from the format string in the column legend, not in each cell; booleans `TRUE`/`FALSE`; errors (`#REF!`) kept verbatim and counted in warning `cell_errors`.
29. Formulas: when `options.office.formulas != "off"`, open a second workbook with `data_only=False` and read `cell.value` strings beginning with `=`. `formulas="sidecar"` (default) writes `{sheet, cell, formula}` entries to the sidecar JSON; `formulas="inline"` renders the cell as `value (=A1*B2)`; `formulas="table"` appends a second table per region with the same shape showing formulas. Shared and array formulas (`ArrayFormula`, `t="shared"`) expand to their text. Cached values that are `None` for formula cells (file saved without recalculation) warn `formula_uncalculated` and render as `=...` only.
30. Named ranges: `wb.defined_names` emitted as a `Table` (`Name`, `Refers to`) under `Heading(level=2, text="Named ranges")` when non-empty. Data validations and conditional formats are not extracted.
31. Wide tables: the six-column and fifty-row rules and the CSV sidecar live in Part 3's table rendering rules; the converter emits the full `Table` and sets `Table.metadata.wide=true` when columns exceed 6 so the renderer can switch representation.
32. Charts in XLSX (`xl/charts/`): emit a `Table` of series like PPTX charts, placed after the sheet's tables.
33. Comments and notes: `ws.comments` are not available in `read_only` mode; when the sheet is under 2,000 rows, load normally and emit `Comment(anchor=cell)` entries.
34. Provenance: `path` = `Sheet1!A1:F30` for tables and `Sheet1!C7` for comments; no `page`.

CSV/TSV path:

35. Detect encoding with `charset-normalizer` on the first 1 MB; strip BOM. Sniff the dialect with `csv.Sniffer` on the first 64 KB over candidates `, ; \t |`; if the sniffer fails, pick the delimiter with the most consistent count per line. Record `dialect` in metadata.
36. Header detection as in step 26 using `csv.Sniffer.has_header` as a tie-breaker. Emit one `Table`. Ragged rows (fewer or more fields than the header) are padded or overflow into the last column with warning `ragged_rows` and a count. Apply `max_rows` with truncation warning.
37. Numeric columns: detect with a sample of 500 rows; store `column_types` in sidecar for the legend. Never reformat values (no rounding, no thousands separator changes): finance users need exact strings.

LibreOffice shell-out (shared):

38. Locate `soffice` (`LIBREOFFICE_PATH`, then PATH, then standard install dirs on macOS and Windows). Run `soffice --headless --norestore --convert-to <target> --outdir <tmp> <input>` under a per-file timeout (default 120 s), with `HOME` set to a temp profile dir so parallel runs do not fight over the profile lock. Reject inputs over `options.office.libreoffice_max_bytes` (default 100 MB). If `soffice` is absent, apply the per-format fallbacks in 2b and warn `libreoffice_missing`.

### 2d. IR blocks and provenance

DOCX: `Heading`, `Paragraph` (with inline `TrackedChange`, `Link`, emphasis spans), `List`, `Table` (spans), `Image`, `Figure`, `Footnote`, `Equation`, `Comment`, `TrackedChange`, `Quote` (style `Quote`/`Intense Quote`/`Block Text`), `Code` (style `Code`, `HTML Preformatted`, or monospace font runs covering a whole paragraph), `Raw`. Mandatory provenance: `path`. PPTX: `Slide`, `Heading`, `Paragraph`, `List`, `Table`, `Image`, `Comment`, `Link`; mandatory `page` (slide number) and `path`; `bbox` when the shape has a position. XLSX/CSV: `Heading`, `Table`, `Comment`, `Paragraph` (for legends); mandatory `path`.

### 2e. Known failure modes to test

1. Tracked changes dropped (Pandoc default `accept`); the fixture asserts both the inserted and deleted text appear with authors.
2. Comments dropped, replies flattened, resolved status lost.
3. Heading levels wrong when the author used direct formatting instead of styles.
4. Numbering restarts (`w:lvlOverride`/`w:startOverride`) producing wrong ordinal numbers; the renderer uses `1.` for all ordered items so only the ordered/unordered distinction matters, but nesting must be right.
5. Vertically merged cells producing duplicated or empty cells.
6. Text boxes skipped (resume sidebars).
7. Hidden text and white text included silently (injection vector) or dropped silently.
8. Legacy `.doc` with embedded OLE objects; expect `Raw` placeholders with warning `ole_object_skipped`.
9. PPTX where the title placeholder is empty and the visible title is a free text box; the title heuristic must pick the top-most, largest-font text.
10. PPTX speaker notes missing or containing the whole lecture.
11. Decks with hidden slides.
12. XLSX with a hidden sheet containing the real data (and `veryHidden` sheets).
13. XLSX saved without cached values (every formula cell `None`).
14. XLSX with 1,048,576 rows claimed by `calculate_dimension()` but only 200 used.
15. Dates stored as serial numbers in `General` format (render the number, not a date, and warn `possible_serial_dates` when a column of 40,000-ish integers has a date-like header).
16. CSV with semicolon delimiter and comma decimal (European); CSV with embedded newlines inside quoted fields; UTF-16 CSV from Excel "Unicode Text" export; a `.csv` that is actually HTML (bank exports); handle by detection order in section 13 and warn `misnamed_file`.
17. ODT/RTF when LibreOffice is absent.

### 2f. Fixtures

1. `office/docx-tracked-changes`: two authors, insertions, deletions, a move, a formatting change, three comments including one reply and one resolved.
2. `office/docx-styles-and-lists`: Title, Subtitle, H1 to H4 by style, one heading by direct formatting, nested mixed lists with a restart, a footnote and an endnote, a hyperlink, an inline image with alt text, a caption.
3. `office/docx-tables-merged`: tables with `gridSpan`, `vMerge`, a nested table, header row flag.
4. `office/docx-textbox-and-hidden`: a resume layout with a sidebar text box, a `w:vanish` run, and white text on white.
5. `office/doc-legacy` and `office/rtf-simple` and `office/odt-basic`: `requires: [libreoffice]` for the DOC case; RTF and ODT also have a no-LibreOffice variant exercising the fallbacks (`meta.yaml` `env: {INTOMD_DISABLE_LIBREOFFICE: "1"}`).
6. `office/pptx-lecture`: 10 slides with a section header, titles, bullets at three levels, a table with a merged cell, a bar chart with two series, a picture with alt text, speaker notes on 4 slides, one hidden slide, a SmartArt list.
7. `office/pptx-no-placeholders`: a deck built from free text boxes only.
8. `office/xlsx-multi-sheet`: three sheets (one hidden), formulas with cached values, a merged header, two data regions on one sheet, a named range, percent and currency formats, a cell comment, an `#REF!` error.
9. `office/xlsx-uncalculated`: generated by openpyxl without values, so every formula cell is `None`.
10. `office/csv-dialects`: four inputs in one case directory (`input.csv` comma UTF-8, `input.semicolon.csv`, `input.utf16.csv`, `input.ragged.csv`) with one expected output each (the harness supports `inputs:` list in `meta.yaml`).
11. `office/numbers-basic` and `office/keynote-basic`: `requires: [iwork]`; generated with the iWork preview fallback variant too.

### 2g. Acceptance thresholds

DOCX: heading_retention 0.95, table_cell_accuracy 0.95, text_similarity 0.98, element_counts within 5 percent, provenance_completeness 1.0; tracked-changes fixture additionally requires 100 percent of `TrackedChange` and `Comment` blocks present with author. PPTX: heading_retention 0.95 (slide titles), text_similarity 0.96, element_counts (slides exact, notes exact), table_cell_accuracy 0.9. XLSX/CSV: table_cell_accuracy 0.99, element_counts (tables exact), provenance 1.0. Fallback variants (no LibreOffice): text_similarity 0.9, other scores not enforced.

### 2h. Options

`options.office`: `engine` (`native` default, `docling`, `pandoc`), `track_changes` (`all` default, `accept`, `reject`), `include_comments` (profile-dependent default), `include_headers_footers` (false), `include_hidden_slides` (true), `include_hidden_sheets` (true), `include_notes` (true), `infer_headings` (true), `keep_hidden` (false), `formulas` (`sidecar` default, `inline`, `table`, `off`), `max_rows` (10000), `max_cols` (256), `sheets` (list of names or indexes), `ocr_images` (false), `render_pages` (false), `libreoffice_timeout_s` (120), `libreoffice_max_bytes` (100 MB), `csv_delimiter`, `csv_encoding`, `csv_header` (`auto`, `yes`, `no`).

### 2i. Phase

Phase 1 for everything except `ocr_images` (Phase 2, needs the OCR pipeline) and iWork (Phase 1 if the Docling extra installs cleanly on CPU in CI, otherwise Phase 2).

---

## 3. documents/google-workspace

### 3a. Scope and input matrix

| URL pattern | Kind | Export endpoint |
|---|---|---|
| `docs.google.com/document/d/<id>/...` | Docs | `https://docs.google.com/document/d/<id>/export?format=docx` (preferred) and `format=md` (secondary, used for comparison in shadow-run only) |
| `docs.google.com/spreadsheets/d/<id>/...` | Sheets | `https://docs.google.com/spreadsheets/d/<id>/export?format=xlsx` (all sheets); `format=csv&gid=<gid>` only as a per-sheet fallback |
| `docs.google.com/presentation/d/<id>/...` | Slides | `https://docs.google.com/presentation/d/<id>/export/pptx` |
| `docs.google.com/drawings/d/<id>/...` | Drawings | `export/svg` then the image path of the OCR pipeline; Phase 2 |
| `drive.google.com/file/d/<id>/...` and `drive.google.com/open?id=` | Drive file | `https://drive.google.com/uc?export=download&id=<id>` then registry by detected type |
| `docs.google.com/forms/...` | Forms | refused with warning `unsupported_source` and advice to export responses to Sheets |

Only links shared as "anyone with the link" work. The converter never prompts for Google credentials. A 401, 403, or an HTML login page in the response produces a stub with warning `private_link` and the message "This Google file is not public. Open it in Google, use File > Download, and convert the downloaded file." Phase 5 may add OAuth for self-host only.

### 3b. Libraries

`httpx` (BSD) for fetch with the SSRF-safe client from Part 1; the office converter (section 2) does the conversion. No Google API client library; no API key required for public exports. Rate: at most 1 request per second per host, 3 retries with backoff on 429 and 5xx.

### 3c. Build steps

1. `can_handle`: 1.0 for the URL patterns above; 0.0 for anything else.
2. Parse the file id with the regex `/d/([a-zA-Z0-9_-]{20,})`; for `open?id=` read the query parameter. Reject ids that fail the regex.
3. Fetch the export URL with `Accept: */*` and the project user agent (section 13). Follow at most 3 redirects within `google.com` and `googleusercontent.com`. If the final `Content-Type` starts with `text/html`, inspect for `accounts.google.com` or `ServiceLogin` and emit the `private_link` stub; for "virus scan warning" pages from `drive.google.com/uc`, parse the confirm form (`confirm=` token) and refetch once.
4. Enforce `options.gworkspace.max_bytes` (default 100 MB) via `Content-Length` and a streaming cap.
5. Hand the bytes to the office converter with the detected type. Sheets export as XLSX so every sheet is converted (the CSV endpoint exports the first sheet only; use it only when `format=xlsx` returns an error, and then iterate `gid` values discovered by scraping `/edit` HTML is not allowed; instead warn `first_sheet_only`).
6. Slides: the PPTX export includes speaker notes; verify in the fixture.
7. Docs: the DOCX export preserves headings by style, comments (as DOCX comments when the sharer allowed commenters), footnotes, and images; tracked changes do not exist in the Docs export (suggestions are not exported), so emit warning `suggestions_not_exported` whenever the source is a Doc, as an informational note.
8. Set `Document.metadata.source` to the canonical URL `https://docs.google.com/<kind>/d/<id>/edit`, `source_type="google-docs"|"google-sheets"|"google-slides"`, and `fetched` timestamp.
9. Cache the export bytes by `(id, Last-Modified)` in the Part 1 content cache for 1 hour so a Doc and its sidecar re-request do not refetch.

### 3d. IR blocks and provenance

Delegated to section 2. The converter adds `Document.metadata.google = {id, kind, export_format}`. Provenance as for the underlying office format.

### 3e. Known failure modes

1. Private link returning an HTML login page that a naive converter treats as the document (the fixture asserts the stub, not a document full of "Sign in" text).
2. Sheets with multiple tabs where only the first is converted.
3. Published-to-web URLs (`/pub`, `/pubhtml`, `/e/2PACX-...`): these ids do not match the `/d/<id>` regex; add a second pattern for `2PACX-` ids and use the `pub?output=docx` and `pub?output=xlsx` forms.
4. Large Sheets exports timing out (Google generates XLSX on request; allow 60 s).
5. Drive `uc` download returning the virus-scan interstitial for files over 100 MB (cap is 100 MB, so refuse and warn `size_cap`).
6. Docs with embedded Drawings exported as PNG only.
7. Slides whose notes are empty on every slide (no warning; notes heading omitted).

### 3f. Fixtures

Network fixtures use recorded HTTP cassettes (`vcrpy`, MIT) stored next to the input as `cassette.yaml`; the harness replays them, so CI needs no network. Inputs are `input.url` files containing the URL.

1. `gworkspace/doc-public`: a public Doc with headings, a table, a footnote, an image, a comment.
2. `gworkspace/sheet-three-tabs`: public Sheet with three tabs, one hidden.
3. `gworkspace/slides-with-notes`: public Slides with notes on two slides.
4. `gworkspace/doc-private`: cassette of the login redirect; expected output is the stub with `private_link`.
5. `gworkspace/doc-published-pacx`: a `/e/2PACX-` published Doc.
6. `gworkspace/drive-file-pdf`: a Drive file link to a small PDF.

### 3g. Acceptance thresholds

Same as the underlying office thresholds. The private case requires exactly one warning `private_link` and zero body blocks other than the stub paragraph.

### 3h. Options

`options.gworkspace`: `max_bytes` (100 MB), `timeout_s` (60), `sheets_format` (`xlsx` default, `csv`), plus pass-through of `options.office`.

### 3i. Phase

Phase 1 (public links only). Drawings: Phase 2. OAuth self-host path: Phase 5.

---

## 4. documents/ebooks-and-text

### 4a. Scope and input matrix

| Input | Extensions / MIME | Engine |
|---|---|---|
| EPUB 2 and 3 | `.epub`, `application/epub+zip` | native (zip + lxml + the HTML converter from section 5's HTML-to-IR module) |
| MOBI, AZW, AZW3, KFX (non-DRM) | `.mobi`, `.azw`, `.azw3`, `.prc` | Calibre `ebook-convert` to EPUB (GPL, shell-out only), then EPUB path |
| FB2, CHM | `.fb2`, `.chm` | FB2 native (XML); CHM via `ebook-convert` |
| LaTeX | `.tex`, `.ltx`, `.bib` alongside | Pandoc shell-out when present (GPL) else pure-Python `intomd_text.latex` |
| Jupyter | `.ipynb` | native JSON walker (no nbconvert dependency; nbconvert is BSD and allowed, but the walker is 200 lines and avoids the Jinja template stack) |
| Markdown | `.md`, `.markdown`, `.mdx`, `.qmd`, `.rmd` | `markdown-it-py` (MIT) parse to tokens, then IR |
| Plain text | `.txt`, `.text`, `text/plain`, no extension | heuristic structurer |
| HTML files | `.html`, `.htm`, `.xhtml`, `.mhtml`, `.mht`, `.webarchive` | section 5's HTML-to-IR module in "file mode" (no boilerplate removal unless `options.text.html_readability=true`) |
| RTF | `.rtf` | section 2 (listed here for routing clarity) |
| reStructuredText, AsciiDoc, Org, Textile, MediaWiki | `.rst`, `.adoc`, `.asciidoc`, `.org`, `.textile`, `.wiki` | Pandoc when present; else `docutils` (public domain/BSD) for RST, and a plain-text fallback with heading heuristics for the rest, warning `markup_partial` |

### 4b. Libraries and fallbacks

1. EPUB: `zipfile` + `lxml` for `META-INF/container.xml`, OPF, NCX/nav; HTML chapters go through the shared HTML-to-IR module. Fallback: Docling EPUB backend.
2. MOBI/AZW: `ebook-convert` located via `CALIBRE_PATH` or PATH (`/Applications/calibre.app/Contents/MacOS/ebook-convert` on macOS). Absent: warn `calibre_missing` and emit a stub explaining how to install Calibre. Never import Calibre's Python. DRM-protected files (`EXTH` record 209 or a `.azw` that fails to convert with a DRM message) produce warning `drm_protected` and a stub; the project never ships or links DRM removal.
3. LaTeX: Pandoc shell-out (`pandoc -f latex -t json`) when `pandoc` is on PATH and `options.text.latex_engine != "builtin"`. Builtin: a regex and state-machine parser handling `\documentclass`, `\title`/`\author`/`\date`, `\section`..`\subparagraph` (starred too), `\begin{abstract}`, `itemize`/`enumerate`/`description`, `verbatim`/`lstlisting`/`minted`, `tabular` (with `\multicolumn` to col_span, `\hline` ignored), `figure` with `\caption` and `\includegraphics`, `equation`/`align`/`gather`/`$$`/`\[` to `Equation`, inline `$...$` kept as inline math, `\cite{}` to `[@key]`, `\ref`/`\label`, `\footnote{}`, `\textbf`/`\emph`/`\texttt`, `\href`/`\url`, `\input`/`\include` resolved relative to the main file (max depth 5, same directory tree only), comments stripped, and unknown macros passed through as text with their arguments and warning `latex_unknown_macro` listing names. `.bib` files next to the main file are parsed with `bibtexparser` (BSD) and attached as a references list (section 12 covers standalone BibTeX).
4. ipynb: stdlib `json`, `nbformat` (BSD) for validation only.
5. Markdown: `markdown-it-py` with `mdit_py_plugins` (MIT) for footnotes, tables, front matter, task lists, math (`$`), and containers (for Obsidian callouts `> [!note]`).
6. Plain text: no library.
7. HTML files: `selectolax` (MIT) or `lxml` through the section 5 module. MHTML: stdlib `email` to unpack parts; `.webarchive`: `plistlib` to extract `WebMainResource`.
8. RST: `docutils` to its doctree, then IR.

### 4c. Build steps

EPUB:

1. Validate `mimetype` entry equals `application/epub+zip` (warn `epub_mimetype_missing` if absent, continue). Parse `container.xml` to find the OPF.
2. From the OPF read `dc:title`, `dc:creator` (with `opf:role`), `dc:language`, `dc:identifier` (ISBN, UUID), `dc:date`, `dc:publisher`, `dc:description` into metadata. Read the `spine` for reading order and the `manifest` for hrefs.
3. Build the TOC from EPUB3 `nav.xhtml` (`epub:type="toc"`) or EPUB2 `toc.ncx`. Produce a map from `href#fragment` to TOC title and depth.
4. For each spine item in order (skip `linear="no"` items but include them at the end under `Heading(level=2, text="Non-linear content")` when `options.text.epub_nonlinear=true`), parse the XHTML with the HTML-to-IR module in file mode. Before the first block of each spine item, if the TOC maps this href to a title, emit `Heading(level=toc_depth)` with that title unless the chapter's first block is already a heading with the same normalized text (avoid duplicate chapter titles). Chapters not in the TOC get no synthetic heading.
5. Images referenced by chapters resolve via the manifest and are written to assets as `images/<original-basename>`; covers (`properties="cover-image"` or `<meta name="cover">`) are emitted once at the top as `Image(role="cover")` only in `full`.
6. Footnotes: EPUB3 `epub:type="noteref"`/`footnote` pairs become `Footnote`; EPUB2 anchor-based notes (links to `#fn1` whose target is a short paragraph at the chapter end) are detected heuristically with the same rule as section 1 step 12.
7. Page-list (`epub:type="page-list"`) maps print page numbers; when present, emit `PageBreak(page=N)` at the anchor positions so print citations work, and set `metadata.has_print_pages=true`.
8. Provenance: `path` = `OEBPS/chapter3.xhtml#id` (spine href plus nearest ancestor id), `page` from the page-list when available.

MOBI/AZW/CHM:

9. Run `ebook-convert <input> <tmp>/out.epub --no-default-epub-cover` under a 300 s timeout. Hand the EPUB to the EPUB path. Record `metadata.converted_via="calibre"` and the Calibre version.

LaTeX:

10. Pick the main file: if a directory is given, the `.tex` containing `\documentclass`; if several, the one with `\begin{document}`, else warn `latex_main_ambiguous` and pick the largest.
11. Pandoc path: parse the JSON AST into IR (Header, Para, BulletList, OrderedList, CodeBlock, Table with cell spans, Math display/inline, Note to Footnote, Cite, Image, Link, Div/Span attributes stored in `metadata`).
12. Builtin path: run the parser from 4b step 3. Set `metadata.latex_engine`.
13. Equations are kept verbatim as LaTeX; never attempt to simplify.

ipynb:

14. Load JSON; validate with `nbformat` (schema violations warn `notebook_invalid` and continue best-effort). Read `metadata.kernelspec.language` to set the code fence language (default `python`).
15. For each cell in order: `markdown` cells go through the Markdown parser (step 20) with attachments (`cell.attachments`) resolved to assets; `code` cells emit `Code(language, text=source, metadata.execution_count)`, followed by outputs when `options.text.notebook_outputs != "off"`: `stream` outputs as `Code(language="text", role="output")`, `execute_result`/`display_data` by MIME preference `text/markdown` > `text/html` (tables through the HTML module, otherwise text) > `image/png`/`image/jpeg`/`image/svg+xml` (decoded from base64 into assets, emitted as `Image(role="output")`) > `text/plain`; `error` outputs as `Code(language="text", role="error")` with the traceback ANSI-stripped. `raw` cells become `Raw`. Output cap: `options.text.notebook_max_output_chars` (default 5,000 per output) with truncation marker and warning `output_truncated`.
16. Cell tags (`metadata.tags`) containing `hide-cell`, `remove-cell` hide the cell only when `options.text.notebook_honor_tags=true` (default false, with the hidden count in a warning so nothing is silent).
17. Provenance: `path` = `cells[12]` and `cells[12].outputs[0]`; `line` for code.

Markdown normalization:

18. Parse front matter (YAML between `---` fences at the top, or TOML `+++`) into `metadata.frontmatter` and keep it verbatim in the sidecar; the output frontmatter merges the Part 1 schema fields on top of the original keys (original keys that collide with schema keys move under `original_frontmatter`).
19. Convert tokens to IR: headings, paragraphs, lists (tight and loose preserved in `List.tight`), fenced code with info string, indented code (language None), tables (GFM), block quotes (`Quote`), footnotes, images, links (reference-style resolved to inline), HTML blocks (`Raw(format="html")`), math blocks (`Equation`), Obsidian wikilinks `[[Note]]` and `![[embed]]` kept as `Link(kind="wikilink")`, task list items with `checked`.
20. Normalization is lossless in text: do not reflow paragraphs, do not change emphasis markers unless `options.text.markdown_style` is set (`atx` headings and `-` bullets are the renderer defaults in Part 1).
21. MDX: strip `import`/`export` lines and JSX blocks into `Raw(format="jsx")` with warning `mdx_components_stripped`.

Plain text structurer:

22. Decode with `charset-normalizer`; normalize line endings. Detect structure in this order: (1) Markdown-ish (`#` headings, `- ` bullets, fenced code) → route to the Markdown parser; (2) Setext/underlined headings (a line followed by `===` or `---` of similar length); (3) ALL-CAPS short lines (under 60 chars, at least 3 words or a trailing colon) surrounded by blank lines → `Heading(level=2)`; (4) numbered outline lines (`1.`, `1.1`, `A.`, `(a)`, `Section 3`) → heading level by depth of numbering when the line is short and followed by body text, else list item; (5) indented blocks of 4 or more spaces or tab → `Code`; (6) lines of `-+|` box drawing or consistent column alignment (3 or more runs of 2+ spaces in 5 consecutive lines) → `Table` via whitespace column splitting with warning `table_inferred`; (7) blank-line separated runs → `Paragraph`, joining hard-wrapped lines (a line under 80 chars followed by a line starting lowercase is a wrap, not a new paragraph). Emit nothing as `Raw`; worst case is one `Paragraph` per blank-line run.
23. If the text looks like a transcript (`^\[?\d{1,2}:\d{2}(:\d{2})?\]?\s` on more than 30 percent of lines, or `^[A-Z][A-Za-z .'-]{1,30}:\s` speaker labels on more than 30 percent), emit `TranscriptSegment(speaker, start, text)` blocks instead, with `timestamp` provenance. This handles pasted Zoom, Otter, YouTube transcripts without the media pipeline.
24. If the text looks like a log file (section 8 rule), hand to the log converter.
25. Provenance: `line` for every block (start line).

HTML files:

26. In file mode, the HTML-to-IR module converts the whole `<body>` with `<nav>`, `<script>`, `<style>`, `<noscript>`, `aria-hidden`, and CSS-hidden elements removed (hidden removal count goes to `removed_hidden_elements`). `<title>` and `<meta>` populate metadata. Readability extraction is off by default for files (the user saved the whole page on purpose) and on for URLs (section 5).
27. MHTML: unpack with `email.message_from_bytes`; the root `text/html` part is converted; `cid:` image references resolve to sibling parts written as assets.

### 4d. IR blocks and provenance

All block types except `Slide`, `TrackedChange`, and `Comment` (Markdown HTML comments `<!-- -->` become `Raw` only in `full`). Mandatory provenance: `path` for EPUB, ipynb, and HTML; `line` for Markdown, plain text, LaTeX, RST. `page` for EPUB only with a page-list.

### 4e. Known failure modes

1. EPUB chapter titles duplicated (TOC heading plus the chapter's own `<h1>`).
2. EPUB2 with no NCX and a spine of 200 tiny files (one per paragraph): treat consecutive spine items without TOC entries as one chapter.
3. EPUB with `linear="no"` endnotes file.
4. DRM-locked MOBI.
5. LaTeX with `\input` chains and custom macros from `\newcommand` (expand single-argument `\newcommand` definitions in the builtin parser; warn on others).
6. `align` environments with `&` alignment markers and `\\` line breaks: keep verbatim inside one `Equation`.
7. ipynb with 50 MB of base64 image outputs: enforce `max_bytes` and output caps; a notebook with no outputs saved.
8. Markdown with mixed CRLF, tabs in code blocks, and reference links defined after use.
9. Plain text that is actually CSV or JSON (detection order in section 13 catches it before this converter).
10. Hard-wrapped email-style text at 72 columns being split into one paragraph per line.
11. HTML file saved from a SPA containing only a `<div id="root">` and scripts: emit a stub with warning `empty_body_js_required` and suggest the URL path.
12. HTML with `<base href>` affecting relative image paths.

### 4f. Fixtures

1. `text/epub3-novel`: three chapters with nav TOC, footnotes, a cover, one `linear="no"` notes file, a page-list.
2. `text/epub2-ncx-fragmented`: NCX-only TOC with 40 spine items.
3. `text/mobi-public-domain`: a public-domain MOBI from Project Gutenberg; `requires: [calibre]`.
4. `text/latex-paper`: main file with two `\input`s, abstract, sections, `align`, a `tabular` with `\multicolumn`, a figure, `\cite` with a `.bib`, custom `\newcommand`; two expected outputs (`expected.pandoc.md` with `requires: [pandoc]`, `expected.md` builtin).
5. `text/ipynb-analysis`: markdown cells with math and an attachment, code cells with stream output, a DataFrame HTML table output, a PNG plot, one error traceback, kernel `python3`.
6. `text/markdown-obsidian`: front matter, wikilinks, embeds, callouts, task lists, footnotes, a GFM table, fenced code with language, an HTML block.
7. `text/plaintext-structured`: underlined headings, ALL-CAPS headings, numbered outline, an indented code block, a whitespace table, hard-wrapped paragraphs.
8. `text/plaintext-transcript`: a pasted Zoom transcript with `[00:12:34] Name:` lines.
9. `text/html-saved-page`: a saved article with nav, hidden spans, `<base>`, relative images; plus `input.mhtml` variant.
10. `text/rst-doc`: headings with adornments, directives (`.. code-block::`, `.. note::`), a grid table.

### 4g. Acceptance thresholds

EPUB: heading_retention 0.95, text_similarity 0.98, element_counts within 5 percent, provenance 1.0. LaTeX builtin: heading_retention 0.95, text_similarity 0.93, equations 0.9 present; Pandoc variant text_similarity 0.97. ipynb: element_counts exact for cells, text_similarity 0.98. Markdown: text_similarity 0.995 (lossless target), element_counts exact. Plain text: heading_retention 0.8, text_similarity 0.97. HTML file: heading_retention 0.9, text_similarity 0.95.

### 4h. Options

`options.text`: `latex_engine` (`auto` default: pandoc if present, `pandoc`, `builtin`), `epub_nonlinear` (true), `epub_cover` (`full` profile only), `notebook_outputs` (`all` default, `text`, `off`), `notebook_max_output_chars` (5000), `notebook_honor_tags` (false), `markdown_style` (`preserve` default, `normalize`), `plaintext_structure` (`auto` default, `off`), `html_readability` (false for files), `calibre_timeout_s` (300).

### 4i. Phase

Phase 1 for EPUB, LaTeX, ipynb, Markdown, plain text, HTML files, RST. MOBI/CHM via Calibre: Phase 1 as an optional-tool path (the fixture is skipped when Calibre is absent). AsciiDoc/Org/Textile without Pandoc: Phase 5 or community contribution; with Pandoc: Phase 1.

---

## 5. web/pages

### 5a. Scope and input matrix

| Input | Route |
|---|---|
| `http(s)://` URL whose response is `text/html` or `application/xhtml+xml` | this converter |
| URL whose response is `application/pdf` or any non-HTML type | fetched here, handed to the registry by detected type (PDF to section 1, images to the OCR pipeline, etc.) |
| URL matching a social/forum pattern (section 7), a Google Workspace pattern (section 3), a repo or PR pattern (section 8), a feed (section 7), arXiv/PubMed/EDGAR (section 12) | those converters win on `can_handle` (0.9+) over this one (0.7) |
| Raw HTML string passed via API (`input.kind == "html"`) with an optional `base_url` | HTML-to-IR module in page mode |
| `view-source:`, `file://` | refused on the public instance; `file://` allowed in CLI and self-host (routes to section 4) |

### 5b. Libraries and fallback chain

1. Fetch: `httpx` (BSD) with HTTP/2, the SSRF guard from Part 1 (resolve DNS once, reject private, loopback, link-local, and metadata ranges, pin the resolved IP for the connection, re-check on every redirect), gzip/brotli (`brotli` MIT), max 5 redirects, 30 s total budget by default.
2. Extraction primary: Trafilatura (Apache-2.0, 1.8+) with `output_format="xml"` so structure is retained (`<head>`, `<p>`, `<list>`, `<item>`, `<quote>`, `<code>`, `<table>`, `<graphic>`), `include_tables=True`, `include_images=True`, `include_links=True`, `include_formatting=True`, `include_comments=False` by default, `favor_precision=False`, `deduplicate=True`. Convert the TEI-like XML to IR.
3. Extraction fallback 1: `readability-lxml` (Apache-2.0) when Trafilatura returns under 200 characters or under 25 percent of the visible text length (measured on the cleaned DOM). Fallback 2: Defuddle is a JavaScript library (MIT); do not depend on Node in the Python core. Instead port its two most valuable behaviors into the HTML-to-IR module: MathJax/KaTeX element to LaTeX recovery (read `annotation[encoding="application/x-tex"]`, `data-latex`, `alt` on MathJax images, or the `script[type="math/tex"]` source) and footnote normalization (links with `rel="footnote"`, `role="doc-noteref"`, or `href="#fn"` patterns to `Footnote`). When `intomd[node]` is installed and `options.web.engine == "defuddle"`, shell out to `defuddle` CLI for shadow-run comparison only.
4. Fallback 3: whole-`<body>` conversion through the HTML-to-IR module with boilerplate tags removed (`nav`, `header`, `footer`, `aside`, `form`, `[role=navigation]`, `[role=banner]`, `[role=contentinfo]`, cookie banners by class pattern), warning `readability_fallback_full_body`.
5. JS rendering: Crawl4AI (Apache-2.0, uses Playwright, Apache-2.0; browsers downloaded separately) under the `intomd[browser]` extra. Triggered when `options.web.render == "always"`, or when `render == "auto"` and the static fetch yields a page whose cleaned text is under 300 characters while the raw HTML contains `<script>` tags totaling over 50 KB or a root element matching `#root, #app, #__next, #___gatsby, [data-reactroot]`. Time budget `options.web.render_timeout_s` (default 20 s, hard max 60 s), `wait_until="networkidle"` with a 5 s idle cap, scroll to bottom once for lazy content, block `image`, `media`, `font` resource types unless images are requested, no persistent profile on the public instance. The rendered DOM then goes through step 2 onward.
6. Metadata: Trafilatura's `extract_metadata` for title, author, date, sitename, categories, tags; plus a direct pass over `<meta property="og:*">`, `<meta name="twitter:*">`, `<meta name="citation_*">` (Highwire tags on academic pages), `<link rel="canonical">`, `<html lang>`, JSON-LD `Article`/`NewsArticle`/`BlogPosting` (`headline`, `author`, `datePublished`, `dateModified`), `<time datetime>`. Precedence: JSON-LD > citation_* > og/twitter > Trafilatura > `<title>`. Language: `<html lang>` first, then `lingua-py` (Apache-2.0) on the extracted text (section 13).

### 5c. Build steps

1. `can_handle`: 0.7 for any `http(s)` URL (lower than specialized URL converters), 0.9 for `input.kind == "html"`.
2. Policy checks before fetch: scheme is `http` or `https`; host passes the SSRF guard; the host is not on the instance deny list (`INTOMD_BLOCKED_HOSTS`); robots.txt (step 3).
3. robots.txt policy: fetch `/robots.txt` once per host per hour (cached), parse with `protego` (BSD). Default `options.web.robots = "respect"` on the public instance (configured by the operator, Part 4) and `"ignore"` for the local CLI, because a user fetching one page they can open in a browser is not a crawler. When respecting and the path is disallowed for the project user agent or `*`, emit a stub with warning `robots_disallowed` and the matched rule. The site crawler (section 6) always respects robots.txt regardless of mode unless the operator sets `INTOMD_CRAWL_IGNORE_ROBOTS=1` for self-host.
4. User agent policy: `intomd/<version> (+https://<project-url>/bot; convert-to-markdown)` by default. `options.web.user_agent = "browser"` sends a current desktop Chrome UA string for self-host only; the public instance locks the honest UA. Send `Accept-Language` from `language_hint` when set.
5. Fetch with streaming; abort when `Content-Length` or bytes read exceed `options.web.max_bytes` (default 10 MB HTML on public, 50 MB self-host). Record final URL, status, headers (`Content-Type`, `Last-Modified`, `ETag`), and timing into metadata. 4xx/5xx produce a stub with warning `http_error` and the status; 429 retries once after `Retry-After` up to 10 s.
6. Non-HTML content: detect by `Content-Type` and Magika on the first 64 KB; hand bytes to the registry with the URL as `source`. PDFs linked from pages are therefore handled by section 1 without special code; the only web-specific addition is that `Document.metadata.source` is the URL and `fetched` is set.
7. Decode: honor the `Content-Type` charset, then `<meta charset>`, then `charset-normalizer`.
8. Pre-clean the DOM (this is the prompt-injection hygiene pass from the research and it runs before any extractor): remove `<script>`, `<style>`, `<noscript>`, `<template>`, `<iframe>` (keep `src` as a `Link` when it points to a video platform), elements with `hidden`, `aria-hidden="true"`, inline `display:none`/`visibility:hidden`/`font-size:0`/`opacity:0`, off-screen positioning (`left:-9999px`), and `<div>`s whose class or id matches a hidden-pattern list. Count removals into `removed_hidden_elements`. Strip zero-width and bidi-control code points from text nodes and count into `removed_invisible_chars`. The text of removed hidden elements is kept in the sidecar under `hidden_text` (capped at 10 KB) so nothing is silently gone and the injection scanner (Part 1) can score it.
9. Paywall and consent-wall detection: before extraction, test for (a) JSON-LD `isAccessibleForFree: false` or `hasPart` with `isAccessibleForFree: false`, (b) known paywall container selectors and classes (`.paywall`, `#piano-*`, `.tp-modal`, `.meteredContent`, `[data-paywall]`), (c) a body text under 400 characters that contains subscribe, sign in, or "continue reading" phrasing in the detected language, (d) HTTP 402 or 451. When any trigger fires and the extracted article body is shorter than 40 percent of the page's `og:description`-implied length or under 600 characters, emit the extracted preview plus warning `paywall_detected` with the message "This page appears to be paywalled; only the free preview was captured." Never attempt bypass (no AMP, no cache, no archive.org by default; `options.web.archive_fallback=true` on self-host may try `web.archive.org/web/2id_/<url>` and marks the source accordingly). Consent walls (GDPR cookie interstitials) are handled by the JS renderer clicking common accept buttons only when `options.web.consent_click=true` (self-host default true, public default false).
10. Run the extractor chain (5b steps 2 to 4). Convert the result to IR with the HTML-to-IR module: `h1`..`h6` to `Heading` (levels normalized so the article title is H1 and the first in-body heading level is shifted to H2 if the page uses H1 for every section), `p` to `Paragraph`, `ul`/`ol` (nested) to `List`, `pre`/`code` to `Code` with language from `class="language-x"`, `data-lang`, or highlight.js classes, `blockquote` to `Quote`, `table` to `Table` with `rowspan`/`colspan` to spans and `thead`/`th` to header rows (also handle header-less tables and `caption`), `img` to `Image(alt, src absolute, title)` and `figure`/`figcaption` to `Figure(caption)`, `picture`/`srcset` resolved to the largest candidate, `a` to inline `Link` with absolute `href` (relative resolved against `<base>` or the final URL; `javascript:` and `mailto:` kept as text and link respectively), `hr` to a `Raw("---")`, `dl` to a two-column `Table`, `details`/`summary` to a `Heading(level+1)` plus body, `math`/MathJax/KaTeX to `Equation`, `sup` footnote refs to `Footnote` links, `del`/`ins` to emphasis-style spans (not `TrackedChange`).
11. Link preservation: inline links stay inline in `full` and `agent`; in `compact`, the renderer converts them to a numbered reference list at the end (Part 1 rule). The converter also emits `Document.metadata.links` as a deduplicated list of `{text, href, rel}` for all in-body links, and `outbound_pdfs` for links ending in `.pdf` so the user can request those as follow-ups (not fetched automatically).
12. Images: by default do not download (public instance never does). `options.web.images = "reference"` (default) keeps absolute URLs and alt text; `"download"` (self-host) fetches up to `max_images` (20) under 5 MB each into assets and may run the OCR pipeline captioner in Phase 2. Images with empty alt and no caption get `alt="image"` and are counted in warning `images_without_alt`.
13. Comments sections: excluded by default. `options.web.include_comments=true` sets Trafilatura `include_comments=True` and appends the result under `Heading(level=2, text="Comments")` with each comment as a `Quote`. The structured comment tree for forums is section 7.
14. Metadata assembly (5b step 6): `title`, `author`, `published`, `modified`, `canonical`, `language`, `sitename`, `description`, `tags`. `source` is the canonical URL when it is same-origin with the fetched URL; otherwise the fetched URL with `metadata.canonical` recorded separately (cross-origin canonicals are a hijack vector). Compute `metadata.readability_ratio` = extracted chars / cleaned body chars for the sidecar.
15. Provenance: every block gets `path` as a CSS-ish locator (`body > main > article > p:nth-of-type(7)`), computed from the extractor's retained element when available (Trafilatura XML carries no DOM path, so for the primary path locate the block by text matching back into the cleaned DOM; where the match fails, `path` is `article#<block index>`). `line` is not used.
16. Post-check: if the result has zero `Paragraph` blocks and the page had visible text, run fallback 3; if still empty, emit the stub with warning `extraction_empty`.

### 5d. IR blocks and provenance

`Heading`, `Paragraph`, `List`, `Code`, `Quote`, `Table` (spans), `Image`, `Figure`, `Footnote`, `Equation`, `Link`, `Raw`. Mandatory provenance: `path`.

### 5e. Known failure modes

1. Very short articles where Trafilatura returns nothing and Readability wins (the 0.57 vs 0.80 F1 case): the fallback threshold must trigger.
2. `<figcaption>` dropped by Trafilatura: the HTML-to-IR module runs a figure pass on the cleaned DOM independently and merges captions by image `src`.
3. Code blocks losing language or being split by line-number spans (`<span class="ln">`): strip line-number tables (`table.highlighttable`, `.linenos`) before extraction.
4. Multi-page articles (`rel="next"`, "Page 2 of 5"): not auto-followed; record `metadata.next_page` and warn `multipage_article`.
5. Paywalled page returning a teaser that looks complete.
6. Cookie wall returning only the consent text.
7. SPA shells with no content without JS.
8. Infinite scroll pages where the renderer captures only the first screen (one scroll pass; warn `lazy_content_possible` when the page height grows after scrolling).
9. Relative links and `srcset` on CDN domains.
10. Pages where every section uses `<h1>` (level normalization).
11. `<table>` used for layout (one row, one column, nested): unwrap tables that have no `th`, a single column, or nested block content in every cell.
12. Cross-origin canonical URLs.
13. Prompt-injection text in hidden elements; the fixture asserts the text is absent from the body and present in sidecar `hidden_text` with an injection flag.
14. Redirect to a PDF.
15. Large pages over the byte cap (truncate at the cap on a tag boundary and warn `size_cap`).
16. Non-UTF-8 legacy pages (Shift_JIS, Windows-1251).
17. AMP pages and `amp-img` elements (map `amp-img` to `img`).

### 5f. Fixtures

HTML fixtures are stored as `input.html` with `meta.yaml: {url: "https://example.test/..."}` so the harness runs the converter in page mode with a fake final URL and no network; render-dependent cases use a recorded `rendered.html` with `requires: [browser]`.

1. `web/article-standard`: a blog post with og and JSON-LD metadata, headings, lists, a code block with language, a figure with caption, inline links, a comments section (excluded), a nav and footer.
2. `web/article-short`: a 120-word post where Trafilatura under-extracts.
3. `web/docs-page-mathjax`: documentation page with MathJax equations, footnotes, a table with colspan, a `details` block.
4. `web/paywall-teaser`: JSON-LD `isAccessibleForFree: false`, a 300-character teaser, a subscribe wall.
5. `web/spa-shell`: static HTML with `<div id="root">` and bundles; `rendered.html` contains the content. Two expected outputs: static (stub with `empty_body_js_required`) and rendered.
6. `web/hidden-injection`: an article with a `display:none` div containing "ignore previous instructions", zero-width characters inside words, and an `aria-hidden` span.
7. `web/legacy-encoding`: a Windows-1251 page with a wrong charset header.
8. `web/layout-tables`: a 2005-era page built from nested layout tables with one real data table inside.
9. `web/multipage`: page 1 of 3 with `rel="next"`.
10. `web/link-to-pdf`: cassette where the URL 302s to a PDF; expected output is the PDF conversion with `source` set to the URL.

### 5g. Acceptance thresholds

heading_retention 0.9, text_similarity 0.95 against the hand-cleaned article body, element_counts within 10 percent (code blocks and tables exact), table_cell_accuracy 0.9, provenance 1.0. Boilerplate leakage measured as `extra_text_ratio` (characters in output not in expected) must be under 0.05. Paywall and SPA cases assert warnings exactly.

### 5h. Options

`options.web`: `engine` (`trafilatura` default, `readability`, `full_body`, `defuddle` when installed), `render` (`auto` default, `always`, `never`), `render_timeout_s` (20), `robots` (`respect` on public, `ignore` on CLI), `user_agent` (`intomd` default, `browser` self-host), `max_bytes`, `timeout_s` (30), `include_comments` (false), `include_links` (true), `images` (`reference` default, `download`, `skip`), `max_images` (20), `archive_fallback` (false), `consent_click` (self-host true), `headers` (dict, self-host only, for cookies the user supplies), `language`.

### 5i. Phase

Phase 1: static fetch, extraction chain, metadata, hygiene, paywall detection, PDF hand-off, robots and UA policy. Phase 3: Crawl4AI rendering, consent click, archive fallback, user-supplied cookies. Image download and captioning: Phase 2 with the OCR pipeline.

---

## 6. web/sites

### 6a. Scope and input matrix

| Input | Route |
|---|---|
| A URL with `options.site.crawl=true` or the CLI `intomd crawl <url>` | crawler |
| A sitemap URL (`/sitemap.xml`, `sitemap_index.xml`, `.xml` responding with `<urlset>` or `<sitemapindex>`) | sitemap-driven corpus |
| A documentation site root (detected by generator, 6c step 4) | docs special-casing |
| `<site>/llms.txt` or `llms-full.txt` present | preferred source |

### 6b. Libraries

`httpx` for static crawling with the section 5 page converter per page; Crawl4AI `AsyncWebCrawler` with `BFSDeepCrawlStrategy` under `intomd[browser]` for JS sites; `protego` for robots; `usp` is not used (write a 60-line sitemap parser with lxml, including gzip sitemaps); `simhash` implemented inline (64-bit over shingled tokens) for near-duplicate detection.

### 6c. Build steps

1. Normalize the start URL: strip fragments, utm parameters, trailing `index.html`. Determine the scope origin (scheme plus host, with `www.` and bare host treated as the same origin) and the path prefix when `options.site.scope == "prefix"` (default: `origin` for a root URL, `prefix` when the start URL has a path of depth 1 or more, e.g. `/docs/`).
2. llms.txt preference: fetch `<origin>/llms.txt` and `<origin>/llms-full.txt`. If `llms-full.txt` exists and is under `options.site.max_bytes_total`, convert it as Markdown (section 4) and return it as the corpus with `metadata.source_kind="llms-full"`, skipping the crawl unless `options.site.prefer_llms_txt=false`. If only `llms.txt` exists, parse its link list (Markdown links under `##` sections per the llms.txt spec) and use those links as the seed set instead of crawling, with `metadata.source_kind="llms-txt-seeded"`. Record which was used in a warning-level info `llms_txt_used`.
3. Sitemap discovery: robots.txt `Sitemap:` lines, then `/sitemap.xml`, `/sitemap_index.xml`, `/sitemap-index.xml`. Parse recursively (index to child sitemaps, gzip supported), collect `<loc>` plus `<lastmod>`, filter to scope, cap at `options.site.max_pages`. When a sitemap exists, use it as the seed set and still follow in-page links only if `options.site.follow_links=true` (default true for docs sites, false for sitemap-seeded general sites).
4. Documentation generator detection on the start page: Docusaurus (`meta[name="generator"][content^="Docusaurus"]`, `#__docusaurus`), MkDocs (`meta[name="generator"][content^="mkdocs"]`, `.md-content`), Material for MkDocs (`.md-nav`), GitBook (`gitbook` in generator or `.gitbook-root`), ReadTheDocs (`readthedocs.org` assets, `.rst-content`, `#rtd-sidebar`), Mintlify (`mintlify` in asset URLs or `#content-area`), Sphinx (`.sphinxsidebar`, `.body[role=main]`), VitePress (`.VPDoc`), Nextra (`nextra` asset path), Starlight (`.sl-markdown-content`). For each, use the known main-content selector instead of Readability (main content extraction is deterministic on these generators) and the known sidebar nav selector to read the ordered page list and section nesting, which becomes the corpus TOC order. Also try the generator's raw source conventions: Docusaurus and MkDocs often serve `.md` at the same path (`/docs/intro.md` or `index.md`); Mintlify serves `/<path>.md`; ReadTheDocs serves `/_sources/<path>.rst.txt`. When a raw source is available and `options.site.prefer_source=true` (default), fetch it and convert via section 4 (Markdown or RST), with `metadata.source_kind="raw-source"` per page; fall back to HTML extraction on 404.
5. Crawl loop (static mode): BFS from seeds, same scope only, `max_depth` (default 3), `max_pages` (default 200 CLI, 50 public), `max_bytes_total` (default 100 MB), concurrency 4 per host, delay `crawl_delay` from robots or 0.5 s, honor `Retry-After`. Only follow `<a href>` within `<main>`, `<nav>`, `<article>`, sidebar nav, and pagination links; never follow `nofollow` links, query-string variants that differ only by sort or page params unless `?page=` pagination of a listing is explicitly allowed (`options.site.follow_pagination`), logout or action URLs (`/logout`, `?action=`, `/cart`), or binary assets other than PDFs when `options.site.include_pdfs=true` (default true, counted against `max_pages`).
6. URL dedup: canonical URL from the page's `<link rel="canonical">` (same origin only) collapses variants; URL normalization lowercases scheme and host, removes default ports, sorts query parameters, removes tracking parameters. Content dedup: simhash of extracted text; pages within Hamming distance 3 of an already-kept page are dropped with the kept page's URL recorded under `metadata.duplicates`.
7. JS mode (`render="auto"` per page as in section 5, or `options.site.render="always"`): use Crawl4AI's deep crawl with the same scope filter and caps, `stream=True` so pages are converted as they arrive.
8. Per-page conversion: call the section 5 converter with `metadata.crawl = {depth, parent_url, discovered_via}`. Strip the site-wide repeated blocks: compute the set of block text hashes that appear on more than 60 percent of pages (nav, footer, "edit this page" links) and remove them from each page with one corpus-level warning `boilerplate_removed_corpus` carrying the count.
9. Output assembly: `options.site.output = "combined"` (default) produces one `Document` with an H1 of the site title, a generated TOC (Part 1 renderer) in the nav order from step 4 or BFS order otherwise, and each page as a section whose heading level is 2 plus its nav depth (page headings are shifted down accordingly, clamped at 6, with warning `heading_depth_clamped` when clamping occurs). Each page section starts with `<!-- source: <url> -->` via a `Raw` block and carries `metadata.url`. `"separate"` produces one `Document` per page in a `DocumentSet` (Part 1) with filenames derived from the URL path, plus an `index.md` with the TOC and links. `"both"` does both.
10. Corpus metadata: `pages_fetched`, `pages_skipped` with reasons (`robots`, `scope`, `dedup`, `error`, `cap`), `total_tokens`, `crawl_duration_s`, `generator`, `source_kind`, and a `crawl_log` array in the sidecar with one entry per URL.
11. Resume: persist the frontier and visited set to the Part 1 job store every 25 pages so a crashed crawl resumes with `intomd crawl --resume <job-id>`.

### 6d. IR blocks and provenance

As section 5 per page. Each block additionally carries `provenance.source_id = <page url>` so combined output stays traceable. `Raw` for source markers. Mandatory: `path` and `source_id`.

### 6e. Known failure modes

1. Crawling off-origin via a CDN subdomain (`cdn.example.com`) or a docs subdomain (`docs.example.com` when started at `example.com`): subdomains are out of scope unless `options.site.include_subdomains=true`.
2. Infinite URL spaces (calendars, faceted search, `?page=N` to infinity): the query-parameter rules plus `max_pages` plus a per-path-pattern cap (no more than 50 URLs sharing a path template where numbers are replaced by `N`).
3. Sitemaps listing 200,000 URLs; cap and warn `sitemap_truncated`.
4. Sitemap `lastmod` missing; fine, just no incremental logic.
5. Versioned docs (`/docs/1.x/`, `/docs/2.x/`, `/en/latest/`, `/en/stable/`): detect version segments and crawl only the version of the start URL or the one marked latest, warning `versions_skipped` with the list.
6. Localized duplicates (`/en/`, `/fr/`): crawl only the start URL's locale unless `include_locales` is set.
7. Docs sites where the nav is rendered client-side (Mintlify, some Docusaurus): fall back to sitemap order, then BFS.
8. Session or tracking parameters producing infinite variants.
9. A combined document exceeding 16 MB or the renderer's size cap: switch to `separate` automatically and warn `combined_too_large`.
10. Heading depth overflow in combined mode.
11. `llms-full.txt` that is stale relative to the site (compare the count of H1 sections with sitemap size; warn `llms_txt_may_be_stale` when the sitemap has more than 2x the pages).

### 6f. Fixtures

Site fixtures are directories of cassettes (`site/`) served by the harness's local static server on a random port; `meta.yaml` sets `url: http://localhost:{port}/`.

1. `sites/mkdocs-material`: a 12-page Material for MkDocs build with nav nesting, a versioned sibling (`/1.0/`) that must be skipped, raw `.md` sources available.
2. `sites/docusaurus`: a Docusaurus build with `/docs/` prefix, client-side nav, sitemap.xml, two locales.
3. `sites/llms-full`: a site that serves `llms-full.txt`; the crawl must not run.
4. `sites/llms-txt-seeded`: a site with `llms.txt` listing 5 of 20 pages.
5. `sites/blog-with-pagination`: a listing with `?page=` pagination and tag pages (faceted explosion), 30 posts, duplicate `www` and non-`www` links.
6. `sites/sitemap-index-gz`: a sitemap index pointing to two gzipped sitemaps and a PDF.
7. `sites/readthedocs-sphinx`: with `_sources/*.rst.txt`.

### 6g. Acceptance thresholds

Per-page scores as section 5. Corpus-level: `pages_fetched` exact, `pages_skipped` reasons exact, nav order exact for docs cases, dedup count exact, TOC headings exact. Wall-clock budget in `meta.yaml` (local server, so tight).

### 6h. Options

`options.site`: `crawl` (false), `scope` (`auto`, `origin`, `prefix`, `domain`), `include_subdomains` (false), `include_locales` (list), `max_depth` (3), `max_pages` (200 CLI, 50 public), `max_bytes_total` (100 MB), `concurrency` (4), `delay_s` (0.5), `follow_links` (auto), `follow_pagination` (false), `include_pdfs` (true), `prefer_llms_txt` (true), `prefer_source` (true), `render` (`auto`), `output` (`combined`, `separate`, `both`), `dedup` (true), `resume` (job id), `url_include` and `url_exclude` (regex lists).

### 6i. Phase

Phase 1: sitemap parsing, llms.txt preference, static BFS crawl with caps, docs-generator detection and raw-source fetching, combined and separate output. Phase 3: Crawl4AI deep crawl for JS sites and client-side nav. Public instance crawl caps: Phase 4 configuration.

---

## 7. web/social-and-forums

### 7a. Scope and input matrix

| Source | URL patterns | Access tier | Method |
|---|---|---|---|
| Reddit | `reddit.com/r/<sub>/comments/<id>/...`, `redd.it/<id>`, `reddit.com/r/<sub>` (listing), `old.reddit.com`, `/user/<name>` | sanctioned | append `.json` with `raw_json=1&limit=500`; `morechildren` API for collapsed comments |
| Hacker News | `news.ycombinator.com/item?id=<id>`, `/user?id=` | sanctioned | Algolia `hn.algolia.com/api/v1/items/<id>` (full nested tree in one call) |
| Stack Exchange | `stackoverflow.com/questions/<id>/...`, `*.stackexchange.com/questions/<id>`, `/a/<id>`, `/q/<id>` | sanctioned API, key optional | API 2.3 `questions/{id}?site=&filter=withbody` plus `questions/{id}/answers` and `/comments`; without a key the quota is 300/day per IP, so cache aggressively and fall back to HTML extraction (section 5 with Stack Exchange's `#question`, `.answer` selectors) when 400 `throttle_violation` |
| Wikipedia and MediaWiki | `*.wikipedia.org/wiki/<title>`, any site exposing `/w/api.php` | sanctioned | REST `/api/rest_v1/page/html/<title>` (Parsoid HTML with data-mw) for body; `action=parse&prop=wikitext` for infobox templates; `mwparserfromhell` (MIT) for template parsing |
| X/Twitter | `x.com/<user>/status/<id>`, `twitter.com/...` | tier 2, ToS-risky | fxtwitter API (`api.fxtwitter.com/<user>/status/<id>`) first; syndication endpoint (`cdn.syndication.twimg.com/tweet-result?id=`) second; both are unofficial; self-host only by default; the public instance returns a stub unless the operator enables it |
| Bluesky | `bsky.app/profile/<handle>/post/<rkey>`, `at://` URIs | sanctioned | `public.api.bsky.app/xrpc/app.bsky.feed.getPostThread?uri=at://<did>/app.bsky.feed.post/<rkey>&depth=100`; handle to DID via `com.atproto.identity.resolveHandle` |
| Mastodon and Fediverse | `https://<instance>/@<user>/<id>`, `/users/<user>/statuses/<id>` | sanctioned | `GET /api/v1/statuses/<id>` and `/context` (ancestors and descendants); instance detected by `/.well-known/nodeinfo` (also covers Misskey, Pleroma, Akkoma with their endpoints) |
| Threads | `threads.net/@<user>/post/<id>` | tier 2 | HTML extraction of the embedded JSON (`data-sjs` scripts) best-effort; flagged `experimental`; self-host only |
| LinkedIn posts | `linkedin.com/posts/...`, `/pulse/...` | tier 2, high risk | best-effort section 5 extraction of the public (logged-out) page with `og:` metadata; warning `tos_risk_source`; self-host only |
| Substack | `<name>.substack.com/p/<slug>`, custom domains detected by `substack` in assets | sanctioned (public posts) | `GET <post-url>?format=json` is unofficial but stable; primary is section 5 extraction; JSON used for metadata (`title`, `subtitle`, `post_date`, `audience`, `body_html`) and for `audience != "everyone"` paywall detection |
| Medium | `medium.com/@<user>/<slug>`, custom domains with `medium.com` assets | sanctioned | section 5 extraction; `?format=json` endpoint (strip the `])}while(1);</x>` prefix) for metadata and paywall (`isLocked`) |
| RSS/Atom/JSON Feed | any URL whose content type is `application/rss+xml`, `application/atom+xml`, `application/feed+json`, or whose body root is `<rss>`, `<feed>`, or JSON with `version: https://jsonfeed.org` | sanctioned | `feedparser` (BSD) |
| Generic forum | phpBB, Discourse, XenForo, vBulletin, Lemmy, Flarum | sanctioned for public pages | Discourse: `<topic-url>.json` (official); Lemmy: `/api/v3/post?id=` and `/api/v3/comment/list`; others: section 5 with per-engine post selectors and author/date extraction |

### 7b. Libraries

`httpx`; `feedparser` (BSD-2); `mwparserfromhell` (MIT); `atproto` client is not needed (plain HTTP to the public AppView); no `praw` (it requires OAuth app credentials; the `.json` endpoint does not). All responses are untrusted data: run the injection scanner on every post body.

### 7c. Build steps

Shared thread model:

1. Define `ThreadNode = {id, author, author_id, created, score, depth, parent_id, body_blocks, permalink, edited, flags: [op, mod, deleted, removed, collapsed]}` in `intomd_social.model`. Every source adapter produces a root post plus a tree of `ThreadNode`s.
2. Shared renderer to IR: the root post becomes `Heading(level=1, text=title)` plus metadata, then the body blocks (post text parsed from Markdown for Reddit, from HTML for HN and Mastodon and Bluesky facets, via the HTML-to-IR module). Then `Heading(level=2, text="Comments (N)")`. Each comment becomes a `Comment` block with `metadata.depth`, `score`, `author`, `created`, `parent_id`, and `body` as nested blocks. The Markdown renderer (Part 1) renders a comment as a blockquote nested by depth (one `>` per depth level, capped at `options.social.max_depth`, default 8, deeper replies flattened to the cap with `(reply to <author>)` prefix) with a header line `**author** · score · timestamp` and the body below. `compact` profile sorts by score and truncates to `max_comments` (default 200 full, 50 compact) with warning `comments_truncated` and the count omitted.
3. Deleted or removed comments (`[deleted]`, `[removed]`, Mastodon tombstones) are kept as placeholders so the tree shape is preserved, flagged `deleted`.
4. Provenance: `source_id` = post or comment id, `timestamp` = created epoch seconds, `path` = `comments/<id>`.

Reddit:

5. Normalize the URL to `https://www.reddit.com<path>.json` with `raw_json=1` (avoids HTML entity escaping) and `limit=500`, `sort=` from `options.social.sort` (default `confidence`, i.e. "best"). Send the honest user agent; Reddit requires a descriptive UA. Rate limit 1 request per 2 seconds per instance; honor `Retry-After` and `x-ratelimit-remaining`.
6. Parse the two-element listing: `[0]` is the link (`title`, `selftext` Markdown, `url`, `author`, `created_utc`, `score`, `upvote_ratio`, `num_comments`, `link_flair_text`, `is_self`, `over_18`, `media`, `gallery_data`), `[1]` is the comment forest. Walk `replies` recursively. `kind == "more"` nodes list hidden child ids: fetch them via `api/morechildren?link_id=t3_<id>&children=<csv>&api_type=json` in batches of 100 while under `max_comments`; otherwise warn `comments_collapsed` with the count.
7. Self-text and comment bodies are Reddit-flavored Markdown; parse with the Markdown parser (section 4) after converting Reddit specifics: `>!spoiler!<` to `(spoiler) text`, `^(superscript)`, `r/`, `u/` links to absolute links. `body_html` is not needed.
8. Link posts: emit the URL as a `Link` under the title and, when `options.social.fetch_linked=true`, convert the linked page through the registry as a child document with `max_bytes` enforced. Gallery and image posts emit `Image` blocks; video posts emit a `Link` to the media and are a job for the media pipeline (Phase 2, `options.social.fetch_media`).
9. Subreddit and user listings: emit a `Table` (`Title`, `Score`, `Comments`, `Posted`, `URL`) of up to `max_posts` (100) entries; comments are not fetched for listings unless `expand_threads=true` (counts against the rate limit, so default false).
10. Crossposts: follow `crosspost_parent_list[0]` for the body with `metadata.crosspost_of`.

Hacker News:

11. Extract the id; call Algolia `items/<id>`. The response is the full tree with `children`, `author`, `created_at`, `points` (null on comments), `text` (HTML), `title`, `url`, `type`. HN has no comment scores; omit score. Map `type == "comment"` to nodes, `story`/`ask`/`job`/`poll` to the root (poll options appended as a `Table`). `[dead]`/`[flagged]` appear as `text: null` with no author; keep placeholders. Convert `text` HTML via the HTML-to-IR module (HN HTML is `<p>`, `<i>`, `<a>`, `<pre><code>` only). Story URL handled as Reddit step 8.
12. For user pages, use the Firebase `user/<id>.json` for `about` and `karma` and Algolia `search_by_date?tags=comment,author_<id>` for the last 100 comments as a `Table`.

Stack Exchange:

13. Map host to the API `site` parameter (`stackoverflow`, `superuser`, `<name>.stackexchange` → `<name>`). Call `questions/{id}?site=X&filter=!nNPvSNdWme` (a saved filter including `body_markdown`, `comments`, `answers.body_markdown`, `answers.comments`, `accepted_answer_id`, `tags`, `score`, `view_count`, `last_edit_date`, `owner.display_name`). Pass `key` from `INTOMD_STACKEXCHANGE_KEY` when set (raises quota to 10,000/day); handle `backoff` field by sleeping.
14. Render: H1 title; tags as `metadata.tags`; the question body from `body_markdown`; question comments as `Comment` blocks; then `Heading(level=2, text="Answers (N)")`; each answer as `Heading(level=3, text="Answer by <name> · score N · accepted")` (accepted first, then by score) with its body and comments. Code blocks survive because `body_markdown` is Markdown; fence language is inferred from the tags (`python` tag → `python` fence) when the fence has none.
15. Fallback on throttle or API outage: section 5 extraction with the selectors `#question .s-prose`, `.answer .s-prose`, `.comment-copy`, authors from `.user-details a`, with warning `api_fallback_html`.

Wikipedia and MediaWiki:

16. Resolve the article title (URL-decode, underscores to spaces). Fetch Parsoid HTML (`/api/rest_v1/page/html/<title>` on Wikimedia; `/w/rest.php/v1/page/<title>/html` or `action=parse&prop=text` elsewhere). Set `redirect=true` and record `metadata.redirected_from`.
17. Pre-clean Wikipedia-specific chrome: `.mw-editsection`, `.reference` superscripts converted to `Footnote` links keyed to `#cite_note-N` targets, `.navbox`, `.sidebar`, `.hatnote` (kept as a `Quote` with `role="hatnote"` in `full`, dropped in `compact`), `.mw-empty-elt`, `table.ambox` (maintenance banners dropped with a count), `.noprint`, `.IPA` kept, `<math>` with `alttext` → `Equation(latex=alttext)`.
18. Infobox: `table.infobox` (and `.infobox_v2`, `.infobox_v3` on other wikis) → `Table` with two columns `Field`, `Value` under `Heading(level=2, text="Infobox")` placed right after the lead section; multi-line values joined with `; `; nested infobox rows flattened. Additionally parse wikitext `{{Infobox ...}}` with `mwparserfromhell` when `options.social.wiki_infobox_source="wikitext"` to get raw parameter names; default is HTML (rendered values are what readers see).
19. Body: sections from `<section data-mw-section-id>` and `h2`..`h6` map to headings with H2 as the top level (article title is H1). `.wikitable` to `Table` with spans. Images: `figure` → `Figure(caption)` with the `//upload.wikimedia.org` src made absolute. References section: each `<li id="cite_note-N">` becomes a `Footnote(id=N)` placed at the end of the document (not per section, since references are shared), and inline `[N]` superscripts become `[^N]`.
20. Categories into `metadata.categories`; `metadata.revision_id` and `metadata.last_modified` from the REST headers; `license="CC-BY-SA-4.0"` with attribution URL set in frontmatter (required by Wikipedia's license; the frontmatter renderer must emit `license` and `attribution` keys).
21. Other MediaWiki sites: detect via `<meta name="generator" content="MediaWiki">` from section 5 and `can_handle` 0.85; same pipeline using `action=parse`.

X/Twitter:

22. Default on the public instance: `can_handle` 0.9 and immediately emit a stub with warning `tos_risk_source` and the text "X posts are fetched only on self-hosted instances; paste the post text or use the browser extension." On self-host (`INTOMD_ENABLE_X=1`), call fxtwitter (`api.fxtwitter.com/<user>/status/<id>`): returns `tweet.text`, `author`, `created_at`, `replying_to`, `quote`, `media.photos/videos`, `likes`, `retweets`, and for threads `thread` arrays in some responses. Reconstruct a thread by following `replying_to_status` when the author matches the root author up to `max_thread_posts` (50), each hop one request. Fallback: syndication endpoint for a single tweet. On any failure, stub with `fetch_failed` and the suggestion to use the extension. Mark every X document `experimental=true`.
23. Rendering: a thread is a sequence of `Paragraph` blocks each prefixed with `**@user** · timestamp` (as `TranscriptSegment`-like but using `Comment` with `depth=0`); quoted tweets become nested `Quote`; media as `Image`/`Link`.

Bluesky:

24. Resolve `handle` → DID via `com.atproto.identity.resolveHandle`. Build the AT URI. Call `getPostThread` with `depth=100`, `parentHeight=50`. Walk `thread.post` (root), `thread.parent` chain upward (the post may not be the root; the converter emits the true root first), `replies[]` recursively. Facets (`app.bsky.richtext.facet`) carry links, mentions, and tags with byte offsets; apply them to produce inline `Link`s. Embeds: `app.bsky.embed.images` → `Image(alt)`, `embed.external` → `Link` with title and description as a `Quote`, `embed.record` (quote post) → nested `Quote`, `embed.video` → `Link`. `likeCount`, `repostCount`, `replyCount` as score fields. Blocked or not-found nodes (`blockedPost`, `notFoundPost`) become placeholders.
25. Profile URLs (`bsky.app/profile/<handle>`) → `getAuthorFeed` with `limit=100` into a `Table`.

Mastodon and Fediverse:

26. Detect the software via `/.well-known/nodeinfo` → `software.name`. Mastodon-compatible (`mastodon`, `pleroma`, `akkoma`, `gotosocial`, `firefish`): `GET /api/v1/statuses/<id>` (public statuses need no token) and `/api/v1/statuses/<id>/context` for `ancestors` and `descendants` (flat lists with `in_reply_to_id`; rebuild the tree). `content` is HTML; `spoiler_text` (content warning) becomes a `Paragraph(role="cw")` prefixed `CW:` before the body; `media_attachments` with `description` as alt; `card` as a `Link` with description; `reblog` unwrapped with `metadata.boosted_by`. Misskey-family: `POST /api/notes/show` and `/api/notes/children`. Rate limit 300 requests per 5 minutes per instance per Mastodon defaults; use at most 1 per second.
27. Authenticated-only or local-only posts return 401/404; stub with `private_post`.

Threads and LinkedIn:

28. Both are `experimental=true`, self-host only, and route through section 5 with a post-specific extraction step: Threads: parse the `<script type="application/json" data-sjs>` blobs for `thread_items[].post.caption.text`, `user.username`, `taken_at`, `like_count`; LinkedIn: the logged-out page exposes `og:title`, `og:description` (truncated), `article:author`; use `.attributed-text-segment-list__content` when present. Both emit warning `tos_risk_source` and `best_effort_extraction`.

Substack and Medium:

29. Substack: fetch `<url>?format=json` after a successful section 5 extraction; if the JSON exists, override `title`, `subtitle`, `author` (`publishedBylines[].name`), `published` (`post_date`), and set `metadata.paywalled = audience in ("only_paid", "founding")`; when paywalled and `body_html` is truncated, add the section 5 `paywall_detected` warning. Podcast posts (`type == "podcast"`) emit a `Link` to `podcast_url` for the media pipeline. Comments: `GET /api/v1/post/<id>/comments` (public) when `include_comments=true`, rendered through the shared thread model.
30. Medium: fetch `<url>?format=json`, strip the XSSI prefix, read `payload.value` for `title`, `creator`, `firstPublishedAt`, `isLocked`, `paragraphs[]` (typed paragraphs: 1 text, 3 H1, 13 H2, 4 image, 6 quote, 8 pre, 9 bullet, 10 ordered, with `markups` for links and code). Prefer building IR from `paragraphs[]` since it is cleaner than the DOM; fall back to section 5 on failure. `isLocked` with a short body → `paywall_detected`.

RSS/Atom/JSON Feed:

31. Parse with `feedparser`. Emit H1 feed title and `metadata.feed = {link, description, updated, language, generator}`. Each entry becomes `Heading(level=2, text=entry.title)` followed by metadata line (author, published, link) and the body from `content[0].value` or `summary`, converted through the HTML-to-IR module (feeds are HTML in CDATA). `enclosures` become `Link`s (audio enclosures are podcast episodes; `<podcast:transcript>` URLs are recorded as `metadata.transcript_url` for the media pipeline). `options.social.feed_max_entries` (default 50) with truncation warning. `options.social.feed_fetch_full=true` fetches each entry's `link` through section 5 (counts against caps) because many feeds are summaries only.
32. Feed autodiscovery: when a page URL is given with `options.social.feed=true`, read `<link rel="alternate" type="application/rss+xml">` and convert that.

Generic forums:

33. Discourse: `GET <topic-url>.json` (append `.json`, official API, no key needed for public topics) returns `post_stream.posts[]` with `cooked` HTML, `username`, `created_at`, `reply_to_post_number`, `like_count`; posts beyond the first 20 come from `/t/<id>/posts.json?post_ids[]=`. Build the tree by `reply_to_post_number` (Discourse is mostly flat; depth 0 for non-replies). Lemmy: `/api/v3/post?id=` and `/api/v3/comment/list?post_id=&max_depth=8&limit=300` with `path` strings for tree building. phpBB/XenForo/vBulletin/Flarum: section 5 with engine-specific selectors (`.postbody`, `.message-body`, `.postcontent`, `.Post-body`) and author/date from adjacent elements; flat list of `Comment` blocks with `depth=0` and quotes preserved as `Quote`.

### 7d. IR blocks and provenance

`Heading`, `Paragraph`, `Comment` (thread nodes), `Quote`, `Link`, `Image`, `Table` (listings, infoboxes, polls), `Footnote` (Wikipedia), `Equation` (Wikipedia), `Code`, `List`. Mandatory provenance: `source_id` and `timestamp` on every `Comment`; `path` on Wikipedia body blocks (section id); `source_id` on the root.

### 7e. Known failure modes

1. Reddit `more` nodes hiding half the thread; the fixture has 600 comments with collapsed children.
2. Reddit returning HTML (blocked UA or 429) instead of JSON; detect by content type and warn `fetch_blocked`.
3. HN `[dead]` and deeply nested (depth 30) threads.
4. Stack Exchange quota exhaustion and the `backoff` field.
5. Wikipedia infobox with nested tables and rowspans; references with the same citation reused (`cite_ref-foo_12-0`, `12-1`).
6. Wikipedia math `<math>` elements with `alttext` vs. fallback images.
7. X thread where the root is a reply to someone else (stop at author change).
8. Bluesky post that is mid-thread (must climb to the root) and blocked parents.
9. Mastodon remote statuses whose `context` is partial because the instance has not fetched all replies; warn `thread_partial_federation`.
10. Feeds with relative URLs in content and `content:encoded` vs `description` duplication (prefer `content:encoded`).
11. Substack custom domains not matching `*.substack.com` (detect by `substackcdn.com` in asset URLs from the section 5 fetch and re-dispatch).
12. Medium's JSON endpoint changing shape; the fallback must cover it.
13. Discourse topics with 2,000 posts; `max_comments` cap.
14. Thread bodies containing prompt-injection text; the scanner flags, never alters.

### 7f. Fixtures

All network cases use cassettes.

1. `social/reddit-thread-collapsed`: a 600-comment thread with `more` nodes, a deleted comment, spoiler syntax, a crosspost.
2. `social/reddit-link-post`: link post with `fetch_linked=true` resolving to a cassette page.
3. `social/hn-thread-deep`: 300 comments, depth 25, two dead comments, a poll story.
4. `social/stackexchange-question`: accepted answer, three answers, comments, code in `body_markdown`, plus a throttle cassette variant forcing the HTML fallback.
5. `social/wikipedia-article`: an article with an infobox (rowspans), hatnotes, math, 40 references with reuse, a wikitable, images, a redirect.
6. `social/bluesky-midthread`: a reply post whose root is two parents up, with facets and an image embed.
7. `social/mastodon-context`: a status with CW, ancestors and descendants, a boost.
8. `social/x-thread-selfhost`: fxtwitter cassette of a 6-post thread with a quote tweet; plus the public-instance stub expectation (`env: {INTOMD_ENABLE_X: ""}`).
9. `social/substack-paywalled` and `social/medium-locked`.
10. `social/rss-podcast-feed`: 10 entries with enclosures and a `podcast:transcript` tag; `social/atom-blog` with `content` HTML.
11. `social/discourse-topic`: 60 posts with `reply_to_post_number`.

### 7g. Acceptance thresholds

Thread cases: comment count exact (after caps), tree shape exact (parent ids), author and timestamp present on 100 percent, text_similarity 0.97 on bodies, provenance 1.0. Wikipedia: heading_retention 0.95, table_cell_accuracy 0.9 on the infobox and wikitable, footnotes count exact. Feeds: entries exact, text_similarity 0.95.

### 7h. Options

`options.social`: `max_comments` (200), `max_depth` (8), `sort` (`best`, `top`, `new`, `old`), `include_deleted` (true), `fetch_linked` (false), `fetch_media` (false), `expand_threads` (false for listings), `max_posts` (100), `include_scores` (true), `feed_max_entries` (50), `feed_fetch_full` (false), `wiki_infobox_source` (`html`, `wikitext`), `wiki_keep_hatnotes` (profile-dependent), `enable_tier2` (false; self-host only).

### 7i. Phase

Phase 3 for everything in this family, except RSS/Atom (Phase 1, needed by section 6 and the media pipeline) and Wikipedia (Phase 1, pure sanctioned API and high value for researchers). X, Threads, LinkedIn: Phase 3, `experimental`, self-host only.

---

## 8. code

### 8a. Scope and input matrix

| Input | Detection | Sub-converter |
|---|---|---|
| Local directory containing `.git` or more than one source file | path is a directory | `RepoPackConverter` |
| `github.com/<o>/<r>`, `/tree/<ref>/<path>`, `gitlab.com/<g>/<p>`, `/-/tree/<ref>/<path>`, `codeberg.org`, `bitbucket.org/<o>/<r>/src/<ref>`, `git@...` and `.git` URLs | URL patterns | `RepoPackConverter` (clone or API tarball) |
| `github.com/<o>/<r>/pull/<n>`, `gitlab.com/.../-/merge_requests/<n>` | URL | `PullRequestConverter` |
| `github.com/<o>/<r>/issues/<n>`, `/discussions/<n>`, `gitlab.com/.../-/issues/<n>` | URL | `IssueConverter` |
| `github.com/<o>/<r>/blob/<ref>/<path>`, `raw.githubusercontent.com`, `gist.github.com` | URL | `SourceFileConverter` after raw fetch |
| `.diff`, `.patch`, `text/x-diff`, content starting with `diff --git` or `---`/`+++` pairs | Magika `diff` | `DiffConverter` |
| Single source files: ~200 extensions (Magika and `identify` (MIT) language map) | Magika code types | `SourceFileConverter` |
| `openapi.yaml/json`, `swagger.json`, any JSON/YAML with top-level `openapi` or `swagger` key; `asyncapi` | content keys | `OpenApiConverter` |
| Postman `*.postman_collection.json` (`info._postman_id` and `item[]`) | content keys | `PostmanConverter` |
| `.sql` schema dumps (`CREATE TABLE`), `schema.prisma`, `.dbml` | content | `SqlSchemaConverter` |
| `Dockerfile`, `docker-compose.yml`, `.env.example`, `*.toml`/`*.ini`/`*.cfg`/`*.conf`/`*.yaml` config files, `Makefile`, `.github/workflows/*.yml` | name patterns | `ConfigFileConverter` (thin wrapper over `SourceFileConverter` plus key summary) |
| `.log`, `*.log.N`, `*.log.gz`, text with timestamp-prefixed lines on 60 percent of lines | content | `LogConverter` |
| Stack traces pasted or in files (`Traceback (most recent call last)`, `at com.`, `Exception in thread`, `panicked at`, `goroutine N [running]`) | content | `StackTraceConverter` |

### 8b. Libraries

1. Packing: implement natively in Python (no Node dependency). Behaviors are modeled on Repomix (MIT) and gitingest (MIT): tree, `.gitignore` respect via `pathspec` (MPL-2.0), file contents in fences, token counts via `tiktoken` (MIT) `cl100k_base`, secret scanning, compression via `tree-sitter` (MIT) with `tree-sitter-language-pack` (MIT) for signature-only mode. Optional: when `repomix` is on PATH and `options.code.engine == "repomix"`, shell out with `--style markdown` for shadow-run comparison.
2. Git: `dulwich` (Apache-2.0) for shallow clones and log; never require the `git` binary, but use it when present for speed (`git clone --depth 1 --filter=blob:none`).
3. GitHub and GitLab APIs: `httpx`; tokens from `GITHUB_TOKEN` / `GITLAB_TOKEN` (optional; unauthenticated GitHub allows 60 requests per hour, which is enough for one PR). Tarball download via `/repos/{o}/{r}/tarball/{ref}` avoids cloning.
4. Secrets: `detect-secrets` (Apache-2.0) plugins (AWS, Azure, GitHub, Slack, Stripe, JWT, private keys, high-entropy strings, keyword-based) run on every file before output; matches are replaced with `[REDACTED:<type>]` and listed in the sidecar under `redactions` with file and line. Files named like credentials (`.env`, `*.pem`, `*.key`, `id_rsa*`, `*.p12`, `credentials.json`, `.npmrc` with tokens, `.netrc`) are excluded entirely with warning `secret_file_excluded`. `options.code.redact=false` is allowed only on the CLI and self-host and prints a warning.
5. OpenAPI: `openapi-spec-validator` (Apache-2.0) optional for validation; parsing is stdlib `json` plus `pyyaml` (MIT); `$ref` resolution via `jsonref` (MIT) with cycle protection.
6. SQL: `sqlglot` (MIT) to parse DDL across dialects; falls back to regex on parse errors.
7. Logs and stack traces: stdlib `re`; `dateutil` (Apache/BSD) for timestamp parsing.
8. Language detection for fences: `identify` (MIT) extension map plus Magika's label; shebang sniffing for extensionless files.

### 8c. Build steps

RepoPackConverter:

1. Acquire the tree: local path as-is; GitHub/GitLab URL to tarball (ref from the URL or default branch via API), extracted into a temp dir with the archive-bomb rules from section 12; `git@`/`.git` URLs via shallow clone (self-host only; the public instance accepts only `https://github.com|gitlab.com|codeberg.org` tarballs under 50 MB). Subpath URLs (`/tree/<ref>/<path>`) restrict the pack to that subtree.
2. Collect files with `os.walk`, applying in order: `.gitignore` chains (`pathspec` gitwildmatch, respecting nested `.gitignore` files), `.intomdignore` (same syntax), default excludes (`.git`, `node_modules`, `vendor`, `dist`, `build`, `.venv`, `__pycache__`, `*.min.js`, `*.map`, `*.lock` kept but truncated to 50 lines, binary files by Magika, images, fonts, archives, files over `max_file_bytes` default 512 KB), then `options.code.include`/`exclude` globs. Record counts per exclusion reason in the sidecar.
3. Detect the project: language mix by extension bytes, `README*` (included first in full), `package.json`/`pyproject.toml`/`Cargo.toml`/`go.mod` name and description, license file name, default branch, commit sha (from `.git/HEAD` or the API), and emit them into metadata (`repo`, `ref`, `commit`, `languages`, `license_file`).
4. Order files: README first, then manifests and config at the root, then source files by directory depth then path, tests last (`test`, `tests`, `spec`, `__tests__` directories) unless `options.code.tests_first`. Docs directories (`docs/`) go after source.
5. Emit IR: `Heading(level=1, text="<repo> at <ref>")`, a `Paragraph` summary (file count, total bytes, total tokens, languages), `Heading(level=2, text="Directory tree")` with a `Code(language="text")` tree (directories first, files sorted, excluded directories shown as `node_modules/ (excluded, 1,204 files)`), then `Heading(level=2, text="Files")`, and per file `Heading(level=3, text=<relative path>)` with `metadata.tokens`, `bytes`, `language`, then a `Code(language, text)` block. Code fences use the longest run of backticks in the content plus one, minimum three (Part 1 renderer handles this given `Code.text`).
6. Budgeting: compute tokens per file with `tiktoken`. If the total exceeds `options.code.token_budget` (default none on CLI, 200k on public), apply smart truncation in this order until under budget: (a) drop lockfiles, generated files (`*.generated.*`, `*_pb2.py`, `*.g.dart`, files with a `@generated` or `Code generated by` header), and minified files; (b) drop test directories; (c) switch to compressed mode (step 7) for files over 300 lines; (d) truncate each remaining file to its first `N` lines where `N` scales so the budget fits, keeping at least 40 lines, with a trailing `... (truncated, 1,230 more lines)` marker inside the fence; (e) drop files from the deepest directories. Every step logs to the sidecar `budget_actions` and emits one warning `token_budget_applied` with the actions taken. The tree always stays complete so the reader knows what exists.
7. Compressed mode (`options.code.compress=true` or budget-triggered): for languages with a tree-sitter grammar, keep imports, class and function signatures, docstrings, type definitions, exported constants, and the first comment block; replace bodies with `...`. For other languages, keep lines matching `^(import|from|export|def|class|fn|func|pub|struct|interface|type|enum|package|module|use|#include)\b` plus the 2 following lines. Mark the file heading with `(signatures only)`.
8. Secrets (8b step 4) run on every file's text before it enters IR; redactions are applied in place.
9. Git history: when `options.code.include_log=true`, emit `Heading(level=2, text="Recent commits")` with a `Table` of the last `log_count` (50) commits (sha7, date, author, subject). `include_diff=true` on a local repo appends the working-tree diff through the `DiffConverter`.
10. Provenance: `path` = relative file path; `line` = 1 for file blocks (the whole file is one `Code` block; line-level anchoring is the consumer's job via the fence). Tree block: `path="."`.
11. Output modes: single combined `Document` (default) or `DocumentSet` with one document per file plus an index when `options.code.output="separate"`.

SourceFileConverter:

12. Detect language (8b step 8). Emit `Heading(level=1, text=<filename>)`, metadata (`language`, `lines`, `bytes`, `tokens`, shebang), and one `Code` block. Markdown-family and notebook files are routed to section 4 instead. `.svg` is treated as XML (section 10) unless `options.code.svg_as_image`.
13. Optional symbol outline (`options.code.outline=true`): tree-sitter query for top-level definitions producing a `List` of `name (kind) line N` before the code block. Default on for files over 500 lines.

PullRequestConverter:

14. GitHub: `GET /repos/{o}/{r}/pulls/{n}` (title, body, author, state, base, head, merged, created, labels, additions, deletions, changed_files), `/pulls/{n}/files` (paged, 100 per page, `patch` field per file), `/pulls/{n}/reviews`, `/pulls/{n}/comments` (review comments with `path`, `line`/`original_line`, `diff_hunk`, `in_reply_to_id`), `/issues/{n}/comments` (conversation comments), `/pulls/{n}/commits`. GitLab: `/projects/{id}/merge_requests/{iid}`, `/changes`, `/notes`, `/discussions`. Use the token when available; on 403 rate limit, stub with `rate_limited` and the reset time.
15. Emit: H1 `PR #n: <title>`; metadata table (author, state, branches, created, merged, labels, +/- lines, files); `Heading(level=2, text="Description")` with the body as Markdown (section 4 parser; GitHub task lists and mentions preserved); `Heading(level=2, text="Commits")` table; `Heading(level=2, text="Changes")` with per-file `Heading(level=3, text=<path> (+a −d))` and the patch as `Code(language="diff")` (files with over `max_patch_lines` 500 are truncated with a marker; renamed and binary files noted); `Heading(level=2, text="Review comments")` grouped by file and line as `Comment` blocks with `metadata.path`, `line`, `diff_hunk` context (one `Code(language="diff")` with the hunk), threaded by `in_reply_to_id`; `Heading(level=2, text="Conversation")` with issue comments and review summaries (`APPROVED`, `CHANGES_REQUESTED`) as `Comment` blocks in time order.
16. Provenance: `source_id` = comment or commit id; `path` and `line` on review comments; `timestamp` on every comment.

IssueConverter:

17. GitHub issues and discussions (`GET /repos/{o}/{r}/issues/{n}` and `/comments`; discussions via GraphQL `discussion(number:)` with `comments(first:100)` and nested `replies`), GitLab issues and notes. Emit H1 title, metadata table (state, author, labels, assignees, milestone, created, closed, reactions counts), body, then `Comment` blocks (discussion replies nested with `depth`). Linked PRs and cross-references (`#123` in text) become `Link`s to absolute URLs. Timeline events (labeled, closed, referenced) are included only in `full` as a `Table` when `options.code.include_timeline=true`.

DiffConverter:

18. Parse unified diffs (`diff --git`, `---`/`+++`, `@@` hunks, `rename from/to`, `Binary files`, `new file mode`, `deleted file mode`) and combined diffs. Emit H1 `Diff (<n> files, +a −d)`, a summary `Table` (file, status, +/-), and per file `Heading(level=2)` plus `Code(language="diff")` with the hunks verbatim. `options.code.diff_context` can expand context when the source files are available locally (`git diff -U<n>`); otherwise verbatim. Provenance: `path` = file, `line` = hunk start line in the new file.

OpenApiConverter:

19. Load JSON or YAML; detect version (`openapi: 3.x`, `swagger: "2.0"`, `asyncapi`). Resolve `$ref`s (local and relative-file refs; remote refs refused on public, allowed self-host under the SSRF guard). Validate optionally and warn `spec_invalid` with the first 5 errors, continuing.
20. Emit: H1 `info.title` with version, `info.description` as Markdown, servers as a `Table`, security schemes as a `Table`. Then `Heading(level=2, text="Endpoints")` and, grouped by first tag (untagged last), `Heading(level=3, text="<METHOD> <path>")` with `summary`, `description`, `operationId`, parameters as a `Table` (name, in, type, required, description, default/enum), request body per media type with the schema rendered as a nested `List` (property, type, required, description, constraints) up to `schema_depth` (4), responses as a `Table` (status, description, media type) with each response schema rendered the same way, and an example JSON as `Code(language="json")` when `example`/`examples` exist (generate a minimal example from the schema when `options.code.openapi_examples="generate"`). Then `Heading(level=2, text="Schemas")` with each component schema once (endpoints reference them by name after the first expansion to avoid duplication; `options.code.openapi_inline_schemas=true` inlines everywhere). Deprecated operations are marked `(deprecated)` in the heading. AsyncAPI: channels and messages follow the same shape with `publish`/`subscribe` in place of methods.
21. Provenance: `path` = JSON pointer (`/paths/~1users~1{id}/get`).

PostmanConverter:

22. Walk `item[]` recursively (folders are items with `item[]`). Emit H1 collection name, `info.description`, variables as a `Table`, then per folder `Heading(level=2)` and per request `Heading(level=3, text="<METHOD> <name>")` with the resolved URL (`{{var}}` kept verbatim), headers table, query params table, body (`raw` as `Code` with language from `options.raw.language`, `formdata`/`urlencoded` as tables, `graphql` as `Code(language="graphql")`), auth type, pre-request and test scripts as `Code(language="javascript")` when `options.code.postman_scripts=true`, and saved responses (`response[]`) as `Code` with status. Environment files (`*.postman_environment.json`) are a `Table` of variables with secret-type values redacted.

SqlSchemaConverter:

23. Parse with `sqlglot` (dialect from `options.code.sql_dialect` or auto-detected by trying `postgres`, `mysql`, `sqlite`, `tsql`, `bigquery`, `snowflake`). For each `CREATE TABLE`, emit `Heading(level=2, text=<schema.table>)` with a `Table` (column, type, nullable, default, constraints) and a `List` of indexes, foreign keys (`→ other_table(col)`), and comments (`COMMENT ON`). Views, functions, triggers, enums, and sequences get their own H2 sections with the definition as `Code(language="sql")`. Emit a relationships summary `Table` (from table, column, to table, column) under `Heading(level=2, text="Relationships")`. Data `INSERT` statements are summarized (count per table) and omitted unless `options.code.sql_include_data=true` (then as `Code` capped by `max_file_bytes`). Prisma: parse `model` blocks with a small grammar; DBML: `Table`/`Ref` blocks. Provenance: `line` of each statement.

ConfigFileConverter:

24. Dockerfile: `Code(language="dockerfile")` plus a `List` summary (base images per stage, exposed ports, entrypoint, cmd, copied paths, env keys with values redacted when they look like secrets). docker-compose: services table (name, image, ports, volumes, depends_on) plus the YAML as `Code`. GitHub Actions: triggers, jobs, steps summary plus `Code`. Generic TOML/INI/YAML/JSON config: route to section 10 for the structured summary, then the raw `Code`. `.env*` files: keys only with values replaced by `[REDACTED]` always (even `.env.example`, which may contain real values by mistake), warning `env_values_redacted`.

LogConverter:

25. Detect the line format on a 500-line sample: timestamp regexes (ISO 8601, syslog `MMM dd HH:MM:SS`, Apache CLF `[dd/MMM/yyyy:HH:MM:SS +0000]`, epoch seconds and milliseconds, `yyyy-mm-dd HH:MM:SS,mmm` Python logging), level tokens (`DEBUG|INFO|WARN|WARNING|ERROR|CRITICAL|FATAL|TRACE`), JSON lines (`{"` start and valid JSON on 90 percent of lines, with `timestamp`/`time`/`ts`/`@timestamp` and `level`/`severity` keys). Record the detected format and the time span (first and last timestamp) in metadata.
26. Normalize timestamps to ISO 8601 UTC in a leading column when `options.code.log_normalize_time=true` (default true); keep the original string in the sidecar mapping only when the user asks (`log_keep_original_time`), since logs can be huge. Multi-line entries (continuation lines without a timestamp, stack traces) attach to the preceding entry.
27. Dedupe: collapse runs of identical message bodies (after masking numbers, hex ids, UUIDs, IPs, and timestamps with placeholders `<n>`, `<hex>`, `<uuid>`, `<ip>`) into one line with a suffix `(repeated 412 times, first 12:00:01, last 12:04:33)`. Non-adjacent duplicates are collapsed only when `options.code.log_dedupe="global"` (default `adjacent`). Record the dedupe count in a warning `log_lines_collapsed`.
28. Emit: H1 `<filename>` with metadata (format, span, line counts by level as a `Table`), then `Heading(level=2, text="Errors and warnings")` listing ERROR and above entries (capped at 200, each with its stack trace attached via the StackTraceConverter), then `Heading(level=2, text="Log")` with the normalized lines as a `Code(language="log")` block, truncated to `options.code.log_max_lines` (default 5,000; tail by default since the end is usually what matters, `log_head=true` to keep the head) with a marker and warning `log_truncated`. JSON lines render as `timestamp level message key=value ...` with nested objects flattened by dot paths.
29. Rotated and gzipped logs (`app.log.1`, `app.log.2.gz`) given as a directory or glob are concatenated in chronological order (by first timestamp), with file boundaries marked by `<!-- file: app.log.2.gz -->` `Raw` blocks.
30. Secrets run on logs too (tokens in URLs, `Authorization:` headers, passwords in connection strings).

StackTraceConverter:

31. Recognize Python, Java/Kotlin/Scala, JavaScript/Node/TypeScript, Go, Rust, C#/.NET, Ruby, PHP, Swift/Objective-C, and C/C++ (gdb, ASan) trace formats. Parse into `{language, exception_type, message, frames: [{function, file, line, column, module, in_app}], cause_chain}`. `in_app` is true when the file path is not in a known framework or stdlib location (site-packages, node_modules, `java.`, `org.springframework`, `runtime/`, etc.).
32. Emit: H1 `<exception_type>: <message>`, a `Table` of frames (index, function, file:line, in_app) with the innermost first in the order the language prints (preserve print order; note `metadata.frame_order="innermost_first"|"outermost_first"`), the original trace as `Code(language="text")` verbatim, and `cause_chain` sections (`Caused by:`) nested the same way. Secrets redaction applies to the message. Multiple traces in one input become one H2 per trace with a count summary.

### 8d. IR blocks and provenance

`Heading`, `Paragraph`, `Code` (dominant), `Table`, `List`, `Comment` (PR and issue comments), `Link`, `Raw` (file markers). Mandatory provenance: `path` on every block; `line` on `Code` blocks from diffs, logs, SQL statements, and stack frames; `source_id` and `timestamp` on `Comment`.

### 8e. Known failure modes

1. Secrets leaking into output (AWS key in a test fixture, a `.env` committed by mistake, tokens in logs); the fixture asserts zero matches post-redaction with an independent regex pass.
2. `.gitignore` negations (`!keep.me`) and nested ignore files.
3. Binary files detected as text (UTF-16 source, BOM files) and text files detected as binary (minified JS with long lines; treat lines over 2,000 chars as minified, included only as a truncated head).
4. Symlink loops and symlinks pointing outside the repo (never follow outside the root).
5. Monorepos over the token budget: the budget actions must keep the tree complete.
6. Backtick runs inside code breaking fences.
7. Generated files bloating output (protobuf, lockfiles).
8. PR with 400 changed files and a 20 MB patch; per-file cap plus total cap with warning.
9. Review comments on outdated diffs (`line` null, `original_line` set): use `original_line` and mark `(outdated)`.
10. OpenAPI with circular `$ref`s and `allOf`/`oneOf` compositions; `allOf` merged, `oneOf`/`anyOf` listed as alternatives.
11. Swagger 2.0 `definitions` and `parameters` in body form.
12. SQL dumps with dialect-specific syntax (`ENGINE=InnoDB`, `SERIAL`, `IDENTITY(1,1)`), `CREATE TABLE IF NOT EXISTS`, quoted identifiers.
13. Logs with mixed timestamp formats, timezone-less timestamps (assume UTC, warn `timezone_assumed`), and a 2 GB file (stream; never load fully; tail by seeking).
14. Interleaved stack traces from multiple threads.
15. GitHub rate limit without a token.

### 8f. Fixtures

1. `code/repo-python-small`: a 40-file Python project with nested `.gitignore`, a `!negated` rule, a test dir, a lockfile, a generated `_pb2.py`, a symlink loop, a fake AWS key in `tests/fixtures/creds.txt`, a committed `.env`, a UTF-16 file, and a README.
2. `code/repo-budget`: the same repo with `token_budget: 8000` forcing all five budget actions; expected output verifies the tree is complete and the actions list.
3. `code/repo-compress-ts`: a TypeScript project with `compress=true`; expected signatures only.
4. `code/github-pr`: cassette of a PR with 6 files, a rename, a binary file, 12 review comments including an outdated one and a reply thread, two reviews, and conversation comments.
5. `code/github-issue-discussion`: an issue with 20 comments and a discussion with nested replies.
6. `code/diff-unified`: a multi-file `.patch` with a rename and a binary file.
7. `code/openapi-petstore-plus`: OpenAPI 3.1 with circular refs, `allOf`, `oneOf`, examples, deprecated ops, security schemes; plus a Swagger 2.0 variant.
8. `code/postman-collection`: nested folders, auth, scripts, environment file with a secret.
9. `code/sql-schema-multi-dialect`: Postgres and MySQL dumps with FKs, views, a trigger, enums, and INSERT data.
10. `code/dockerfile-compose-actions`: a multi-stage Dockerfile, a compose file, a workflow file, and a `.env.example`.
11. `code/log-mixed`: a 20,000-line log with repeated lines, JSON lines segment, Python and Java stack traces, timezone-less timestamps, and a `.gz` rotation.
12. `code/stacktraces`: one file per language with cause chains.
13. `code/source-single-files`: a directory of 15 single files across languages, including an extensionless script with a shebang and a minified JS file.

### 8g. Acceptance thresholds

Repo packs: file set exact (after exclusions), tree exact, token counts within 2 percent, redactions exact (zero leaks), text_similarity 0.999 on included code (code must be verbatim). PR and issue: comment count and threading exact, text_similarity 0.98. OpenAPI: endpoint count exact, table_cell_accuracy 0.95, heading_retention 0.95. SQL: table and column counts exact. Logs: line counts by level exact, dedupe count exact, text_similarity 0.97 on the kept lines. Stack traces: frame count and `in_app` flags exact.

### 8h. Options

`options.code`: `engine` (`native`, `repomix`), `include`/`exclude` (globs), `respect_gitignore` (true), `max_file_bytes` (512 KB), `token_budget` (none CLI, 200k public), `compress` (false), `outline` (auto), `tests_first` (false), `include_log` (false), `log_count` (50), `include_diff` (false), `output` (`combined`, `separate`), `redact` (true), `secret_plugins` (list), `ref` (branch, tag, sha), `subpath`, `max_patch_lines` (500), `include_timeline` (false), `openapi_examples` (`spec`, `generate`, `off`), `openapi_inline_schemas` (false), `schema_depth` (4), `postman_scripts` (false), `sql_dialect` (auto), `sql_include_data` (false), `log_normalize_time` (true), `log_dedupe` (`adjacent`, `global`, `off`), `log_max_lines` (5000), `log_head` (false), `svg_as_image` (false).

### 8i. Phase

Phase 1: repo packing (local and GitHub/GitLab tarballs), single files, diffs, PRs and issues, OpenAPI, SQL schemas, config files, logs, stack traces. Postman: Phase 1 (small). Shallow clones of arbitrary git URLs: Phase 3 (self-host). Tree-sitter compression: Phase 1 if grammar wheels install cleanly on all three CI platforms, else Phase 2 with the regex fallback shipping in Phase 1.

---

## 9. communication

### 9a. Scope and input matrix

| Input | Detection | Sub-converter |
|---|---|---|
| `.eml`, `message/rfc822`, text starting with RFC 5322 headers (`From:`/`Received:`/`Return-Path:` in the first 2 KB) | Magika `eml`, content | `EmailConverter` |
| `.msg` (OLE2 CFB with `__substg1.0_` streams) | magic `D0 CF 11 E0` plus stream names | `MsgConverter` |
| `.mbox`, `.mbx`, files starting with `From ` lines | content | `MboxConverter` |
| `.pst`, `.ost` | magic `!BDN` | refused in default install; `intomd[pst]` extra wraps `libpff` (LGPL, shell-out to `pffexport`) producing EML files, Phase 5 |
| Gmail/Outlook thread "export": `.eml` from "Show original" or "Download message", Outlook `.msg`, or a pasted thread as text | user-supplied files only; no IMAP, no OAuth | `EmailConverter`/`MsgConverter`/plain-text thread splitter |
| Slack export: zip or directory with `channels.json`, `users.json`, and `<channel>/<YYYY-MM-DD>.json` | structure | `SlackExportConverter` |
| Discord: DiscordChatExporter JSON (`guild`, `channel`, `messages[]`) or HTML (`chatlog__message-container`), and Discord data package `messages/<id>/messages.json` or `.csv` | content keys | `DiscordExportConverter` |
| Teams: chat export JSON from the Graph export or Purview eDiscovery (`messages[]` with `from.user.displayName`, `body.content` HTML), and the "Export chat" HTML | content | `TeamsExportConverter` |
| WhatsApp: `.txt` export (`_chat.txt` or `WhatsApp Chat with X.txt`) with optional media folder, or a zip | first-line pattern | `WhatsAppConverter` |
| iMessage: `imessage-exporter` TXT or HTML output, or `chat.db` directly (self-host only, read-only SQLite) | content / magic | `IMessageConverter` |
| SMS backups: SMS Backup & Restore XML (`<smses>`), Android `sms-*.xml`, iOS `SMS` CSV exports | root element | `SmsXmlConverter` |
| Telegram: Desktop export `result.json` (`"type": "personal_chat"|"private_supergroup"`, `messages[]` with `text_entities`) and HTML `messages.html` | content | `TelegramExportConverter` |
| `.ics`, `text/calendar` | content `BEGIN:VCALENDAR` | `IcsConverter` |
| `.vcf`, `text/vcard` | content `BEGIN:VCARD` | `VcfConverter` |

### 9b. Libraries

1. EML/MBOX: stdlib `email` (policy `default`), `mailbox` for MBOX; `html2text` is not used (the HTML-to-IR module handles HTML bodies); `charset-normalizer` for undeclared charsets.
2. MSG: `extract-msg` is GPLv3, so it is an optional extra `intomd[msg-gpl]`. Default path: a native MSG reader built on `olefile` (BSD-2) that reads the documented property streams (`__substg1.0_0037001F` subject, `0C1A` sender name, `0C1F` sender email, `0E04` display to, `0E03` cc, `1000` body, `1013` HTML body (binary stream), `1009` RTF-compressed body, `0039`/`0E06` dates from `__properties_version1.0`, `__attach_version1.0_#` substorages with `3701` data and `3704`/`3707` filenames, `__recip_version1.0_#` for recipients, embedded messages as nested storages with `3701` being a storage). RTF-compressed bodies decompress with a 150-line LZFu implementation (public algorithm, MS-OXRTFCP) and the RTF is de-encapsulated to HTML when it carries `\fromhtml1` (MS-OXRTFEX), else converted via the RTF fallback in section 2. The `olefile` path covers 95 percent of real `.msg` files; when it fails and `extract-msg` is installed and opted in, use it; otherwise warn `msg_partial`.
3. Slack, Discord, Teams, Telegram: stdlib `json`; Discord HTML via the HTML-to-IR module with selectors.
4. WhatsApp: `dateutil` plus a locale table; `regex` (Apache-2.0) for Unicode-aware parsing (LRM/RLM marks, narrow no-break spaces in iOS exports).
5. iMessage `chat.db`: stdlib `sqlite3` opened read-only (`file:...?mode=ro&immutable=1`); `typedstream` decoding for `attributedBody` via a small parser (the `imessage-exporter` format is preferred and documented; raw db support is self-host only and `experimental`).
6. SMS XML: `lxml` iterparse.
7. ICS: `icalendar` (BSD-2) with `recurring-ical-events` (MIT) for expansion; VCF: `vobject` (Apache-2.0).
8. Attachments: every attachment goes through the registry recursively with the depth and size limits from section 12, producing child documents under `Heading(level=2, text="Attachment: <name>")`; attachments that cannot be converted are listed in an attachments `Table` with size and type and warning `attachment_unconverted`.

### 9c. Build steps

EmailConverter:

1. Parse with `email.message_from_bytes(policy=email.policy.default)`. Decode RFC 2047 headers. Build the headers `Table` (`From`, `To`, `Cc`, `Bcc` when present, `Date` (parsed to ISO 8601 with offset), `Subject`, `Message-ID`, `In-Reply-To`, `References`, `Reply-To`, `List-Id`) under H1 `Subject`. Full raw headers go to the sidecar; `options.comm.all_headers=true` renders them all (including `Received` chains, `DKIM-Signature`) in a collapsible section.
2. Body selection: prefer `text/html` when present and `options.comm.body="auto"` (HTML carries structure: quotes, lists, tables, inline images); convert through the HTML-to-IR module in file mode with `cid:` images resolved to attachments. Fall back to `text/plain`. Record `metadata.body_source`. When both exist and differ materially (plain is under 50 percent of HTML text length), note `metadata.body_alternatives=true`.
3. Quoted-reply stripping (`options.comm.strip_quotes`, default `mark`): detect quoted history by `>` prefixes, `On <date>, <name> wrote:` and localized variants (`Le ... a écrit :`, `Am ... schrieb ...`, `El ... escribió:`), Outlook `-----Original Message-----` and `From:/Sent:/To:/Subject:` header blocks, Gmail `gmail_quote` div, `blockquote[type=cite]`. `mark` wraps the history in a `Quote(role="reply_history")` so it is visually separated and droppable by profile (`compact` drops it); `strip` removes it with warning `quoted_history_removed` and the count; `keep` leaves it inline. Signature blocks (`-- ` delimiter, `Sent from my iPhone`, a 2-6 line trailing block with phone or URL patterns) become `Paragraph(role="signature")`, dropped in `compact`.
4. Attachments: for each part with `Content-Disposition: attachment` or an inline part that is not referenced by `cid:`, write to assets and convert via the registry (9b step 8). `message/rfc822` parts (forwarded emails) convert through this same converter as children. Winmail.dat (`application/ms-tnef`) parsed with `tnefparse` (LGPL; so optional `intomd[tnef]`), else warning `tnef_unparsed`. Calendar invites (`text/calendar` parts) go to the ICS converter and render under the body.
5. Thread reconstruction (for MBOX, multiple EML files, or a directory): group by `References`/`In-Reply-To` into trees (JWZ algorithm), fall back to normalized subject (`Re:`, `Fwd:`, `AW:`, `WG:`, `[list]` prefixes stripped) plus participants within 30 days. Emit one document per thread when `options.comm.threads="separate"` or a combined document with H1 per thread, H2 per message (`From · Date`), and messages in chronological order with `metadata.depth` for reply nesting. When `strip_quotes="strip"` and the thread is reconstructed, quoted history is removed with high confidence since the earlier message is present in full.
6. Provenance: `source_id` = `Message-ID`; `timestamp` = `Date`; `path` = `body` / `attachments/<n>` / `headers`.

MsgConverter:

7. Read the OLE streams (9b step 2) into the same intermediate as EML (headers, body candidates, attachments, recipients, embedded messages) and run steps 1 to 6. Outlook-specific properties worth keeping: `0x0E1D` normalized subject, `0x1035` Internet Message-ID, `0x1042` In-Reply-To, `0x007D` transport headers (parse these as the real RFC 5322 headers when present), categories (`Keywords` named property), importance, flag status. Signed/encrypted (`.p7m` attachments, `0x001A` class `IPM.Note.SMIME`) are reported with warning `smime_not_decrypted`.

MboxConverter:

8. `mailbox.mbox` iterating messages (handles `>From ` escaping). Enforce `max_messages` (default 5,000) and `max_bytes`. Run thread reconstruction. For Gmail Takeout MBOX, read `X-Gmail-Labels` into `metadata.labels` and allow `options.comm.label_filter`.

Gmail/Outlook thread via user export:

9. No API access. Accept: a folder of `.eml`, a `.mbox`, `.msg` files, a PDF print of a thread (routes to section 1), or pasted text. Pasted text thread splitting: split on `On ... wrote:` and `From:` header blocks into pseudo-messages and run the thread renderer with warning `thread_reconstructed_from_text`. Document in the CLI help that Gmail "Show original" gives the EML.

SlackExportConverter:

10. Load `users.json` into an id → `{name, real_name, display_name, is_bot, deleted}` map, `channels.json`/`groups.json`/`mpims.json`/`dms.json` for channel metadata (name, purpose, topic, members, created, is_archived). `options.comm.name_field` picks `display_name` (default), `real_name`, or `name`; fall back through them.
11. For each channel directory (or those in `options.comm.channels`), read all `YYYY-MM-DD.json` files in date order and concatenate messages. Replace `<@U123>` mentions with `@name`, `<#C123|general>` with `#general`, `<https://url|label>` with Markdown links, `<!here>`/`<!channel>` kept as text. Convert Slack mrkdwn to Markdown: `*bold*` → `**bold**`, `_italic_` → `*italic*`, `~strike~` → `~~strike~~`, code and fenced blocks preserved, `&gt;` quotes to `Quote`. Prefer `blocks[]` rich text when present (it carries lists and links losslessly); fall back to `text`.
12. Thread reconstruction (the research's core differentiator): messages with `thread_ts` equal to their own `ts` are thread parents; messages with `thread_ts != ts` are replies. Slack exports list replies inline by day, which can be days after the parent and in a different file. Build `parent_ts → [replies]` across all files first, then emit each parent with its replies nested immediately beneath it (as `Comment` blocks with `depth=1`), and do not re-emit replies in the top-level stream. Replies whose parent is missing (parent outside the export date range) are grouped under a synthetic parent `Comment(text="(thread parent not in export)")` keyed by `thread_ts`, with warning `orphan_thread_replies` and the count. `reply_count` and `reply_users` on the parent are cross-checked; mismatches add `metadata.thread_incomplete=true`.
13. Message subtypes: `channel_join`, `channel_leave`, `channel_purpose`, `pinned_item`, `bot_message` (keep with the bot name), `file_share` (render the file as an attachment line with name, type, and, when the export includes files or `url_private` is reachable with a token, convert through the registry), `tombstone`, `thread_broadcast` (a reply also shown in channel: show once in the thread and once as a one-line pointer in the stream). Join/leave events are omitted unless `options.comm.include_system=true`. Edited messages carry `metadata.edited=true`; the export does not keep prior versions.
14. Reactions: `reactions[]` rendered as a trailing line `(reactions: 👍 3, 🎉 1)` only when `options.comm.include_reactions=true` (default false; `:emoji:` names are converted to Unicode via a small built-in table, unknown custom emoji kept as `:name:`).
15. Output: one document per channel (`DocumentSet`) by default, or combined with H1 per channel. Each message is a `Comment(author, timestamp, depth)` whose body is a block list; the renderer prints `**name** [2024-03-01 14:22]` then the body, with consecutive messages from the same author within 5 minutes merged into one block when `options.comm.merge_consecutive=true` (default true in `compact`, false in `full`; merging changes granularity and must be reversible from the sidecar which keeps every `ts`). Day boundaries emit `Heading(level=2, text=YYYY-MM-DD)`.
16. Canvases (`canvases.json` and `canvases/` HTML) and huddle transcripts, when present, are converted as attachments under the channel.
17. Provenance: `source_id` = `ts` (Slack's message id), `timestamp` = `float(ts)`, `path` = `<channel>/<date>.json#<index>`.

DiscordExportConverter:

18. DiscordChatExporter JSON: `messages[]` with `id`, `type` (`Default`, `Reply`, `ThreadCreated`, `GuildMemberJoin`, ...), `timestamp`, `timestampEdited`, `content` (Discord Markdown; near-GFM), `author.{name, nickname, isBot}`, `attachments[]`, `embeds[]`, `reactions[]`, `mentions[]`, `reference.messageId` for replies. Replies render as `Comment` with `metadata.reply_to` and a quoted first line of the referenced message. Thread channels are exported as separate channels; when the export contains a parent channel and its threads (`channel.category`/name conventions), link them. Embeds render as `Quote` with title, description, and fields as a two-column `Table`. Attachments through the registry when the files are present locally (`--media` export) else as `Link`s. HTML exports: parse `.chatlog__message-group` and children. Data-package `messages.csv` (ID, Timestamp, Contents, Attachments) renders as a flat stream with no author (it is the user's own messages) and warning `discord_package_no_authors`.

TeamsExportConverter:

19. Graph/Purview JSON: `messages[]` with `from.user.displayName`, `createdDateTime`, `body.contentType` (`html`), `body.content`, `attachments[]`, `mentions[]`, `replyToId`, `reactions[]`. HTML bodies through the HTML-to-IR module; mentions `<at id="0">Name</at>` resolved from `mentions[]`. `replyToId` builds threads exactly like Slack step 12. Channel messages vs chat: `channelIdentity` present means channel. The HTML "Export chat" format: parse `div[data-tid="chat-pane-message"]` or fall back to the HTML-to-IR module with warning `teams_html_best_effort`.

WhatsAppConverter:

20. Detect the line format from the first 50 lines against a table of known patterns: Android `DD/MM/YYYY, HH:MM - Name: text`, iOS `[DD/MM/YYYY, HH:MM:SS] Name: text`, US `M/D/YY, h:mm AM - Name:`, German `DD.MM.YY, HH:MM - Name:`, with optional LRM/RLM and narrow NBSP before AM/PM. Determine day-first vs month-first by scanning for any day value over 12; if ambiguous, use `options.comm.date_order` or `language_hint` locale defaults, and warn `date_order_assumed`. Continuation lines (no timestamp prefix) append to the previous message. System messages (`Messages and calls are end-to-end encrypted`, `X added Y`, `X changed the subject`) are kept with `role="system"` or omitted per `include_system`. Media placeholders (`<Media omitted>`, `image omitted`, `IMG-20240301-WA0001.jpg (file attached)`) resolve to files in the sibling media folder or zip when present and convert through the registry (images to the OCR pipeline in Phase 2), else render as `(media omitted)`. `This message was deleted` and `You deleted this message` kept as placeholders. Emit `Comment` blocks with day headings as in Slack step 15. Provenance: `line`, `timestamp`.

IMessageConverter:

21. `imessage-exporter` TXT format: blocks of `<timestamp>\n<sender>\n<text>` separated by blank lines, with `Tapbacks:` and `Replying to ...` lines; parse into `Comment` with `metadata.reply_to`, reactions, attachments (paths in the export's attachments folder), `(edited)` markers. HTML format: parse `.message` elements. Raw `chat.db` (self-host, `experimental`): query `message` joined with `handle` and `chat_message_join`, decode `text` or `attributedBody` (typedstream), convert Apple epoch (nanoseconds since 2001-01-01) to ISO 8601, group by chat with participant names resolved from `chat.chat_identifier` (phone numbers and emails; no contact names unless `options.comm.contacts_vcf` is supplied, in which case the VCF converter's map resolves them), handle `associated_message_type` 2000-2005 as reactions and 3000-3005 as reaction removals, `thread_originator_guid` as replies. Never write to the db; copy it to a temp file first if the OS has it locked.

SmsXmlConverter:

22. SMS Backup & Restore: `<sms address date type body contact_name readable_date>` (type 1 received, 2 sent) and `<mms>` with `<parts><part ct= text=>` and `<addrs>`. Group by `address` (normalized E.164 when possible), one H2 per conversation, `Comment` per message with `author` = contact name or address, direction in `metadata.direction`. MMS text parts rendered; image parts (`data` base64) written to assets and converted in Phase 2. `date` is epoch milliseconds.

TelegramExportConverter:

23. `result.json`: `messages[]` with `id`, `type` (`message`, `service`), `date`, `from`, `from_id`, `reply_to_message_id`, `text` (string or array of typed entities: `bold`, `italic`, `code`, `pre` with `language`, `text_link` with `href`, `mention`, `hashtag`, `link`, `spoiler`, `blockquote`), `photo`, `file`, `media_type`, `sticker_emoji`, `forwarded_from`, `edited`, `reactions[]`, `poll`. Build Markdown from the entity array (never from the flattened string). Replies via `reply_to_message_id` nest like Slack step 12. Service messages per `include_system`. Media files relative to the export folder go through the registry (voice messages to the media pipeline in Phase 2). Polls become a `Table` (option, votes). Multi-chat exports (`chats.list[]`) produce one document per chat. HTML exports (`messages.html`, `messages2.html`): parse `.message.default` elements with `.from_name`, `.date[title]`, `.text`.

IcsConverter:

24. Parse with `icalendar`. Expand recurrences with `recurring-ical-events` within `options.comm.ics_range` (default: 1 year before to 1 year after today, or the explicit `DTSTART` span for finite calendars), cap at `ics_max_events` (2,000). Emit H1 `X-WR-CALNAME` or filename, `Table` (start, end, summary, location, organizer, attendees count, status, recurrence) sorted by start, and per event `Heading(level=3, text=summary)` with `DESCRIPTION` as Markdown (descriptions are often plain text with `\n`), `LOCATION`, `URL`, `ATTENDEE` list with `PARTSTAT`, `VALARM` reminders, `CATEGORIES`, and time zones converted to the calendar's `TZID` with an ISO 8601 offset. `VTODO` and `VJOURNAL` get their own sections. All-day events render as dates without times. Provenance: `source_id` = `UID`, `timestamp` = start epoch.

VcfConverter:

25. Parse vCard 2.1, 3.0, 4.0 with `vobject`. Emit H1 `Contacts (N)` and one `Table` (name, organization, title, emails, phones, addresses, birthday, note) when `N <= 200`, else a `DocumentSet` chunked by 200 plus the table; `PHOTO` binary data written to assets and referenced only in `full`. Expose the parsed map (`email/phone → FN`) to the iMessage and SMS converters via `options.comm.contacts_vcf`.

### 9d. IR blocks and provenance

`Heading`, `Table` (headers, calendars, contacts), `Paragraph`, `Quote` (reply history, embeds), `Comment` (every chat message), `List`, `Code`, `Image`, `Link`, `Raw`. Mandatory provenance: `source_id` and `timestamp` on every `Comment` and email message; `path` on attachments; `line` on WhatsApp and imessage-exporter TXT.

### 9e. Known failure modes

1. Slack thread replies emitted twice or detached from their parents (the central research finding); orphan replies when the parent predates the export window.
2. Slack user ids never resolved (bots, deleted users, external Slack Connect users missing from `users.json`): render as `@U0123` with warning `unresolved_users` and a count.
3. `.msg` with RTF-only body encapsulating HTML; `.msg` with embedded `.msg` attachments three levels deep; `.msg` Unicode vs ANSI (`001E` vs `001F`) property variants.
4. EML with a wrong `charset`, base64 bodies, `format=flowed` plain text (unwrap soft breaks), and `Content-Transfer-Encoding: 8bit` with raw UTF-8.
5. Quoted-reply detection removing real content (a user quoting a contract clause with `>`); `strip` must require a reply-header line, not `>` alone.
6. WhatsApp day-first vs month-first ambiguity; iOS invisible characters; multi-line messages with timestamps inside the text (a quoted timestamp line that matches the pattern: require the sender name to be a known participant seen in the first 50 lines or the line to be preceded by a blank boundary).
7. Discord replies referencing messages outside the export.
8. Telegram `text` as an array with nested `blockquote` entities and `pre` with language.
9. ICS with `RRULE` until far future (cap) and `EXDATE`s; floating times with no `TZID`; Outlook ICS with `X-MICROSOFT-CDO-ALLDAYEVENT`.
10. Teams HTML with nested tables for layout.
11. MBOX files of 5 GB (stream; `mailbox.mbox` is lazy but builds a TOC; acceptable); messages with `From ` inside bodies unescaped (corrupt split: detect by header validity and merge back).
12. Attachments that are themselves archives or emails (recursion limits from section 12).
13. Chat exports containing injection text; flagged, not altered.

### 9f. Fixtures

1. `comm/eml-html-with-attachments`: HTML body with inline `cid:` image, a quoted history from Gmail, a signature, a PDF attachment, a forwarded `message/rfc822` part, a calendar invite part.
2. `comm/eml-thread-folder`: 8 `.eml` files forming two threads via `References`, one with a broken chain (subject matching), `format=flowed` plain text.
3. `comm/mbox-gmail-takeout`: 30 messages with labels and a `>From ` escaped body.
4. `comm/msg-outlook`: generated with `extract-msg`'s test corpus licensing permitting or synthesized with a CFB writer: RTF-encapsulated HTML body, two attachments, one embedded `.msg`, transport headers.
5. `comm/slack-export`: two channels and one DM over 5 days, threads whose replies land on later days, an orphan reply, a `thread_broadcast`, bot messages, a file share, reactions, an unresolved external user, `blocks` rich text with a list.
6. `comm/discord-dce-json` and `comm/discord-dce-html`: replies, embeds, attachments, a thread channel, a reaction; plus a data-package `messages.csv`.
7. `comm/teams-graph-json`: channel messages with `replyToId` threads and `<at>` mentions.
8. `comm/whatsapp-locales`: four inputs (Android en-GB day-first, iOS en-US month-first with narrow NBSP, German, Android with media folder) with one expected output each.
9. `comm/imessage-exporter-txt`: with tapbacks, replies, an attachment, an edited message; `comm/imessage-chatdb` (synthetic db built in `fixtures/_gen`, `experimental`).
10. `comm/sms-backup-xml`: sms and mms with two conversations.
11. `comm/telegram-result-json`: entities array, reply, forwarded, poll, service messages, a sticker.
12. `comm/ics-recurring`: weekly RRULE with EXDATE, an all-day event, a floating-time event, a VTODO.
13. `comm/vcf-mixed-versions`: 2.1, 3.0, 4.0 cards with a photo.

### 9g. Acceptance thresholds

Email: headers table exact, text_similarity 0.97 on the body, attachments count exact, quote classification exact (the fixture labels which paragraphs are history). Chat exports: message count exact, thread parentage exact, author resolution exact, timestamps exact to the second, text_similarity 0.98. ICS: event count after expansion exact, table_cell_accuracy 0.98. VCF: contact count exact, table_cell_accuracy 0.98.

### 9h. Options

`options.comm`: `body` (`auto`, `html`, `text`), `strip_quotes` (`mark`, `strip`, `keep`), `all_headers` (false), `threads` (`combined`, `separate`), `max_messages` (5000), `label_filter`, `channels` (list), `name_field`, `include_system` (false), `include_reactions` (false), `merge_consecutive` (profile-dependent), `date_order` (`auto`, `dmy`, `mdy`), `contacts_vcf` (path), `ics_range`, `ics_max_events` (2000), `attachments` (`convert` default, `list`, `skip`), `max_attachment_depth` (3).

### 9i. Phase

Phase 1: EML, MSG (olefile path), MBOX, thread reconstruction, ICS, VCF, attachments recursion. Phase 3: Slack, Discord, Teams, WhatsApp, iMessage (exporter formats), SMS XML, Telegram. `chat.db` direct: Phase 3, `experimental`, self-host. PST: Phase 5 via the LGPL extra.

---

## 10. data

### 10a. Scope and input matrix

| Input | Detection | Sub-converter |
|---|---|---|
| `.json`, `.jsonl`/`.ndjson`, `.json5`, `application/json`, `application/x-ndjson` | Magika `json`, content | `JsonConverter` |
| `.yaml`, `.yml` | Magika `yaml` | `YamlConverter` |
| `.xml`, `.xsd`, `.rss`-like generic XML, `.svg` (as XML), `.plist` | Magika `xml`, `<?xml` | `XmlConverter` (feeds go to section 7, XBRL/JATS/USPTO/HL7/MusicXML/KML to section 12 by root element) |
| `.toml`, `.ini`, `.cfg`, `.properties`, `.env` (keys only) | content | `TomlIniConverter` |
| `.parquet`, `.arrow`, `.feather`, `.orc` | magic `PAR1`, `ARROW1` | `ColumnarConverter` |
| `.sqlite`, `.db`, `.sqlite3`, `application/vnd.sqlite3` | magic `SQLite format 3` | `SqliteConverter` |
| `.duckdb` | magic | `SqliteConverter` via DuckDB (MIT) when `intomd[duckdb]` installed |
| Database connection strings (`postgres://`, `mysql://`, `mongodb://`, `jdbc:`, `Server=...;Database=`) | pattern | refused on public (`connection_string_refused`), self-host `intomd[db]` Phase 5 |
| API responses (JSON with `data`/`items`/`results` arrays, pagination keys) | JSON shape | `JsonConverter` with API heuristics |
| Survey exports: Typeform CSV/XLSX, Google Forms responses CSV, SurveyMonkey XLSX, Qualtrics CSV (3 header rows) | header patterns | `SurveyConverter` on top of section 2 CSV/XLSX |
| HDF5, NetCDF, `.npy`/`.npz`, `.mat`, `.sav`/`.dta` | magic | `intomd[sci]` extra (h5py BSD, netCDF4 MIT, numpy BSD, pyreadstat Apache); Phase 5; schema and shape summary only |

### 10b. Libraries

`json` (stdlib) with `orjson` (Apache/MIT) optional for speed; `json5` (Apache) for `.json5`; `pyyaml` with `yaml.safe_load` only (never `load`); `lxml` with `resolve_entities=False`, `no_network=True`, `huge_tree=False` (XXE and billion-laughs protection; also set `XMLParser(load_dtd=False)`); `tomllib` (stdlib) and `configparser`; `pyarrow` (Apache-2.0) for Parquet/Arrow/ORC with `pyarrow.parquet.ParquetFile` for metadata without a full read; `sqlite3` stdlib read-only; `pandas` optional for statistics (fallback to pure-Python stats on a sample).

### 10c. Build steps

JsonConverter:

1. Parse. On failure, try JSON Lines (one object per line), then `json5`, then a lenient repair (`json-repair`, MIT) only with `options.data.repair=true` and warning `json_repaired`. Enforce `max_bytes` (default 50 MB) by sampling (step 5) rather than refusing.
2. Shape analysis: compute a schema summary by walking up to `options.data.schema_sample` (10,000) values per path: for each JSON pointer path, record types seen, counts, null rate, example values (3), and for arrays the element type distribution and length stats. Detect records (arrays of objects with over 60 percent shared keys) and tables (records whose values are all scalars).
3. Emit: H1 `<filename>`, a `Paragraph` summary (top-level type, size, record count, depth), `Heading(level=2, text="Schema")` with a `Table` (path, type(s), count, null %, example) limited to `schema_max_paths` (200) with a note on the remainder, then `Heading(level=2, text="Data")`: tables of records as `Table` blocks (with the six-column rule delegated to the renderer; nested objects inside records flattened by dot path to `schema_depth` 3 and deeper values rendered as compact JSON strings), scalar maps as a two-column `Table`, and anything else as pretty-printed JSON in a `Code(language="json")` block, sampled.
4. API response heuristics: when top-level keys include one of `data`, `items`, `results`, `records`, `hits`, `edges` (GraphQL, unwrap `node`), `value` (OData), treat that array as the primary table and the siblings (`total`, `page`, `next`, `cursor`, `meta`) as a metadata `Table`. Error envelopes (`error`, `errors[]`) render first with a warning `api_error_payload`.
5. Sampling for large files: keep the first `head_rows` (100), a stratified middle sample, and the last `tail_rows` (20) of any record array over `max_rows` (default 1,000), with a marker row `... (N rows omitted)` and warning `rows_sampled`; the full array is written as a JSON sidecar when `options.data.full_sidecar=true` (default on CLI, off public). Streaming parse with `ijson` (BSD) for files over 20 MB so memory stays bounded.
6. Pretty-print rules: 2-space indent, keys in original order, strings not re-escaped beyond JSON requirements, numbers verbatim (never float-round: parse with `parse_float=str` when emitting, so `1.10` stays `1.10`), long strings over 500 chars truncated in tables with a `…` and full in sidecar.
7. Provenance: `path` = JSON pointer for every block (tables carry the array pointer; rows are addressable as `<pointer>/<index>`).

YamlConverter:

8. `safe_load_all` for multi-document files; each document becomes an H2 section. Same shape analysis and rendering as JSON. Preserve comments by also keeping the raw text as a `Code(language="yaml")` block in `full` (comments are often the documentation). Anchors and aliases are expanded by the loader; note `metadata.anchors_expanded=true` when any `&` appears. Kubernetes manifests (`apiVersion` + `kind`) render a header table (kind, name, namespace) per document. `options.data.yaml_tags="ignore"` makes unknown `!tags` load as strings instead of failing.

XmlConverter:

9. Parse securely (10b). Dispatch by root element and namespace to section 12 converters (XBRL `xbrl`/`xbrli`, JATS `article`, USPTO `us-patent-grant`, HL7 `ClinicalDocument`, MusicXML `score-partwise`, KML `kml`, SVG `svg`, plist `plist`, RSS/Atom to section 7). Otherwise: build a structural summary (`Table`: element path, count, attributes, text sample) up to 200 paths, detect record-like repeats (an element repeated over 5 times with the same child set becomes a `Table` with child elements and attributes as columns), and emit the raw XML pretty-printed as `Code(language="xml")` sampled to `max_rows` repeats. Mixed-content documents (DocBook, TEI, DITA, XHTML) are converted by a lightweight mapping (`title`, `para`, `section`, `list`, `table`) with the rest as `Raw`; DocBook via Pandoc when present. plist: `plistlib` to a dict, then the JSON path. SVG: `<title>`, `<desc>`, and `<text>` nodes as paragraphs plus a summary; the image itself goes to the OCR pipeline only on request.
10. Provenance: `path` = XPath (`/root/items/item[12]`); `line` from `sourceline`.

TomlIniConverter:

11. TOML via `tomllib`, INI via `configparser` (with `interpolation=None`, `strict=False`, case preserved), `.properties` via a 20-line parser, `.env` via a key parser with values redacted (section 8 rule). Emit H1 filename, one `Table` per section (key, value, comment when the preceding line is a comment), nested TOML tables as H2/H3 by dotted path, arrays of tables as `Table`s. Keep the raw file as `Code` in `full`. Secrets scanning applies.

ColumnarConverter:

12. Open with `pyarrow.parquet.ParquetFile` (or `ipc.open_file`/`orc.ORCFile`). Read metadata only: schema (name, type, nullable, nested structure), row count, row groups, compression, created-by, key-value metadata (pandas metadata JSON decoded and summarized). Emit H1 filename, summary `Paragraph`, `Heading(level=2, text="Schema")` `Table`, `Heading(level=2, text="Statistics")` `Table` from row-group statistics when present (min, max, null count, distinct when available) without reading data, then `Heading(level=2, text="Sample rows")` with `head_rows` from the first row group and `tail_rows` from the last, reading only those row groups and only up to `max_cols` (50) columns (warn `columns_truncated`). Partitioned datasets (a directory with `_metadata` or Hive-style `key=value` subdirectories) are summarized at the dataset level with the partition keys and file count, sampling two files. Never load the full table. Nested columns (struct, list, map) render as JSON strings in sample rows. Decimal and timestamp types render with their logical type (timezone included). Provenance: `path` = `<file>:<row_group>:<row>` for samples, column name for schema rows.

SqliteConverter:

13. Open read-only immutable (copy to temp if on a read-only mount with a hot journal). Refuse databases over `max_bytes` (default 2 GB) for full stats, but still list schema. Read `sqlite_master`: tables, views, indexes, triggers with their `sql`. Emit H1 filename, `Heading(level=2, text="Tables")` with a summary `Table` (name, rows via `SELECT COUNT(*)` capped by a 5 s statement timeout using `set_progress_handler`, columns, size estimate from `dbstat` when available), then per table `Heading(level=3)` with the column `Table` (`PRAGMA table_info` plus `foreign_key_list`), index list, and `Heading(level=4, text="Sample")` with `head_rows` via `SELECT * LIMIT` and `tail_rows` via `ORDER BY rowid DESC` (or primary key), with per-column simple stats (null count, distinct count, min, max for numeric and date-like text) computed only when the table has under `stats_max_rows` (1,000,000) rows. Views and triggers get their `sql` as `Code`. `options.data.tables` restricts the set; `options.data.sql` (self-host only) runs a user-provided read-only query (`PRAGMA query_only=1`) and renders the result. BLOB columns render as `<blob N bytes>`; FTS virtual tables and WAL mode handled. Provenance: `path` = `<table>` / `<table>/rowid=<n>`.

Connection strings:

14. `can_handle` 1.0 for the patterns; on public always stub with `connection_string_refused` ("Export the data to CSV, Parquet, or SQLite and convert that file"). Self-host with `intomd[db]` (SQLAlchemy MIT, drivers per user) in Phase 5: introspect schema, sample rows per table with `LIMIT`, same rendering as SQLite, `statement_timeout` enforced, read-only transaction, credentials never written to output or logs (the frontmatter `source` is the host and database only).

SurveyConverter:

15. Runs after the CSV/XLSX converter produces a `Table`; triggered when `options.data.survey="auto"` and the header row looks like questions (over 50 percent of headers over 25 chars or ending with `?`, or known tool columns: Typeform `#`, `Start Date (UTC)`, `Submit Date (UTC)`, `Network ID`; Google Forms `Timestamp` first column with question headers; Qualtrics three header rows with `ImportId` JSON in row 3; SurveyMonkey two header rows with `Respondent ID`, `Collector ID`). Emit `Heading(level=2, text="Questions")` as a numbered `List` of the full question texts (Q1..Qn) with detected type (single choice when distinct values under 10 and short, multi-select when values contain the tool's separator, numeric scale, free text, date), then per question a `Table` of answer frequencies for closed questions (value, count, percent) and a sampled `List` of free-text responses (up to `survey_text_sample` 50 per question) with respondent ids, and finally the raw responses `Table` with headers abbreviated to `Q1..Qn` (the legend is the questions list) so the wide-table rule does not destroy readability. Respondent metadata columns (timestamps, IPs, emails) are moved to the sidecar and the body carries only a respondent index unless `options.data.survey_pii=true`; warning `pii_columns_removed` with the column names.

### 10d. IR blocks and provenance

`Heading`, `Paragraph`, `Table`, `Code`, `List`, `Raw`. Mandatory provenance: `path` (pointer, XPath, table/row, column) on every block; `line` on XML and config blocks when available.

### 10e. Known failure modes

1. XXE and entity expansion in XML (security fixture must pass without network or expansion).
2. YAML `!!python/object` tags (safe_load refuses; the converter must not crash and must warn `yaml_unsafe_tags`).
3. JSON numbers losing precision (`1.10`, 19-digit ids, `1e400`); keep as strings in tables.
4. Deeply nested JSON (depth 200) causing recursion errors: iterative walk with `max_depth` and `depth_truncated` warning.
5. Huge single-line JSON (50 MB) and JSONL with a trailing partial line.
6. Parquet with 3,000 columns or 10,000 row groups; sampling must stay O(sample).
7. SQLite with a table of 500 million rows (`COUNT(*)` timeout → `rows ≥ N (estimated)` from `sqlite_stat1` or `max(rowid)`), encrypted SQLCipher files (magic not matching → `sqlite_encrypted`), corrupted files.
8. Survey exports where the question header is in row 2 (Qualtrics) and row 1 is an id; multi-select values with `;` or `, ` separators.
9. XML with multiple namespaces and default namespace changes mid-document.
10. INI files with duplicate keys and no sections.
11. API responses with mixed error and data.
12. BOM-prefixed JSON; JSON with comments (treat as JSON5).

### 10f. Fixtures

1. `data/json-api-response`: `{data: [...200 records with nested address], meta: {page, next}}` plus an error-envelope variant.
2. `data/json-nested-deep-and-precise`: depth 60, big ints, `1.10`, unicode keys, 1,500 records to trigger sampling.
3. `data/jsonl-logs-like`: 5,000 lines with a partial last line.
4. `data/yaml-k8s-multidoc`: three manifests with anchors and comments.
5. `data/yaml-unsafe-tags`: a document with `!!python/object`.
6. `data/xml-generic-records` and `data/xml-xxe-attack` (must produce no entity content and no network call) and `data/xml-docbook-chapter`.
7. `data/toml-ini-env`: `pyproject.toml`, a `.ini` with duplicates, a `.env` with secrets.
8. `data/parquet-wide-partitioned`: a Hive-partitioned dataset generated by `fixtures/_gen` with 40 columns, nested struct, decimals, timestamps with tz, 3 row groups.
9. `data/sqlite-app-db`: 6 tables with FKs, a view, a trigger, an FTS table, a BLOB column, 200k rows in one table; plus an encrypted-looking variant.
10. `data/survey-typeform` and `data/survey-google-forms` and `data/survey-qualtrics`: with multi-select, scales, free text, and PII columns.
11. `data/connection-string`: `input.txt` containing `postgres://user:pass@host/db`; expected stub.

### 10g. Acceptance thresholds

Schema tables: table_cell_accuracy 0.98; record tables: cell accuracy 0.99 on the sampled rows (exact row selection is deterministic); element_counts exact; provenance 1.0; security fixtures: exact expected output and zero network calls (harness asserts via the SSRF guard's call log).

### 10h. Options

`options.data`: `max_bytes` (50 MB JSON/YAML/XML, 2 GB SQLite/Parquet metadata), `max_rows` (1000), `head_rows` (100), `tail_rows` (20), `max_cols` (50), `schema_sample` (10000), `schema_max_paths` (200), `schema_depth` (3), `max_depth` (64), `full_sidecar` (CLI true), `repair` (false), `yaml_tags` (`ignore`), `tables` (list), `stats` (true), `stats_max_rows` (1e6), `sql` (self-host), `survey` (`auto`, `on`, `off`), `survey_text_sample` (50), `survey_pii` (false), `pretty` (true).

### 10i. Phase

Phase 1 for all of JSON, YAML, XML, TOML/INI, Parquet/Arrow, SQLite, surveys, connection-string refusal. DuckDB and live database introspection: Phase 5. Scientific formats: Phase 5.

---

## 11. notes-apps

### 11a. Scope and input matrix

| Input | Detection | Sub-converter |
|---|---|---|
| Notion export zip or folder: `.md` files with ` <32-hex>` suffixes, `.csv` databases (and `_all.csv`), nested folders, `index.html` in HTML exports | name pattern `^(.+) ([0-9a-f]{32})\.(md|csv|html)$` | `NotionExportConverter` |
| Obsidian vault: a folder containing `.obsidian/` or many `.md` with `[[wikilinks]]` | structure | `ObsidianVaultConverter` |
| Evernote `.enex` | root `<en-export>` | `EnexConverter` |
| OneNote: only via export (`.docx`/`.pdf` from OneNote's export, or `.onepkg`/`.one` refused), or Obsidian Importer output | extension | route to section 2 or 1; `.one` → stub `onenote_export_required` |
| Apple Notes: export via the Exporter app (`.html`, `.md`, `.enex`) or `osascript` dump; `.html` folder with `Attachments/` | structure | `AppleNotesExportConverter` (HTML folder) or ENEX path |
| Confluence: space export HTML (`index.html`, `attachments/`, `styles/`), XML export (`entities.xml` in zip), or Cloud "Export to Word/PDF" | structure | `ConfluenceExportConverter` (HTML and XML) |
| Jira: issue export CSV/XML (`<rss><channel><item><key>`), JSON from the REST API | content | `JiraExportConverter` |
| Trello: board JSON export (`cards[]`, `lists[]`, `actions[]`, `checklists[]`) | keys | `TrelloExportConverter` |
| Asana: project CSV export (`Task ID,Created At,...`) or JSON | header | `AsanaExportConverter` |
| Kindle `My Clippings.txt` | first lines and `==========` separators | `KindleClippingsConverter` |
| Readwise CSV export (`Highlight,Book Title,Book Author,Amount of Highlights,...` or the newer `Title,Author,Highlight,Note,Location,Date`) | header | `ReadwiseConverter` |
| Browser bookmarks: Netscape HTML (`<!DOCTYPE NETSCAPE-Bookmark-file-1>`), Chrome `Bookmarks` JSON, Firefox `.jsonlz4` (self-host, `lz4` BSD) | content | `BookmarksConverter` |
| Logseq graph, Roam JSON, Bear/Ulysses textbundle, Joplin JEX, Standard Notes JSON, Google Keep Takeout (`Keep/*.json`) | structure | Phase 5 with a shared "notes bundle" model; Keep and Roam are small and ship in Phase 3 |

### 11b. Libraries

Markdown parser from section 4; `lxml` for ENEX and Confluence; `csv`; `zipfile`; `python-frontmatter` (MIT) for Obsidian; `lz4` (BSD) optional for Firefox; the HTML-to-IR module for Confluence and Apple Notes HTML; `dateutil` for Kindle dates in many locales.

### 11c. Build steps

NotionExportConverter:

1. Unpack (archive rules from section 12). Walk files; strip the ` <32-hex>` id suffix from every file and folder name into `metadata.notion_id`; keep a map `id → clean relative path`.
2. Each `.md` page: parse with the Markdown parser. Fix links: Notion exports links as URL-encoded relative paths with the id suffix (`[Child](Parent%20abc.../Child%20def....md)`); decode, resolve through the id map, and rewrite to the clean path (or to an internal anchor when the output is combined). External links untouched. Rewrite image references the same way (images live in the page's folder).
3. Callouts: Notion's Markdown export emits callouts as `<aside>` HTML blocks (`<aside>\n💡 text\n</aside>`); convert to `Quote(role="callout", icon=💡)` which the renderer prints as an Obsidian-style `> [!note]` callout in `full` and a plain blockquote in `compact`. Toggle blocks come as `<details><summary>`; convert to a heading plus body as in section 5. Equations come as `$$`; preserved. Embedded videos and bookmarks come as bare links; keep.
4. Databases: a database page is a `.csv` (and the `_all.csv` variant includes all views' rows; prefer `_all.csv` when both exist and dedupe by the first column). Convert to a `Table` with the first column being the title property linking to the row's page `.md` when it exists (sub-pages of database rows live in a same-named folder). Property types inferred from values (dates, multi-select with `, `, checkboxes `Yes`/`No`, relations as page names, URLs). Database pages inline in a parent page (`[Untitled Database](...csv)` links) are expanded in place as the table when `options.notes.inline_databases=true` (default true) rather than linked.
5. HTML exports (which carry comments and more styling): parse with the HTML-to-IR module using Notion's classes (`.page-title`, `.callout`, `.toggle`, `.collection-content` tables, `.comment` blocks → `Comment`). Prefer HTML over Markdown when both are present and `options.notes.prefer_html=true` (default false; Markdown is cleaner, but set true when comments matter).
6. Page metadata: Notion writes properties as a leading block of `Key: value` lines after the H1 in Markdown exports; parse the first contiguous `^[A-Z][\w ]+: ` run into frontmatter (`created`, `tags`, `status`, etc.).
7. Output: a `DocumentSet` mirroring the clean folder structure (default) or combined with H1 per top-level page and nested pages as deeper sections by folder depth. Index page listing the tree in both modes.
8. Provenance: `path` = clean relative path plus line.

ObsidianVaultConverter:

9. Walk the vault, respecting `.obsidian/app.json` `userIgnoreFilters` and skipping `.obsidian/`, `.trash/`, and `options.notes.exclude` globs. Index every note by filename stem (case-insensitive, with alias support from frontmatter `aliases`) and every attachment.
10. Per note: parse frontmatter (kept verbatim under `metadata.frontmatter` and merged into output frontmatter as section 4 step 18), then Markdown with Obsidian extensions: `[[Note]]`, `[[Note|alias]]`, `[[Note#Heading]]`, `[[Note#^block]]`, `![[embed]]` (notes, images, PDFs with `#page=`), `^block-id` anchors, `%%comments%%` (dropped in output, counted), tags `#tag` and nested `#a/b` (collected into `metadata.tags`), callouts `> [!type]` (kept as `Quote(role="callout")`), dataview inline fields `key:: value` (collected into `metadata.fields`), `==highlight==`, task lists with custom states.
11. Wikilink resolution: `options.notes.wikilinks` = `resolve` (default: rewrite to a relative Markdown link to the resolved note's output path, with the display text preserved), `text` (replace with the display text only), `keep` (leave `[[...]]` syntax). Unresolved links are kept as text with warning `unresolved_wikilinks` and a count (listed in sidecar). Note embeds `![[Note]]` are expanded inline (depth 3, cycle-safe) when `options.notes.expand_embeds=true` (default false; default renders as a link), heading and block embeds extract just that section.
12. Dataview and Templater code blocks (` ```dataview `, `<% %>`) are kept as `Code` with their language; they are not executed. Canvas files (`.canvas` JSON) render nodes as a `List` of cards with text and links to referenced notes, edges as a `Table`. Excalidraw `.excalidraw.md` files render their embedded text elements only.
13. Output: `DocumentSet` mirroring the vault (default) or combined; backlinks index (`metadata.backlinks` per note) computed from the link graph and optionally rendered as a trailing `Heading(level=2, text="Backlinks")` list when `options.notes.backlinks=true`.

EnexConverter:

14. Iterparse `<note>` elements (ENEX files can be gigabytes). For each: `<title>`, `<created>`/`<updated>` (`YYYYMMDDTHHMMSSZ`), `<tag>` list, `<note-attributes>` (`author`, `source-url`, `latitude`, `reminder-time`), `<content>` as a CDATA ENML document. Parse ENML as XHTML through the HTML-to-IR module with ENML specifics: `<en-media hash= type=>` resolved to the `<resource>` whose `<data>` MD5 matches (`<resource-attributes><file-name>`), written to assets and emitted as `Image` or attachment `Link` (PDFs converted via the registry when `attachments="convert"`); `<en-todo checked=>` to task list items; `<en-crypt>` kept as `(encrypted content)` with warning `encrypted_content`; `<div style="...-en-codeblock:true">` to `Code`. Highlighted text (`background-color` spans) becomes `==highlight==` in `full`.
15. Output: one document per note in a `DocumentSet` named by sanitized title plus a short hash, with frontmatter (`title`, `created`, `updated`, `tags`, `source_url`, `author`), or combined. Notebook name is not in ENEX (one file per notebook by convention): take it from the filename into `metadata.notebook`.

AppleNotesExportConverter:

16. HTML folder exports (from Exporter or Notes' own "Export as PDF" is a PDF): each `.html` is a note with `<title>`, body in `<div>`s with attachments in a sibling folder. Convert via the HTML-to-IR module, map `<ul class="Apple-dash-list">` to lists, checklists (`<ul class="checklist">`) to tasks, tables normal. Created and modified from file mtimes (Apple Notes HTML carries no dates) with warning `dates_from_filesystem`. Folder structure → `DocumentSet` structure. ENEX exports from Apple Notes go through the ENEX path.

ConfluenceExportConverter:

17. HTML space export: parse `index.html` for the page tree (`<ul>` nested links), then each page HTML: title from `#title-text`, body from `#main-content`, breadcrumbs from `#breadcrumbs`, labels from `.aui-label`, attachments from `#attachments` and the `attachments/<pageId>/` folder, comments from `.comment` (`→ Comment`). Confluence macros survive as HTML: code macro (`.code.panel pre` with `data-syntaxhighlighter-params` language), info/note/warning/tip panels (`.confluence-information-macro` → `Quote(role="callout")`), expand (`.expand-container` → heading plus body), table of contents (dropped), Jira issue macros (`.jira-issue` → `Link`), status lozenges (`.status-macro` → text), page properties tables, children macro (dropped; the tree index replaces it), attachments macro. Table layout (`.confluenceTable` with `th.confluenceTh`) → `Table` with spans. Page tree → output structure and heading depth in combined mode.
18. XML export (`entities.xml`): parse `<object class="Page">` with `<property name="title">`, `<property name="bodyContents">` referencing `BodyContent` objects holding storage-format XHTML (`<ac:structured-macro>`, `<ri:attachment>`, `<ac:link>`); map the storage format with the same macro rules (`ac:name` instead of classes); versions: keep only the current (`<property name="contentStatus">current` and no `originalVersion`), with `metadata.version` and history count. Spaces, parents (`<property name="parent">`) build the tree. Attachments in `attachments/<contentId>/<attachmentId>/<version>`.

JiraExportConverter:

19. CSV export: columns `Issue key`, `Summary`, `Issue Type`, `Status`, `Priority`, `Assignee`, `Reporter`, `Created`, `Updated`, `Description`, repeated `Comment` columns (each `date;author;text`), `Labels` repeated, `Sprint`, custom fields. Emit H1 project (from key prefix), a summary `Table` (key, type, status, priority, assignee, summary), then per issue `Heading(level=2, text="KEY-123: summary")`, a metadata `Table`, `Description` (Jira wiki markup → Markdown: `h1.`, `*bold*`, `_italic_`, `{code:lang}`, `{noformat}`, `{quote}`, `||header||`, `|cell|`, `[link|url]`, `!image.png!`, `{color}` stripped, `#` and `*` lists), and comments as `Comment` blocks. XML export: `<item>` with `<key>`, `<summary>`, `<description>` (HTML), `<comments><comment author= created=>` (HTML), `<customfields>`; use the HTML-to-IR module. REST JSON: `issues[].fields` with ADF (`description.content[]` document) → walk ADF node types (`paragraph`, `heading`, `bulletList`, `orderedList`, `codeBlock`, `table`, `panel`, `mention`, `inlineCard`, `mediaSingle`) to IR; `comment.comments[]` likewise.

TrelloExportConverter:

20. Board JSON: H1 board name with `desc`; per list (in `pos` order, archived lists under `Heading(level=2, text="Archived lists")` when `include_archived`) `Heading(level=2)`; per card `Heading(level=3, text=name)` with a metadata line (labels, members, due, closed), `desc` as Markdown, checklists (`checklists[]` matched by `idCard`) as task lists with `state`, attachments as `Link`s, custom fields, and comments from `actions[]` of type `commentCard` as `Comment` blocks (chronological). Cards with no description and no checklist collapse to a single list item under the list heading when `options.notes.trello_compact=true` (default true in `compact`).

AsanaExportConverter:

21. CSV: `Task ID, Created At, Completed At, Last Modified, Name, Section/Column, Assignee, Assignee Email, Start Date, Due Date, Tags, Notes, Projects, Parent task, Blocked By, Blocking` plus custom fields. Group by `Section/Column` as H2, tasks as H3 with a metadata table and `Notes` as Markdown-ish text, subtasks (`Parent task` set) nested under their parent as a `List`, dependencies as `Link`s by task name. Email columns go to the sidecar (PII rule). JSON (API export): `data[]` with `notes`, `html_notes` (prefer, through the HTML-to-IR module), `memberships[].section.name`, `subtasks` fetched or absent, `stories` as comments.

KindleClippingsConverter:

22. Split on lines of `==========`. Each clipping: line 1 title and author `Title (Author)` (author in the last parentheses; titles can contain parentheses, so take the last group), line 2 `- Your Highlight on page 12 | Location 345-350 | Added on Monday, March 4, 2024 10:15:22 PM` (types: Highlight, Note, Bookmark, Clip; localized variants: `- La subrayado en la página`, `- Ihre Markierung bei Position`, `- Votre surlignement`; parse with a per-language table and `dateutil` with `dayfirst` from the detected language), blank line, text. Group by book (normalized title plus author), sort by location then page, attach a `Note` clipping to the immediately preceding highlight with the same location as `metadata.note`. Dedupe overlapping highlights (Kindle keeps the shorter earlier version when a user extends a highlight: drop a highlight whose text is a prefix of or contained in the next highlight with an overlapping location range) with a count in `clippings_deduped`. Emit H1 `Kindle clippings (N books, M highlights)`, H2 per book with author and count, each highlight as a `Quote` with a trailing `(p. 12, loc. 345)` and the note indented beneath. Bookmarks listed as a `List` per book. Clip limit markers (`<You have reached the clipping limit for this item>`) counted and warned `kindle_clip_limit`. Provenance: `line`, `source_id` = location.

ReadwiseConverter:

23. Detect columns by header set (both the legacy and current exports). Group by `Book Title`/`Title`, each highlight a `Quote` with `Note` beneath, `Location`/`Page`, `Highlighted at`/`Date`, `Tags`, `Color`, `Book Author`/`Author`, `Category` (books, articles, tweets, podcasts) as H2 grouping above book when mixed, `Source URL` as a link on the book heading. Same dedupe as Kindle. Readwise Markdown exports (one `.md` per book with their template) are already Markdown and route to section 4.

BookmarksConverter:

24. Netscape HTML: walk `<DL><DT><H3>` folders recursively and `<A HREF ADD_DATE LAST_MODIFIED ICON TAGS>` entries; emit folders as nested headings (H2..H6, deeper folders as nested lists) and bookmarks as a `List` of `Link`s with the added date and tags; `ICON` data URIs dropped. Chrome `Bookmarks` JSON: `roots.bookmark_bar/other/synced` with `children[]` of `type: folder|url`, `date_added` in WebKit microseconds since 1601 (convert). Firefox `bookmarkbackup-*.jsonlz4`: mozLz4 header (`mozLz40\0`) then `lz4.block.decompress`; the JSON tree has `children`, `uri`, `dateAdded` in microseconds. Dedupe identical URLs across folders only when `options.notes.dedupe_bookmarks=true`. Optionally fetch each bookmark through section 5 with `options.notes.fetch_bookmarks=true` (self-host; respects caps and robots; one document per bookmark in a `DocumentSet`).

Google Keep and Roam (Phase 3):

25. Keep Takeout: `Keep/*.json` with `title`, `textContent`, `listContent[{text, isChecked}]`, `labels[]`, `color`, `isArchived`, `isPinned`, `createdTimestampUsec`, `userEditedTimestampUsec`, `attachments[{filePath, mimetype}]`; one document per note with frontmatter; archived and trashed under their own folders. Roam JSON: pages with nested `children[{string, uid, children, create-time}]` blocks → nested `List` items with `((uid))` block references resolved to the referenced string and `[[Page]]` links handled like Obsidian wikilinks.

### 11d. IR blocks and provenance

`Heading`, `Paragraph`, `List` (tasks), `Table`, `Quote` (callouts, highlights), `Code`, `Image`, `Link`, `Comment` (Notion HTML, Confluence, Jira, Trello), `Equation`, `Raw`. Mandatory provenance: `path` (relative file path) and `line` where the source is text; `source_id` for Jira keys, Trello card ids, Kindle locations, Notion ids.

### 11e. Known failure modes

1. Notion callouts left as `<aside>` HTML (the research's named loss); toggles as `<details>`; database links to `.csv` left dangling; URL-encoded links with ids unresolved; duplicate pages (same title, different ids) collapsing into one path (append the short id when names collide).
2. Notion exports where `_all.csv` and the view `.csv` both exist (dedupe) and where a database has sub-page folders.
3. Obsidian: wikilinks to notes with the same stem in different folders (resolve by Obsidian's rule: shortest path when unique, else the first in alphabetical path order with warning `ambiguous_wikilink`); links with `#headings` whose heading text contains Markdown; `%%` comments spanning lines; frontmatter that is not valid YAML (keep raw, warn).
4. ENEX files of 4 GB with base64 PDFs (iterparse, streaming decode to assets, never hold the resource in memory).
5. ENEX `en-media` hash mismatch (resource missing) → warning `missing_resource`.
6. Confluence macros that carry the real content in `ac:parameter` (e.g. `code` body in `ac:plain-text-body` CDATA) and nested layout sections (`ac:layout`), page versions duplicated in XML exports.
7. Jira CSV with multiple `Comment` columns and multiline cells; wiki markup tables with `||` headers; ADF `mediaSingle` with no accessible file.
8. Trello JSON with 10,000 actions (filter to `commentCard` only while streaming).
9. Kindle clippings in a non-English locale and with the clipping limit notice; titles with parentheses; duplicate highlights after extension.
10. Firefox lz4 without the extra; stub with `extra_required`.
11. Apple Notes HTML with no dates.
12. Bookmarks HTML with 50,000 entries (list caps apply; `max_rows`).

### 11f. Fixtures

1. `notes/notion-export-md`: nested pages, a database with `_all.csv` and sub-page folder, callouts, toggles, equations, internal links, an image, two pages with the same title.
2. `notes/notion-export-html`: the same workspace as HTML with comments.
3. `notes/obsidian-vault`: 30 notes with frontmatter, aliases, ambiguous stems in two folders, heading and block links, embeds, callouts, dataview fields, a canvas, a `%%` comment, an invalid-frontmatter note, attachments, `.obsidian/app.json` with an ignore filter.
4. `notes/enex-notebook`: 12 notes with tags, todos, an image resource, a PDF resource, an `en-crypt` block, highlights, a missing resource.
5. `notes/apple-notes-html`: a folder export with a checklist and an attachment.
6. `notes/confluence-html-space` and `notes/confluence-xml-space`: pages with code, info panels, expand, a Jira macro, a table with spans, comments, attachments, two versions of one page (XML).
7. `notes/jira-csv`, `notes/jira-xml`, `notes/jira-json-adf`.
8. `notes/trello-board-json`: 3 lists, 15 cards, checklists, comments, an archived list.
9. `notes/asana-csv`: sections, subtasks, dependencies, custom fields, emails.
10. `notes/kindle-my-clippings`: English and Spanish entries, notes attached to highlights, an extended highlight pair, a bookmark, the clip-limit notice, a title with parentheses.
11. `notes/readwise-csv-legacy` and `notes/readwise-csv-current`.
12. `notes/bookmarks-netscape`, `notes/bookmarks-chrome-json`, `notes/bookmarks-firefox-jsonlz4` (`requires: [lz4]`).
13. `notes/keep-takeout` and `notes/roam-json` (Phase 3).

### 11g. Acceptance thresholds

Notion and Obsidian: link resolution exact (every expected link target), heading_retention 0.98, text_similarity 0.98, callout count exact, element_counts within 5 percent. ENEX: note count exact, resources exact, text_similarity 0.97. Confluence: page tree exact, heading_retention 0.95, table_cell_accuracy 0.9, macro mapping exact by count. Jira/Trello/Asana: item counts exact, comment counts exact, table_cell_accuracy 0.97. Kindle/Readwise: highlight count after dedupe exact, grouping exact, text_similarity 0.99. Bookmarks: entry count exact, folder structure exact.

### 11h. Options

`options.notes`: `output` (`set` default, `combined`), `inline_databases` (true), `prefer_html` (false), `wikilinks` (`resolve`, `text`, `keep`), `expand_embeds` (false), `backlinks` (false), `exclude` (globs), `attachments` (`convert`, `list`, `skip`), `include_archived` (false), `trello_compact` (profile), `dedupe_highlights` (true), `dedupe_bookmarks` (false), `fetch_bookmarks` (false), `keep_comments` (true).

### 11i. Phase

Phase 1: Notion, Obsidian, ENEX, Kindle, Readwise, bookmarks (HTML and Chrome). Phase 3: Confluence, Jira, Trello, Asana, Apple Notes HTML, Keep, Roam, Firefox lz4. Phase 5: Logseq, Joplin, Bear/textbundle, Standard Notes, OneNote native (if a permissive `.one` parser appears; otherwise never).

---

## 12. specialized

Each sub-converter here is small and lives in `packages/converters/specialized/` as its own module with its own entry point, so it can be disabled individually. Many are Phase 5; the phase column in 12i is per sub-converter.

### 12a. Scope and input matrix

| Input | Detection | Sub-converter |
|---|---|---|
| SEC EDGAR: `sec.gov/Archives/edgar/data/<cik>/<accession>/...`, `sec.gov/cgi-bin/browse-edgar`, `efts.sec.gov`, an accession number `0001234567-24-000123`, a ticker or CIK with `--form 10-K` | URL and pattern | `EdgarConverter` |
| XBRL instance `.xml`/`.xbrl` and inline XBRL `.htm` (`ix:nonFraction`) | root `xbrl`/`xbrli`, `ix:` namespace | `XbrlConverter` |
| Earnings call transcripts (PDF, HTML, text with `Operator:`, `Q&A`, speaker-name lines, `[Operator Instructions]`) | content classifier | `EarningsCallConverter` (post-processor over the PDF/web/text output) |
| Bank and card statements (PDF) | classifier: `Statement Period`, `Beginning Balance`, `Ending Balance`, date-amount-balance rows | `BankStatementConverter` (post-processor over PDF tables) |
| Invoices and receipts (PDF, image) | classifier: `Invoice`, `Total`, `Tax`, `Due`, line items; images route via OCR | `InvoiceConverter` |
| Contracts (DOCX, PDF) | classifier: numbered clauses, `WHEREAS`, defined-term capitalization, `IN WITNESS WHEREOF` | `ContractConverter` (post-processor) |
| Court filings and depositions (PDF with line-numbered pages, `Q.`/`A.` pairs, caption blocks, `CERTIFICATE OF REPORTER`) | classifier | `LegalTranscriptConverter` |
| arXiv: `arxiv.org/abs/<id>`, `/pdf/<id>`, bare ids `2510.19817`, `hep-th/9901001` | pattern | `ArxivConverter` |
| PubMed and PMC: `pubmed.ncbi.nlm.nih.gov/<pmid>`, `PMC<id>`, `pmc.ncbi.nlm.nih.gov/articles/PMC...`, DOIs via `doi.org` | pattern | `PubMedConverter` |
| JATS XML (`<article>` with `article-meta`) | root | `JatsConverter` |
| BibTeX `.bib`, `text/x-bibtex` | content `@article{` | `BibtexConverter` |
| USPTO: `patents.google.com/patent/US...`, `ppubs.uspto.gov`, USPTO XML (`us-patent-grant`, `us-patent-application`), patent numbers `US10123456B2` | pattern and root | `PatentConverter` |
| HL7 v2 (`MSH|^~\&`) and FHIR JSON (`resourceType`) and CDA XML (`ClinicalDocument`) | content | `HealthConverter` (self-host only) |
| MusicXML (`.musicxml`, `.mxl` zip, root `score-partwise`), MIDI (`.mid`, metadata only) | root/magic | `MusicConverter` |
| GeoJSON (`"type": "FeatureCollection"`), KML/KMZ, GPX, Shapefile (`.shp` with sidecars, Phase 5) | content | `GeoConverter` |
| Archives: `.zip`, `.tar`, `.tar.gz`/`.tgz`, `.tar.bz2`, `.tar.xz`, `.7z`, `.rar`, `.gz`/`.bz2`/`.xz` single files, `.jar`/`.war`/`.apk`/`.ipa` (as zip, metadata only), `.iso` (refused) | magic | `ArchiveConverter` |
| Figma: `figma.com/file|design/<key>`, with `FIGMA_TOKEN` | URL | `FigmaConverter` (self-host only) |
| Product pages and reviews (any page with JSON-LD `Product`, `Offer`, `AggregateRating`, `Review`) | JSON-LD on a section 5 page | `StructuredDataConverter` (post-processor) |
| Job postings (JSON-LD `JobPosting`; LinkedIn, Indeed, Greenhouse `boards.greenhouse.io`, Lever `jobs.lever.co`, Workable, Ashby) | JSON-LD or host pattern | `StructuredDataConverter` |
| App store listings (`apps.apple.com/<cc>/app/<slug>/id<n>`, `play.google.com/store/apps/details?id=`) | pattern | `AppStoreConverter` |
| 3D models, fonts (metadata only): `.stl`, `.obj`, `.glb`, `.ttf`, `.otf` | magic | Phase 5 via `trimesh` (MIT) and `fontTools` (MIT), metadata tables only |

### 12b. Libraries

`edgartools` (MIT) for EDGAR and XBRL financial statements; `python-xbrl` is not used; for raw XBRL facts outside edgartools, `lxml` plus a 300-line contexts/units/facts walker; `arelle` (Apache-2.0) optional extra for validation. `arxiv` (MIT) client or plain `httpx` to the export API (`export.arxiv.org/api/query?id_list=`); `httpx` to NCBI E-utilities (`efetch.fcgi?db=pubmed&rettype=xml`, `db=pmc` for JATS) with `NCBI_API_KEY` optional; `bibtexparser` (BSD) v2; `hl7apy` (MIT); `fhir.resources` is not needed (walk JSON); `music21` (BSD-3) for MusicXML summaries with a pure-lxml fallback for part and measure counts; `mido` (MIT) for MIDI; `shapely` (BSD) optional for geometry stats, otherwise pure Python; `py7zr` (LGPL, so `intomd[7z]` extra; default refuses 7z with `extra_required`), `rarfile` (ISC) needing `unrar`/`bsdtar` binaries (shell-out only; refuse when absent); `zipfile`, `tarfile` (stdlib, with `filter="data"` on Python 3.12); `extruct` (BSD) for JSON-LD, Microdata, RDFa; `figma` REST API via `httpx`.

### 12c. Build steps

EdgarConverter:

1. Require an identity string: `INTOMD_EDGAR_IDENTITY="Name email@example.com"` (SEC rule); on the public instance the operator sets one; the CLI prompts once and stores it in config. Rate limit 10 requests per second per the SEC's limit (use 5).
2. Resolve the input to a filing: an Archives URL gives CIK and accession directly; a ticker/CIK plus `--form` and optional `--year` uses `edgartools` `Company(ticker).get_filings(form=...)` latest; an accession number uses `find(accession)`. Record `metadata.edgar = {cik, company, form, filed, period, accession, url}`.
3. For 10-K, 10-Q, 20-F, 8-K, S-1, DEF 14A: use `edgartools` `filing.obj()` to get the typed object (`TenK` etc.) and its item sections (`Item 1`, `1A`, `7`, `7A`, `8`, ...). Emit H1 `<company> <form> <period>`, a cover `Table` (CIK, ticker, filer status, fiscal year end, shares outstanding, public float from the cover page facts), then `Heading(level=2)` per item in the filing's order with the item's text converted by the HTML-to-IR module from the filing's HTML (edgartools gives clean HTML per item; `to_markdown()` is used for shadow comparison). Nested headings inside items (`Overview`, `Results of Operations`) become H3/H4 by the HTML heading levels or bold-paragraph heuristics (`options.specialized.edgar_infer_headings`, default true). Tables inside items (the many financial and segment tables in Item 7 and Item 8) go through the HTML table path with spans preserved and a caption from the preceding bold line.
4. XBRL facts to tables: `filing.xbrl()` gives statements; emit `Heading(level=2, text="Financial statements (XBRL)")` with H3 per statement (`Balance Sheet`, `Income Statement`, `Cash Flow`, `Equity`, `Comprehensive Income`) as `Table`s from `statement.to_dataframe()` with columns per period and rows per concept with the presentation-linkbase labels and indentation shown as leading `·` characters for hierarchy depth; units and scale in the caption (`USD, in thousands`); then `Heading(level=3, text="Facts")` with a `Table` (concept, value, unit, period, dimensions) for every non-statement fact, capped at `xbrl_max_facts` (5,000). Run `compare_context()` where available and record `metadata.xbrl_check` (match ratio against the SEC rendering); below 0.95 warn `xbrl_statement_mismatch`.
5. Exhibits (`EX-99`, `EX-10`, press releases) are listed in an `Exhibits` table and converted as child documents when `options.specialized.edgar_exhibits=true`. Full-text search (`efts.sec.gov/LATEST/search-index?q=`) results render as a `Table` of filings (not converted).
6. Provenance: `path` = `item/<id>` and `xbrl/<statement>/<concept>`; `source_id` = accession; `page` not applicable (HTML filings). For the PDF rendering some users supply, section 1 handles it and this converter's classifier (`UNITED STATES SECURITIES AND EXCHANGE COMMISSION` in page 1) applies item detection as a post-processor with `metadata.edgar_detected=true`.

XbrlConverter:

7. Instance XML: parse contexts (entity, period instant/duration, segment dimensions), units (measures, divide), facts (element, contextRef, unitRef, decimals, value, `xsi:nil`). Inline XBRL: walk `ix:nonFraction`, `ix:nonNumeric`, `ix:continuation`, `ix:hidden`, `ix:resources` (contexts and units live in `ix:resources`), applying `scale`, `sign`, and `format` transforms (the `ixt` registry: `num-dot-decimal`, `num-comma-decimal`, `date-month-day-year`, `zero-dash`, etc.; implement the 20 most common and warn `ixt_format_unknown` otherwise). Emit a contexts `Table`, a units `Table`, and a facts `Table` (concept with namespace prefix, value as rendered by the transform, unit, period, dimensions, decimals, source id), grouped by period when under 100 contexts. The inline HTML body is also converted by the HTML path so the readable document remains, with each tagged value annotated in `full` by a trailing `<!-- xbrl: us-gaap:Revenue 2024-FY -->` `Raw` marker when `options.specialized.xbrl_annotate=true`.

EarningsCallConverter:

8. Input classifier on a converted `Document` (from PDF, web, or text): presence of `Operator` as a speaker, `Question-and-Answer`/`Q&A` heading, `[Operator Instructions]`, and more than 5 distinct `Name - Title` speaker lines. When matched, re-segment paragraphs into `TranscriptSegment(speaker, text)` blocks: a speaker line is a short paragraph matching `^([A-Z][\w.'-]+( [A-Z][\w.'-]+){0,4})( -- | - | \u2014 |, )(.{3,80})$` or a bold run; the title part becomes `metadata.speaker_title` and company affiliation (`Analyst, Morgan Stanley`). Insert `Heading(level=2)` for `Prepared Remarks` and `Questions and Answers` when found; nested H3 per analyst question block (question speaker becomes the heading `Q: <analyst>, <firm>`). The `Operator` segments are kept but `compact` drops them. No timestamps exist in text transcripts; when the source was audio (media pipeline), timestamps flow through. Extract `metadata.earnings = {company, ticker, quarter, fiscal_year, date, participants: [{name, title, company, role: management|analyst|operator}]}` from the header block. Provenance: as the underlying source (page or url) plus `source_id` = segment index.

BankStatementConverter:

9. Classifier on a PDF `Document`: first two pages contain `Statement` and either `Beginning Balance`/`Opening Balance`/`Previous Balance` and `Ending Balance`/`Closing Balance`/`New Balance`, and at least one `Table` has a date column and an amount column. When matched (or `options.specialized.mode="bank"`), run the post-processor; never run it silently in other modes (it changes table shapes).
10. Table normalization: find transaction tables across all pages, rejoin page-split tables (section 1 rule), unify headers to canonical names by synonym map (`Date`/`Trans Date`/`Posting Date` → `date`; `Description`/`Details`/`Transaction` → `description`; `Withdrawals`/`Debits`/`Payments` → `debit`; `Deposits`/`Credits` → `credit`; `Amount` → `amount` (signed); `Balance`/`Running Balance` → `balance`). Multi-line descriptions (continuation rows with empty date and amount) are merged into the previous row's description. Parse dates with the statement's year (statements print `03/14` without a year: take from the statement period, handling December-to-January wrap). Parse amounts: strip currency symbols and thousands separators, handle `(1,234.56)` and `1,234.56-` and `CR`/`DR` suffixes as sign markers, detect comma-decimal locales from the balance column, and never round. Zero vs letter O and `1` vs `l` corrections are applied only when a reconciliation (step 11) fails and the substitution makes it pass, and each such correction is listed in the sidecar `ocr_corrections` with a warning `amount_corrected_by_reconciliation`.
11. Reconciliation: for statements with a running balance column, check each row: `balance[i] == balance[i-1] + credit[i] - debit[i]` (or `+ amount[i]`) to the cent; for statements without running balances, check `ending == beginning + sum(credits) - sum(debits)` and the printed totals (`Total Deposits`, `Total Withdrawals`) against column sums. Report `metadata.reconciliation = {status: pass|fail|partial, rows_checked, first_failing_row, delta}`. On failure, emit a prominent warning `reconciliation_failed` with the row provenance (page and bbox) of the first mismatch and the delta, and insert a `Paragraph(role="warning")` at the top of the document saying the figures did not reconcile and listing the suspect rows; never attempt to "fix" by dropping rows. Sign-reversal detection: if the reconciliation passes when debit and credit columns are swapped, swap and warn `columns_swapped_by_reconciliation`. Phantom row detection: a row at a page boundary identical to the last row of the previous page is dropped with warning `duplicate_row_at_page_break`.
12. Output: H1 `<bank> statement <period>`, an account summary `Table` (account last 4 digits only: mask any full account number in the output and sidecar, warning `account_number_masked`; period; beginning and ending balance; totals), the transactions `Table` with columns `date, description, debit, credit, balance, page`, and a `Paragraph` reconciliation status line. CSV sidecar always (Part 3 rule). Provenance: every row carries `page` and `bbox` from the source table cell row.

InvoiceConverter:

13. For images and scanned PDFs, the OCR pipeline (Part 3) is called with `hint="invoice"` so it returns layout blocks; for born-digital PDFs section 1's blocks are used. Key-value extraction is rule-based (no LLM): labeled fields found by regex over lines near labels (`Invoice (No|Number|#)`, `Date`, `Due Date`, `PO (Number)?`, `Bill To`, `Ship To`, `Subtotal`, `Tax`/`VAT`/`GST` with rate, `Total`/`Amount Due`, `IBAN`, `BIC/SWIFT`, `VAT ID`, `Payment Terms`, currency detection by symbol or ISO code). Line items: the largest table with a quantity-like and an amount-like column; normalize headers (`Qty`, `Description`, `Unit Price`, `Amount`). Validation: `sum(line amounts) == subtotal` and `subtotal + tax == total` to the cent, with tolerance of 0.01 per line for rounding; IBAN mod-97 check; VAT ID format check per country; date sanity (due >= issue). Any failing check → warning `invoice_validation_failed` with details and `metadata.invoice.validated=false`. Emit H1 `Invoice <number> from <vendor>`, a `Table` of fields with a `Confidence` column (`exact` for born-digital, OCR confidence bucket for scans, `inferred` for values found without a label), the line items `Table`, a totals `Table`, and the full text beneath. Receipts (short, no invoice number, `Thank you`, `Change`) use the same path with `metadata.kind="receipt"`, extracting merchant, date, time, items, subtotal, tax, tip, total, payment method (last 4 masked).

ContractConverter:

14. Classifier on DOCX or PDF output: clause numbering (`1.`, `1.1`, `(a)`, `Article I`, `Section 2.3`), recitals (`WHEREAS`), defined terms (capitalized multi-word phrases in quotes followed by `means` or in a `Definitions` section), execution block (`IN WITNESS WHEREOF`, signature lines). When matched or `mode="contract"`: preserve clause numbering verbatim in the heading or list text (never renumber; the Markdown renderer must emit ordered lists with explicit source numbers for contract documents via `List.explicit_numbers=true`), build heading levels from the numbering depth (Article → H2, `1.1` → H3, `(a)` → list item), and emit a `Heading(level=2, text="Defined terms")` section at the end with a `Table` (term, definition excerpt, clause reference) built from `"Term" means ...` and `"Term" shall mean` patterns and the Definitions section; cross-references (`Section 4.2`) become `Link`s to the heading anchors. Tracked changes from DOCX flow through unchanged (section 2) and are summarized in a `Table` (clause, author, insertions, deletions) under `Heading(level=2, text="Redline summary")` when any exist. Parties extracted from the preamble (`between X ("Buyer") and Y ("Seller")`) into `metadata.contract.parties`; dates (effective date, term) into `metadata.contract`. Schedules and exhibits become H2 sections. Nothing is paraphrased; the verbatim guarantee from the legal persona applies to this converter above all.

LegalTranscriptConverter:

15. Classifier: pages with line numbers `1` to `25` in the left margin (detected by a column of integers 1..25 or 1..28 at a consistent x position on most pages), a caption block (`IN THE ... COURT`, `Case No.`, `v.`), `Q.`/`A.` or `Q `/`A ` dialogue, `THE COURT:`/`MR. SMITH:` speaker labels, `(Whereupon`, `CERTIFICATE`. Depositions and hearing transcripts are usually born-digital PDFs from court reporters; scanned ones go through OCR first.
16. Page:line provenance: for each page, map every text line to its line number by y-position proximity to the margin numbers (tolerance 40 percent of line pitch); lines without a nearby number (headers, footers) get `line=None`. Every `TranscriptSegment` carries `page` and `line` (start) and `line_end`. The renderer emits `[12:3]`-style anchors (`page:line`) at the start of each segment in `full` and `agent` profiles (the legal persona's citation form) and `<!-- page N -->` markers as usual. Condensed transcripts (4 pages per sheet) are detected by four line-number columns per page and split into logical pages with the printed page numbers.
17. Dialogue: `Q.`/`Q:` lines start an examining-attorney segment with `speaker="Q"` and `A.` lines `speaker="A"`; `MR. SMITH:` and `THE COURT:` labels set `speaker` to the label; `BY MR. SMITH:` sets the current examiner so `Q` segments carry `metadata.examiner`; parentheticals `(Pause.)`, `(Exhibit 4 marked.)` become `TranscriptSegment(speaker=None, role="annotation")`. Continuation lines append to the current segment. The caption, appearances, index, exhibit list, and certificate pages become H2 sections with their content as paragraphs or tables (exhibit index as a `Table`). Word-index pages (concordances at the end) are dropped with warning `word_index_dropped` unless `options.specialized.keep_word_index=true`.
18. Court filings (briefs, motions, orders): line numbers exist on pleading paper (California style); use the same page:line mapping, and treat `I.`, `A.`, `1.` outline headings as H2..H4; footnotes as section 1; the caption as a `Table`; the signature block and certificate of service as H2 sections. Bates numbers (`ABC000123` patterns in the footer) are captured into `metadata.bates = {prefix, first, last}` and each page's `PageBreak` carries `metadata.bates`.

ArxivConverter:

19. Normalize the id (new `YYMM.NNNNN[vN]` and old `archive/YYMMNNN`). Fetch metadata from the export API (title, authors, abstract, categories, published, updated, DOI, journal ref, comments, version list). Fetch the PDF from `arxiv.org/pdf/<id>vN` with a 1 request per 3 seconds limit (arXiv's stated courtesy limit) and convert via section 1 with `academic="on"`; when `options.specialized.arxiv_source=true`, fetch the e-print source tarball (`arxiv.org/e-print/<id>`), detect LaTeX, and convert via section 4's LaTeX path instead (cleaner math), with the PDF as a fallback. Merge: API metadata wins over PDF-derived metadata; emit frontmatter `arxiv_id`, `doi`, `authors`, `categories`, `published`, `abstract`, `license` (arXiv license URL from the API when present). HTML versions (`arxiv.org/html/<id>`) are used when `options.specialized.arxiv_prefer_html=true` and available (section 5 with MathML recovery).

PubMedConverter:

20. PMID → `efetch` XML (title, abstract with labeled sections, authors with affiliations, journal, pub date, DOI, MeSH terms, PMC id, publication types). If a PMC id exists and the article is in the open-access subset, fetch JATS via `efetch?db=pmc&id=` (or the OA API `oa.fcgi` for the package) and convert through `JatsConverter`; otherwise emit the abstract-only document with warning `fulltext_unavailable` and the DOI link (never attempt publisher scraping behind paywalls). DOIs via `doi.org` content negotiation (`Accept: application/vnd.citationstyles.csl+json`) for metadata, then route to the resolved URL via section 5 (which will hit paywall detection where applicable). PMC URLs directly → JATS.

JatsConverter:

21. Parse `<front>` (`journal-meta`, `article-meta`: title, contributors with affiliations via `xref rid`, abstract(s), keywords, pub dates, DOI, license), `<body>` (`sec` with `title` → headings by nesting depth starting at H2, `p`, `list`, `table-wrap` → `Table` with `caption` and `table-wrap-foot`, `fig` → `Figure` with `caption` and `graphic xlink:href` resolved within the package, `disp-formula`/`inline-formula` with `tex-math` → `Equation` or MathML converted to LaTeX via a minimal MathML-to-LaTeX walker when `tex-math` is absent, `xref ref-type="bibr"` → citation links `[^rN]`, `fn-group` → footnotes, `boxed-text` → callout quotes, `supplementary-material` → links), `<back>` (`ref-list` → `References` H2 with each `ref` formatted from `element-citation`/`mixed-citation` as author, title, source, year, DOI; `ack`, `app-group` as sections, `glossary` as a table). Frontmatter carries the metadata; `license` from `<license>`.

BibtexConverter:

22. Parse with `bibtexparser` v2 (handles `@string`, `@comment`, `@preamble`, concatenation, and LaTeX accents via the `latexcodec` middleware (MIT) so `{\"o}` becomes `ö`). Emit H1 `<filename> (N entries)`, a `Table` (key, type, author (first + et al. when over 3), title, year, venue, DOI) sorted by `options.specialized.bib_sort` (`key`, `year`, `author`), then, in `full`, per entry `Heading(level=3, text=key)` with all fields as a two-column `Table` and the abstract and note fields as paragraphs. Keys become anchors so LaTeX documents converted in section 4 can link `[@key]` to them. Duplicate keys warn `bibtex_duplicate_keys`.

PatentConverter:

23. Google Patents URL: fetch the page (section 5 fetch policy) and parse its structured sections (`abstract`, `claims` with `.claim` and dependency structure via `claim-ref`, `description` with `heading` elements, `citations` tables, `family`, `legal events`, `inventor`, `assignee`, `priority date`, `publication date`, `classifications` CPC). USPTO XML (grant or application): `us-bibliographic-data-grant` (publication reference, application reference, classifications, invention title, inventors, assignees, priority claims, citations), `abstract`, `description` (with `heading` → H2/H3, `p` with `num` attributes kept as `metadata.para_num`, `tables` → `Table`, `maths` → `Equation`, `img` references listed as figures), `claims` (`claim` → ordered list items with the claim number verbatim and `claim-ref` dependency captured as `metadata.depends_on`; independent claims marked in bold in `full`). Emit H1 `<number>: <title>`, bibliographic `Table`, Abstract, Claims (as an ordered `List` with explicit numbers and nesting of dependent claims under their independent claim when `options.specialized.claims_tree=true`), Description with its headings, Citations `Table`, Figures `List`. Docling's USPTO backend is used for shadow comparison.

HealthConverter:

24. Self-host only: on the public instance `can_handle` returns 1.0 and emits a stub with `phi_refused` ("Health data is not accepted on the public instance"). On self-host, every output starts with a `Paragraph(role="warning")`: "This document may contain protected health information; handle according to your obligations" and the warning `phi_possible` is set. HL7 v2: parse with `hl7apy` (fall back to a raw `|^~\&` splitter on version mismatch), emit a `Table` per segment type (MSH, PID, PV1, OBR, OBX, ...) with field positions and names from the version's spec, repeating segments as rows, and a readable summary (message type, sending app, patient id masked to the last 4 by default via `options.specialized.phi_mask`, default true, encounter, observations as a `Table` of code, value, units, reference range, flags). FHIR JSON: `Bundle` → iterate `entry[].resource`; per `resourceType` a section with a key field table (Patient: name masked, birthDate year only when masked, gender; Observation: code display, value with unit, effective date, status; Condition, MedicationRequest, Encounter, DiagnosticReport, DocumentReference with attached data decoded and routed to the registry); unknown resource types rendered via section 10's JSON path. CDA XML: `recordTarget` masked, `component/structuredBody/section` → H2 per section with `title`, narrative `text` via the HTML-to-IR module (CDA narrative is XHTML-like), and `entry` elements summarized as tables.

MusicConverter:

25. MusicXML (`.mxl` unzipped via `META-INF/container.xml`): `music21.converter.parse` when installed; emit H1 work title, a metadata `Table` (composer, lyricist, parts, measures, key signatures, time signatures, tempo markings, duration estimate), per part `Heading(level=2)` with a `Table` of measures (measure, key, time, chord symbols, lyrics) when under 500 measures, and lyrics as `Paragraph`s per verse. Without music21: lxml counts and titles only, warning `music_summary_only`. MIDI: `mido` for tracks, tempo map, time signature, note counts, instruments, duration; no notation.

GeoConverter:

26. GeoJSON: features count, geometry types, bbox (computed), CRS note, and a `Table` of features (id, type, properties flattened, centroid lat/lon, vertex count) capped at `max_rows`; property schema table like section 10. KML/KMZ: `Document`/`Folder` hierarchy → headings, `Placemark` → table rows (name, description via HTML module, coordinates, style), `GroundOverlay` and `NetworkLink` listed. GPX: tracks and routes with distance (haversine), elevation gain, duration, point counts; waypoints as a `Table`. Coordinates rendered to 6 decimals; never simplify geometries.

ArchiveConverter:

27. Open by type. Enforce bomb protection before extracting anything: total declared uncompressed size <= `options.specialized.archive_max_total` (default 2 GB CLI, 200 MB public), per-entry size <= `archive_max_entry` (500 MB), entry count <= `archive_max_entries` (10,000), compression ratio per entry <= 100:1 (count bytes as you stream and abort at the cap, since declared sizes lie), nesting depth <= `archive_max_depth` (3; an archive inside an archive inside an archive stops), path traversal rejected (`..`, absolute paths, symlinks to outside; `tarfile.extractall(filter="data")`), and device or FIFO entries skipped. Encrypted zips are listed with warning `archive_encrypted` and not extracted unless `options.specialized.archive_password` is set.
28. Stream entries to a temp directory one at a time, convert each through the registry (respecting the parent's `max_bytes` budget shared across entries), and emit: H1 `<archive name>`, a listing `Table` (path, size, modified, type, converted yes/no), then each converted entry under `Heading(level=2, text=<path>)` with its blocks shifted down one level, or as a `DocumentSet` when `output="separate"`. Known bundle types are special-cased before generic handling: `.jar`/`.war`/`.apk`/`.ipa` emit the manifest (`META-INF/MANIFEST.MF`, `AndroidManifest.xml` via `androguard` is not included; binary XML is listed only, `Info.plist`) and the listing, never decompiling; `.epub`, `.docx`, `.pptx`, `.xlsx`, `.pages`, `.mxl`, `.kmz`, Notion zips, Slack zips are detected by their internal markers and routed to their dedicated converters instead. Single-file compressions (`.gz`, `.bz2`, `.xz`) decompress with the ratio guard and route by the inner type.

FigmaConverter:

29. Self-host only with `FIGMA_TOKEN`. `GET /v1/files/<key>?depth=2` for the document tree (pages, frames), then `GET /v1/files/<key>/nodes?ids=` per page for text nodes. Emit H1 file name, per page `Heading(level=2)`, per top-level frame `Heading(level=3, text=frame name)` with all `TEXT` node `characters` in layout order (sorted by `absoluteBoundingBox` y then x) as paragraphs, component names and instances as a `List`, and, when `options.specialized.figma_images=true`, `GET /v1/images/<key>?ids=&format=png` to export frames into assets (counts against caps). Comments via `/v1/files/<key>/comments` as `Comment` blocks anchored by node id. Rate limits per Figma's headers. Provenance: `path` = node id, `bbox` from the bounding box normalized to the frame.

StructuredDataConverter (product pages, reviews, job postings):

30. Runs as a post-processor on section 5 output when `extruct` finds JSON-LD, Microdata, or RDFa of types `Product`, `Offer`, `AggregateRating`, `Review`, `JobPosting`, `Recipe`, `Event`, `Organization`, `Person`, `FAQPage`, `HowTo`, `Course`, `SoftwareApplication`, `LocalBusiness`. For each recognized object, emit a `Table` under `Heading(level=2, text="Structured data: <type>")` after the article metadata and before the body: Product (name, brand, sku, gtin, price with currency from offers, availability, rating value and count, description), Review list (author, rating, date, body excerpt) as a `Table` plus full bodies as `Quote`s in `full` capped at `max_reviews` (50), JobPosting (title, hiring organization, location(s), employment type, salary range with currency and unit, date posted, valid through, remote flag, description as Markdown), Recipe (ingredients list, instructions as an ordered list, times, yield, nutrition table), Event (name, start, end, location, offers), FAQPage (question/answer pairs as H3 plus paragraph). Job boards without JSON-LD (Greenhouse, Lever, Ashby, Workable) have known selectors for title, location, department, and the description container; use them with `metadata.source_kind="selector"`. Reviews rendered on the page but not in structured data (Amazon-style `[data-hook="review"]`) are extracted with per-site selectors only when `options.specialized.site_selectors=true` (self-host) because those sites forbid scraping in their ToS; warn `tos_risk_source`.

AppStoreConverter:

31. Apple: fetch `https://itunes.apple.com/lookup?id=<id>&country=<cc>` (public JSON, sanctioned): name, seller, bundle id, version, release notes, description, price, currency, rating, rating count, genres, content rating, size, minimum OS, screenshots URLs, languages, release date, current version release date. Google Play: no public API; fetch the store page via section 5 and parse the embedded data (`AF_initDataCallback` scripts) best-effort for the same fields, with `experimental=true` and warning `best_effort_extraction`. Reviews: Apple's RSS `https://itunes.apple.com/<cc>/rss/customerreviews/id=<id>/sortBy=mostRecent/json` (public) up to `max_reviews` as a `Table` (title, rating, version, date, body excerpt) plus `Quote`s in `full`; Google Play reviews require the Play Developer API and are not fetched. Emit H1 app name, a details `Table`, Description as Markdown, `What's new` as a section, screenshots as `Image` links, reviews.

### 12d. IR blocks and provenance

All block types. Mandatory provenance by sub-converter: EDGAR `path` and `source_id`; XBRL `path` (fact id) ; earnings `source_id`; bank statements `page` and `bbox` on every transaction row; invoices `page` and `bbox` on every extracted field (the `Table` row carries the provenance of the source cell); contracts `path` or `page`; legal transcripts `page` and `line` on every segment; arXiv/PubMed/JATS `path`; BibTeX `line` and `source_id` (key); patents `path`; health `path`; music `path` (part/measure); geo `path` (feature index); archives `path` (entry path, plus the inner converter's fields); Figma `path` and `bbox`; structured data `path` (JSON-LD pointer); app store `source_id`.

### 12e. Known failure modes

1. EDGAR without an identity (hard fail with a clear message, never a silent 403 retry loop); 10-K item detection on filings that use non-standard item headings or put Item 8 in exhibits (`Item 8` pointing to `EX-13`: follow the exhibit).
2. Inline XBRL with `ix:continuation` chains and `scale="6"` values rendered without scaling (a 1,000x error).
3. Earnings call speaker lines mis-split when a company name contains ` - `.
4. Bank statements: separate deposits and withdrawals sections (Chase), run-together fields (Wells Fargo), ACH codes in descriptions (BofA), phantom rows at page breaks, running balance missing on some rows, foreign-currency sub-ledgers, statements where the year rolls over mid-period, and OCR `O`/`0` confusion; the reconciliation fixture must fail loudly on a deliberately corrupted row.
5. Invoices with multiple currencies, VAT-inclusive line items, discounts, rounding lines; receipts with no tax line.
6. Contracts whose numbering restarts in each Article, with `(i)`, `(ii)` roman lists ambiguous against `(h)`, `(i)` alphabetic lists (disambiguate by sequence context), and defined terms used before definition.
7. Deposition pages where line numbers are images (scanned): OCR first, then mapping; condensed four-up pages; page numbers in the header vs printed transcript page numbers (use the printed one).
8. arXiv versioned ids and withdrawn papers; source tarballs with multiple `.tex` files and `.bbl`.
9. PubMed articles with no PMC full text; JATS with MathML only.
10. BibTeX with `@string` macros and non-ASCII in keys.
11. Patents with 200 claims and deep dependency trees; USPTO XML with multiple concatenated `<?xml` documents in one file (weekly bulk files: split on the declaration).
12. HL7 with custom Z-segments and escaped delimiters (`\F\`, `\S\`); FHIR bundles with contained resources and references (`Patient/123`) left as text.
13. KMZ with NetworkLinks (not followed).
14. Zip bombs (42.zip style nested, and a single 4 GB entry of zeros), zip-slip paths, symlinked tar entries, archives whose declared sizes are wrong, `.apk` with 20,000 entries.
15. Figma files over the 32 MB response limit: paginate by page ids.
16. Product pages with multiple `Product` objects (variants) and `Offer` arrays; reviews in `review` vs `reviews` keys.
17. App Store lookups for apps not in the requested country.

### 12f. Fixtures

1. `specialized/edgar-10k-small` (cassette of a small filer's 10-K with inline XBRL; items, statements, an exhibit) and `specialized/edgar-8k-press-release`.
2. `specialized/xbrl-instance` and `specialized/ixbrl-scale-and-continuation`.
3. `specialized/earnings-call-text` (synthetic transcript with prepared remarks, Q&A, an operator, a hyphenated company name).
4. `specialized/bank-statement-clean` (synthetic ReportLab PDF, running balance, page-split table, year rollover), `specialized/bank-statement-corrupt` (one amount altered so reconciliation must fail at a known row), `specialized/bank-statement-split-sections` (deposits and withdrawals in separate tables, no running balance), `specialized/bank-statement-scanned` (`requires: [ocr]`, with an `O` for `0` that reconciliation corrects).
5. `specialized/invoice-born-digital`, `specialized/invoice-scanned` (`requires: [ocr]`), `specialized/receipt-photo` (`requires: [ocr]`).
6. `specialized/contract-docx-redline`: articles, nested clauses, roman and alpha lists, defined terms, cross-references, tracked changes, an exhibit.
7. `specialized/deposition-pdf` (line-numbered pages, Q/A, exhibits marked, certificate, word index), `specialized/deposition-condensed`, `specialized/brief-pleading-paper` (with Bates numbers).
8. `specialized/arxiv-abs` (cassette: API plus PDF; and the source tarball variant), `specialized/pubmed-pmc-jats`, `specialized/pubmed-abstract-only`, `specialized/jats-article-file`.
9. `specialized/bibtex-strings-accents`.
10. `specialized/patent-uspto-xml`, `specialized/patent-google-page` (cassette).
11. `specialized/hl7-adt-oru` (synthetic messages with Z-segments and escapes), `specialized/fhir-bundle` (synthetic), `specialized/cda-ccd` (synthetic); all with the public-instance refusal variant.
12. `specialized/musicxml-two-parts` (`requires: [music21]` for the full variant) and `specialized/midi-file`.
13. `specialized/geojson-features`, `specialized/kmz-folders`, `specialized/gpx-track`.
14. `specialized/archive-nested-mixed` (zip containing a tar.gz containing a docx and a csv, plus an encrypted entry), `specialized/archive-zip-bomb` (must abort with `archive_bomb_suspected` and zero extracted bytes beyond the cap), `specialized/archive-zip-slip` (must refuse the traversal entry and convert the rest), `specialized/archive-jar-manifest`.
15. `specialized/figma-file` (cassette, `requires: [FIGMA_TOKEN]` env; skipped by default).
16. `specialized/product-page-jsonld`, `specialized/job-posting-jsonld`, `specialized/job-posting-greenhouse`, `specialized/recipe-jsonld`.
17. `specialized/appstore-lookup` (cassette) and `specialized/playstore-page` (cassette, `experimental`).

### 12g. Acceptance thresholds

EDGAR: item headings exact, statement table_cell_accuracy 0.98 (numbers must be exact strings), text_similarity 0.95. XBRL: fact count exact and values exact after transforms. Earnings: segment count exact, speaker labels 0.98. Bank statements: transactions exact (every cell), reconciliation status exact per fixture (`pass` on clean, `fail` at the named row on corrupt, `pass` after a logged correction on scanned). Invoices: field table_cell_accuracy 0.95 born-digital, 0.85 scanned; validation flags exact. Contracts: clause numbering verbatim (100 percent), defined terms count within 5 percent, tracked changes exact. Legal transcripts: page:line on 100 percent of dialogue segments and exact against the fixture's known lines; Q/A speaker exact. arXiv/PubMed/JATS: heading_retention 0.95, equations 0.9, references count exact. BibTeX: entry count exact, cell accuracy 0.99. Patents: claim count exact with dependencies. Health: segment and resource counts exact, masking verified (no unmasked identifiers by regex). Geo: feature counts and bbox exact. Archives: listing exact, security fixtures exact. Structured data: field tables 0.95. App store: details table 0.95.

### 12h. Options

`options.specialized`: `mode` (`auto`, `bank`, `invoice`, `contract`, `legal`, `earnings`, `off`), `edgar_identity`, `edgar_exhibits` (false), `edgar_infer_headings` (true), `xbrl_max_facts` (5000), `xbrl_annotate` (false), `reconcile` (true), `mask_account_numbers` (true), `invoice_validate` (true), `claims_tree` (true), `keep_word_index` (false), `bates` (true), `arxiv_source` (false), `arxiv_prefer_html` (false), `bib_sort` (`key`), `phi_mask` (true), `archive_max_total`, `archive_max_entry`, `archive_max_entries`, `archive_max_depth` (3), `archive_password`, `figma_images` (false), `site_selectors` (false), `max_reviews` (50), `appstore_country` (`us`).

### 12i. Phase

Phase 1: EDGAR and XBRL (edgartools), arXiv, PubMed/JATS, BibTeX, patents (XML), archives (zip/tar/gz with all protections), GeoJSON/KML/GPX, structured-data post-processor (JSON-LD), app store lookup. Phase 2: invoices and receipts (OCR), scanned bank statements and depositions (OCR hand-off; the born-digital versions are Phase 1 behind the `mode` flag and graduate to the full persona mode in Phase 5). Phase 3: Google Patents page, Play Store page, job boards by selector, Figma. Phase 5: finance mode (bank statement reconciliation as the default pipeline for the persona, CSV/JSON always), legal mode (page:line, Bates, verbatim guarantee, audit log), contracts, earnings calls, health (HL7/FHIR/CDA, self-host), music, 7z/rar extras, 3D and fonts.

---

## 13. Cross-cutting rules

These rules live in the core package (`intomd.detect`, `intomd.limits`, `intomd.warnings`, `intomd.experimental`) and every converter above depends on them. Build them before any converter family; the fixture harness tests them with their own `fixtures/_core/` cases.

### 13.1 Content-type detection order

1. Build `intomd.detect.detect(input: InputRef) -> Detection` returning `{mime, extension, label, confidence, source: magika|libmagic|extension|url|sniff|declared}`.
2. Order of evidence, highest priority first, with the rule that a later source can only override an earlier one when the earlier one's confidence is below 0.8:
   1. Container markers for zip-based formats before anything else, because Magika and libmagic both say `zip` for DOCX, EPUB, Notion exports, and Slack exports: open the zip central directory (never extract) and match `[Content_Types].xml` + `word/` → DOCX, + `ppt/` → PPTX, + `xl/` → XLSX, `mimetype` entry equal to `application/epub+zip` → EPUB, `META-INF/container.xml` with `score` → MXL, `Index/Document.iwa` or `preview.pdf` + `.pages` extension → iWork, `doc.kml` → KMZ, `channels.json` + `users.json` → Slack export, files matching the Notion ` <32-hex>` pattern at the root → Notion export, `META-INF/MANIFEST.MF` → JAR, `AndroidManifest.xml` → APK, `Payload/*.app` → IPA, `result.json` with `messages` → Telegram, `messages/index.json` → Discord package. Same idea for OLE2: `__substg1.0_` streams → MSG, `WordDocument` stream → DOC, `Workbook` → XLS, `PowerPoint Document` → PPT.
   2. Magika (Apache-2.0, 1 MB model, bundled) on the first 64 KB plus the last 64 KB. Accept its label when `score >= 0.9`. Map Magika labels to the registry's MIME keys with a table in `intomd/detect/magika_map.py` (Magika has ~200 labels; unknown labels fall through).
   3. libmagic via `python-magic` (MIT; the libmagic library itself is BSD) when installed, else the pure-Python `puremagic` (MIT) fallback. Accept when it returns something more specific than `text/plain`, `application/octet-stream`, or `data`.
   4. Extension map (`intomd/detect/extensions.py`, ~400 entries) when the bytes are text-like or when the two sniffers disagree. For text-like content the extension decides between Markdown, CSV, TSV, LaTeX, RST, log, source languages; without an extension, the text sniffers run: JSON (`json.loads` on the first 1 MB succeeds, or JSONL), YAML (`---` or `key: value` on most lines and `safe_load` succeeds), CSV (`csv.Sniffer` finds a consistent delimiter with at least 3 columns on 90 percent of the first 200 lines), XML (`<?xml` or a root tag), HTML (`<html`, `<!doctype html`, or 5+ HTML tags in the first 4 KB), EML (RFC 5322 headers), diff, log (section 8 rule), BibTeX (`@\w+{`), ICS/VCF (`BEGIN:`), HL7 (`MSH|`), transcript (section 4 rule), Markdown (3+ Markdown constructs), then plain text.
   5. URL pattern map (`intomd/detect/urls.py`) when the input is a URL and no bytes have been fetched yet: every converter's `can_handle` is called with the URL only; the highest confidence wins, ties broken by the registry's declared priority (specialized URL converters above generic web). After fetch, the response `Content-Type` is a declared source with confidence 0.6 and the bytes are re-detected by steps 1 to 4; a mismatch between the declared type and the detected type is recorded as warning `content_type_mismatch` and the detected type wins.
   6. Declared type from the API caller (`content_type` field) is the lowest priority (0.5) and only decides ties.
3. Misnamed files (`.csv` that is HTML, `.pdf` that is a Word document, `.jpg` that is a PNG) are handled by this order automatically; always warn `misnamed_file` when the extension's implied type differs from the detected type.
4. The registry asks every converter `can_handle(input_with_detection)` and sorts by confidence; the first converter to return a `Document` with at least one block wins; a `ConversionError` or an empty document falls through to the next candidate, with the failures listed in `metadata.converter_attempts`. The last resort is the plain-text structurer for text-like bytes and the stub note for binary.
5. Detection is covered by `fixtures/_core/detect/` with one file per label, including misnamed and extensionless cases, and a table-driven test asserting the chosen converter.

### 13.2 Encoding detection

1. `intomd.detect.decode(bytes, declared: str | None) -> (text, encoding, confidence)`: strip and record BOMs (UTF-8, UTF-16 LE/BE, UTF-32); if a BOM exists, it wins. Otherwise try the declared encoding (HTTP charset, XML declaration, HTML meta, EML part charset) strictly; on decode error fall back to `charset-normalizer` on up to 1 MB; accept its best guess when its confidence is at least 0.7 and the result has no replacement characters; otherwise decode as UTF-8 with `errors="replace"` and warn `encoding_uncertain` with the replacement count.
2. Normalize line endings to `\n`. Apply NFC normalization to text (not NFKC: NFKC would change ligatures and compatibility characters that legal and accessibility users need preserved; NFKC is applied only inside the injection scanner's own copy). Strip or flag zero-width and bidi control characters per section 5 step 8, recording counts; for non-web inputs (documents, code) zero-width characters are kept but counted and flagged, because code and some scripts legitimately use them.
3. Record `metadata.encoding` and `metadata.encoding_confidence`. Binary inputs never go through this path.

### 13.3 Language detection

1. `intomd.detect.language(text, hint) -> (code, confidence)` using `lingua-py` (Apache-2.0) in its low-accuracy mode (smaller memory) on up to the first 20 KB of extracted body text, restricted to the 75 supported languages. A structural hint wins when present and confident: `<html lang>`, EPUB `dc:language`, DOCX `w:lang` on the majority of runs, PDF `/Lang`, ASR language from the media pipeline. The user's `language_hint` overrides everything and sets `metadata.language_source="user"`.
2. Mixed-language documents: when the top two languages each exceed 30 percent of sampled paragraphs, set `metadata.languages=[...]` and `language` to the majority with warning-level info `multilingual_content`.
3. Language feeds OCR language selection (Part 3), the WhatsApp date-order default, quoted-reply pattern selection, and the Kindle locale table.

### 13.4 Size, page, duration, and count caps

Caps are declared per converter in a `Limits` dataclass attached to the converter class and enforced by the registry before and during conversion, so no converter can forget them. Defaults below; the public instance (Part 4) overrides with smaller values through `INTOMD_LIMITS_PROFILE=public`; the CLI uses `local`.

| Converter | Local default | Public default | Behavior at cap |
|---|---|---|---|
| PDF | 500 MB, 2,000 pages | 25 MB, 200 pages | truncate pages, `truncated=true`, `page_cap_reached` |
| Office DOCX/PPTX | 200 MB | 25 MB | refuse over bytes; slides capped at 500 (`slide_cap_reached`) |
| XLSX/CSV | 200 MB, 10,000 rows per sheet, 256 cols, 50 sheets | 25 MB, 2,000 rows, 64 cols, 20 sheets | truncate rows and sheets with warnings |
| Google Workspace | 100 MB | 25 MB | refuse |
| EPUB/MOBI | 200 MB | 25 MB | refuse; chapters capped at 500 |
| ipynb | 50 MB, outputs 5,000 chars each | 10 MB, 2,000 chars | truncate outputs |
| Plain text/Markdown/LaTeX | 50 MB | 10 MB | truncate with marker |
| Web page | 50 MB, 30 s fetch, 20 s render | 10 MB, 15 s fetch, no render | truncate or refuse; `size_cap`, `timeout` |
| Site crawl | 200 pages, depth 3, 100 MB, 10 min | 50 pages, depth 2, 20 MB, 3 min | stop and report `pages_skipped: cap` |
| Social threads | 200 comments full, 50 compact, 10 requests | 100 comments, 5 requests | `comments_truncated` |
| Repo pack | 500 MB tree, 512 KB per file, no token budget | 50 MB tarball, 256 KB per file, 200k tokens | budget actions |
| PR/issues | 400 files, 500 patch lines each, 1,000 comments | 100 files, 200 lines, 300 comments | truncate with warnings |
| Logs | 2 GB streamed, 5,000 output lines | 50 MB, 2,000 lines | tail |
| Email/MBOX | 5 GB mbox streamed, 5,000 messages, attachments 100 MB each, depth 3 | 25 MB, 200 messages, attachments 10 MB, depth 2 | truncate |
| Chat exports | 1 GB, 200,000 messages | 50 MB, 20,000 messages | truncate by date range from the end |
| Data (JSON/YAML/XML) | 500 MB streamed, 1,000 rows rendered | 25 MB, 500 rows | sample |
| Parquet/SQLite | 10 GB metadata-only, samples 100+20 rows | 100 MB, 50+10 | sample |
| Notes apps | 2 GB export, 20,000 notes | 50 MB, 2,000 notes | truncate |
| Archives | 2 GB total, 500 MB entry, 10,000 entries, depth 3, ratio 100:1 | 200 MB, 50 MB, 1,000, depth 2, ratio 100:1 | abort extraction (`archive_bomb_suspected`), list only |
| OCR pages (via Part 3) | 500 pages | 20 pages | `ocr_page_cap` |
| Media (via Part 3) | 6 hours | 15 minutes | refuse over cap |

Every cap that truncates sets `Document.truncated=true` and adds exactly one warning naming what was cut and how to raise the cap. Every cap that refuses produces the stub note with the cap named. Caps are reported in `intomd limits` CLI output and in the API's `/limits` endpoint.

### 13.5 Per-converter timeouts

1. The registry runs each `convert()` under a budget `Limits.timeout_s` (local defaults: PDF 600 s plus 2 s per page, Office 120 s, web 45 s, crawl 600 s, repo 300 s, data 120 s, archives 600 s shared with children, email 300 s, chat exports 300 s, specialized 300 s; public: one third of each, PDF 120 s). Timeouts are cooperative: converters receive `options.deadline` (a monotonic timestamp) and must check `ctx.check_deadline()` at every page, file, message, row-batch, or network call boundary; the registry also runs a hard watchdog that cancels the worker (Part 1 job model) at `timeout_s + 30`.
2. On a cooperative timeout, the converter returns what it has with `truncated=true` and warning `timeout_partial` naming the last completed unit (page, file, message). On the hard watchdog, the registry emits the stub note with `timeout_hard` and whatever partial `Document` the converter had published to the builder.
3. Child conversions (attachments, archive entries, linked PDFs, crawled pages) share the parent's deadline; the parent reserves 10 percent of its remaining budget for finalization before dispatching a child.
4. Network calls use connect 10 s, read 30 s, and total per-request 60 s regardless of the converter budget; shell-outs (LibreOffice, Calibre, Pandoc, ebook-convert, unrar) get their own per-process timeouts listed in their sections and are killed with their process group.

### 13.6 Warning taxonomy

1. `intomd.warnings.Warning(code: str, severity: info|warning|error, message: str, provenance: Provenance | None, data: dict)`; codes are stable strings listed in `intomd/warnings/codes.py` with their severity and a one-line description; adding a code requires adding it to that file and to `docs/warnings.md` (a test asserts the two match). Warnings appear in frontmatter as `warnings: [code, ...]` (deduplicated codes) and in the sidecar in full with counts and provenance. The stub note (Part 1) lists `error`-severity warnings in its body.
2. Codes by family (severity in parentheses; `info` codes are omitted from `compact` frontmatter):
   - Core and detection: `misnamed_file` (warning), `content_type_mismatch` (warning), `encoding_uncertain` (warning), `multilingual_content` (info), `engine_fallback` (warning), `converter_failed` (error), `extraction_empty` (error), `size_cap` (warning), `page_cap_reached` (warning), `row_cap_reached` (warning), `timeout_partial` (warning), `timeout_hard` (error), `extra_required` (error), `experimental_converter` (info), `injection_suspected` (warning; from the Part 1 scanner), `removed_hidden_elements` (info), `removed_invisible_chars` (info), `pii_columns_removed` (info).
   - PDF: `encrypted_no_password` (error), `copy_restricted_ignored` (info), `pages_without_text` (warning; data lists pages), `ocr_unavailable` (warning), `ocr_confidence_low` (warning; from Part 3), `reading_order_uncertain` (warning), `heading_source_structure_tree` (info), `structure_tree_unusable` (info), `removed_running_header_footer` (info), `table_rejoined` (info), `equation_unrecognized` (warning), `xfa_partial` (warning), `iwork_preview_fallback` (warning).
   - Office: `heading_inferred_from_formatting` (info), `textbox_content_relocated` (info), `hidden_slides_included` (info), `hidden_sheets_included` (info), `formula_uncalculated` (warning), `cell_errors` (warning), `possible_serial_dates` (info), `ragged_rows` (warning), `smartart_flattened` (info), `ole_object_skipped` (warning), `legacy_text_only` (warning), `libreoffice_missing` (warning), `pages_estimated` (info), `equation_partial` (warning).
   - Google: `private_link` (error), `first_sheet_only` (warning), `suggestions_not_exported` (info).
   - Ebooks and text: `epub_mimetype_missing` (info), `calibre_missing` (error), `drm_protected` (error), `latex_main_ambiguous` (warning), `latex_unknown_macro` (info), `notebook_invalid` (warning), `output_truncated` (info), `mdx_components_stripped` (info), `table_inferred` (info), `empty_body_js_required` (error), `markup_partial` (warning).
   - Web: `robots_disallowed` (error), `http_error` (error), `paywall_detected` (warning), `readability_fallback_full_body` (info), `multipage_article` (info), `lazy_content_possible` (info), `images_without_alt` (info), `fetch_blocked` (error), `fetch_failed` (error).
   - Sites: `llms_txt_used` (info), `llms_txt_may_be_stale` (info), `sitemap_truncated` (warning), `versions_skipped` (info), `boilerplate_removed_corpus` (info), `heading_depth_clamped` (info), `combined_too_large` (warning).
   - Social: `comments_truncated` (warning), `comments_collapsed` (info), `tos_risk_source` (warning), `private_post` (error), `thread_partial_federation` (info), `api_fallback_html` (warning), `best_effort_extraction` (warning), `rate_limited` (error).
   - Code: `secret_file_excluded` (info), `token_budget_applied` (warning), `log_lines_collapsed` (info), `log_truncated` (warning), `timezone_assumed` (info), `spec_invalid` (warning), `env_values_redacted` (info).
   - Communication: `quoted_history_removed` (info), `thread_reconstructed_from_text` (info), `orphan_thread_replies` (warning), `unresolved_users` (warning), `attachment_unconverted` (warning), `tnef_unparsed` (warning), `smime_not_decrypted` (warning), `msg_partial` (warning), `date_order_assumed` (warning), `discord_package_no_authors` (info), `teams_html_best_effort` (warning).
   - Data: `json_repaired` (warning), `rows_sampled` (info), `columns_truncated` (info), `depth_truncated` (info), `yaml_unsafe_tags` (warning), `api_error_payload` (warning), `sqlite_encrypted` (error), `connection_string_refused` (error).
   - Notes: `unresolved_wikilinks` (info), `ambiguous_wikilink` (info), `missing_resource` (warning), `encrypted_content` (info), `dates_from_filesystem` (info), `kindle_clip_limit` (warning), `clippings_deduped` (info).
   - Specialized: `xbrl_statement_mismatch` (warning), `ixt_format_unknown` (warning), `reconciliation_failed` (error), `amount_corrected_by_reconciliation` (warning), `columns_swapped_by_reconciliation` (warning), `duplicate_row_at_page_break` (info), `account_number_masked` (info), `invoice_validation_failed` (warning), `word_index_dropped` (info), `fulltext_unavailable` (warning), `bibtex_duplicate_keys` (warning), `phi_refused` (error), `phi_possible` (warning), `music_summary_only` (info), `archive_encrypted` (warning), `archive_bomb_suspected` (error), `archive_path_rejected` (warning).
3. Severity drives the CLI exit code (0 with info and warning, 2 with any error unless `--allow-errors`), the stub-note decision (an `error` with zero body blocks produces the stub), and the API's `status` field (`ok`, `partial`, `failed`).
4. Every warning with provenance is also rendered in `full` and `agent` profiles as an HTML comment at the block position (`<!-- warning: reconciliation_failed page=4 -->`) so a reader scanning the Markdown sees it where it applies; `compact` and `rag` keep warnings in frontmatter only.

### 13.7 The `experimental` flag

1. A converter class declares `experimental = True` when its source is unofficial, fragile, or ToS-risky (X, Threads, LinkedIn, Play Store pages, iMessage `chat.db`, Medium JSON, Substack JSON, mirror chains in Part 3) or when its parser is new and below threshold in the fixture suite. The registry excludes experimental converters from `can_handle` resolution unless `options.experimental=true` (CLI `--experimental`, API `experimental: true`, env `INTOMD_EXPERIMENTAL=1`), in which case they participate normally and every resulting document carries `metadata.experimental=true` and the info warning `experimental_converter` naming the converter, plus `frontmatter.experimental: true`.
2. Individual features inside a stable converter can be experimental too: declare them in the converter's options model with `Field(..., json_schema_extra={"experimental": True})` (for example `options.pdf.forms="inline"`); the options loader rejects them with a clear message unless the global flag is on.
3. The fixture harness runs experimental fixtures (`meta.yaml: experimental: true`) in a separate job that may fail without blocking merges but reports a trend; a converter graduates when its fixtures pass the thresholds on three consecutive weekly runs, at which point `experimental` is removed in a PR that also updates `docs/converters.md`.
4. The public instance never enables experimental converters regardless of the request flag (operator policy in Part 4); the API returns `experimental_disabled` with the self-host instructions.
5. `intomd converters list` shows each converter's family, formats, phase, license tier of its dependencies, caps, and whether it is experimental, so users can see at a glance what the install can and cannot do.
