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
