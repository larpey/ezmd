# 2026-10-24-heldout: damaged copies of the held-out arXiv papers

The confirmation [issue #23](https://github.com/larpey/ezmd/issues/23) asked for: the `file_repaired` warning was
written after one truncated paper in the ten-paper damaged sample lost 9% of its words with no sign. A fix shaped
to those ten files would look the same on them, so this run damages the 79 arXiv papers outside the 30-paper
sample (`run --corpus arxiv-damaged --split heldout`), papers no converter change was ever checked against, the
same three ways (`tools/bench/damage.py`: scan, pages, trunc; 237 copies), and converts them with the merged
`main` (`ezmd-main`, commit 4fe7461) and with the published 0.1.0 wheel (`ezmd`), which has no such warning.

`damaged-scores.json` is the scorer's output (`tools/bench/scoring/damaged.py`).

## Result

| build | silent loss, all 237 | trunc: silent / repaired and converted / refused loudly | scan: silent | pages: silent | page accuracy |
|---|---|---|---|---|---|
| ezmd main (fix) | 0 of 237 | 0 of 79 / 46 / 33 | 0 of 79 | 0 of 79 | 1.00 (158 image variants) |
| ezmd 0.1.0 | 1 of 237 | 1 of 79 / 46 / 33 | 0 of 79 | 0 of 79 | 1.00 |

- Of the 46 truncated files qpdf repaired, every one carries `file_repaired` in the fixed build. One of them,
  `2605.03112`, kept 94.9% of its words: silent in 0.1.0, declared now. The other 45 kept 95.2% to 99.6%.
- Text recall is the same for both builds to the third decimal (trunc 0.572 against 0.574; the words are gone from
  the file, and the fix declares the loss rather than recovering it).
- Scan recall is 0.004, not 0: the frontmatter's title and warning text share a few dozen words with the paper.

## Conditions

- Same machine and cache as `2026-10-24`. GPU idle. Per-document timeout 300 s. Only the two ezmd builds ran;
  the other tools' behaviour on damaged files is in the sample run and does not change with ezmd's fix.
- The damaged copies are built once into `~/.cache/ezmd-bench/corpora/arxiv/damaged` (about 1.1 GB for the 89
  papers); the build is deterministic for a given pypdfium2 and Pillow version.
