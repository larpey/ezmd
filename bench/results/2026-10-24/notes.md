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

## QA model

- `openai/gpt-oss-20b` (MXFP4 GGUF) served by LM Studio on the same GPU, loaded with a 32,768-token context,
  one request at a time, temperature 0, seed 20261013, reasoning effort low. Documents are cut to 24,000 o200k
  tokens before they are sent (no paper in the sample needed cutting except through MinerU's embedded images,
  which are replaced by a placeholder first).
- 148 questions over the 30 papers (five each; one paper yielded three that passed the grounding check).
  Questions are cached under the corpus and shared by every tool row, so every tool answered the same questions.
- The same model grades. UNKNOWN and empty answers are wrong without a model call.

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

## Later the same day: independent witness and damaged papers

- `arxiv-source-recall` was added after the first run and scored over the same outputs. The LaTeX sources came
  from `https://arxiv.org/e-print/<id>` (`fetch --only arxiv-source`); 9 of the 109 papers (3 of the 30 in the
  sample: 2309.11883, 2601.09140, 2604.27899) were submitted as PDF only and have no source. The raw pdfium text
  layer scores 0.945 against the source. Against it ezmd main scores 0.947, ezmd 0.1.0 and rag 0.946, MinerU 0.944,
  Docling 0.943, pymupdf4llm 0.935, compact 0.707, MarkItDown 0.616; paired, ezmd main is +0.004 [+0.002, +0.006]
  over Docling, +0.003 [-0.001, +0.007] over MinerU and +0.012 [+0.005, +0.019] over pymupdf4llm. Link targets
  and DOIs are stripped from the source witness: the first version counted them and credited the full profile,
  which writes URLs out, with words that never print.
- `arxiv-damaged` (`tools/bench/damage.py`, ten papers of the sample, seeded; scan / pages / trunc) ran with
  `--timeout 900` for every tool but Marker and Unstructured (Docker off). The game client was closed partway
  through this run, so its timings are mixed and not reported. ezmd's one silent loss is `2402.18566~trunc`:
  QPDF rebuilt the cross-reference table, pdfium read all 15 pages, 9% of the words (the tail of one content
  stream) were gone and no warning said so; issue #23. ezmd's page accuracy was first scored 0.81 on
  `2604.27899~pages` because that paper has five pages with no text of its own (full-page figures) that the warning
  rightly lists; the scorer now expects those pages, and scores 1.00.
- Speed pass (`runs/2026-10-24-speed/arxiv`, 07:28 to 07:56 local): every tool again over the same 30 papers
  with the game client closed and the GPU otherwise idle (about 3 GB of desktop use). Outputs were identical
  (text recall matched the first pass for every tool to four decimals), so only the timings changed: medians in
  seconds per paper, first pass -> clean pass: ezmd 0.1.0 1.03 -> 1.20, ezmd main full 1.18 -> 1.46, rag 1.22 ->
  1.26, compact 1.13 -> 1.50, MarkItDown 1.69 -> 1.45, pymupdf4llm 4.84 -> 4.66, Docling 6.74 -> 5.75, MinerU
  15.60 -> 12.55. The GPU tools gained 15 to 20%; the CPU tools moved within noise. `docs/benchmarks.md` reports
  the clean pass.
- Claude token counts (`tokens --corpus arxiv --date 2026-10-24 --pdf`, model claude-sonnet-5-5; Sonnet, Opus
  and Haiku return the same count, checked on 2301.00845: 31,802 each): every output of every tool, and the raw
  PDF upload of 28 of the 30 papers (2604.27899 has 108 pages and 2605.03239 is 29.7 MB, 39.6 MB as base64;
  the API takes 100 pages and 32 MB). Upload: 3,054 Claude tokens per page. Output as a share of the upload:
  compact 0.37, Docling 0.47, pymupdf4llm 0.52, ezmd main 0.55, ezmd 0.1.0 0.56, MinerU 0.59, rag 0.67,
  MarkItDown 0.69. These live in scores.json `secondary` (`claude_pdf_upload_tokens_per_page`,
  `claude_share_of_pdf_upload`), not in the category tables.
