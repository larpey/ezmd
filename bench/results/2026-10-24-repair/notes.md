# 2026-10-24-repair: the `file_repaired` warning says where

Follow-up to [issue #23](https://github.com/larpey/ezmd/issues/23) and `2026-10-24-heldout`. The warning those
runs confirmed was a file-level flag. This build (`ezmd_converters/pdf/repair.py`, branch `feat/repair-page-detail`
on top of `main` 4e26941) adds to its detail what the repaired file's object graph can place: the pages whose
content stream is gone or cut (`pages_content_damaged`, also the warning's `page`), the pages that draw an image or
form XObject that is gone (`pages_figures_missing`), and a count of fonts that lost part of their definition
(`fonts_damaged`). The scorer (`tools/bench/scoring/damaged.py`) gains `located_when_lost`: of the repaired files
that lost over 5% of their words, the share whose warning carries any of the three.

`damaged-scores.json` is the scorer's output for the 30-paper damaged sample, `damaged-scores-heldout.json` for
the 237 damaged copies of the 79 held-out papers (`run --split heldout`), `ezmd-main` only.

## Result

| split | silent loss | trunc: repaired and converted / refused loudly | repaired files with located detail | located when lost | trunc recall | page accuracy |
|---|---|---|---|---|---|---|
| sample | 0 of 30 | 5 / 5 | 5 of 5 | 1 of 1 | 0.486 | 1.00 (20 image variants) |
| held out | 0 of 237 | 46 / 33 | 44 of 46 | 1 of 1 | 0.572 | 1.00 (158 image variants) |

Held out: of the 46 repaired files, 42 count damaged fonts, 18 name pages that lost a figure or form, 2 name pages
that lost their content stream, and 2 locate nothing (the cut fell in objects no page draws). The one file that lost
over 5% of its words, `2605.03112` (94.7% kept), names page 6 as having lost a figure and 27 damaged fonts.

- All five repaired truncated files carry located detail. The one that lost over 5% of its words, `2402.18566`
  (91% kept), names page 1, whose second content stream (the arXiv stamp) is gone, and 16 damaged fonts. The words
  it lost are on pages 3, 12 and 13, set in those fonts; the message says text set in them may be incomplete on
  pages that cannot be pinpointed.
- The other four: `2601.01904` names pages 4 and 26 as having lost a figure and 22 fonts; `2605.12617` page 19
  and 27 fonts; `2511.10456` 17 fonts; `2604.22634` 8 fonts.
- Silent loss, recall and page accuracy are unchanged from `2026-10-24-heldout` and `2026-10-24-fix3`; the change
  adds to the warning's detail and does not touch extraction.

## Why fonts are counted, not placed

Measured on the 51 repaired truncated papers of the sample and held-out sets against the intact papers' text
(pdfium on both; a page counts as lost under 90% word overlap or 90% of the characters):

| classifier over each page's reachable objects | pages flagged | of which lost text | lost pages missed |
|---|---|---|---|
| any reference the repair left dangling | 803 | 27 | 1 |
| only entries that map codes to text (content, font, encoding, ToUnicode, glyph procedures, widths, descendant fonts, XObjects) | 375 | 17 | 11 |
| definite losses only (content stream gone or cut; XObject gone) | 47 | 4 | 24 |

28 pages lost text in all. The words that went were figure axis labels (Type3 fonts whose glyph procedures were
past the cut), math symbols and ligatures (fonts whose program or ToUnicode map was past the cut), text drawn
through a form XObject that was past the cut, and one page whose content stream was. Whether a damaged font costs
text on a given page depends on the font type and pdfium's fallbacks, so the detail places the definite losses
and counts the fonts. 47 of the 51 repaired files have at least one damaged font; every one of the 12 that lost
over 5% of their words carries located detail.

## Conditions

- Same machine and cache as `2026-10-24`. GPU idle. Per-document timeout 300 s. `install --tools ezmd-main
  --force` rebuilt the tool's wheels from this checkout first; the run before that rebuild carried the previous
  build's warnings and was discarded.
