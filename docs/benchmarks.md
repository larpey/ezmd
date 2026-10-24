# Benchmarks

ezmd is measured against free converters on public benchmarks, scored by each benchmark's own code. The ezmd
project wrote the harness; the harness, the pinned competitor versions and the results are in the repository, so
every number on this page can be rerun and checked. Report a problem with it as an
[issue](https://github.com/larpey/ezmd/issues).

The short version: on web articles ezmd is second to Trafilatura, which its web converter is built on. On PDFs,
the layout-model tools (MinerU, Marker, Docling) are well ahead. The default install has no layout model and no
OCR: on PDFs it is light and fast (about 0.1 s and 250 MB per page), not accurate. `ezmd[docs]` closes part of the
gap but still scores below Docling on its own, although it runs Docling; that is a known issue for 0.1.x. OCR comes
in Phase 2; see the [roadmap](roadmap.md). On whole born-digital papers, measured by what a model can answer from
the output ([below](#whole-papers-what-a-model-gets)), every converter ties; ezmd keeps the most text and is the only
one that says when it loses some, and its output is about 25% larger in tokens than Docling's, for reasons that are
listed and fixable.

## Results

Measured on 2026-10-13. The ezmd PDF scores are a 0.1.0rc5 build whose PDF code differs from 0.1.0 only in comments;
the ezmd web scores are 0.1.0rc4, because the rc5 rerun covered the PDF benchmarks only (rc5 also changed web tables
and Wikipedia pages). Each cell is the score with its 95% bootstrap interval. Higher is better.

The rc5 PDF fixes were developed while looking at these samples, so the default-install PDF scores here may be
fitted to them. The [held-out scores](#held-out) below are on documents ezmd was never tuned on.

| tool | olmOCR-Bench (pass rate) | OmniDocBench text (1 - edit distance) | OmniDocBench tables (TEDS) | Web articles (body F1) |
|---|---|---|---|---|
| MinerU 4.0.12 | 0.797 [0.782, 0.811] | 0.946 [0.932, 0.960] | 0.847 [0.800, 0.892] | not supported |
| Marker 2.0.0 (non-default, see below) | 0.759 [0.742, 0.775] | 0.882 [0.857, 0.906] | 0.657 [0.599, 0.711] | not supported |
| Docling 2.138.0 | 0.543 [0.527, 0.557] | 0.851 [0.817, 0.882] | 0.580 [0.514, 0.641] | 0.713 [0.685, 0.742] |
| **ezmd[docs]** | 0.480 [0.464, 0.494] | 0.666 [0.618, 0.712] | 0.421 [0.347, 0.495] | 0.914 [0.895, 0.930] |
| **ezmd** (default install) | 0.335 [0.318, 0.352] | 0.498 [0.455, 0.543] | 0.179 [0.129, 0.233] | 0.914 [0.895, 0.930] |
| pymupdf4llm 1.28.2 | 0.333 [0.314, 0.351] | 0.620 [0.570, 0.669] | 0.433 [0.362, 0.501] | not supported |
| Unstructured 0.27.27-dev2 | 0.313 [0.297, 0.330] | 0.676 [0.629, 0.721] | 0.002 [0.000, 0.005] | 0.755 [0.726, 0.783] |
| MarkItDown 0.1.8 | 0.264 [0.247, 0.282] | 0.443 [0.391, 0.491] | 0.097 [0.056, 0.139] | 0.653 [0.622, 0.683] |
| Trafilatura 2.3.1 | not supported | not supported | not supported | 0.952 [0.939, 0.963] |

Samples: olmOCR-Bench, 336 of its 1,403 PDFs (up to 50 per test file); OmniDocBench, 300 of the 981 pages that have
original PDFs (129 with tables); the ScrapingHub article-extraction benchmark, all 181 pages. The samples use seed
20261013, and the document ids are in `results.json`.

## Whole papers: what a model gets

Measured on 2026-10-24 on 30 whole arXiv papers (CC BY 4.0, a seeded sample of 109; `bench/CORPORA.md`). The page
benchmarks above score a page's edit distance against a human transcription. This one scores what a downstream model
gets from the converted file, with the PDF itself as the witness, so the comparison needs no human ground truth:

- **Answer accuracy.** A local model (gpt-oss-20b through LM Studio) wrote five questions per paper from the PDF's
  own text layer, never from a converter's output, each backed by a quote checked against the text layer. The same
  model answered the 148 questions from each tool's Markdown and graded the answers against the references.
- **Text recall.** The share of the text layer's word occurrences present in the output.
- **Silent loss.** The paper lost more than 5% of its words and the tool raised no warning that means content was
  dropped or cut. Only ezmd has a warning channel; its always-on notices (removed running headers, hidden elements)
  do not count, so this standard is stricter for ezmd than for the others, for whom every such loss is silent.
- **Outline recall.** The share of the PDF's bookmarks found as a heading in the output, over the 24 papers with
  three or more bookmarks.
- **Tokens per page.** o200k tokens of the output per PDF page, frontmatter removed; MinerU's embedded images count
  as one placeholder each.

Each cell is the mean over the 30 papers with its 95% bootstrap interval. `ezmd main` is the unreleased code of
this repository at 7a13bd5 (the 0.1.1 release plus the PDF fixes of PR #19) under the `full`, `rag` and `compact`
profiles; `ezmd 0.1.0` is the release.

| tool | answer accuracy | correct answers per 10k tokens | text recall | silent loss (lower is better) | outline recall | tokens per page (lower is better) |
|---|---|---|---|---|---|---|
| Docling 2.138.0 | 0.800 [0.707, 0.887] | 2.53 | 0.978 | 0.10 | 0.844 | 930 |
| MinerU 4.0.12 | 0.796 [0.736, 0.849] | 2.07 | 0.969 | 0.13 | 0.874 | 1,226 |
| **ezmd 0.1.0** | 0.782 [0.702, 0.856] | 2.03 | 0.994 | 0.00 | 0.506 | 1,181 |
| **ezmd main, rag** | 0.782 [0.693, 0.862] | 1.88 | 0.992 | 0.00 | 0.786 | 1,363 |
| pymupdf4llm 1.28.2 | 0.771 [0.671, 0.860] | 2.25 | 0.973 | 0.17 | 0.843 | 1,055 |
| **ezmd main, full** | 0.758 [0.660, 0.847] | 2.06 | 0.992 | 0.00 | 0.786 | 1,158 |
| **ezmd main, compact** | 0.729 [0.636, 0.813] | 3.07 | 0.707 | 0.00 | 0.567 | 727 |
| MarkItDown 0.1.8 | 0.718 [0.629, 0.804] | 1.61 | 0.677 | 0.90 | 0.010 | 1,441 |

What it says, with the paired tests over the same 30 papers (`bench/results/2026-10-24/summary.md`):

- **On born-digital papers the converter barely moves answer accuracy.** All three ezmd rows tie with Docling on
  the paired test, and every other tool's interval overlaps Docling's; even MarkItDown's output, which glues words together and loses a third of the text, still answers 72% of
  the questions. The questions are facts a model can often find in a damaged text. Where converters differ is in
  what reaches the model and whether anyone is told.
- **ezmd keeps the most text and is the only tool that says when it loses some.** Text recall 0.992 against
  Docling's 0.978 (paired difference +0.014 [+0.008, +0.020]). Docling, MinerU and pymupdf4llm each lost more than
  5% of the words on 3 to 5 of the 30 papers with no signal; MarkItDown did on 27. ezmd lost that much on 0 papers
  in the full and rag profiles. In the compact profile, which caps output at 16k tokens, it lost it on 19 papers and
  declared every one (`truncated: true`), which is why compact's silent-loss rate is also 0: declared loss is not
  silent, and 0.707 recall is the price the profile's cap sets.
- **ezmd's output is bigger than it should be.** The full profile costs 228 more tokens per page than Docling
  ([+160, +301], paired), and rag 433 more. The gap is not the kept text (1.4% more words). It is, measured over
  the 30 outputs: paragraphs split on each PDF line in manuscripts with wide line spacing (ezmd emits 19,194
  paragraphs where Docling emits 4,660, and 13,627 of ezmd's are fragments under 120 characters that end
  mid-sentence); citation links kept with their full URLs (15,340 tokens); the generated contents list, orientation
  line, anchors and page markers (21,000 tokens); figure lettering emitted as tables with synthesized headers; and in
  the rag profile two chunk markers around every 400 tokens (about 150,000 tokens over the sample). Each of these
  is a converter fix or a profile default, and they are the next work.
- **Outline recall jumped with the PDF fixes** (0.506 for 0.1.0 to 0.786 for main) and still trails MinerU
  (0.874) and Docling (0.844).
- **Compact is the one profile that beats Docling on correct answers per token** (3.07 against 2.53, paired
  +0.54 [+0.00, +1.12]), at the cost of answer accuracy on the papers it cuts.

Conditions and caveats: the witness is pdfium's text layer, which is also what ezmd's default PDF engine reads
(Docling and MinerU extract text their own way), so ezmd's text-recall lead partly measures agreement with its own
extractor, and the questions were written from that same text; one run, one grader model, 148 questions, and the
grader's judgment of short answers is the metric; the questions ask for short stated facts (some from tables, none from figures), so a converter that
garbles a table's structure can still score when the value survives somewhere in its text. Marker and Unstructured were not run (Docker was off). A game client was idle on the same
GPU. Everything needed to rerun it, including the question cache's seed, is in the repository; the questions
themselves are regenerated by the local model.

## Held-out

ezmd 0.1.0 (from PyPI, default install) also runs on the olmOCR-Bench PDFs outside the published sample: 1,067
documents ezmd was never tuned on.

| split | documents | olmOCR-Bench (pass rate) |
|---|---|---|
| published sample | 336 | 0.335 [0.318, 0.352] |
| held-out | 1,067 | 0.381 [0.365, 0.397] |

The headline is the mean of the per-category pass rates, so the two rows do not compare directly: every
`old_scans_math` PDF is in the sample (where ezmd scores 0), and none is held out. Per category:

| category | sample | held-out |
|---|---|---|
| headers and footers | 0.286 | 0.408 |
| multi-column | 0.573 | 0.551 |
| long tiny text | 0.307 | 0.271 |
| tables | 0.390 | 0.292 |
| old scans | 0.123 | 0.141 |
| arXiv math | 0.000 | 0.000 |

Over the same categories the two splits score about the same, but tables score lower on unseen documents, so the
table numbers in the main table are likely fitted to the sample. The other tools have not run on the held-out split,
and the OmniDocBench held-out pages (681) are converted but not scored yet.

The full scorecards are in
[`bench/results/2026-10-13/summary.md`](https://github.com/larpey/ezmd/blob/main/bench/results/2026-10-13/summary.md),
with OmniDocBench reading order and formulas, ezmd's fixture corpus, speed, and memory for each tool. The rc5 rerun
of ezmd against the same documents is in
[`bench/results/rc5/compare.md`](https://github.com/larpey/ezmd/blob/main/bench/results/rc5/compare.md).

## Conditions

- One desktop: Ryzen 9 7900X, 96 GB RAM, RTX 4090 (24 GB), Windows 11. Every tool ran through its documented default
  entry point, in its own pinned environment, with a 300 s timeout per document.
- An idle game shared the machine during the run (about half the GPU and 6 GB of VRAM), so the speed and memory
  numbers are indicative only. It can also lower scores: a timeout or crash scores zero, and Marker's settings
  were changed because of it (next item).
- **Marker** ran with `VLLM_GPU_MEMORY_UTILIZATION=0.65` instead of its default 0.85. At 0.85, with the game
  present, its vLLM server could not finish a document within the timeout. On a GPU with nothing else running,
  the default may score differently.
- **Every tool runs at its defaults**, through its documented entry point with no tuning. That is what a new user
  gets, but some tools have slower modes that score higher: Unstructured's default strategy reads the text layer
  and detects no tables (hence its 0.002 TEDS), while its `hi_res` strategy does.
- **OmniDocBench** here is not its leaderboard setup. The ground truth is the current release (v1.6), the inputs
  are the original PDF slices from v1.0, so only the 981 pages that have one are eligible (they lean towards
  digital, text-layer pages), and every tool gets the PDF rather than the page image. The scores are not
  comparable with the published Overall.
- Scoring: ezmd's YAML frontmatter is removed before scoring (only ezmd writes one); other tools' output is scored
  as written. On olmOCR-Bench a document a tool failed to convert fails all of its tests.
- OmniDocBench formulas use edit distance, because its CDM metric needs a Linux TeX setup. Image-only benchmarks
  (PubTabNet, FinTabNet) and paid APIs were not run.
- ezmd's fixture corpus is self-graded: the fixtures were written alongside ezmd's converters. The full scorecard
  includes it as supporting evidence only.

## Rerun it

```bash
git clone https://github.com/larpey/ezmd && cd ezmd
uv sync --all-packages
uv run python -m tools.bench install     # competitor environments, pinned in tools/bench/competitors.toml
uv run python -m tools.bench fetch       # the public corpora and their official scorers, pinned
uv run python -m tools.bench run --corpus olmocr                  # the published sample
uv run python -m tools.bench run --corpus olmocr --split heldout  # the rest (use another --date)
uv run python -m tools.bench score --corpus olmocr
uv run python -m tools.bench report      # bench/results/<date>/summary.md
```

`make bench-full` runs every corpus and every tool, which takes hours on one GPU. The harness, its options and the
corpus pins are described in
[`tools/bench/README.md`](https://github.com/larpey/ezmd/blob/main/tools/bench/README.md) and
[`bench/CORPORA.md`](https://github.com/larpey/ezmd/blob/main/bench/CORPORA.md).
