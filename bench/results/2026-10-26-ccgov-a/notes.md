## What this run is

The first snapshot of the `ccgov` corpus: the 10,452 files the Common Crawl pull had fetched when the run
started, on the afternoon the corpus was built (`tools/bench/cc.py`, crawl `CC-MAIN-2026-43`, .gov, .mil and
.edu hosts). The manifest is ordered rarest type first, so this snapshot is the long tail of the modern web:
243 detected types, from subtitles, mailboxes and MathML through Mathematica notebooks, Fortran, Stata and
SAS data, DVI, Lotus 1-2-3 and WordPerfect to shared libraries and Java bytecode. The common types (PDF,
HTML, OOXML, JSON, CSV) come later in the pull and in a later snapshot. Same tool, build and scorer as the
Govdocs1 pilot (`bench/results/2026-10-26-pilot/`): ezmd main at d078ebb, six workers, 120-second limit,
LibreOffice 26.8.1 through `LIBREOFFICE_PATH`, outcome scored and smells read.

## Results

Clean rate 0.9997 [0.9993, 1.0000] over 10,452 files: 6,225 outputs, 4,224 declared refusals, 3 bugs
(three macro-enabled Excel workbooks of 2.6 to 3.1 MB over the 120-second limit). 4,427 seconds of
conversion. 157 of the 243 types produced at least one output; 86 were refused outright.

What the refusals are, largest clusters first:

| n | refusal | what the files are |
|---|---|---|
| 1,343 | `no converter (application/octet-stream)` | Protein Data Bank text (282), flow cytometry data (240), WordPerfect (190), PGP signatures, and other binaries |
| 1,066 | `refusing executable input` | ELF objects and shared libraries (467), Java bytecode (401), Flash (75), COFF (71), Python bytecode (37), Mach-O, wasm |
| 362 | `no converter (application/x-dvi)` | TeX DVI |
| 222 | `no converter (application/marc)` | library MARC records (16 more converted as text) |
| 195 | `no converter (application/postscript)` | PostScript (39 more, misnamed, converted through another path) |
| 126 | `no converter (lotus-1-2-3)` | Lotus spreadsheets |
| 90 | `no available converter (parquet)` | the `data` extra is not installed in the bench build |
| 115 | `all converters failed ... input looks binary` | SAS transport files, assembly listings, AppleDouble |
| 166 | `no converter` for Mathematica notebooks and packages, OCaml, ML | text files with no chain |
| 71 | `no converter (application/x-sql)` | SQL scripts, text |
| 33 | `no converter (application/x-plist)` | XML property lists |
| 29 | `no converter (application/vnd.ms-office)` | Visio (13), Outlook `.msg` (6), Publisher (4): the generic OLE verdict beat the extension |
| 17 | `all converters failed ... openpyxl could not open` | `.xlsb` binary workbooks and `.xlam` add-ins; LibreOffice reads them but is not in that chain |
| 14 | `no converter (message/news)` | Usenet messages, RFC 822 |
| 9 | `no converter (application/x-mimearchive)` | MHTML; the #35 alias fixes this |

The correct refusals (executables, DVI, PostScript, MARC, Lotus, cytometry, certificates) are the majority.
The ones that are defects are the same two shapes the Govdocs1 pilot found, now with modern examples:
readable text refused for want of a chain (SQL, config files, DTDs, Mathematica, property lists, Usenet
messages, PDB text labelled binary: about 600 files), and a generic container verdict or a first converter
that cannot read the format ending the attempt when a later converter would have succeeded (`vnd.ms-office`,
`.xlsb`).

## Smells of the 6,225 outputs (`smells.md`)

Gated-clean rate 0.9716 [0.9672, 0.9754]. `truncated_full` 169 (tab-separated text 52, xlsm 47, GeoPackage
36, SQLite 7: data files hitting the full profile's row caps, flagged but, as in the pilot, not always
warned); `empty` 4 (Illustrator files read as PDF, nothing extracted, no warning); `heading_repeated` 4;
`lone_bullet` 0 once the smell stopped counting a lone `*` or `-` in source code (it had flagged 135 C,
JavaScript and YAML files, which is why that rule now counts glyph bullets only). Reported: `repeated_lines`
354 and `empty_table` 146, both mostly the macro-enabled workbooks (125 and 119), which are large sparse
sheets rendered row by row and the same shape as the three timeouts.

## What this says

- **The modern long tail refuses cleanly.** No undeclared exception in 10,452 files of 243 types, and
  three timeouts. The executable guard refused a thousand binaries with the right message.
- **The defects are the pilot's defects.** Text that is not `text/*` by MIME has no floor, and a generic
  container verdict ends the attempt. Both are registry and detection rules, not per-format converters, and
  one fix each covers hundreds of files here and dozens in Govdocs1.
- **Spreadsheets are where the smells and the timeouts meet.** Large sparse workbooks produce repeated and
  empty rows, run over the row cap with a flag but not always a warning, and three of them run over two
  minutes. A trailing-empty-row trim and a streaming row cap would address all three.
