## What this run is

The first pass of the everyday-documents coverage work: ezmd main (d078ebb, the 0.1.1 release plus #25 and
#27) over the ten official Govdocs1 threads, 9,875 files across 43 extensions as a .gov crawler named them in
2009, with no ground truth. The question is not how good the Markdown is but whether each conversion ends the
way the contract says: an output, a declared refusal (`ConversionError`, `UnsupportedMediaType`,
`InputTooLarge`), or a bug (any other exception, a timeout, a dead worker). `tools/bench/scoring/corpus.py`
scores that outcome and clusters the failures by exception class and the frame that raised, which is the list
a fix pass works from (`clusters.md` under the run; the clusters below are copied from it).

## Run conditions

- Corpus: `govdocs1` (`bench/CORPORA.md`), the ten threads extracted flat by `fetch --only govdocs1` from a
  copy on a local drive (`EZMD_GOVDOCS1`); 9,875 files, 2.9 GB. Every file was attempted whatever its type.
- Tool: `ezmd-main` only, eight worker processes (`run --workers 8`), 120-second limit per file, raised to
  240 seconds for the reruns below. LibreOffice 26.8.1 extracted to a user folder (no system install) and
  passed through `LIBREOFFICE_PATH`; the first pass ran without it and refused every legacy Office file, so
  those 1,900 results were dropped and redone with it in place. The 89 results whose error wrapped another
  exception were redone twice more, after the registry started chaining the cause and after the worker's
  frame picker was fixed, so `results.jsonl` holds one record per file from the same code.
- Scoring: `score --corpus govdocs1`, clean rate with a bootstrap interval over the per-document outcomes.
- 30,539 seconds of conversion in total, 64 minutes of wall time for the first pass. Per type (median, p95,
  max seconds): doc 13.2 / 16.0 / 120 (LibreOffice's throwaway profile costs about 12 s per file), xls
  13.3 / 26.3 / 74, ppt 13.2 / 15.3 / 24, pdf 0.41 / 3.9 / 45, txt 0.09 / 0.9 / 145, html 0.08 / 0.6 / 21.

## Results

Clean rate 0.9941 [0.9926, 0.9955] over 9,875 files: 7,945 outputs, 1,872 declared refusals, 58 bugs.

| type | n | ok | declared | bug | what the refusals are |
|---|---|---|---|---|---|
| pdf | 2,378 | 2,377 | 0 | 1 | heading level 7 in a tagged PDF |
| html | 2,116 | 2,112 | 4 | 0 | XHTML routed to the XML parser (3), one binary |
| jpg, gif, png | 1,461 | 0 | 1,461 | 0 | no image converter before Phase 2 |
| doc | 797 | 735 | 5 | 57 | Word heading levels 7 to 9; two LibreOffice targets wrong; one package guard |
| txt | 788 | 778 | 10 | 0 | YAML/XML look-alikes with no text fallback (6), labelled binary (2), 175 MB cap (1) |
| xls | 584 | 584 | 0 | 0 | |
| ppt, pps | 512 | 491 | 21 | 0 | container verdict `cdfv2` (3), package guard (5), LibreOffice (2), the rest declared |
| xml | 353 | 308 | 45 | 0 | RDF/XML has no converter (37), malformed XML with no fallback (7), plist (1) |
| ps, eps | 248 | 2 | 246 | 0 | PostScript is not claimed; the two "ok" are gzip files misnamed .ps |
| csv, gz, log, kml, rtf, docx, xlsx, pptx, zip, ... | 450 | 448 | 2 | 0 | |
| swf, dbase3, unk, kmz, wp, sql, fm, pub, dwf, ... | 188 | 101 | 87 | 0 | unclaimed formats refused; `unk` files by content |

Failure clusters (bugs first), from `clusters.md`:

| kind | n | class | where | types |
|---|---|---|---|---|
| bug | 57 | `ValidationError` | `ezmd_converters/office/docx_walker.py:232 _main_block` | doc |
| bug | 1 | `ValidationError` | `ezmd_converters/pdf/headings.py` (structure-tree level, unclamped) | pdf |
| declared | 6 | `ConversionError` | OOXML package guard: a member over the 100:1 compression ratio, in a package LibreOffice itself wrote | ppt 5, doc 1 |
| declared | 6 | `ConversionError` | `data.yaml` / `data.xml` parse failure on a `.txt`, no fallback to text | txt |
| declared | 7 | `ConversionError` | malformed XML (`junk after document element`, `not well-formed`, bad character reference), no fallback | xml |
| declared | 3 | `ConversionError` | XHTML sent to `data.xml` (libmagic says `application/xml`, Magika's `html` below threshold) | html |
| declared | 5 | `ConversionError` | LibreOffice given the wrong target (Magika's `xls`/`ppt` guess outranks libmagic's `msword`), or `cdfv2` refused | doc 3, ppt 3 |
| declared | 3 | `ConversionError` | printable ASCII labelled `proteindb` by Magika becomes `application/octet-stream` and is refused | txt 2, tmp 1 |
| declared | 38 | `ConversionError` | `application/rdf+xml` and `application/x-plist`: XML dialects with no converter | xml |
| declared | 1 | `ConversionError` | LibreOffice over its 180 s limit | doc |
| declared | 1,461 | `ConversionError` | `no converter for` an image type | jpg, gif, png |
| declared | 246 | `ConversionError` | PostScript | ps, eps |
| declared | 34 | `UnsupportedMediaType` | `refusing executable input (application/x-shockwave-flash)` | swf |

Not in the table: the 4 MB plain-text file (`088753`, an ASCII raster grid) that timed out at 120 s in the
first pass and converted in 145 s with the higher limit. The profile puts 150 of its 160 seconds in
`escape_inline`, which runs markdown-it's inline parser over the file's single four-million-character
paragraph; that is a defect whatever the limit.

## What this says

- **The crash gate is nearly clean on the first pass.** No undeclared exception reached the worker, no worker
  died, and the 58 bugs are one defect: a heading level over 6 (Word's Heading 7 to 9, a tagged PDF's H7)
  handed to an IR field that refuses it. It had hidden as a declared error because the registry wrapped it;
  chaining the cause (this PR) is what made it count.
- **The declared refusals hold the rest of the defects.** Reading each cluster found seven more: the single
  huge paragraph in the renderer, three detection faults (an unmapped Magika label beating text evidence,
  XHTML taken for XML, a container verdict beating the extension for OLE files), a missing plain-text fallback
  for content-sniffed data types, `+xml` dialects with no converter, and the package guard rejecting
  LibreOffice's own output. Filed as #ISSUES.
- **Legacy Office is the expensive third.** doc, xls and ppt are 19% of the files and 86% of the conversion
  time, at 13 seconds each, almost all of it LibreOffice starting with a throwaway profile. A persistent
  profile per worker (still macro-free) would cut that to about a second and is the single largest speed
  item in the pilot.
- **Outcome is the floor, not the measure.** 7,945 outputs were written and nothing here says whether they
  are right: the two "ok" PostScript files are gzip archives listed as members, and every HTML page counts
  the same whether Trafilatura kept the article or the navigation. The smell scorer (empty or near-empty
  output, output far smaller than the text layer, replacement characters, repeated lines, runs of one
  character, mostly-empty tables, injection flags on clean documents) is the next step on this corpus and
  on `ccgov`, the modern-types corpus pulled from Common Crawl the same day.
