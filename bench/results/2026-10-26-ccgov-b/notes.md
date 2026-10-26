## What this run is

The second `ccgov` snapshot, three hours after the first: the 24,127 files on disk when the run started, the
rarest types of snapshot a plus the first of the common modern types, pulled ahead of the rest through a
priority manifest: every Word document the crawl holds (3,295 `.docx`), the PowerPoint decks (290), RTF
(735), EPUB (96), SubRip subtitles (358), email (368) and mailboxes (295), and the start of the legacy `.doc`
set. Excel, CSV, Markdown and JSON were still being pulled and are in the next snapshot. Same build, scorer
and settings as snapshot a (`bench/results/2026-10-26-ccgov-a/`), eight workers.

## Results

Clean rate 0.9986 [0.9981, 0.9990] over 24,127 files: 15,039 outputs, 9,054 declared refusals, 34 bugs.
20,666 seconds of conversion.

| type | n | ok | declared | bug |
|---|---|---|---|---|
| docx | 3,295 | 3,269 | 5 | 21 |
| pptx | 290 | 286 | 4 | 0 |
| rtf | 735 | 735 | 0 | 0 |
| epub | 96 | 96 | 0 | 0 |
| srt | 358 | 358 | 0 | 0 |
| eml | 368 | 365 | 3 | 0 |
| mbox | 295 | 295 | 0 | 0 |

The 34 bugs are the two defects already on the list: the heading level over 6 (31: 21 `.docx`, 10 files
libmagic calls `x-tika-msoffice`; Word's Heading 7 to 9 is used in 0.6% of government Word documents) and the
three macro-enabled workbooks over the time limit. The new declared clusters on the modern Office types: the
OOXML package guard rejected 3 real `.docx` and 3 real `.pptx` for a member over the 100:1 ratio (the guard
issue, now with native files and not only LibreOffice's output), one `.docx` that is not a zip, 25 `.xlsb`,
`.xlam` and `tika-msoffice` files that openpyxl cannot open and no later converter tried, and 38 text files
sent to the XML parser (Perl scripts, ASX playlists, config files, Stata data) with no text fallback.

## Smells of the 15,039 outputs

Gated-clean rate 0.9856. `truncated_full` 197, `heading_repeated` 10, `empty` 5, `lone_bullet` 4. Reported:
`repeated_lines` 552, `empty_table` 310, `replacement_chars` 133, `shrunk` 69, `mojibake` 24, and, now that
the sidecar carries the frontmatter's `injection_risk`, `injection` 1,154: 7.7% of the outputs at medium or
high, the false-positive families of the sweep in the two earlier runs, with code, scripts and logs adding
`rm -rf` and `run the command` hits.

## What this says

- **The modern Office path holds.** 99.2% of Word documents, 98.6% of PowerPoint decks and every RTF, EPUB,
  subtitle and mailbox file produced an output with no crash; the Word failures are one defect (heading
  levels) plus the package guard.
- **The same four fixes cover both corpora.** Heading-level clamp, text floor for text-like MIME types,
  container-verdict resolution with a LibreOffice fallback for `.xlsb`, and the package guard's ratio rule on
  XML parts. Each is a registry, detection or guard rule, not a per-format converter.
- **The injection flag is the loudest smell now.** One output in thirteen is marked medium or high on a
  corpus with no injection in it; on code and logs the rate is higher. That is the false-positive issue.
