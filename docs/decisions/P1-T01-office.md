# P1-T01 (Office part): decision entries

Proposed entries for DECISIONS.md. The orchestrator folds them in at merge.

## Approach note: DOCX (`documents.docx`)
- Library: lxml 6.1.3 (BSD-3-Clause; verified `lxml-6.1.3.dist-info/licenses/LICENSE.txt`). The parser reads
  the OOXML parts directly: `word/document.xml`, styles, numbering, footnotes, endnotes, comments, and
  commentsExtended. Entry point: `intomd_converters.office.docx:DocxConverter`.
- Why not python-docx or Pandoc: python-docx (MIT) does not expose `w:ins`, `w:del`, `w:moveFrom`,
  `w:moveTo`, `w:rPrChange`, comment replies, or resolved state, so the spec's own lxml path was needed
  anyway. Pandoc is GPL. It could only ever run as an optional external binary, and its default
  `--track-changes=accept` is the silent-loss trap the spec warns about. The default install therefore
  needs neither. The `office.engine=pandoc` option is not implemented. Adding it later means a sandboxed
  shell-out that maps the JSON AST.
- Known issues and mitigations:
  - Tracked changes can't be placed inline because the IR has no inline revision span. Paragraph text holds
    the unchanged runs, and each change is anchored to the paragraph. Headings, list items, and cells hold
    the accepted text in place.
  - Moves are recorded as a delete at the origin plus an insert at the destination (`attrs.move`). The IR's
    `move` kind is kept in both the accept and reject renderings, which would print moved text twice.
  - Comments with a reply are linked through `commentsExtended` paraIds.
  - TOC content controls and TOC/INDEX field results are skipped.
  - Field state spans paragraphs, with a nesting cap of 64.
  - `mc:AlternateContent` reads the Choice branch only, so text boxes are not duplicated.
  - Hidden and white-on-white text is excluded and counted.
- Fallback: none in the default install. Docling DOCX can be added behind `[docs]`.
- Fixtures: `office/docx-review`, `office/docx-structure`, `office/docx-macro`. Threshold 0.95. All three
  score 1.0 against reviewed goldens.

## Approach note: PPTX (`documents.pptx`)
- Library: lxml 6.1.3. python-pptx 1.0.2 (MIT) was evaluated and dropped as a runtime dependency. It pulls
  in Pillow 12.3.0, whose metadata now says `MIT-CMU`, which `tools/license_check.py` rejects, plus
  XlsxWriter. The parsing it would have saved (shape trees, text bodies, tables, chart caches, notes
  parts) is plain XML. python-pptx is still used in `fixtures/office/_generate.py` through
  `uv run --with python-pptx==1.0.2`.
- Entry point: `intomd_converters.office.pptx:PptxConverter`.
- Shape reading:
  - Group transforms are applied.
  - Placeholder positions are inherited from the layout and then the master.
  - Reading order is top, then left.
  - When there is no title placeholder, the slide title comes from the top-most, largest-font text box.
- What is extracted:
  - charts, from the cached `c:ser` values
  - SmartArt, from the `dgm:dataModel` parOf tree
  - notes, from the notes slide body placeholder
  - comments, legacy and modern
- Notes follow D-0017 (a Paragraph child with `attrs.slide_part="notes"`). The slide title is carried only
  on `Slide.title`, because the renderer already prints it as a heading.
- Fixture: `office/pptx-lecture` (5 slides, notes on 3, a table with a merged cell, a chart, a hidden
  slide). Threshold 0.95. Scores 1.0.

## Approach note: XLSX (`documents.xlsx`)
- Library: openpyxl 3.1.5 (MIT; verified `openpyxl-3.1.5.dist-info/LICENCE.rst`) with et-xmlfile 2.0.0
  (MIT). Entry point: `intomd_converters.office.xlsx:XlsxConverter`.
- Load: two `load_workbook` passes, one with `data_only=True` for cached values and one with
  `data_only=False` for formulas. Both run on the sanitized package copy, with `keep_links=False`.
  defusedxml is present, so openpyxl's own parser is defused as well.
- Load mode: full when the sheet XML is 20 MB or less, which is needed for merged cells, comments, and bold
  headers. Larger workbooks use read-only mode.
- Known issue: openpyxl writes formulas without cached values. The fixture generator injects the values
  Excel would cache.
- Header rule (Part 2 step 26), with multi-row headers joined at render time:
  - 1 when the first row is all strings and the next row has a typed value
  - 2 when two string rows come first
  - 1 when the first row is all bold
  - 1 when the workbook marks the region's first row as a header: it is the row just above a defined name's
    range (the name covers data, not labels), or the first row of an autofilter or of a table with a header
    row (Skeptic re-review: the hidden Lookup sheet's `Code`/`Meaning` row)
  - otherwise 0, and the renderer synthesizes headers
- Column types: numeric mixes resolve to currency, then percent, then float.
- Display values (Skeptic review): cached numbers are rendered with their Excel number format
  (`office/numfmt.py`), for example `"$"#,##0.00` gives `$120.50`. `raw_value` keeps the number.
  `formulas_present` is left to the renderer, which emits it once. Workbooks no longer set
  `Metadata.pages`; `Metadata.sheets` follows once the core field lands.
- Fixture: `office/xlsx-multi-sheet`. Threshold 0.95. Scores 1.0. `formula_uncalculated` and
  `possible_serial_dates` are covered by unit tests.

## Approach note: ODF (`documents.odf`)
- Library: lxml over `content.xml`, `styles.xml`, and `meta.xml`. odfpy 1.4.1 (Apache-2.0) is used only
  by the fixture generator.
- Deviation from Part 2 2b: the native parser runs first and LibreOffice is the fallback. The native path
  keeps headings, lists, tables, notes, comments, and tracked changes without spawning a process.
- ODS sheets reuse the XLSX table builder. Repeated rows and columns are capped, so `number-rows-repeated`
  bombs stay bounded. ODP pages become Slides with notes.
- Fixture: `office/odt-basic`. Threshold 0.9, the no-LibreOffice allowance. Scores 1.0.

## Approach note: RTF (`documents.rtf`) and LibreOffice (`documents.libreoffice`)
- striprtf 0.0.33 (BSD-3-Clause; verified `licenses/LICENSE`) provides the plain-text fallback, plus the
  info-group title and author.
- LibreOffice (MPL-2.0) is only ever an external binary run through `intomd.core.sandbox.run`:
  - a throwaway profile with `registrymodifications.xcu` disabling macros
  - `HOME` and `TMPDIR` set to the temp dir
  - `--convert-to docx|xlsx|pptx`, with the output going through the same sanitizer and native converters
- When `soffice` can't be found at registration, `documents.libreoffice` is registered as `Unavailable`
  with reason `libreoffice_missing`. The RTF chain then falls through to striprtf, which warns
  `libreoffice_missing`. At conversion time, a missing binary returns an empty document carrying that
  warning.
- `INTOMD_DISABLE_LIBREOFFICE=1` hides `soffice` (from the spec's fixture env).
- Fixture: `office/rtf-simple`. Threshold 0.9. Scores 1.0.
- Not done: `olefile` DOC text extraction and `xlrd` for `.xls`. Without LibreOffice these formats have no
  converter.

## Review follow-ups (after main 8d0e0cd, D-0026)
- DOCX and ODT tracked insertions and deletions are inline `InlineSpan.change` spans, with
  `change_author` and `change_id` (moves: `moveFrom:<id>` / `moveTo:<id>`). `TrackedChange` blocks remain
  for whole-paragraph changes and moves (`attrs.scope="paragraph"`) and for formatting-only changes.
- `Metadata.sheets` (XLSX, ODS) and `Metadata.slides` (PPTX, ODP) are set; `pages` is not.
- No LibreOffice fixture: main supports `requires_binaries = ["soffice"]` (016d147), but no machine used
  for this task has LibreOffice, and a fixture without a golden hard-fails. Follow-up for a host with
  `soffice`: add `office/doc-legacy` (a small `.doc` written by LibreOffice) with `requires_binaries`.

## iWork
`documents.iwork` is registered as `Unavailable(requires_extras=("iwork",))`, because the roadmap assigns
it to Docling. The preview-PDF fallback (`iwork_preview_fallback`) is deferred: it needs the PDF family's
converter as a child conversion, and a fixture for it would fail until that family merges.

## Security (Part 1 8.2)
`intomd_converters.office._package.OfficePackage` is the single gate for zip containers:
- the archive limits
- OLE2 detection, for encrypted OOXML
- removal of macro, ActiveX, OLE embedding, and ODF Basic/Scripts parts
- filtering of external relationships (oleObject, attachedTemplate, frame, subDocument, and `file:`/UNC
  hyperlinks), counted across every `.rels` part including `settings.xml.rels`
- DOCTYPE refusal
- hardened lxml parsing
- `sanitized_bytes()` for engines that open the zip themselves

## New warning code
- `slide_cap_reached`: severity warning, `truncates=True`. Named in Part 2 13.4.

## New dependencies (`packages/converters` defaults)
- lxml `>=5.3` (locked 6.1.3): BSD-3-Clause, about 4 MB wheel. Safe XML for OOXML and ODF.
- openpyxl `>=3.1` (locked 3.1.5): MIT, about 250 KB, plus et-xmlfile 2.0.0 (MIT). Values, formulas,
  merges, and comments.
- defusedxml `>=0.7` (locked 0.7.1): PSF-2.0, 25 KB. Already in the lock transitively; declared because
  openpyxl uses it when present.
- striprtf `>=0.0.26` (locked 0.0.33): BSD-3-Clause, about 10 KB. RTF text fallback.
- Generator-only, not dependencies: python-pptx 1.0.2 (MIT) and odfpy 1.4.1 (Apache-2.0), run with
  `uv run --with`.

## Spec deviations to log
- Part 4 4.3.3 lists python-pptx in the default install. It is not used, for the Pillow license reason
  above.
- The `move` change kind is mapped to delete/insert with `attrs.move` (reason above).
- ODF: native first, LibreOffice second.
- Spreadsheet region captions are only added when a sheet has more than one region.
