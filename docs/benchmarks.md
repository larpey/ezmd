# Benchmarks

ezmd is measured against free converters on public benchmarks, scored by each benchmark's own code. The ezmd
project wrote the harness; the harness, the pinned competitor versions and the results are in the repository, so
every number on this page can be rerun and checked. Report a problem with it as an
[issue](https://github.com/larpey/ezmd/issues).

The short version: on web articles ezmd is second to Trafilatura, which its web converter is built on. On PDFs,
the layout-model tools (MinerU, Marker, Docling) are well ahead. The default install has no layout model and no
OCR: on PDFs it is light and fast (about 0.1 s and 250 MB per page), not accurate. `ezmd[docs]` closes part of the
gap but still scores below Docling on its own, although it runs Docling; that is a known issue for 0.1.x. OCR comes
in Phase 2; see the [roadmap](roadmap.md).

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
