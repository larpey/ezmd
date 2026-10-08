# Office documents

The Office family (`documents.*`) converts Word, PowerPoint, Excel, OpenDocument, and RTF files. It is in
the default install and needs no system binaries. LibreOffice is optional and only used for legacy binary
formats and higher-fidelity RTF.

| Converter | Inputs | Engine | Install |
|---|---|---|---|
| `documents.docx` | `.docx`, `.docm`, `.dotx`, `.dotm` | lxml over the OOXML parts | default |
| `documents.pptx` | `.pptx`, `.pptm`, `.potx`, `.ppsx` | lxml over the OOXML parts | default |
| `documents.xlsx` | `.xlsx`, `.xlsm`, `.xltx`, `.xltm` | openpyxl | default |
| `documents.odf` | `.odt`, `.ods`, `.odp` and templates | lxml over `content.xml` | default |
| `documents.rtf` | `.rtf` | striprtf, as plain text | default |
| `documents.libreoffice` | `.doc`, `.dot`, `.wpd`, `.xls`, `.xlsb`, `.ppt`, `.pps`; also RTF and ODF | `soffice --headless`, then the native converter | needs LibreOffice on `PATH` or `LIBREOFFICE_PATH` |
| `documents.iwork` | `.pages`, `.numbers`, `.key` | Docling (planned) | listed as unavailable for now |

Fallback chains: RTF tries LibreOffice first, then `documents.rtf`. ODF tries `documents.odf` first, then
LibreOffice. Legacy binary formats only go through LibreOffice. When `soffice` can't be found,
`documents.libreoffice` shows up as unavailable, with the reason `libreoffice_missing`.

## Safety

Every package is checked before any parser sees it:

- Zip limits: at most 10,000 entries, a total uncompressed size under `INTOMD_ARCHIVE_MAX_BYTES` (500 MB
  by default), no entry over a 100:1 compression ratio, and no encrypted members. Nothing is extracted to
  disk.
- Active content is removed and reported as `removed_script_or_macro`. That covers `vbaProject.bin`,
  `vbaData.xml`, ActiveX parts, embedded OLE `.bin` objects, ODF `Basic/` and `Scripts/`, and external
  relationships of type oleObject, attachedTemplate, frame, and subDocument. Hyperlinks with a `file:` or
  UNC target are dropped too. Hyperlinks are kept only for http(s), mailto, and ftp.
- XML is parsed with entity resolution, network access, and DTD loading turned off. A part that declares a
  DOCTYPE is refused. openpyxl runs on a rewritten copy of the package, using defusedxml.
- Hidden text (`w:vanish`, white-on-white runs, ODF hidden text) is left out of the body and counted in
  `removed_hidden_elements`. `office.keep_hidden=true` stores it in `metadata.extra.hidden_text`.
- LibreOffice runs through the sandbox with a throwaway profile that disables macros. Its OOXML output goes
  through the same checks.
- Size caps: 200 MB for DOCX, PPTX, and XLSX (refused above that), 50 MB for RTF, and 100 MB per file for
  LibreOffice.

## What is preserved

**DOCX.** Headings come from the style chain (`Heading N`, `Title`, outline levels). Bold, enlarged
paragraphs are inferred as headings and warned with `heading_inferred_from_formatting`. Also kept:

- nested lists, ordered or bullet from `numbering.xml`
- tables with `gridSpan`/`vMerge` spans, header rows, and nested tables (emitted after the outer table)
- footnotes and endnotes
- hyperlinks
- images with alt text
- captions, attached to the preceding table or image
- quotes, code styles, and OMML equations as LaTeX (`equation_partial` when a construct has no mapping)
- text boxes, relocated after their paragraph (`textbox_content_relocated`)

Tracked insertions and deletions (`w:ins`, `w:del`, `w:moveFrom`, `w:moveTo`) are inline spans at their
exact position (`InlineSpan.change`, `change_author`, `change_id`), so every profile shows them in place:
resolved under `accept`/`reject`, as CriticMarkup under `annotate`. Moves are a deletion at the origin and an
insertion at the destination, with `change_id` set to `moveFrom:<id>` / `moveTo:<id>`. A paragraph that is
entirely one insertion, deletion, or move becomes an empty Paragraph plus an anchored `TrackedChange` block
(`attrs.scope="paragraph"`, plus `attrs.move` for moves). Formatting-only changes (`w:rPrChange`) are anchored
`TrackedChange(change="format")` blocks. Comments become `Comment` blocks with author, date, the anchored text, `reply_to`, and the
resolved state from `commentsExtended.xml`. Provenance `path` is `body[i]` and `source_id` is `w14:paraId`.

**PPTX.** Each slide is a `Slide` block in presentation order, and its content is attached as children:

- body text as paragraphs, or as lists nested by bullet level
- tables with merged cells
- charts as data tables captioned `Chart: <title>`, with `attrs.chart_type`
- SmartArt as lists (`smartart_flattened`)
- pictures with alt text
- speaker notes as a Paragraph with `attrs.slide_part="notes"`
- slide comments (legacy and modern)

Shapes are read top to bottom, then left to right, and placeholder positions are inherited from the layout.
When there is no title placeholder, the top-most, largest-font text box becomes the title. Hidden slides are
included with `attrs.hidden="true"` and `hidden_slides_included`. Section names become level-1 headings.
Provenance has `source_page` set to the slide number, `path` set to `slide{N}/shape{id}`, and a bbox.

**XLSX.** Every worksheet comes through, in workbook order, including hidden and veryHidden ones. Each
sheet gets a level-2 heading; hidden sheets get `attrs.hidden="true"` and `hidden_sheets_included`. Within
a sheet:

- each contiguous region (split on two or more empty rows or columns) becomes a Table; header rows come from
  the cell types, bold first rows, and the workbook's own markers (the row above a defined name's range, the
  first row of an autofilter or table)
- cells hold the cached values; `TableCell.formula` holds the formula
- `Table.column_types` is set per column
- merged cells are kept as spans
- dates are ISO 8601
- numbers are shown as the spreadsheet displays them, using the cell's number format: decimals, thousands
  separators, currency symbols, negative sections, percent, scientific. `TableCell.raw_value` keeps the
  unformatted number, and fractions or formats the converter doesn't understand show the raw number
- error values are kept as written (`cell_errors`)

Beyond the tables, named ranges get their own table, and cell comments are anchored to the table they sit
in. Warnings: `formula_uncalculated` (the formula text is shown when there is no
cached value), and `possible_serial_dates`.

**ODF.** ODT keeps headings, spans, links, lists, tables, footnotes, comments, and tracked changes (inline
spans, as for DOCX). ODS
sheets use the XLSX table builder. ODP pages become slides with notes.

**RTF.** Without LibreOffice, RTF comes through as paragraph text plus the info-group title and author.
Pictures and embedded objects are counted as skipped.

## Options

Pass these as `ConvertOptions.extra["office.<name>"]`:

- `include_comments`
- `include_hidden_slides`
- `include_hidden_sheets`
- `include_notes`
- `infer_headings`
- `keep_hidden`
- `formulas`: `sidecar` (default), `inline`, `table` (adds a formulas table per region), or `off`
- `max_rows` (10,000)
- `max_cols` (256)
- `max_sheets` (50)
- `max_slides` (500)
- `libreoffice_timeout_s` (120)
- `libreoffice_max_bytes` (100 MB)

`ConvertOptions.tracked_changes=False` merges insertions and drops deletions, with no `TrackedChange`
blocks. `ConvertOptions.comments=False` drops comments. `ConvertOptions.formulas=False` turns formulas off.

## Warnings

- `removed_script_or_macro`
- `removed_hidden_elements`
- `heading_inferred_from_formatting`
- `textbox_content_relocated`
- `ole_object_skipped`
- `equation_partial`
- `hidden_slides_included`
- `smartart_flattened`
- `slide_cap_reached`
- `hidden_sheets_included`
- `formulas_present` (emitted by the renderer once per output)
- `formula_uncalculated`
- `cell_errors`
- `possible_serial_dates`
- `row_cap_reached`
- `columns_truncated`
- `truncated` (sheet cap)
- `libreoffice_missing`
- `image_skipped` (RTF)
- `extraction_empty`

## Known limitations

- Inline tracked changes carry author and id but not the date (the span has no date field); the date is
  kept on whole-paragraph `TrackedChange` blocks.
- There is no LibreOffice fixture yet. The harness supports `requires_binaries = ["soffice"]`, but a golden
  can only be produced where `soffice` is installed, and the build machine and the Linux gate image have
  none. A host with LibreOffice should add one (a small `.doc` plus its golden). Until then, on such a host
  `test_has_fixture[documents.libreoffice]` fails, because the converter is available there.
- In the DOCX converter:
  - headers and footers are not extracted (`include_headers_footers` is not implemented yet)
  - `customXml` parts, `render_pages`, and `ocr_images` are not implemented
  - Strict OOXML namespaces are not supported
- XLSX charts and data validations are not extracted. Workbooks with more than 20 MB of sheet XML stream in
  read-only mode, which loses merged cells, comments, and bold-header detection. Rows after 50 consecutive
  empty rows are not read.
- The PPTX chart parser reads cached series values only. Picture OCR is Phase 2.
- `.doc`, `.xls`, and `.ppt` need LibreOffice. The `olefile`/`xlrd` fallbacks in the spec are not
  implemented, and without LibreOffice these formats get no converter.
- iWork is unavailable until the Docling backend lands. The embedded-preview fallback
  (`iwork_preview_fallback`) waits on the PDF family.
- CSV/TSV belong to the data family (P1-T05).
