# Benchmarks

ezmd is measured against free converters on public benchmarks, scored by each benchmark's own code. The harness,
the pinned competitor versions and the raw results are in the repository, so every number on this page can be
rerun.

The short version: on web articles ezmd is second to Trafilatura, which its web converter is built on. On PDFs,
the layout-model tools (MinerU, Marker, Docling) are well ahead. The default
install has no layout model and no OCR, and `ezmd[docs]` closes part of the gap. OCR comes in Phase 2; see the
[roadmap](roadmap.md).

## Results

Measured on 2026-10-13. The ezmd PDF scores are 0.1.0rc5, which has the same code as 0.1.0; the ezmd web scores
are 0.1.0rc4, because the rc5 rerun covered the PDF benchmarks only (rc5 also changed web tables and Wikipedia
pages). Each cell is the score with its 95% bootstrap interval. Higher is better.

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

Samples: olmOCR-Bench, 336 PDFs (up to 50 per test file); OmniDocBench, 300 of the 981 pages that have original
PDFs (129 with tables); the ScrapingHub article-extraction benchmark, all 181 pages. The samples use seed 20261013,
and the document ids are in `results.json`.

The full scorecards are in
[`bench/results/2026-10-13/summary.md`](https://github.com/larpey/ezmd/blob/main/bench/results/2026-10-13/summary.md),
with OmniDocBench reading order and formulas, ezmd's fixture corpus, speed, and memory for each tool. The rc5 rerun
of ezmd against the same documents is in
[`bench/results/rc5/compare.md`](https://github.com/larpey/ezmd/blob/main/bench/results/rc5/compare.md).

## Conditions

- One desktop: Ryzen 9 7900X, 96 GB RAM, RTX 4090 (24 GB), Windows 11. Every tool ran through its documented default
  entry point, in its own pinned environment, with a 300 s timeout per document.
- An idle game shared the machine during the run (about half the GPU and 6 GB of VRAM), so the speed and memory
  numbers are indicative only. The scores are not affected.
- **Marker** ran with `VLLM_GPU_MEMORY_UTILIZATION=0.65` instead of its default 0.85. At 0.85, with the game
  present, its vLLM server could not finish a document within the timeout. On a GPU with nothing else running,
  the default may score differently.
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
uv run python -m tools.bench run --corpus olmocr
uv run python -m tools.bench score --corpus olmocr
uv run python -m tools.bench report      # bench/results/<date>/summary.md
```

`make bench-full` runs every corpus and every tool, which takes hours on one GPU. The harness, its options and the
corpus pins are described in
[`tools/bench/README.md`](https://github.com/larpey/ezmd/blob/main/tools/bench/README.md) and
[`bench/CORPORA.md`](https://github.com/larpey/ezmd/blob/main/bench/CORPORA.md).
