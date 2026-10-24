# Benchmark corpora

Sources, pinned revisions, licenses and samples for the competitive benchmark (`tools/bench`, ROADMAP
P4-B01/P4-B02, DECISIONS D-0060). Corpus content is never committed: `python -m tools.bench fetch` downloads
everything into the cache directory (`~/.cache/ezmd-bench/corpora`, or `$EZMD_BENCH_CACHE`). Only scores,
document ids and summaries are committed under `bench/results/`.

| Corpus | Source and revision | License | Used for | Sample |
|---|---|---|---|---|
| olmOCR-Bench | Hugging Face `allenai/olmOCR-bench`, revision `54a96a6fb6a2bd3b297e59869491db4d3625b711` (1,403 single-page PDFs, 7 test files) | ODC-BY-1.0 (dataset card) | PDF: official unit tests (text presence/absence, reading order, tables, math, baseline) | seeded stratified: up to 50 PDFs per test file, seed 20261013 (`tools/bench/corpora.py`); ids in `results.json` |
| OmniDocBench | Hugging Face `opendatalab/OmniDocBench`: ground truth `OmniDocBench.json` from `main` at `aa1ee96d106dbe53d0ae59474d75c6e6d9b53fec` (1,651 pages); original PDF page slices `ori_pdfs/` from branch `v1_0` at `f5f559bddf50e36f7f9899d842d0006f13ce8afc` (981 pages). Evaluation code: github.com/opendatalab/OmniDocBench at `f133a71e9e91c3621c7ce8994200a7b394a06eb3` (Apache-2.0) | Dataset: research use only, not for commercial use (dataset card "Copyright Statement"); measured here, never redistributed | PDF: end-to-end text edit distance, reading order, table TEDS, display-formula edit distance | seeded random 300 of the 981 pages that have an original PDF slice, seed 20261013 |
| Article extraction benchmark | github.com/scrapinghub/article-extraction-benchmark at `4a3bc979f76c0df73cb95fe272e2fc1b96f9f010` (181 pages, `ground-truth.json`, `evaluate.py`) | MIT (repository); the HTML pages are third-party web content kept only in the cache | Web: article-body shingle F1 with the benchmark's own `evaluate.py` | all 181 |
| arXiv papers | `bench/corpora/arxiv-manifest.json`: 109 whole papers (arXiv ids, titles, subject sets), sampled from OpenAlex (`primary_location.source.id:S4306400194`, licence `cc-by`), each licence re-checked on its arXiv abstract page; `fetch --only arxiv` downloads `https://arxiv.org/pdf/<id>` | CC BY 4.0 (every paper; the manifest records the URL) | PDF, whole documents: text recall against the PDF's own text layer, silent loss (loss with no warning), outline recall against the PDF's bookmarks, o200k tokens per page, and local-model QA accuracy (`tools/bench/qa.py`) | seeded 30 of 109 (seed 20261013); the other 79 are the held-out split |
| ezmd fixtures | `fixtures/` in this repository (94 fixtures) | CC0 / self-generated, public domain, CC-BY (each `meta.toml` `[provenance]`) | Office, email, EPUB, notebooks, code, data, archives, EDGAR, text, web, PDF: `ezmd.testing.score` against the goldens. Self-graded and biased toward ezmd's output conventions: supporting evidence only | all 94 |

Not used in this baseline: PubTabNet and FinTabNet (see D-0060: table images need OCR, which no ezmd release
has yet, and the OmniDocBench table TEDS already covers tables in PDFs; the PubTabNet download is 12 GB).

Warm-up inputs (`tools/bench/warmup.py`) are generated, not taken from any corpus.
