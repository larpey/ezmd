# Benchmark baseline 2026-10-24-whole

Hardware: AMD Ryzen 9 7900X 12-Core Processor, 24 logical cores, 95.1 GB RAM, GPU NVIDIA GeForce RTX 4090, 24564 MiB, 616.56, Windows 11 (10.0.26200).

Each cell: primary metric [95% CI] (n). fail = error/timeout/crash share of attempted documents; cov = attempted/total; s/doc = median and p95 wall seconds; RSS = median and peak over documents of the per-document peak MB (process tree plus any containers the tool starts, models loaded). Rows marked * are ezmd.

## What this run is

The 2026-10-24 whole-paper benchmark answered questions written from the first 24,000 tokens of each paper
and cut every tool's output at that point, so a converter that drops a paper's tail (ezmd's `compact` profile
stops at 16,000 tokens) was barely measured. This run keeps the same 30 papers and the same outputs for the
tools that did not change, and replaces the question set and the answering step:

- Questions come from every 8,000-token segment of the PDF's text layer (`tools/bench/qa.py`, `scheme:
  segments-8k`): the model is asked for three per segment and the two best-grounded are kept, each with a
  verbatim quote checked against the text layer and the segment's token range recorded. 176 questions over the
  30 papers, one to fourteen each over one to seven segments (the text layers run from 7,909 to 57,520 o200k
  tokens; one paper's single segment yielded one question that passed the grounding check).
- The answering model reads each tool's whole output. The model is loaded with a 131,072-token context; an
  output that does not fit is cut and the record says so (`cut`). No output was cut in this run (MinerU's
  embedded images are replaced by a placeholder before counting).
- A new category, `arxiv-qa-second-half`, scores only the questions whose evidence lies in the second half of
  the text layer, which is where a tail-dropping profile pays.

## Run conditions

- arXiv corpus only (`bench/CORPORA.md`): the seeded 30 of 109 whole papers, seed 20261013; ids in
  `results.json`. The outputs of `docling`, `ezmd` (0.1.0), `ezmd-docs`, `markitdown`, `mineru` and
  `pymupdf4llm` are the 2026-10-24 outputs copied into this run. `ezmd-main`, `ezmd-main-compact` and
  `ezmd-main-rag` were converted at fa1d5cf (main on 2026-10-24, the 0.1.1 release plus #25), wheels built by
  `install`.
- Docker Desktop was not running, so Marker and Unstructured were not attempted and score as failed
  conversions (UNKNOWN to every question) as in the 2026-10-24 run.
- The QA pass was interrupted twice: a game client took the GPU on the night of 2026-10-24 (the first attempt
  hung 30 minutes and timed out; the harness now stops cleanly on a server error and resumes from its caches),
  and the model server refused one MinerU output with HTTP 400 ("Failed to process regex"): MinerU had read a
  table's rules as a 764-character run of one CJK character, and the server's tokenizer could not take it. The
  harness now squeezes runs of one non-ASCII character to 32 before sending, and a refused text fails only that
  document. One MinerU answer set was also lost to a JSON escape bug in the harness (a `\\sum` the model had
  escaped correctly became three backslashes); fixed, re-answered.
- Claude token counts (`arxiv-claude-tokens-per-page`) are the cached counts from the 2026-10-24 run, keyed by
  the output's hash: complete for the ezmd profiles, pymupdf4llm, MarkItDown and ezmd 0.1.0; missing for
  `ezmd-docs` (30), Docling (1) and MinerU (7), whose outputs or caches were not carried over. No API key was
  available on this machine for a recount, so those rows have fewer documents in that one category.
- Timings are not reported: the outputs are the 2026-10-24 outputs, and `docs/benchmarks.md` already reports
  the clean speed pass of that day.

## QA model

- `openai/gpt-oss-20b` (MXFP4 GGUF) served by LM Studio on the same GPU, loaded with a 131,072-token context,
  one request at a time, temperature 0, seed 20261013, reasoning effort low.
- Questions are cached under the corpus (`segments-8k`) and shared by every tool row; answers are cached by
  the exact text the model saw and verdicts by (document, question, answer text), as before, so a tool whose
  output did not change scores the same in every run.
- The same model grades. UNKNOWN and empty answers are wrong without a model call.

## Results

Answer accuracy over the whole paper (176 questions), then on the questions whose evidence is in the second
half of the text layer (n = 29 papers, one paper has no second-half question), with the paired difference
against the best competitor row, MarkItDown:

| tool | whole paper | second half | paired vs MarkItDown (whole) |
|---|---|---|---|
| ezmd [docs] (Docling engine) | 0.808 [0.723, 0.881] | 0.741 [0.634, 0.841] | +0.021 [-0.055, +0.117] |
| MarkItDown 0.1.8 | 0.787 [0.688, 0.870] | 0.753 [0.642, 0.858] | |
| ezmd main, full | 0.780 [0.691, 0.862] | 0.716 [0.603, 0.815] | -0.006 [-0.070, +0.051] |
| ezmd main, rag | 0.761 [0.668, 0.844] | 0.706 [0.603, 0.800] | -0.025 [-0.087, +0.041] |
| Docling 2.138.0 | 0.758 [0.667, 0.839] | 0.707 [0.595, 0.810] | |
| MinerU 4.0.12 | 0.753 [0.657, 0.835] | 0.684 [0.573, 0.793] | |
| ezmd 0.1.0 | 0.698 [0.577, 0.805] | 0.621 [0.483, 0.750] | -0.089 [-0.170, -0.027] |
| pymupdf4llm 1.28.2 | 0.677 [0.558, 0.788] | 0.582 [0.456, 0.711] | |
| ezmd main, compact | 0.564 [0.425, 0.695] | 0.453 [0.306, 0.608] | -0.223 [-0.324, -0.136] |

- **The compact profile's cut is now measured, and it is not cheap.** With questions spread over the whole paper,
  compact answers 0.564 against 0.780 for the full profile on the same papers, and 0.453 against 0.716 on
  second-half questions. The 2026-10-24 run scored compact 0.729 because 145 of its 148 questions came from the
  part compact kept. A consumer that needs the whole paper should not use compact; the profile's own
  `truncated` flag and the `pdf_pages_converted` metadata say when the tail went.
- **The full profile ties the best rows and the field is flat.** Six tools sit within 0.06 of each other with
  overlapping intervals; the paired test calls ezmd main a tie with MarkItDown, Docling and MinerU. The questions
  are facts a model can find in a readable text, which every tool but compact and 0.1.0 provides for the whole
  paper. MarkItDown's rise (0.738 to 0.787) is the only ranking change worth a sentence: its output is close to the
  raw text layer the questions were written from, and reading the whole paper rewards that, while its 0.677 text
  recall and 0.90 silent-loss share are unchanged.
- **0.1.0 to main is a real gain for the text-layer engine:** 0.698 to 0.780 on the same questions, and 0.621 to
  0.716 on the second half, where the double-spaced-paragraph and running-header fixes of #19 and the figure
  handling land.
- The other categories (text recall, source recall, silent loss, outline recall, tokens per page) are the
  2026-10-24 numbers, since the outputs are the same files; `summary.md` repeats them for completeness.

## The figure-lettering fix on the same papers (`bench/results/2026-10-25-figtext/compare.md`)

`runs/2026-10-25-figtext` converted the 30 papers with #27 (figure lettering kept out of table detection) under
the three ezmd profiles and answered the same 176 questions. Paired, after minus before: answer accuracy full
-0.004 [-0.013, +0.000], compact +0.013 [+0.000, +0.035], rag +0.007 [-0.005, +0.023]; second-half full -0.006
[-0.017, +0.000]; o200k tokens per page full -18.8 [-32.8, -7.2] and rag -21.9 [-38.6, -8.3]; outline recall,
text recall, source recall and silent loss unchanged. Pipe tables in the full profile's Markdown went from 581 to
413 over the 30 papers (10 papers changed, 100 figure paragraphs), with no body text lost: the 1.2% of word
tokens that disappeared are synthesized table headers and repeated row keys. One compact output grew: a 47-row
pulsar table in 2604.22634 that lettering had pushed over the row cap is rendered in full now.

## arXiv papers, correct answers per 10k tokens of converted text

| tool | metric [95% CI] | n | fail | cov | s/doc med | s/doc p95 | RSS MB med | RSS MB peak |
|---|---|---|---|---|---|---|---|---|
| ezmd-main-compact* | 2.173 [1.647, 2.712] | 30 | 0.0% | 30/30 | 1.12 | 3.88 | 232 | 350 |
| ezmd-docs* | 2.171 [1.890, 2.433] | 30 | 0.0% | 30/30 | 4.84 | 23.81 | 2727 | 4635 |
| docling | 2.112 [1.800, 2.402] | 30 | 0.0% | 30/30 | 6.74 | 22.61 | 3051 | 5053 |
| ezmd-main* | 1.893 [1.602, 2.184] | 30 | 0.0% | 30/30 | 1.22 | 4.35 | 239 | 349 |
| pymupdf4llm | 1.843 [1.500, 2.165] | 30 | 0.0% | 30/30 | 5.60 | 29.18 | 483 | 654 |
| mineru | 1.734 [1.433, 2.020] | 30 | 0.0% | 30/30 | 22.11 | 126.82 | 4815 | 6811 |
| ezmd* | 1.671 [1.325, 1.987] | 30 | 0.0% | 30/30 | 1.07 | 3.93 | 236 | 358 |
| ezmd-main-rag* | 1.634 [1.381, 1.905] | 30 | 0.0% | 30/30 | 1.22 | 4.39 | 234 | 343 |
| markitdown | 1.576 [1.315, 1.805] | 30 | 0.0% | 30/30 | 1.67 | 15.84 | 177 | 900 |
| marker | n/a | 0 | 100.0% | 30/30 | 4.43 | 10.31 | 1116 | 1635 |
| unstructured | n/a | 0 | 100.0% | 30/30 | n/a | n/a | n/a | n/a |

Not attempted (format not supported): pandoc, trafilatura.

ezmd: **trails** vs docling (gap -0.441; paired diff -0.441 [-0.666, -0.224] over 30 shared).

ezmd-docs: **ties** vs docling (gap +0.059; paired diff +0.059 [-0.136, +0.285] over 30 shared).

ezmd-main: **ties** vs docling (gap -0.219; paired diff -0.219 [-0.471, +0.036] over 30 shared).

ezmd-main-compact: **ties** vs docling (gap +0.061; paired diff +0.061 [-0.392, +0.563] over 30 shared).

ezmd-main-rag: **trails** vs docling (gap -0.478; paired diff -0.478 [-0.723, -0.218] over 30 shared).

## arXiv papers, Claude tokens per page (Anthropic count_tokens; lower is better)

| tool | metric [95% CI] | n | fail | cov | s/doc med | s/doc p95 | RSS MB med | RSS MB peak |
|---|---|---|---|---|---|---|---|---|
| ezmd-main-compact* | 1111.530 [878.550, 1331.770] | 30 | 0.0% | 30/30 | 1.12 | 3.88 | 232 | 350 |
| docling | 1414.376 [1272.186, 1561.572] | 29 | 0.0% | 30/30 | 6.74 | 22.61 | 3051 | 5053 |
| pymupdf4llm | 1590.480 [1433.649, 1770.407] | 30 | 0.0% | 30/30 | 5.60 | 29.18 | 483 | 654 |
| ezmd-main* | 1681.387 [1483.503, 1896.681] | 30 | 0.0% | 30/30 | 1.22 | 4.35 | 239 | 349 |
| mineru | 1738.274 [1519.723, 1990.764] | 23 | 0.0% | 30/30 | 22.11 | 126.82 | 4815 | 6811 |
| ezmd* | 1738.993 [1537.561, 1964.722] | 30 | 0.0% | 30/30 | 1.07 | 3.93 | 236 | 358 |
| ezmd-main-rag* | 1974.960 [1738.399, 2239.920] | 30 | 0.0% | 30/30 | 1.22 | 4.39 | 234 | 343 |
| markitdown | 2112.287 [1848.519, 2376.215] | 30 | 0.0% | 30/30 | 1.67 | 15.84 | 177 | 900 |
| ezmd-docs* | n/a | 0 | 0.0% | 30/30 | 4.84 | 23.81 | 2727 | 4635 |
| marker | n/a | 0 | 100.0% | 30/30 | 4.43 | 10.31 | 1116 | 1635 |
| unstructured | n/a | 0 | 100.0% | 30/30 | n/a | n/a | n/a | n/a |

Not attempted (format not supported): pandoc, trafilatura.

ezmd: **trails** vs docling (gap +324.617; paired diff +321.693 [+222.433, +427.991] over 29 shared).

ezmd-main: **trails** vs docling (gap +267.011; paired diff +263.334 [+180.137, +354.980] over 29 shared).

ezmd-main-compact: **leads** vs docling (gap -302.846; paired diff -325.707 [-506.099, -154.020] over 29 shared).

ezmd-main-rag: **trails** vs docling (gap +560.584; paired diff +557.948 [+437.383, +693.428] over 29 shared).

## arXiv papers, outline recall (PDF bookmarks found as headings)

| tool | metric [95% CI] | n | fail | cov | s/doc med | s/doc p95 | RSS MB med | RSS MB peak |
|---|---|---|---|---|---|---|---|---|
| mineru | 0.874 [0.809, 0.933] | 24 | 0.0% | 30/30 | 22.11 | 126.82 | 4815 | 6811 |
| docling | 0.844 [0.782, 0.901] | 24 | 0.0% | 30/30 | 6.74 | 22.61 | 3051 | 5053 |
| pymupdf4llm | 0.843 [0.759, 0.917] | 24 | 0.0% | 30/30 | 5.60 | 29.18 | 483 | 654 |
| ezmd-docs* | 0.801 [0.718, 0.874] | 24 | 0.0% | 30/30 | 4.84 | 23.81 | 2727 | 4635 |
| ezmd-main* | 0.786 [0.698, 0.863] | 24 | 0.0% | 30/30 | 1.22 | 4.35 | 239 | 349 |
| ezmd-main-rag* | 0.786 [0.698, 0.863] | 24 | 0.0% | 30/30 | 1.22 | 4.39 | 234 | 343 |
| ezmd-main-compact* | 0.571 [0.471, 0.664] | 24 | 0.0% | 30/30 | 1.12 | 3.88 | 232 | 350 |
| ezmd* | 0.506 [0.390, 0.621] | 24 | 0.0% | 30/30 | 1.07 | 3.93 | 236 | 358 |
| markitdown | 0.010 [0.000, 0.026] | 24 | 0.0% | 30/30 | 1.67 | 15.84 | 177 | 900 |
| marker | 0.000 [0.000, 0.000] | 24 | 100.0% | 30/30 | 4.43 | 10.31 | 1116 | 1635 |
| unstructured | 0.000 [0.000, 0.000] | 24 | 100.0% | 30/30 | n/a | n/a | n/a | n/a |

Not attempted (format not supported): pandoc, trafilatura.

ezmd: **trails** vs mineru (gap -0.368; paired diff -0.368 [-0.485, -0.248] over 24 shared).

ezmd-docs: **trails** vs mineru (gap -0.073; paired diff -0.073 [-0.119, -0.028] over 24 shared).

ezmd-main: **trails** vs mineru (gap -0.088; paired diff -0.088 [-0.130, -0.048] over 24 shared).

ezmd-main-compact: **trails** vs mineru (gap -0.303; paired diff -0.303 [-0.410, -0.211] over 24 shared).

ezmd-main-rag: **trails** vs mineru (gap -0.088; paired diff -0.088 [-0.130, -0.048] over 24 shared).

## arXiv papers, answer accuracy (local-model QA over the converted text)

| tool | metric [95% CI] | n | fail | cov | s/doc med | s/doc p95 | RSS MB med | RSS MB peak |
|---|---|---|---|---|---|---|---|---|
| ezmd-docs* | 0.808 [0.723, 0.881] | 30 | 0.0% | 30/30 | 4.84 | 23.81 | 2727 | 4635 |
| markitdown | 0.787 [0.688, 0.870] | 30 | 0.0% | 30/30 | 1.67 | 15.84 | 177 | 900 |
| ezmd-main* | 0.780 [0.691, 0.862] | 30 | 0.0% | 30/30 | 1.22 | 4.35 | 239 | 349 |
| ezmd-main-rag* | 0.761 [0.668, 0.844] | 30 | 0.0% | 30/30 | 1.22 | 4.39 | 234 | 343 |
| docling | 0.758 [0.667, 0.839] | 30 | 0.0% | 30/30 | 6.74 | 22.61 | 3051 | 5053 |
| mineru | 0.753 [0.657, 0.835] | 30 | 0.0% | 30/30 | 22.11 | 126.82 | 4815 | 6811 |
| ezmd* | 0.698 [0.577, 0.805] | 30 | 0.0% | 30/30 | 1.07 | 3.93 | 236 | 358 |
| pymupdf4llm | 0.677 [0.558, 0.788] | 30 | 0.0% | 30/30 | 5.60 | 29.18 | 483 | 654 |
| ezmd-main-compact* | 0.564 [0.425, 0.695] | 30 | 0.0% | 30/30 | 1.12 | 3.88 | 232 | 350 |
| marker | n/a | 0 | 100.0% | 30/30 | 4.43 | 10.31 | 1116 | 1635 |
| unstructured | n/a | 0 | 100.0% | 30/30 | n/a | n/a | n/a | n/a |

Not attempted (format not supported): pandoc, trafilatura.

ezmd: **trails** vs markitdown (gap -0.089; paired diff -0.089 [-0.170, -0.027] over 30 shared).

ezmd-docs: **ties** vs markitdown (gap +0.021; paired diff +0.021 [-0.055, +0.117] over 30 shared).

ezmd-main: **ties** vs markitdown (gap -0.007; paired diff -0.006 [-0.070, +0.051] over 30 shared).

ezmd-main-compact: **trails** vs markitdown (gap -0.223; paired diff -0.223 [-0.324, -0.136] over 30 shared).

ezmd-main-rag: **ties** vs markitdown (gap -0.025; paired diff -0.025 [-0.087, +0.041] over 30 shared).

## arXiv papers, answer accuracy on questions whose evidence is in the paper's second half

| tool | metric [95% CI] | n | fail | cov | s/doc med | s/doc p95 | RSS MB med | RSS MB peak |
|---|---|---|---|---|---|---|---|---|
| markitdown | 0.753 [0.642, 0.858] | 29 | 0.0% | 30/30 | 1.67 | 15.84 | 177 | 900 |
| ezmd-docs* | 0.741 [0.634, 0.841] | 29 | 0.0% | 30/30 | 4.84 | 23.81 | 2727 | 4635 |
| ezmd-main* | 0.716 [0.603, 0.815] | 29 | 0.0% | 30/30 | 1.22 | 4.35 | 239 | 349 |
| docling | 0.707 [0.595, 0.810] | 29 | 0.0% | 30/30 | 6.74 | 22.61 | 3051 | 5053 |
| ezmd-main-rag* | 0.706 [0.603, 0.800] | 29 | 0.0% | 30/30 | 1.22 | 4.39 | 234 | 343 |
| mineru | 0.684 [0.573, 0.793] | 29 | 0.0% | 30/30 | 22.11 | 126.82 | 4815 | 6811 |
| ezmd* | 0.621 [0.483, 0.750] | 29 | 0.0% | 30/30 | 1.07 | 3.93 | 236 | 358 |
| pymupdf4llm | 0.582 [0.456, 0.711] | 30 | 0.0% | 30/30 | 5.60 | 29.18 | 483 | 654 |
| ezmd-main-compact* | 0.453 [0.306, 0.608] | 29 | 0.0% | 30/30 | 1.12 | 3.88 | 232 | 350 |
| marker | n/a | 0 | 100.0% | 30/30 | 4.43 | 10.31 | 1116 | 1635 |
| unstructured | n/a | 0 | 100.0% | 30/30 | n/a | n/a | n/a | n/a |

Not attempted (format not supported): pandoc, trafilatura.

ezmd: **trails** vs markitdown (gap -0.132; paired diff -0.132 [-0.227, -0.052] over 29 shared).

ezmd-docs: **ties** vs markitdown (gap -0.011; paired diff -0.011 [-0.121, +0.103] over 29 shared).

ezmd-main: **ties** vs markitdown (gap -0.037; paired diff -0.037 [-0.112, +0.035] over 29 shared).

ezmd-main-compact: **trails** vs markitdown (gap -0.300; paired diff -0.300 [-0.451, -0.157] over 29 shared).

ezmd-main-rag: **ties** vs markitdown (gap -0.047; paired diff -0.047 [-0.138, +0.043] over 29 shared).

## arXiv papers, silent loss (over 5% of words lost with no warning raised; lower is better)

| tool | metric [95% CI] | n | fail | cov | s/doc med | s/doc p95 | RSS MB med | RSS MB peak |
|---|---|---|---|---|---|---|---|---|
| ezmd* | 0.000 [0.000, 0.000] | 30 | 0.0% | 30/30 | 1.07 | 3.93 | 236 | 358 |
| ezmd-docs* | 0.000 [0.000, 0.000] | 30 | 0.0% | 30/30 | 4.84 | 23.81 | 2727 | 4635 |
| ezmd-main* | 0.000 [0.000, 0.000] | 30 | 0.0% | 30/30 | 1.22 | 4.35 | 239 | 349 |
| ezmd-main-compact* | 0.000 [0.000, 0.000] | 30 | 0.0% | 30/30 | 1.12 | 3.88 | 232 | 350 |
| ezmd-main-rag* | 0.000 [0.000, 0.000] | 30 | 0.0% | 30/30 | 1.22 | 4.39 | 234 | 343 |
| marker | 0.000 [0.000, 0.000] | 30 | 100.0% | 30/30 | 4.43 | 10.31 | 1116 | 1635 |
| unstructured | 0.000 [0.000, 0.000] | 30 | 100.0% | 30/30 | n/a | n/a | n/a | n/a |
| docling | 0.100 [0.000, 0.200] | 30 | 0.0% | 30/30 | 6.74 | 22.61 | 3051 | 5053 |
| mineru | 0.133 [0.033, 0.267] | 30 | 0.0% | 30/30 | 22.11 | 126.82 | 4815 | 6811 |
| pymupdf4llm | 0.167 [0.067, 0.300] | 30 | 0.0% | 30/30 | 5.60 | 29.18 | 483 | 654 |
| markitdown | 0.900 [0.800, 1.000] | 30 | 0.0% | 30/30 | 1.67 | 15.84 | 177 | 900 |

Not attempted (format not supported): pandoc, trafilatura.

ezmd: **ties** vs marker (gap +0.000; paired diff +0.000 [+0.000, +0.000] over 30 shared).

ezmd-docs: **ties** vs marker (gap +0.000; paired diff +0.000 [+0.000, +0.000] over 30 shared).

ezmd-main: **ties** vs marker (gap +0.000; paired diff +0.000 [+0.000, +0.000] over 30 shared).

ezmd-main-compact: **ties** vs marker (gap +0.000; paired diff +0.000 [+0.000, +0.000] over 30 shared).

ezmd-main-rag: **ties** vs marker (gap +0.000; paired diff +0.000 [+0.000, +0.000] over 30 shared).

## arXiv papers, source recall (share of the LaTeX source's words kept; independent witness)

| tool | metric [95% CI] | n | fail | cov | s/doc med | s/doc p95 | RSS MB med | RSS MB peak |
|---|---|---|---|---|---|---|---|---|
| ezmd-main* | 0.947 [0.915, 0.974] | 27 | 0.0% | 30/30 | 1.22 | 4.35 | 239 | 349 |
| ezmd-main-rag* | 0.946 [0.915, 0.973] | 27 | 0.0% | 30/30 | 1.22 | 4.39 | 234 | 343 |
| ezmd* | 0.946 [0.914, 0.973] | 27 | 0.0% | 30/30 | 1.07 | 3.93 | 236 | 358 |
| mineru | 0.944 [0.912, 0.971] | 27 | 0.0% | 30/30 | 22.11 | 126.82 | 4815 | 6811 |
| ezmd-docs* | 0.944 [0.912, 0.971] | 27 | 0.0% | 30/30 | 4.84 | 23.81 | 2727 | 4635 |
| docling | 0.943 [0.911, 0.970] | 27 | 0.0% | 30/30 | 6.74 | 22.61 | 3051 | 5053 |
| pymupdf4llm | 0.935 [0.903, 0.963] | 27 | 0.0% | 30/30 | 5.60 | 29.18 | 483 | 654 |
| ezmd-main-compact* | 0.714 [0.626, 0.801] | 27 | 0.0% | 30/30 | 1.12 | 3.88 | 232 | 350 |
| markitdown | 0.616 [0.517, 0.710] | 27 | 0.0% | 30/30 | 1.67 | 15.84 | 177 | 900 |
| marker | 0.000 [0.000, 0.000] | 27 | 100.0% | 30/30 | 4.43 | 10.31 | 1116 | 1635 |
| unstructured | 0.000 [0.000, 0.000] | 27 | 100.0% | 30/30 | n/a | n/a | n/a | n/a |

Not attempted (format not supported): pandoc, trafilatura.

ezmd: **ties** vs mineru (gap +0.002; paired diff +0.002 [-0.001, +0.006] over 27 shared).

ezmd-docs: **ties** vs mineru (gap -0.000; paired diff -0.000 [-0.004, +0.005] over 27 shared).

ezmd-main: **ties** vs mineru (gap +0.003; paired diff +0.003 [-0.001, +0.007] over 27 shared).

ezmd-main-compact: **trails** vs mineru (gap -0.229; paired diff -0.229 [-0.323, -0.140] over 27 shared).

ezmd-main-rag: **ties** vs mineru (gap +0.002; paired diff +0.002 [-0.002, +0.007] over 27 shared).

## arXiv papers, text recall (share of the PDF text layer's words kept)

| tool | metric [95% CI] | n | fail | cov | s/doc med | s/doc p95 | RSS MB med | RSS MB peak |
|---|---|---|---|---|---|---|---|---|
| ezmd* | 0.994 [0.991, 0.996] | 30 | 0.0% | 30/30 | 1.07 | 3.93 | 236 | 358 |
| ezmd-main-rag* | 0.992 [0.989, 0.995] | 30 | 0.0% | 30/30 | 1.22 | 4.39 | 234 | 343 |
| ezmd-main* | 0.992 [0.989, 0.995] | 30 | 0.0% | 30/30 | 1.22 | 4.35 | 239 | 349 |
| ezmd-docs* | 0.979 [0.973, 0.984] | 30 | 0.0% | 30/30 | 4.84 | 23.81 | 2727 | 4635 |
| docling | 0.978 [0.972, 0.983] | 30 | 0.0% | 30/30 | 6.74 | 22.61 | 3051 | 5053 |
| pymupdf4llm | 0.973 [0.960, 0.983] | 30 | 0.0% | 30/30 | 5.60 | 29.18 | 483 | 654 |
| mineru | 0.969 [0.962, 0.975] | 30 | 0.0% | 30/30 | 22.11 | 126.82 | 4815 | 6811 |
| ezmd-main-compact* | 0.723 [0.615, 0.820] | 30 | 0.0% | 30/30 | 1.12 | 3.88 | 232 | 350 |
| markitdown | 0.677 [0.579, 0.762] | 30 | 0.0% | 30/30 | 1.67 | 15.84 | 177 | 900 |
| marker | 0.000 [0.000, 0.000] | 30 | 100.0% | 30/30 | 4.43 | 10.31 | 1116 | 1635 |
| unstructured | 0.000 [0.000, 0.000] | 30 | 100.0% | 30/30 | n/a | n/a | n/a | n/a |

Not attempted (format not supported): pandoc, trafilatura.

ezmd: **leads** vs docling (gap +0.016; paired diff +0.016 [+0.010, +0.022] over 30 shared).

ezmd-docs: **leads** vs docling (gap +0.001; paired diff +0.001 [+0.000, +0.002] over 30 shared).

ezmd-main: **leads** vs docling (gap +0.014; paired diff +0.014 [+0.008, +0.020] over 30 shared).

ezmd-main-compact: **trails** vs docling (gap -0.254; paired diff -0.254 [-0.360, -0.159] over 30 shared).

ezmd-main-rag: **leads** vs docling (gap +0.014; paired diff +0.014 [+0.008, +0.020] over 30 shared).

## arXiv papers, o200k tokens per page (lower is better)

| tool | metric [95% CI] | n | fail | cov | s/doc med | s/doc p95 | RSS MB med | RSS MB peak |
|---|---|---|---|---|---|---|---|---|
| ezmd-main-compact* | 736.193 [580.389, 887.116] | 30 | 0.0% | 30/30 | 1.12 | 3.88 | 232 | 350 |
| docling | 930.100 [833.002, 1039.280] | 30 | 0.0% | 30/30 | 6.74 | 22.61 | 3051 | 5053 |
| ezmd-docs* | 979.210 [866.895, 1101.705] | 30 | 0.0% | 30/30 | 4.84 | 23.81 | 2727 | 4635 |
| pymupdf4llm | 1054.953 [944.421, 1184.700] | 30 | 0.0% | 30/30 | 5.60 | 29.18 | 483 | 654 |
| ezmd-main* | 1140.087 [996.002, 1300.699] | 30 | 0.0% | 30/30 | 1.22 | 4.35 | 239 | 349 |
| ezmd* | 1180.523 [1033.912, 1349.186] | 30 | 0.0% | 30/30 | 1.07 | 3.93 | 236 | 358 |
| mineru | 1226.143 [1058.364, 1421.564] | 30 | 0.0% | 30/30 | 22.11 | 126.82 | 4815 | 6811 |
| ezmd-main-rag* | 1294.623 [1133.562, 1479.412] | 30 | 0.0% | 30/30 | 1.22 | 4.39 | 234 | 343 |
| markitdown | 1440.580 [1245.652, 1643.544] | 30 | 0.0% | 30/30 | 1.67 | 15.84 | 177 | 900 |
| marker | n/a | 0 | 100.0% | 30/30 | 4.43 | 10.31 | 1116 | 1635 |
| unstructured | n/a | 0 | 100.0% | 30/30 | n/a | n/a | n/a | n/a |

Not attempted (format not supported): pandoc, trafilatura.

ezmd: **trails** vs docling (gap +250.423; paired diff +250.423 [+171.439, +334.749] over 30 shared).

ezmd-docs: **trails** vs docling (gap +49.110; paired diff +49.110 [+26.749, +72.331] over 30 shared).

ezmd-main: **trails** vs docling (gap +209.987; paired diff +209.987 [+144.821, +280.292] over 30 shared).

ezmd-main-compact: **leads** vs docling (gap -193.907; paired diff -193.907 [-320.060, -74.032] over 30 shared).

ezmd-main-rag: **trails** vs docling (gap +364.523; paired diff +364.523 [+286.602, +452.926] over 30 shared).

