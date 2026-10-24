# Benchmark baseline 2026-10-24

Hardware: AMD Ryzen 9 7900X 12-Core Processor, 24 logical cores, 95.1 GB RAM, GPU NVIDIA GeForce RTX 4090, 24564 MiB, 616.56, Windows 11 (10.0.26200).

Each cell: primary metric [95% CI] (n). fail = error/timeout/crash share of attempted documents; cov = attempted/total; s/doc = median and p95 wall seconds; RSS = median and peak over documents of the per-document peak MB (process tree plus any containers the tool starts, models loaded). Rows marked * are ezmd.

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

## arXiv papers, correct answers per 10k tokens of converted text

| tool | metric [95% CI] | n | fail | cov | s/doc med | s/doc p95 | RSS MB med | RSS MB peak |
|---|---|---|---|---|---|---|---|---|
| ezmd-main-compact* | 3.068 [2.600, 3.554] | 30 | 0.0% | 30/30 | 1.13 | 3.90 | 232 | 349 |
| docling | 2.525 [1.979, 3.083] | 30 | 0.0% | 30/30 | 6.74 | 21.85 | 3042 | 5040 |
| pymupdf4llm | 2.250 [1.767, 2.718] | 30 | 0.0% | 30/30 | 4.84 | 25.68 | 480 | 659 |
| mineru | 2.065 [1.636, 2.506] | 30 | 0.0% | 30/30 | 15.60 | 78.85 | 4775 | 6770 |
| ezmd-main* | 2.057 [1.568, 2.541] | 30 | 0.0% | 30/30 | 1.18 | 4.28 | 235 | 348 |
| ezmd* | 2.033 [1.590, 2.457] | 30 | 0.0% | 30/30 | 1.03 | 3.79 | 236 | 356 |
| ezmd-main-rag* | 1.878 [1.421, 2.326] | 30 | 0.0% | 30/30 | 1.22 | 4.42 | 235 | 351 |
| markitdown | 1.613 [1.217, 1.984] | 30 | 0.0% | 30/30 | 1.69 | 16.20 | 176 | 899 |

ezmd: **trails** vs docling (gap -0.491; paired diff -0.491 [-0.804, -0.158] over 30 shared).

ezmd-main: **trails** vs docling (gap -0.468; paired diff -0.468 [-0.792, -0.113] over 30 shared).

ezmd-main-compact: **leads** vs docling (gap +0.543; paired diff +0.543 [+0.001, +1.119] over 30 shared).

ezmd-main-rag: **trails** vs docling (gap -0.647; paired diff -0.647 [-0.959, -0.347] over 30 shared).

## arXiv papers, Claude tokens per page (Anthropic count_tokens; lower is better)

| tool | metric [95% CI] | n | fail | cov | s/doc med | s/doc p95 | RSS MB med | RSS MB peak |
|---|---|---|---|---|---|---|---|---|
| ezmd-main-compact* | 1096.877 [861.671, 1328.859] | 30 | 0.0% | 30/30 | 1.13 | 3.90 | 232 | 349 |
| docling | 1425.253 [1280.921, 1577.441] | 30 | 0.0% | 30/30 | 6.74 | 21.85 | 3042 | 5040 |
| pymupdf4llm | 1590.480 [1433.426, 1770.900] | 30 | 0.0% | 30/30 | 4.84 | 25.68 | 480 | 659 |
| ezmd-main* | 1710.360 [1509.323, 1932.926] | 30 | 0.0% | 30/30 | 1.18 | 4.28 | 235 | 348 |
| ezmd* | 1738.993 [1537.561, 1964.722] | 30 | 0.0% | 30/30 | 1.03 | 3.79 | 236 | 356 |
| mineru | 1819.350 [1592.785, 2079.869] | 30 | 0.0% | 30/30 | 15.60 | 78.85 | 4775 | 6770 |
| ezmd-main-rag* | 2067.327 [1819.438, 2347.938] | 30 | 0.0% | 30/30 | 1.22 | 4.42 | 235 | 351 |
| markitdown | 2112.287 [1848.519, 2376.215] | 30 | 0.0% | 30/30 | 1.69 | 16.20 | 176 | 899 |

ezmd: **trails** vs docling (gap +313.740; paired diff +313.740 [+216.375, +421.178] over 30 shared).

ezmd-main: **trails** vs docling (gap +285.107; paired diff +285.107 [+199.118, +379.341] over 30 shared).

ezmd-main-compact: **leads** vs docling (gap -328.377; paired diff -328.377 [-510.875, -158.294] over 30 shared).

ezmd-main-rag: **trails** vs docling (gap +642.073; paired diff +642.073 [+510.981, +788.297] over 30 shared).

## arXiv papers, outline recall (PDF bookmarks found as headings)

| tool | metric [95% CI] | n | fail | cov | s/doc med | s/doc p95 | RSS MB med | RSS MB peak |
|---|---|---|---|---|---|---|---|---|
| mineru | 0.874 [0.809, 0.933] | 24 | 0.0% | 30/30 | 15.60 | 78.85 | 4775 | 6770 |
| docling | 0.844 [0.782, 0.901] | 24 | 0.0% | 30/30 | 6.74 | 21.85 | 3042 | 5040 |
| pymupdf4llm | 0.843 [0.758, 0.917] | 24 | 0.0% | 30/30 | 4.84 | 25.68 | 480 | 659 |
| ezmd-main* | 0.786 [0.698, 0.863] | 24 | 0.0% | 30/30 | 1.18 | 4.28 | 235 | 348 |
| ezmd-main-rag* | 0.786 [0.698, 0.863] | 24 | 0.0% | 30/30 | 1.22 | 4.42 | 235 | 351 |
| ezmd-main-compact* | 0.567 [0.467, 0.659] | 24 | 0.0% | 30/30 | 1.13 | 3.90 | 232 | 349 |
| ezmd* | 0.506 [0.390, 0.621] | 24 | 0.0% | 30/30 | 1.03 | 3.79 | 236 | 356 |
| markitdown | 0.010 [0.000, 0.026] | 24 | 0.0% | 30/30 | 1.69 | 16.20 | 176 | 899 |

ezmd: **trails** vs mineru (gap -0.368; paired diff -0.368 [-0.485, -0.248] over 24 shared).

ezmd-main: **trails** vs mineru (gap -0.088; paired diff -0.088 [-0.130, -0.048] over 24 shared).

ezmd-main-compact: **trails** vs mineru (gap -0.307; paired diff -0.307 [-0.415, -0.214] over 24 shared).

ezmd-main-rag: **trails** vs mineru (gap -0.088; paired diff -0.088 [-0.130, -0.048] over 24 shared).

## arXiv papers, answer accuracy (local-model QA over the converted text)

| tool | metric [95% CI] | n | fail | cov | s/doc med | s/doc p95 | RSS MB med | RSS MB peak |
|---|---|---|---|---|---|---|---|---|
| docling | 0.800 [0.707, 0.887] | 30 | 0.0% | 30/30 | 6.74 | 21.85 | 3042 | 5040 |
| mineru | 0.796 [0.736, 0.849] | 30 | 0.0% | 30/30 | 15.60 | 78.85 | 4775 | 6770 |
| ezmd* | 0.782 [0.702, 0.856] | 30 | 0.0% | 30/30 | 1.03 | 3.79 | 236 | 356 |
| ezmd-main-rag* | 0.782 [0.693, 0.862] | 30 | 0.0% | 30/30 | 1.22 | 4.42 | 235 | 351 |
| pymupdf4llm | 0.771 [0.671, 0.860] | 30 | 0.0% | 30/30 | 4.84 | 25.68 | 480 | 659 |
| ezmd-main* | 0.758 [0.660, 0.847] | 30 | 0.0% | 30/30 | 1.18 | 4.28 | 235 | 348 |
| ezmd-main-compact* | 0.729 [0.636, 0.813] | 30 | 0.0% | 30/30 | 1.13 | 3.90 | 232 | 349 |
| markitdown | 0.718 [0.629, 0.804] | 30 | 0.0% | 30/30 | 1.69 | 16.20 | 176 | 899 |

ezmd: **ties** vs docling (gap -0.018; paired diff -0.018 [-0.107, +0.076] over 30 shared).

ezmd-main: **ties** vs docling (gap -0.042; paired diff -0.042 [-0.147, +0.067] over 30 shared).

ezmd-main-compact: **ties** vs docling (gap -0.071; paired diff -0.071 [-0.162, +0.027] over 30 shared).

ezmd-main-rag: **ties** vs docling (gap -0.018; paired diff -0.018 [-0.118, +0.082] over 30 shared).

## arXiv papers, silent loss (over 5% of words lost with no warning raised; lower is better)

| tool | metric [95% CI] | n | fail | cov | s/doc med | s/doc p95 | RSS MB med | RSS MB peak |
|---|---|---|---|---|---|---|---|---|
| ezmd* | 0.000 [0.000, 0.000] | 30 | 0.0% | 30/30 | 1.03 | 3.79 | 236 | 356 |
| ezmd-main* | 0.000 [0.000, 0.000] | 30 | 0.0% | 30/30 | 1.18 | 4.28 | 235 | 348 |
| ezmd-main-compact* | 0.000 [0.000, 0.000] | 30 | 0.0% | 30/30 | 1.13 | 3.90 | 232 | 349 |
| ezmd-main-rag* | 0.000 [0.000, 0.000] | 30 | 0.0% | 30/30 | 1.22 | 4.42 | 235 | 351 |
| docling | 0.100 [0.000, 0.200] | 30 | 0.0% | 30/30 | 6.74 | 21.85 | 3042 | 5040 |
| mineru | 0.133 [0.033, 0.267] | 30 | 0.0% | 30/30 | 15.60 | 78.85 | 4775 | 6770 |
| pymupdf4llm | 0.167 [0.067, 0.300] | 30 | 0.0% | 30/30 | 4.84 | 25.68 | 480 | 659 |
| markitdown | 0.900 [0.800, 1.000] | 30 | 0.0% | 30/30 | 1.69 | 16.20 | 176 | 899 |

ezmd: **ties** vs docling (gap -0.100; paired diff -0.100 [-0.200, +0.000] over 30 shared).

ezmd-main: **ties** vs docling (gap -0.100; paired diff -0.100 [-0.200, +0.000] over 30 shared).

ezmd-main-compact: **ties** vs docling (gap -0.100; paired diff -0.100 [-0.200, +0.000] over 30 shared).

ezmd-main-rag: **ties** vs docling (gap -0.100; paired diff -0.100 [-0.200, +0.000] over 30 shared).

## arXiv papers, source recall (share of the LaTeX source's words kept; independent witness)

| tool | metric [95% CI] | n | fail | cov | s/doc med | s/doc p95 | RSS MB med | RSS MB peak |
|---|---|---|---|---|---|---|---|---|
| ezmd-main* | 0.947 [0.915, 0.974] | 27 | 0.0% | 30/30 | 1.18 | 4.28 | 235 | 348 |
| ezmd-main-rag* | 0.946 [0.915, 0.973] | 27 | 0.0% | 30/30 | 1.22 | 4.42 | 235 | 351 |
| ezmd* | 0.946 [0.914, 0.973] | 27 | 0.0% | 30/30 | 1.03 | 3.79 | 236 | 356 |
| mineru | 0.944 [0.912, 0.971] | 27 | 0.0% | 30/30 | 15.60 | 78.85 | 4775 | 6770 |
| docling | 0.943 [0.911, 0.970] | 27 | 0.0% | 30/30 | 6.74 | 21.85 | 3042 | 5040 |
| pymupdf4llm | 0.935 [0.903, 0.963] | 27 | 0.0% | 30/30 | 4.84 | 25.68 | 480 | 659 |
| ezmd-main-compact* | 0.707 [0.618, 0.795] | 27 | 0.0% | 30/30 | 1.13 | 3.90 | 232 | 349 |
| markitdown | 0.616 [0.517, 0.710] | 27 | 0.0% | 30/30 | 1.69 | 16.20 | 176 | 899 |

ezmd: **ties** vs mineru (gap +0.002; paired diff +0.002 [-0.001, +0.006] over 27 shared).

ezmd-main: **ties** vs mineru (gap +0.003; paired diff +0.003 [-0.001, +0.007] over 27 shared).

ezmd-main-compact: **trails** vs mineru (gap -0.236; paired diff -0.236 [-0.331, -0.147] over 27 shared).

ezmd-main-rag: **ties** vs mineru (gap +0.002; paired diff +0.002 [-0.002, +0.007] over 27 shared).

## arXiv papers, text recall (share of the PDF text layer's words kept)

| tool | metric [95% CI] | n | fail | cov | s/doc med | s/doc p95 | RSS MB med | RSS MB peak |
|---|---|---|---|---|---|---|---|---|
| ezmd* | 0.994 [0.991, 0.996] | 30 | 0.0% | 30/30 | 1.03 | 3.79 | 236 | 356 |
| ezmd-main* | 0.992 [0.989, 0.995] | 30 | 0.0% | 30/30 | 1.18 | 4.28 | 235 | 348 |
| ezmd-main-rag* | 0.992 [0.989, 0.995] | 30 | 0.0% | 30/30 | 1.22 | 4.42 | 235 | 351 |
| docling | 0.978 [0.972, 0.983] | 30 | 0.0% | 30/30 | 6.74 | 21.85 | 3042 | 5040 |
| pymupdf4llm | 0.973 [0.961, 0.982] | 30 | 0.0% | 30/30 | 4.84 | 25.68 | 480 | 659 |
| mineru | 0.969 [0.962, 0.975] | 30 | 0.0% | 30/30 | 15.60 | 78.85 | 4775 | 6770 |
| ezmd-main-compact* | 0.707 [0.599, 0.805] | 30 | 0.0% | 30/30 | 1.13 | 3.90 | 232 | 349 |
| markitdown | 0.677 [0.579, 0.762] | 30 | 0.0% | 30/30 | 1.69 | 16.20 | 176 | 899 |

ezmd: **leads** vs docling (gap +0.016; paired diff +0.016 [+0.010, +0.022] over 30 shared).

ezmd-main: **leads** vs docling (gap +0.014; paired diff +0.014 [+0.008, +0.020] over 30 shared).

ezmd-main-compact: **trails** vs docling (gap -0.270; paired diff -0.270 [-0.376, -0.174] over 30 shared).

ezmd-main-rag: **leads** vs docling (gap +0.014; paired diff +0.014 [+0.008, +0.020] over 30 shared).

## arXiv papers, o200k tokens per page (lower is better)

| tool | metric [95% CI] | n | fail | cov | s/doc med | s/doc p95 | RSS MB med | RSS MB peak |
|---|---|---|---|---|---|---|---|---|
| ezmd-main-compact* | 727.100 [569.176, 884.279] | 30 | 0.0% | 30/30 | 1.13 | 3.90 | 232 | 349 |
| docling | 930.107 [833.003, 1039.299] | 30 | 0.0% | 30/30 | 6.74 | 21.85 | 3042 | 5040 |
| pymupdf4llm | 1054.953 [946.508, 1184.591] | 30 | 0.0% | 30/30 | 4.84 | 25.68 | 480 | 659 |
| ezmd-main* | 1158.093 [1011.962, 1321.367] | 30 | 0.0% | 30/30 | 1.18 | 4.28 | 235 | 348 |
| ezmd* | 1180.523 [1033.912, 1349.186] | 30 | 0.0% | 30/30 | 1.03 | 3.79 | 236 | 356 |
| mineru | 1226.150 [1058.370, 1421.583] | 30 | 0.0% | 30/30 | 15.60 | 78.85 | 4775 | 6770 |
| ezmd-main-rag* | 1363.163 [1191.607, 1562.218] | 30 | 0.0% | 30/30 | 1.22 | 4.42 | 235 | 351 |
| markitdown | 1440.580 [1245.652, 1643.544] | 30 | 0.0% | 30/30 | 1.69 | 16.20 | 176 | 899 |

ezmd: **trails** vs docling (gap +250.417; paired diff +250.417 [+171.433, +334.742] over 30 shared).

ezmd-main: **trails** vs docling (gap +227.987; paired diff +227.987 [+160.075, +301.181] over 30 shared).

ezmd-main-compact: **leads** vs docling (gap -203.007; paired diff -203.007 [-331.289, -84.718] over 30 shared).

ezmd-main-rag: **trails** vs docling (gap +433.057; paired diff +433.057 [+343.718, +532.525] over 30 shared).

## Damaged arXiv papers, pages named by the pages_without_text warning (Jaccard; ezmd only)

| tool | metric [95% CI] | n | fail | cov | s/doc med | s/doc p95 | RSS MB med | RSS MB peak |
|---|---|---|---|---|---|---|---|---|
| ezmd* | 1.000 [1.000, 1.000] | 20 | 16.7% | 30/30 | 0.20 | 1.23 | 225 | 244 |
| ezmd-main* | 1.000 [1.000, 1.000] | 20 | 16.7% | 30/30 | 0.39 | 1.33 | 225 | 243 |
| docling | n/a | 0 | 16.7% | 30/30 | 8.13 | 59.78 | 3222 | 4649 |
| markitdown | n/a | 0 | 33.3% | 30/30 | 0.16 | 1.82 | 178 | 230 |
| mineru | n/a | 0 | 30.0% | 30/30 | 14.73 | 67.89 | 4300 | 6704 |
| pymupdf4llm | n/a | 0 | 13.3% | 30/30 | 1.80 | 6.61 | 364 | 583 |

## Damaged arXiv papers, a block of image-only pages: silent loss (lower is better)

| tool | metric [95% CI] | n | fail | cov | s/doc med | s/doc p95 | RSS MB med | RSS MB peak |
|---|---|---|---|---|---|---|---|---|
| ezmd* | 0.000 [0.000, 0.000] | 10 | 16.7% | 30/30 | 0.20 | 1.23 | 225 | 244 |
| ezmd-main* | 0.000 [0.000, 0.000] | 10 | 16.7% | 30/30 | 0.39 | 1.33 | 225 | 243 |
| mineru | 0.100 [0.000, 0.300] | 10 | 30.0% | 30/30 | 14.73 | 67.89 | 4300 | 6704 |
| docling | 0.300 [0.000, 0.600] | 10 | 16.7% | 30/30 | 8.13 | 59.78 | 3222 | 4649 |
| markitdown | 1.000 [1.000, 1.000] | 10 | 33.3% | 30/30 | 0.16 | 1.82 | 178 | 230 |
| pymupdf4llm | 1.000 [1.000, 1.000] | 10 | 13.3% | 30/30 | 1.80 | 6.61 | 364 | 583 |

ezmd: **ties** vs mineru (gap -0.100; paired diff -0.100 [-0.300, +0.000] over 10 shared).

ezmd-main: **ties** vs mineru (gap -0.100; paired diff -0.100 [-0.300, +0.000] over 10 shared).

## Damaged arXiv papers, a block of image-only pages: text recall of the intact paper

| tool | metric [95% CI] | n | fail | cov | s/doc med | s/doc p95 | RSS MB med | RSS MB peak |
|---|---|---|---|---|---|---|---|---|
| mineru | 0.967 [0.959, 0.975] | 10 | 30.0% | 30/30 | 14.73 | 67.89 | 4300 | 6704 |
| docling | 0.962 [0.950, 0.972] | 10 | 16.7% | 30/30 | 8.13 | 59.78 | 3222 | 4649 |
| ezmd-main* | 0.767 [0.737, 0.795] | 10 | 16.7% | 30/30 | 0.39 | 1.33 | 225 | 243 |
| ezmd* | 0.765 [0.736, 0.793] | 10 | 16.7% | 30/30 | 0.20 | 1.23 | 225 | 244 |
| pymupdf4llm | 0.752 [0.726, 0.778] | 10 | 13.3% | 30/30 | 1.80 | 6.61 | 364 | 583 |
| markitdown | 0.488 [0.346, 0.632] | 10 | 33.3% | 30/30 | 0.16 | 1.82 | 178 | 230 |

ezmd: **trails** vs mineru (gap -0.202; paired diff -0.202 [-0.230, -0.173] over 10 shared).

ezmd-main: **trails** vs mineru (gap -0.200; paired diff -0.200 [-0.229, -0.171] over 10 shared).

## Damaged arXiv papers, scanned (every page an image): silent loss (lower is better)

| tool | metric [95% CI] | n | fail | cov | s/doc med | s/doc p95 | RSS MB med | RSS MB peak |
|---|---|---|---|---|---|---|---|---|
| ezmd* | 0.000 [0.000, 0.000] | 10 | 16.7% | 30/30 | 0.20 | 1.23 | 225 | 244 |
| ezmd-main* | 0.000 [0.000, 0.000] | 10 | 16.7% | 30/30 | 0.39 | 1.33 | 225 | 243 |
| mineru | 0.100 [0.000, 0.300] | 10 | 30.0% | 30/30 | 14.73 | 67.89 | 4300 | 6704 |
| docling | 0.800 [0.500, 1.000] | 10 | 16.7% | 30/30 | 8.13 | 59.78 | 3222 | 4649 |
| markitdown | 1.000 [1.000, 1.000] | 10 | 33.3% | 30/30 | 0.16 | 1.82 | 178 | 230 |
| pymupdf4llm | 1.000 [1.000, 1.000] | 10 | 13.3% | 30/30 | 1.80 | 6.61 | 364 | 583 |

ezmd: **ties** vs mineru (gap -0.100; paired diff -0.100 [-0.300, +0.000] over 10 shared).

ezmd-main: **ties** vs mineru (gap -0.100; paired diff -0.100 [-0.300, +0.000] over 10 shared).

## Damaged arXiv papers, scanned: text recall of the intact paper (OCR recovers it)

| tool | metric [95% CI] | n | fail | cov | s/doc med | s/doc p95 | RSS MB med | RSS MB peak |
|---|---|---|---|---|---|---|---|---|
| mineru | 0.970 [0.961, 0.978] | 10 | 30.0% | 30/30 | 14.73 | 67.89 | 4300 | 6704 |
| docling | 0.917 [0.893, 0.940] | 10 | 16.7% | 30/30 | 8.13 | 59.78 | 3222 | 4649 |
| ezmd* | 0.004 [0.003, 0.005] | 10 | 16.7% | 30/30 | 0.20 | 1.23 | 225 | 244 |
| ezmd-main* | 0.004 [0.003, 0.005] | 10 | 16.7% | 30/30 | 0.39 | 1.33 | 225 | 243 |
| markitdown | 0.000 [0.000, 0.000] | 10 | 33.3% | 30/30 | 0.16 | 1.82 | 178 | 230 |
| pymupdf4llm | 0.000 [0.000, 0.000] | 10 | 13.3% | 30/30 | 1.80 | 6.61 | 364 | 583 |

ezmd: **trails** vs mineru (gap -0.966; paired diff -0.966 [-0.974, -0.958] over 10 shared).

ezmd-main: **trails** vs mineru (gap -0.966; paired diff -0.966 [-0.974, -0.958] over 10 shared).

## Damaged arXiv papers, silent loss, all kinds (lost over 5%, no warning; lower is better)

| tool | metric [95% CI] | n | fail | cov | s/doc med | s/doc p95 | RSS MB med | RSS MB peak |
|---|---|---|---|---|---|---|---|---|
| ezmd* | 0.033 [0.000, 0.100] | 30 | 16.7% | 30/30 | 0.20 | 1.23 | 225 | 244 |
| ezmd-main* | 0.033 [0.000, 0.100] | 30 | 16.7% | 30/30 | 0.39 | 1.33 | 225 | 243 |
| mineru | 0.067 [0.000, 0.167] | 30 | 30.0% | 30/30 | 14.73 | 67.89 | 4300 | 6704 |
| docling | 0.400 [0.233, 0.568] | 30 | 16.7% | 30/30 | 8.13 | 59.78 | 3222 | 4649 |
| markitdown | 0.667 [0.500, 0.833] | 30 | 33.3% | 30/30 | 0.16 | 1.82 | 178 | 230 |
| pymupdf4llm | 0.667 [0.500, 0.833] | 30 | 13.3% | 30/30 | 1.80 | 6.61 | 364 | 583 |

ezmd: **ties** vs mineru (gap -0.033; paired diff -0.033 [-0.167, +0.067] over 30 shared).

ezmd-main: **ties** vs mineru (gap -0.033; paired diff -0.033 [-0.167, +0.067] over 30 shared).

## Damaged arXiv papers, file truncated at 80%: silent loss (lower is better)

| tool | metric [95% CI] | n | fail | cov | s/doc med | s/doc p95 | RSS MB med | RSS MB peak |
|---|---|---|---|---|---|---|---|---|
| markitdown | 0.000 [0.000, 0.000] | 10 | 33.3% | 30/30 | 0.16 | 1.82 | 178 | 230 |
| mineru | 0.000 [0.000, 0.000] | 10 | 30.0% | 30/30 | 14.73 | 67.89 | 4300 | 6704 |
| pymupdf4llm | 0.000 [0.000, 0.000] | 10 | 13.3% | 30/30 | 1.80 | 6.61 | 364 | 583 |
| docling | 0.100 [0.000, 0.300] | 10 | 16.7% | 30/30 | 8.13 | 59.78 | 3222 | 4649 |
| ezmd* | 0.100 [0.000, 0.300] | 10 | 16.7% | 30/30 | 0.20 | 1.23 | 225 | 244 |
| ezmd-main* | 0.100 [0.000, 0.300] | 10 | 16.7% | 30/30 | 0.39 | 1.33 | 225 | 243 |

ezmd: **ties** vs markitdown (gap +0.100; paired diff +0.100 [+0.000, +0.300] over 10 shared).

ezmd-main: **ties** vs markitdown (gap +0.100; paired diff +0.100 [+0.000, +0.300] over 10 shared).

## Damaged arXiv papers, file truncated at 80%: text recall of the intact paper

| tool | metric [95% CI] | n | fail | cov | s/doc med | s/doc p95 | RSS MB med | RSS MB peak |
|---|---|---|---|---|---|---|---|---|
| pymupdf4llm | 0.585 [0.291, 0.878] | 10 | 13.3% | 30/30 | 1.80 | 6.61 | 364 | 583 |
| ezmd-main* | 0.486 [0.195, 0.783] | 10 | 16.7% | 30/30 | 0.39 | 1.33 | 225 | 243 |
| ezmd* | 0.486 [0.195, 0.783] | 10 | 16.7% | 30/30 | 0.20 | 1.23 | 225 | 244 |
| docling | 0.480 [0.193, 0.772] | 10 | 16.7% | 30/30 | 8.13 | 59.78 | 3222 | 4649 |
| mineru | 0.096 [0.000, 0.287] | 10 | 30.0% | 30/30 | 14.73 | 67.89 | 4300 | 6704 |
| markitdown | 0.000 [0.000, 0.000] | 10 | 33.3% | 30/30 | 0.16 | 1.82 | 178 | 230 |

ezmd: **ties** vs pymupdf4llm (gap -0.098; paired diff -0.098 [-0.301, +0.014] over 10 shared).

ezmd-main: **ties** vs pymupdf4llm (gap -0.098; paired diff -0.098 [-0.301, +0.014] over 10 shared).

