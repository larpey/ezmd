## Run conditions

- arXiv corpus only (`bench/CORPORA.md`): the seeded 30 of 109 whole papers, seed 20261013; ids in
  `results.json`. The other corpora were not rerun; their 2026-10-13 numbers stand.
- `ezmd-main`, `ezmd-main-compact` and `ezmd-main-rag` are this branch at 7a13bd5 (main at 3c8bdde, the
  0.1.1 release plus the unreleased text-layer PDF fixes of PR #19), wheels built by `install` (`local = true`),
  under the `full`, `compact` and `rag` profiles. `ezmd` is the published 0.1.0 wheel from the 2026-10-13
  baseline's venv; its PDF code is the one 0.1.1 shipped.
- The same machine as the 2026-10-13 baseline. A game client was open and idle for the whole run (about 8.5 GB
  of VRAM and a quarter of the GPU), so every timing is shared with it; speed and memory are indicative only.
- Docker Desktop was not running, so Marker (its vLLM backend is a container) and Unstructured (official image)
  were not attempted. Trafilatura and pandoc do not read PDFs.
- Per-document timeout 300 s. Model loading and warm-up are excluded from s/doc.

## What the metrics mean

- Text recall: share of the PDF text layer's word occurrences (pypdfium2, every page, 3+ alphanumerics,
  NFKC-folded) present in the output. Running headers and footers are part of the text layer, so a tool that
  drops them on purpose gives up a little recall here.
- Silent loss: the document lost more than 5% of those words and the tool raised no warning of a kind that
  means content was dropped, cut or not understood (`tools/bench/scoring/arxiv.py`, LOSS_KINDS). ezmd's
  always-on notices (removed running headers, hidden elements, engine fallback) do not count as a warning; the
  competitors have no warning channel at all. A failed conversion is loud, not silent. Lower is better.
- Outline recall: share of the PDF's bookmarks found as a heading in the output, numbering ignored, over the
  papers with at least three bookmarks.
- Tokens per page: o200k_base tokens of the output (ezmd's frontmatter removed, as in every scorer) over the
  PDF's page count. Lower is better.
- Answer accuracy: five questions per paper written by a local model from the text layer, each backed by a
  verbatim quote that was checked against the text layer, answered from each tool's Markdown by the same model
  (UNKNOWN when the text does not contain the answer) and graded by it against the reference answer. A failed
  conversion answers UNKNOWN to everything. Correct answers per 10k tokens divides the correct count by the
  output's token count.
