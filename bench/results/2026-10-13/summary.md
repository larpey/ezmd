# Benchmark baseline 2026-10-13

Hardware: AMD Ryzen 9 7900X 12-Core Processor, 24 logical cores, 95.1 GB RAM, GPU NVIDIA GeForce RTX 4090, 24564 MiB, 616.56, Windows 11 (10.0.26200).

Each cell: primary metric [95% CI] (n). fail = error/timeout/crash share of attempted documents; cov = attempted/total; s/doc = median and p95 wall seconds; RSS = median and peak over documents of the per-document peak MB (process tree plus any containers the tool starts, models loaded). Rows marked * are ezmd.

## Run conditions

- First baseline (DECISIONS D-0060). ezmd 0.1.0rc4 from wheels built from commit e9dc151 (the code PyPI will get as
  0.1.0rc4), called as `ezmd.convert(path)` (library default profile `full`). `ezmd-docs` is the same with the
  `docs` extra and the Docling models fetched per docs/install.md.
- The machine was also running a game for the whole session (idle, about 40-50% GPU, 5.7 GB VRAM, 1.8 CPU cores).
  Every timing is shared with it. CPU tools ran 18:00-19:24 CDT. GPU tools (ezmd-docs, Docling, MinerU) ran
  21:17-22:17 CDT next to the idle game, with owner approval. Speed and memory numbers are indicative only.
- Marker 2.0.0 ran with a **non-default** setting: `VLLM_GPU_MEMORY_UTILIZATION=0.65` (its default is 0.85) and a
  30-minute vLLM server start-up, 2026-10-13 23:26 to 2026-10-14 02:55 CDT next to the same idle game. With the
  default 0.85, VRAM next to the game reached 23.9 of 24.6 GB, generation ran at 0.3-1.8 tokens/s and the 2-page
  warm-up did not finish in 10 minutes, so no document could finish within 300 s. On a GPU nobody else is using,
  the default may score differently.
- Samples: olmOCR-Bench up to 50 PDFs per test file (336), OmniDocBench 300 of the 981 pages with original PDFs,
  seed 20261013; ids in results.json. AEB and the fixtures are complete.
- Per-document timeout 300 s. Model loading and warm-up are excluded from s/doc (worker start-up).

## Skipped

- Jina Reader and Firecrawl (self-hosted): URL fetchers only, with multi-service stacks; the HTML snapshots would
  need a local serving setup. Deferred.
- PubTabNet and FinTabNet: table images; ezmd 0.1 accepts no image input (`no converter for image/png`).
  OmniDocBench TEDS covers tables in PDFs.
- LLM-QA accuracy: needs paid model calls; pending.
- CDM formula metric: needs TeX Live, Ghostscript and ImageMagick on Linux; display formulas use edit distance.

## ezmd fixtures (self-graded, supporting evidence only): all

| tool | metric [95% CI] | n | fail | cov | s/doc med | s/doc p95 | RSS MB med | RSS MB peak |
|---|---|---|---|---|---|---|---|---|
| ezmd* | 0.938 [0.893, 0.975] | 94 | 1.1% | 94/94 | 0.03 | 0.24 | 233 | 261 |
| ezmd-docs* | 0.930 [0.884, 0.969] | 94 | 1.1% | 94/94 | 0.02 | 0.47 | 2079 | 2201 |
| mineru | 0.687 [0.524, 0.784] | 10 | 10.0% | 10/94 | 0.53 | 9.78 | 3195 | 3423 |
| trafilatura | 0.641 [0.508, 0.768] | 17 | 0.0% | 17/94 | 0.01 | 0.05 | 68 | 69 |
| marker | 0.616 [0.468, 0.713] | 10 | 10.0% | 10/94 | 0.97 | 3.45 | 4600 | 4670 |
| pymupdf4llm | 0.603 [0.474, 0.706] | 13 | 7.7% | 13/94 | 0.52 | 0.94 | 267 | 314 |
| docling | 0.586 [0.496, 0.671] | 44 | 9.1% | 44/94 | 0.02 | 0.71 | 2075 | 2164 |
| pandoc | 0.564 [0.469, 0.655] | 39 | 10.3% | 39/94 | 0.06 | 0.57 | 24 | 190 |
| markitdown | 0.528 [0.460, 0.600] | 68 | 2.9% | 68/94 | 0.01 | 0.10 | 146 | 149 |
| unstructured | 0.453 [0.381, 0.524] | 67 | 7.5% | 67/94 | 0.08 | 0.47 | 1519 | 1534 |

## ezmd fixtures (self-graded, supporting evidence only): archives

| tool | metric [95% CI] | n | fail | cov | s/doc med | s/doc p95 | RSS MB med | RSS MB peak |
|---|---|---|---|---|---|---|---|---|
| ezmd* | 0.859 [0.577, 1.000] | 6 | 0.0% | 6/6 | 0.03 | 0.05 | 216 | 217 |
| ezmd-docs* | 0.859 [0.577, 1.000] | 6 | 0.0% | 6/6 | 0.02 | 0.03 | 1920 | 1920 |
| markitdown | 0.102 [0.032, 0.163] | 4 | 25.0% | 4/6 | 0.02 | 0.02 | 139 | 139 |

Not attempted (format not supported): docling, marker, mineru, pandoc, pymupdf4llm, trafilatura, unstructured.

## ezmd fixtures (self-graded, supporting evidence only): code

| tool | metric [95% CI] | n | fail | cov | s/doc med | s/doc p95 | RSS MB med | RSS MB peak |
|---|---|---|---|---|---|---|---|---|
| ezmd* | 0.729 [0.539, 0.911] | 11 | 0.0% | 11/11 | 0.02 | 0.38 | 218 | 218 |
| ezmd-docs* | 0.729 [0.539, 0.911] | 11 | 0.0% | 11/11 | 0.01 | 0.18 | 1921 | 1921 |
| markitdown | 0.301 [0.281, 0.341] | 3 | 0.0% | 3/11 | 0.12 | 0.16 | 140 | 140 |

Not attempted (format not supported): docling, marker, mineru, pandoc, pymupdf4llm, trafilatura, unstructured.

## ezmd fixtures (self-graded, supporting evidence only): comms

| tool | metric [95% CI] | n | fail | cov | s/doc med | s/doc p95 | RSS MB med | RSS MB peak |
|---|---|---|---|---|---|---|---|---|
| ezmd* | 1.000 [1.000, 1.000] | 9 | 0.0% | 9/9 | 0.10 | 0.30 | 230 | 233 |
| ezmd-docs* | 1.000 [0.999, 1.000] | 9 | 0.0% | 9/9 | 0.06 | 0.83 | 2076 | 2089 |
| unstructured | 0.181 [0.056, 0.312] | 8 | 25.0% | 8/9 | 0.06 | 6.70 | 1487 | 1489 |
| markitdown | 0.063 [0.063, 0.063] | 1 | 0.0% | 1/9 | 0.01 | 0.01 | 140 | 140 |

Not attempted (format not supported): docling, marker, mineru, pandoc, pymupdf4llm, trafilatura.

## ezmd fixtures (self-graded, supporting evidence only): data

| tool | metric [95% CI] | n | fail | cov | s/doc med | s/doc p95 | RSS MB med | RSS MB peak |
|---|---|---|---|---|---|---|---|---|
| ezmd* | 0.941 [0.827, 1.000] | 18 | 5.6% | 18/18 | 0.03 | 0.08 | 233 | 237 |
| ezmd-docs* | 0.941 [0.827, 1.000] | 18 | 5.6% | 18/18 | 0.01 | 0.05 | 2079 | 2081 |
| pandoc | 0.425 [0.225, 0.625] | 4 | 0.0% | 4/18 | 0.04 | 0.58 | 24 | 110 |
| unstructured | 0.240 [0.106, 0.387] | 12 | 0.0% | 12/18 | 0.07 | 0.13 | 1489 | 1489 |
| docling | 0.198 [0.037, 0.444] | 6 | 50.0% | 6/18 | 0.00 | 0.06 | 1963 | 1963 |
| markitdown | 0.192 [0.104, 0.293] | 12 | 0.0% | 12/18 | 0.01 | 0.01 | 140 | 140 |

Not attempted (format not supported): marker, mineru, pymupdf4llm, trafilatura.

## ezmd fixtures (self-graded, supporting evidence only): ebooks

| tool | metric [95% CI] | n | fail | cov | s/doc med | s/doc p95 | RSS MB med | RSS MB peak |
|---|---|---|---|---|---|---|---|---|
| ezmd* | 1.000 [1.000, 1.000] | 5 | 0.0% | 5/5 | 0.03 | 0.08 | 233 | 233 |
| ezmd-docs* | 1.000 [1.000, 1.000] | 5 | 0.0% | 5/5 | 0.01 | 0.01 | 2079 | 2079 |
| markitdown | 0.655 [0.537, 0.758] | 5 | 0.0% | 5/5 | 0.01 | 0.07 | 141 | 142 |
| pymupdf4llm | 0.542 [0.366, 0.750] | 3 | 0.0% | 3/5 | 0.56 | 0.57 | 265 | 288 |
| pandoc | 0.533 [0.262, 0.705] | 5 | 20.0% | 5/5 | 0.06 | 0.82 | 24 | 190 |
| unstructured | 0.161 [0.000, 0.484] | 3 | 66.7% | 3/5 | 0.19 | 0.60 | 1499 | 1512 |

Not attempted (format not supported): docling, marker, mineru, trafilatura.

## ezmd fixtures (self-graded, supporting evidence only): edgar

| tool | metric [95% CI] | n | fail | cov | s/doc med | s/doc p95 | RSS MB med | RSS MB peak |
|---|---|---|---|---|---|---|---|---|
| ezmd* | 0.749 [0.273, 1.000] | 3 | 0.0% | 3/3 | 0.08 | 0.32 | 233 | 256 |
| ezmd-docs* | 0.749 [0.273, 1.000] | 3 | 0.0% | 3/3 | 0.04 | 0.16 | 2080 | 2102 |
| docling | 0.273 [0.238, 0.313] | 3 | 0.0% | 3/3 | 0.04 | 0.04 | 1963 | 1963 |
| markitdown | 0.241 [0.085, 0.366] | 3 | 0.0% | 3/3 | 0.02 | 0.03 | 142 | 144 |
| trafilatura | 0.208 [0.150, 0.247] | 3 | 0.0% | 3/3 | 0.04 | 0.05 | 68 | 69 |
| pandoc | 0.142 [0.116, 0.191] | 3 | 0.0% | 3/3 | 0.16 | 0.18 | 105 | 115 |
| unstructured | 0.119 [0.059, 0.197] | 3 | 0.0% | 3/3 | 0.16 | 0.21 | 1512 | 1512 |

Not attempted (format not supported): marker, mineru, pymupdf4llm.

## ezmd fixtures (self-graded, supporting evidence only): office

| tool | metric [95% CI] | n | fail | cov | s/doc med | s/doc p95 | RSS MB med | RSS MB peak |
|---|---|---|---|---|---|---|---|---|
| ezmd* | 1.000 [1.000, 1.000] | 12 | 0.0% | 12/12 | 0.03 | 0.11 | 256 | 260 |
| ezmd-docs* | 1.000 [1.000, 1.000] | 12 | 0.0% | 12/12 | 0.01 | 0.13 | 2102 | 2105 |
| markitdown | 0.602 [0.535, 0.667] | 10 | 0.0% | 10/12 | 0.02 | 0.03 | 146 | 148 |
| docling | 0.568 [0.432, 0.701] | 9 | 0.0% | 9/12 | 0.03 | 0.23 | 1967 | 1967 |
| unstructured | 0.513 [0.434, 0.581] | 11 | 0.0% | 11/12 | 0.09 | 0.31 | 1518 | 1531 |
| pandoc | 0.447 [0.268, 0.618] | 11 | 27.3% | 11/12 | 0.04 | 0.08 | 24 | 24 |

Not attempted (format not supported): marker, mineru, pymupdf4llm, trafilatura.

## ezmd fixtures (self-graded, supporting evidence only): pdf

| tool | metric [95% CI] | n | fail | cov | s/doc med | s/doc p95 | RSS MB med | RSS MB peak |
|---|---|---|---|---|---|---|---|---|
| ezmd* | 1.000 [1.000, 1.000] | 10 | 0.0% | 10/10 | 0.04 | 0.08 | 260 | 261 |
| ezmd-docs* | 0.928 [0.804, 1.000] | 10 | 0.0% | 10/10 | 0.46 | 0.65 | 2167 | 2201 |
| mineru | 0.687 [0.524, 0.784] | 10 | 10.0% | 10/10 | 0.53 | 9.78 | 3195 | 3423 |
| unstructured | 0.663 [0.470, 0.841] | 10 | 10.0% | 10/10 | 0.12 | 0.21 | 1533 | 1534 |
| docling | 0.637 [0.463, 0.775] | 10 | 10.0% | 10/10 | 0.50 | 0.76 | 2133 | 2164 |
| pymupdf4llm | 0.621 [0.472, 0.721] | 10 | 10.0% | 10/10 | 0.38 | 0.95 | 288 | 314 |
| marker | 0.616 [0.468, 0.713] | 10 | 10.0% | 10/10 | 0.97 | 3.45 | 4600 | 4670 |
| markitdown | 0.585 [0.441, 0.686] | 10 | 10.0% | 10/10 | 0.02 | 0.12 | 148 | 148 |

Not attempted (format not supported): pandoc, trafilatura.

## ezmd fixtures (self-graded, supporting evidence only): text

| tool | metric [95% CI] | n | fail | cov | s/doc med | s/doc p95 | RSS MB med | RSS MB peak |
|---|---|---|---|---|---|---|---|---|
| ezmd* | 1.000 [1.000, 1.000] | 6 | 0.0% | 6/6 | 0.01 | 0.02 | 261 | 261 |
| ezmd-docs* | 1.000 [1.000, 1.000] | 6 | 0.0% | 6/6 | 0.01 | 0.01 | 2170 | 2170 |
| pandoc | 0.883 [0.825, 0.941] | 2 | 0.0% | 2/6 | 0.09 | 0.10 | 64 | 103 |
| markitdown | 0.862 [0.738, 0.971] | 6 | 0.0% | 6/6 | 0.01 | 0.03 | 148 | 148 |
| docling | 0.824 [0.798, 0.851] | 2 | 0.0% | 2/6 | 0.05 | 0.08 | 2124 | 2124 |
| unstructured | 0.642 [0.474, 0.826] | 6 | 0.0% | 6/6 | 0.09 | 0.12 | 1534 | 1534 |

Not attempted (format not supported): marker, mineru, pymupdf4llm, trafilatura.

## ezmd fixtures (self-graded, supporting evidence only): web

| tool | metric [95% CI] | n | fail | cov | s/doc med | s/doc p95 | RSS MB med | RSS MB peak |
|---|---|---|---|---|---|---|---|---|
| ezmd* | 0.987 [0.969, 1.000] | 14 | 0.0% | 14/14 | 0.03 | 0.06 | 261 | 261 |
| ezmd-docs* | 0.987 [0.969, 1.000] | 14 | 0.0% | 14/14 | 0.02 | 0.02 | 2170 | 2170 |
| markitdown | 0.801 [0.694, 0.895] | 14 | 0.0% | 14/14 | 0.01 | 0.02 | 148 | 149 |
| docling | 0.759 [0.636, 0.872] | 14 | 0.0% | 14/14 | 0.01 | 0.02 | 2124 | 2124 |
| pandoc | 0.752 [0.638, 0.848] | 14 | 0.0% | 14/14 | 0.05 | 0.11 | 24 | 106 |
| trafilatura | 0.734 [0.617, 0.836] | 14 | 0.0% | 14/14 | 0.01 | 0.01 | 68 | 69 |
| unstructured | 0.647 [0.524, 0.774] | 14 | 0.0% | 14/14 | 0.06 | 0.09 | 1534 | 1534 |

Not attempted (format not supported): marker, mineru, pymupdf4llm.

## PDF, OmniDocBench display formulas (1 - edit distance; CDM off)

| tool | metric [95% CI] | n | fail | cov | s/doc med | s/doc p95 | RSS MB med | RSS MB peak |
|---|---|---|---|---|---|---|---|---|
| marker | 0.813 [0.746, 0.875] | 17 | 0.7% | 300/300 | 3.84 | 40.02 | 5489 | 9263 |
| mineru | 0.764 [0.634, 0.877] | 17 | 0.0% | 300/300 | 1.12 | 5.67 | 3455 | 3982 |
| unstructured | 0.116 [0.051, 0.192] | 17 | 0.0% | 300/300 | 0.24 | 5.92 | 800 | 12005 |
| ezmd* | 0.093 [0.046, 0.161] | 17 | 0.0% | 300/300 | 0.07 | 0.51 | 234 | 273 |
| markitdown | 0.081 [0.019, 0.163] | 17 | 0.0% | 300/300 | 0.10 | 0.71 | 184 | 239 |
| ezmd-docs* | 0.047 [0.028, 0.068] | 17 | 0.3% | 300/300 | 0.61 | 2.00 | 2642 | 3582 |
| docling | 0.030 [0.007, 0.059] | 17 | 0.0% | 300/300 | 0.98 | 3.17 | 4033 | 5610 |
| pymupdf4llm | 0.029 [0.005, 0.064] | 17 | 0.0% | 300/300 | 0.27 | 0.77 | 286 | 416 |

Not attempted (format not supported): pandoc, trafilatura.

ezmd: **trails** vs marker (gap -0.720; paired diff -0.720 [-0.804, -0.637] over 17 shared).

ezmd-docs: **trails** vs marker (gap -0.766; paired diff -0.766 [-0.833, -0.695] over 17 shared).

## PDF, OmniDocBench reading order (1 - edit distance)

| tool | metric [95% CI] | n | fail | cov | s/doc med | s/doc p95 | RSS MB med | RSS MB peak |
|---|---|---|---|---|---|---|---|---|
| mineru | 0.851 [0.819, 0.879] | 295 | 0.0% | 300/300 | 1.12 | 5.67 | 3455 | 3982 |
| docling | 0.759 [0.722, 0.792] | 295 | 0.0% | 300/300 | 0.98 | 3.17 | 4033 | 5610 |
| marker | 0.718 [0.679, 0.756] | 295 | 0.7% | 300/300 | 3.84 | 40.02 | 5489 | 9263 |
| ezmd-docs* | 0.621 [0.579, 0.660] | 295 | 0.3% | 300/300 | 0.61 | 2.00 | 2642 | 3582 |
| unstructured | 0.613 [0.569, 0.655] | 295 | 0.0% | 300/300 | 0.24 | 5.92 | 800 | 12005 |
| pymupdf4llm | 0.553 [0.500, 0.599] | 295 | 0.0% | 300/300 | 0.27 | 0.77 | 286 | 416 |
| markitdown | 0.480 [0.433, 0.526] | 295 | 0.0% | 300/300 | 0.10 | 0.71 | 184 | 239 |
| ezmd* | 0.426 [0.383, 0.467] | 295 | 0.0% | 300/300 | 0.07 | 0.51 | 234 | 273 |

Not attempted (format not supported): pandoc, trafilatura.

ezmd: **trails** vs mineru (gap -0.425; paired diff -0.425 [-0.472, -0.376] over 295 shared).

ezmd-docs: **trails** vs mineru (gap -0.230; paired diff -0.230 [-0.269, -0.192] over 295 shared).

## PDF, OmniDocBench tables (TEDS)

| tool | metric [95% CI] | n | fail | cov | s/doc med | s/doc p95 | RSS MB med | RSS MB peak |
|---|---|---|---|---|---|---|---|---|
| mineru | 0.847 [0.800, 0.892] | 129 | 0.0% | 300/300 | 1.12 | 5.67 | 3455 | 3982 |
| marker | 0.657 [0.599, 0.711] | 129 | 0.7% | 300/300 | 3.84 | 40.02 | 5489 | 9263 |
| docling | 0.580 [0.514, 0.641] | 129 | 0.0% | 300/300 | 0.98 | 3.17 | 4033 | 5610 |
| pymupdf4llm | 0.433 [0.362, 0.501] | 129 | 0.0% | 300/300 | 0.27 | 0.77 | 286 | 416 |
| ezmd-docs* | 0.421 [0.347, 0.495] | 129 | 0.3% | 300/300 | 0.61 | 2.00 | 2642 | 3582 |
| ezmd* | 0.150 [0.100, 0.203] | 129 | 0.0% | 300/300 | 0.07 | 0.51 | 234 | 273 |
| markitdown | 0.097 [0.056, 0.139] | 129 | 0.0% | 300/300 | 0.10 | 0.71 | 184 | 239 |
| unstructured | 0.002 [0.000, 0.005] | 129 | 0.0% | 300/300 | 0.24 | 5.92 | 800 | 12005 |

Not attempted (format not supported): pandoc, trafilatura.

ezmd: **trails** vs mineru (gap -0.697; paired diff -0.697 [-0.769, -0.627] over 129 shared).

ezmd-docs: **trails** vs mineru (gap -0.426; paired diff -0.426 [-0.520, -0.333] over 129 shared).

## PDF, OmniDocBench text (1 - edit distance)

| tool | metric [95% CI] | n | fail | cov | s/doc med | s/doc p95 | RSS MB med | RSS MB peak |
|---|---|---|---|---|---|---|---|---|
| mineru | 0.946 [0.932, 0.960] | 278 | 0.0% | 300/300 | 1.12 | 5.67 | 3455 | 3982 |
| marker | 0.882 [0.857, 0.906] | 278 | 0.7% | 300/300 | 3.84 | 40.02 | 5489 | 9263 |
| docling | 0.851 [0.817, 0.882] | 278 | 0.0% | 300/300 | 0.98 | 3.17 | 4033 | 5610 |
| unstructured | 0.676 [0.629, 0.721] | 278 | 0.0% | 300/300 | 0.24 | 5.92 | 800 | 12005 |
| ezmd-docs* | 0.666 [0.618, 0.712] | 278 | 0.3% | 300/300 | 0.61 | 2.00 | 2642 | 3582 |
| pymupdf4llm | 0.620 [0.570, 0.669] | 278 | 0.0% | 300/300 | 0.27 | 0.77 | 286 | 416 |
| markitdown | 0.443 [0.391, 0.491] | 278 | 0.0% | 300/300 | 0.10 | 0.71 | 184 | 239 |
| ezmd* | 0.286 [0.245, 0.328] | 278 | 0.0% | 300/300 | 0.07 | 0.51 | 234 | 273 |

Not attempted (format not supported): pandoc, trafilatura.

ezmd: **trails** vs mineru (gap -0.660; paired diff -0.660 [-0.703, -0.617] over 278 shared).

ezmd-docs: **trails** vs mineru (gap -0.280; paired diff -0.280 [-0.328, -0.235] over 278 shared).

## PDF, olmOCR-Bench (unit-test pass rate)

| tool | metric [95% CI] | n | fail | cov | s/doc med | s/doc p95 | RSS MB med | RSS MB peak |
|---|---|---|---|---|---|---|---|---|
| mineru | 0.797 [0.782, 0.811] | 336 | 0.0% | 336/336 | 2.78 | 8.35 | 3501 | 3959 |
| marker | 0.759 [0.742, 0.775] | 336 | 0.0% | 336/336 | 9.23 | 89.31 | 8903 | 11918 |
| docling | 0.543 [0.527, 0.557] | 336 | 0.3% | 336/336 | 1.12 | 3.21 | 3036 | 5867 |
| ezmd-docs* | 0.480 [0.464, 0.494] | 336 | 0.0% | 336/336 | 0.57 | 1.48 | 3079 | 4264 |
| pymupdf4llm | 0.333 [0.314, 0.351] | 336 | 0.0% | 336/336 | 0.36 | 1.28 | 256 | 501 |
| unstructured | 0.313 [0.297, 0.330] | 336 | 0.0% | 336/336 | 0.28 | 27.74 | 729 | 12313 |
| ezmd* | 0.277 [0.262, 0.292] | 336 | 0.0% | 336/336 | 0.08 | 0.30 | 230 | 256 |
| markitdown | 0.264 [0.247, 0.282] | 336 | 0.6% | 336/336 | 0.11 | 0.56 | 172 | 223 |

Not attempted (format not supported): pandoc, trafilatura.

ezmd: **trails** vs mineru (gap -0.520; paired diff -0.474 [-0.507, -0.438] over 336 shared).

ezmd-docs: **trails** vs mineru (gap -0.317; paired diff -0.276 [-0.312, -0.240] over 336 shared).

## Web articles, ScrapingHub AEB (article-body F1)

| tool | metric [95% CI] | n | fail | cov | s/doc med | s/doc p95 | RSS MB med | RSS MB peak |
|---|---|---|---|---|---|---|---|---|
| trafilatura | 0.952 [0.939, 0.963] | 181 | 0.0% | 181/181 | 0.02 | 0.05 | 74 | 79 |
| ezmd* | 0.914 [0.895, 0.930] | 181 | 0.0% | 181/181 | 0.29 | 0.64 | 270 | 282 |
| ezmd-docs* | 0.914 [0.895, 0.930] | 181 | 0.0% | 181/181 | 0.07 | 0.13 | 1969 | 1978 |
| unstructured | 0.755 [0.726, 0.783] | 181 | 0.0% | 181/181 | 0.15 | 0.38 | 716 | 738 |
| pandoc | 0.724 [0.694, 0.753] | 181 | 0.0% | 181/181 | 0.31 | 0.93 | 130 | 992 |
| docling | 0.713 [0.685, 0.742] | 181 | 0.0% | 181/181 | 0.07 | 0.16 | 2040 | 2045 |
| markitdown | 0.653 [0.622, 0.683] | 181 | 0.0% | 181/181 | 0.04 | 0.09 | 160 | 170 |

Not attempted (format not supported): marker, mineru, pymupdf4llm.

ezmd: **trails** vs trafilatura (gap -0.038; paired diff -0.036 [-0.055, -0.016] over 181 shared).

ezmd-docs: **trails** vs trafilatura (gap -0.038; paired diff -0.036 [-0.055, -0.016] over 181 shared).

