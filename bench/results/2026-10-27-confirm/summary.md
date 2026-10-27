# Benchmark baseline 2026-10-27-confirm

Hardware: AMD Ryzen 9 7900X 12-Core Processor, 24 logical cores, 95.1 GB RAM, GPU NVIDIA GeForce RTX 4090, 24564 MiB, 616.56, Windows 11 (10.0.26200).

Each cell: primary metric [95% CI] (n). fail = error/timeout/crash share of attempted documents; cov = attempted/total; s/doc = median and p95 wall seconds; RSS = median and peak over documents of the per-document peak MB (process tree plus any containers the tool starts, models loaded). Rows marked * are ezmd.

## What this run is

The confirmation pass of the everyday-documents fix batch: ezmd main at e66cfbb (the 0.1.1 release plus #25,
#27 and the fourteen pull requests #34 to #47 merged on 2026-10-26) over `govdocs1-held`, twenty Govdocs1
archives drawn by seed from the thousand, minus every file that is in a pilot thread: 19,519 files across
39 extensions, none of which was looked at while the pilot's bugs were found and fixed. The pilot
(`bench/results/2026-10-26-pilot/`) is where the fixes came from, so its clean rate after the fixes is
fitted to it; this run is the number that counts (D-0032, on a held-out split). The scoring is the pilot's:
an output, a declared refusal (`ConversionError`, `UnsupportedMediaType`, `InputTooLarge`), or a bug (any
other exception, a timeout, a dead worker), clustered by exception class and raising frame.

## Run conditions

- Corpus: `govdocs1-held` (`bench/CORPORA.md`), archives 105, 121, 228, 327, 430, 514, 524, 560, 569, 586,
  615, 636, 662, 802, 862, 880, 905, 916, 974 and 975 extracted flat by `fetch --only govdocs1-held` from a
  local copy of the archives (`EZMD_GOVDOCS1`); 19,720 files less the 201 that are in a thread, 9.3 GB.
  Every file was attempted whatever its type.
- Tool: `ezmd-main` only, eight worker processes (`run --workers 8`), 120-second limit per file. LibreOffice
  26.8.1 extracted to a user folder and passed through `LIBREOFFICE_PATH`; as in the pilot, the first pass ran
  without it and refused every legacy Office file, so those 3,747 results were dropped and redone with it in
  place. The seven files that hit the 120-second limit were redone once at 240 seconds, the pilot's rerun
  limit; see the timeouts below.
- Scoring: `score --corpus govdocs1-held`, clean rate with a bootstrap interval over the per-document outcomes,
  the structural smell scorer over every output.
- 36,485 seconds of conversion in total, including the reruns. Per type (median, p95, max seconds): doc 5.1 / 6.8 / 55 (pilot 13.2 /
  16.0: the LibreOffice profile seed of #45), xls 5.2 / 21.7 / 196 (13.3 / 26.3), ppt 5.3 / 6.4 / 120 (13.2 /
  15.3), pdf 0.53 / 5.8 / 184 (0.41 / 3.9), txt 0.15 / 2.2 / 48, html 0.13 / 0.7 / 39, xml 0.17 / 0.7 / 45.

## Results

Clean rate 0.9999 [0.9997, 1.0000] over 19,519 files: 16,509 outputs, 3,008 declared refusals, 2 bugs. The
pilot before the fixes was 0.9941 [0.9926, 0.9955] over 9,875 files with 58 bugs. Both bugs this time are
timeouts; no exception escaped a converter.

| type | n | ok | declared | bug | what the refusals are |
|---|---|---|---|---|---|
| pdf | 4,515 | 4,515 | 0 | 0 | (pilot: heading level 7 in a tagged PDF, now clamped by #38) |
| html | 4,168 | 4,165 | 3 | 0 | JPEG and TIFF images named `.html` (pilot: XHTML routed to the XML parser, now a web page by #46) |
| jpg, gif, png | 2,721 | 0 | 2,721 | 0 | no image converter before Phase 2 |
| doc | 1,459 | 1,459 | 0 | 0 | (pilot: 57 bugs, Word heading levels 7 to 9, clamped by #38) |
| xml | 1,394 | 1,394 | 0 | 0 | (pilot: 45 refusals, RDF/XML and malformed XML, now the XML chain and the text floor of #46 and #39) |
| xls | 1,378 | 1,377 | 1 | 0 | one workbook openpyxl cannot open after LibreOffice converts it |
| txt | 1,085 | 1,083 | 2 | 0 | a binary file (NUL bytes) and an `.xls` named `.txt` LibreOffice could not read (pilot: 10) |
| ppt, pps | 860 | 854 | 6 | 0 | LibreOffice exited without writing a pptx (5) or hit its own 120-second limit (1) (pilot: 21 refusals, `cdfv2` verdicts and the package guard, gone with #40 and #41) |
| ps | 426 | 423 | 3 | 0 | PostScript with no text layer the detector could use (3) |
| csv | 336 | 336 | 0 | 0 | |
| gz | 319 | 318 | 0 | 1 | one timeout, a 4.9 MB archive |
| log | 224 | 223 | 0 | 1 | one timeout, a 32 MB log |
| swf | 143 | 0 | 143 | 0 | executable input, refused |
| unk | 140 | 105 | 35 | 0 | octet-stream with no readable text (29), single pcap, MARC, BMP and `.Z` files |
| eps | 108 | 100 | 8 | 0 | PostScript with no text layer |
| dbase3 | 62 | 0 | 62 | 0 | no dBase converter |
| dwf | 13 | 0 | 13 | 0 | not a recognised archive |

The declared refusals are the contract working: 2,721 images and 143 Flash files are 95% of them, the rest
are formats ezmd does not claim (dBase, DWF, MARC, pcap, `.Z`) or files LibreOffice itself gave up on.

### What the pilot's fixes look like on files they never saw

| fix | pilot before the fix | held-out after it |
|---|---|---|
| #38 heading levels above 6 (doc, pdf) | 58 bugs | 0 bugs of that kind; doc 1,459 of 1,459 |
| #45 LibreOffice profile seed | doc 13.2 s median, 16.0 s p95 | 5.1 s median, 6.8 s p95 |
| #44 injection false positives | 255 high of 7,945 (3.2%); 1 of 7,915 after the fix on the pilot itself | 13 of 16,509 (0.08%) |
| #39 readable text never refused (txt, xml) | 14 refusals (text look-alikes, malformed XML, plist) | 2 refusals, both correct |
| #40, #41 container verdicts and package guard (ppt, doc) | 11 refusals | 0 of those kinds |
| #46 XHTML and XML dialects (html, xml) | 40 refusals | 0 of those kinds |

#42 (escape_inline), #43 (furniture-only pages) and #47 (running headers) change what an output contains,
not whether there is one; the outcome scorer cannot see them, and the smell rates below did not move.

### Timeouts

Seven files hit the 120-second limit: a 1.5 MB PDF (514441), a 62 MB PostScript file (560268), two gzip
archives of 4.9 and 12.5 MB (662596, 916219), a 32 MB log (636409), a 40 MB xls (105748) and an 18 MB ppt
(862796). At 240 seconds four of them convert (the PDF in 184 s, the PostScript file in 195 s, the xls in 196 s,
the 12.5 MB gzip in 138 s), the ppt becomes a declared refusal (LibreOffice's own 120-second limit, a
`ConversionError`), and two are still bugs: the 32 MB log and the 4.9 MB gzip archive exceed 240 seconds. Those
two are the run's only bugs. The pilot had one timeout in 9,875 files; seven in 19,519 at 120 seconds is the
same rate, and the files are large ones. The numbers above and in `summary.md` are after the 240-second rerun.

### Structural smells

Gated-clean rate 0.9477 [0.9443, 0.9511] over the 16,509 outputs (pilot 0.9459 [0.9406, 0.9514]). The gated
smells: `lone_bullet` 458 (454 in PDFs), `truncated_full` 345 (CSV 46, logs 22, HTML 12, long text files
the full profile cuts), `heading_bullet` 102 (96 in PDFs), `heading_repeated` 51 (doc 25, html 23), `empty`
9 (8 of them `unk` files with nothing to render, one PDF). No `control_chars`. The reported smells:
`repeated_lines` 1,179, `empty_table` 808 (469 in PDFs, 207 in xls), `shrunk` 296, `mojibake` 50,
`replacement_chars` 41, `char_run` 33. The same shapes as the pilot in the same proportions; the PDF bullet
and heading smells are the next converter work, not a regression.

## Injection false positives

Read from the frontmatter of the 16,509 outputs: 13 are `injection_risk: high` (0.08%), 509 medium (3.1%),
295 low. The pilot before #44 was 3.2% high; after #44 on the pilot itself, 0.01%. A rescan of the 13 with
the scanner (ezmd's own markers excluded) attributes them:

- `role_hijack` (6): "act as assistant" and "act as an assistant" as a job description in an 1858 journal
  and three organisational documents, "act as a model for" in research prose (2), "you will pretend to be"
  in a behaviour-change curriculum. #44 kept a model-like object ("assistant", "model") as a high on its
  own; these are the everyday uses of those words.
- `delimiter_spoof` (4): a `<system>` element in GForge and Continuum XML configuration files.
- `system_prompt_word` and `imperative_cluster` summing past the threshold (2): a capability list whose
  lines begin "System:" and a telnet transcript.
- `tool_abuse` (1): "call your functions" in a newsgroup post.
- `system_prompt` (1): the literal phrase "system prompt:" in a netCDF tools manual.

Thirteen in sixteen thousand is where #44 said it would be; the `<system>` element and the job-title
"assistant" are the two shapes worth a rule, recorded as follow-ups rather than fixed here.

## Skipped

No competitor was run: the held-out split is a confirmation of ezmd's fixes, and the pilot's competitor
seeds are the comparison point. No file was retried for any reason other than the two reruns above.

## govdocs1-held-clean

| tool | metric [95% CI] | n | fail | cov | s/doc med | s/doc p95 | RSS MB med | RSS MB peak |
|---|---|---|---|---|---|---|---|---|
| ezmd-main* | 1.000 [1.000, 1.000] | 19519 | 15.4% | 19519/19519 | 0.23 | 6.01 | 359 | 5359 |

