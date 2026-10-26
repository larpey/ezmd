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
