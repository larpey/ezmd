# tools/bench: competitive benchmark harness

ROADMAP P4-B01/P4-B02, DECISIONS D-0032 and D-0060. Measures ezmd (default install and `ezmd[docs]`) against
free competitors on public corpora and on ezmd's fixture corpus. Measurement only: nothing here is a
dependency of any ezmd package, and nothing here changes converter behaviour.

```bash
make bench                                    # install tools, smoke corpus, every tool, report
uv run python -m tools.bench install          # competitor venvs / binaries / images (pinned, competitors.toml)
uv run python -m tools.bench fetch            # public corpora + official scorers (pinned, bench/CORPORA.md)
uv run python -m tools.bench run --corpus olmocr [--tools a,b] [--sample N] [--timeout 300] [--date D]
uv run python -m tools.bench score --corpus olmocr [--date D]
uv run python -m tools.bench report [--date D] # bench/results/<D>/results.json + summary.md
make bench-full                               # all corpora, all tools (hours)
```

Corpora: `smoke` (10 fixtures), `fixtures` (all 94), `olmocr`, `omnidoc`, `web`, `arxiv` (30 of 109 whole
CC BY papers; `fetch --only arxiv`), `arxiv-damaged` (three damaged copies of 10 of those papers, built on
first use).

The `arxiv` corpus measures what a downstream model gets, not a page's edit distance: text recall against the
PDF's own text layer and against the paper's LaTeX source (`fetch --only arxiv-source`; the source is the
witness no converter's extractor produced), **silent loss** (more than 5% of the words gone and no warning
raised; only ezmd has a warning channel, and its always-on notices such as removed running headers do not
count), outline recall against the PDF's bookmarks, o200k tokens per page, and answer accuracy. The answers
come from a local model (`tools/bench/qa.py`, LM Studio by default, nothing leaves the machine):

```bash
uv run python -m tools.bench fetch --only arxiv,arxiv-source  # the PDFs and their LaTeX sources
uv run python -m tools.bench run --corpus arxiv --date D       # convert with every tool
uv run python -m tools.bench qa all --corpus arxiv --date D    # generate questions, answer, grade (local model)
uv run python -m tools.bench score --corpus arxiv --date D
uv run python -m tools.bench report --date D
```

`tokens --corpus arxiv --date D [--pdf]` adds exact Claude token counts of every output through Anthropic's free
`count_tokens` endpoint (key from `ANTHROPIC_API_KEY` or keyring `anthropic`/`api_key`; cached by content hash
under the run, so a rerun makes no request), and with `--pdf` the cost of uploading each source PDF as-is, the
baseline the scorer reports every tool's output against. Re-run `score` afterwards.

The `arxiv-damaged` corpus (`tools/bench/damage.py`) puts a known hole in each of ten papers: every page
rendered to an image (a scan), a block of a fifth of the pages rendered to images, and the file truncated at
80% of its bytes. The witness is the intact paper, so the scorer (`tools/bench/scoring/damaged.py`) knows what
was lost and asks whether the tool said so: silent loss per kind and pooled (the primary metric, lower is
better), text recall of the intact paper (a tool with OCR recovers a rendered page), and for ezmd how exactly
its `pages_without_text` warning names the pages. A conversion that fails outright is loud, not silent.

```bash
uv run python -m tools.bench run --corpus arxiv-damaged --date D --timeout 900   # OCR on a scan is slow
uv run python -m tools.bench score --corpus arxiv-damaged --date D
uv run python -m tools.bench run --corpus arxiv-damaged --split heldout --tools ezmd-main --date D2  # the 79 held-out papers, damaged the same way
```

The held-out split of `arxiv-damaged` is the damaged copies of the 79 arXiv papers outside the 30-paper sample,
never used to find or fix a converter fault, so a fix found on the ten sampled papers is confirmed there (#23).

The `govdocs1` corpus is the everyday-documents pilot: the ten official Govdocs1 threads (digitalcorpora.org,
about 1,000 files each across some twenty formats, named by the type the crawler saw). There is no ground
truth, so the scorer (`tools/bench/scoring/corpus.py`) grades the outcome: an output written, a declared
refusal (`ConversionError`, `UnsupportedMediaType`, `InputTooLarge`), or a bug (any other exception, a timeout,
a worker crash). The primary metric is the clean rate; `clusters.md` under the run groups the bugs by exception
class and the frame that raised (`where` in results.jsonl, the innermost frame of ezmd's own code) and the
declared errors by message shape, each with sample document ids. Every file is attempted whatever its type,
because a clean refusal of a format ezmd does not claim is part of the contract. `--workers N` runs N worker
processes over round-robin shards of the corpus; `EZMD_GOVDOCS1` points at a copy on another drive.

```bash
EZMD_GOVDOCS1=D:/corpora/govdocs1 uv run python -m tools.bench fetch --only govdocs1   # ten zips, extracted flat
uv run python -m tools.bench run --corpus govdocs1 --tools ezmd-main --workers 8 --timeout 120 --date D
uv run python -m tools.bench score --corpus govdocs1 --date D                             # clean rate + clusters.md
```

`score` also runs the structural smell scorer (`tools/bench/scoring/smell.py`) over every output and writes
`smells.md`: per smell, how many outputs show it, by type, with samples. The gated smells (`empty`,
`control_chars`, `lone_bullet`, `heading_bullet`, `heading_repeated`, `truncated_full`) are the shapes no
release should ship with; the reported ones (`shrunk`, `replacement_chars`, `mojibake`, `repeated_lines`,
`char_run`, `empty_table`, `injection`) have legitimate causes and are read, not gated. The gated-clean rate
is in the scores under `secondary.smells`.

Two more outcome corpora cover what Govdocs1 cannot. `ccgov` (`tools/bench/cc.py`) is modern everyday files
from Common Crawl, .gov, .mil and .edu hosts, every document type the crawl detected (OOXML, ODF, RTF, EPUB,
JSON, CSV, Markdown, subtitles, email, notebooks) in full and HTML and PDF as seeded samples, one capture per
content digest, pulled by HTTP range request from the public WARC files with the payload digest verified.
The manifest is built with DuckDB from the index slices that hold those hosts (`EZMD_CC_INDEX`, the crawl in
`EZMD_CC_CRAWL`); the pull resumes from `pulled.jsonl` and a file named `STOP` in the root stops it between
files. `media` (`tools/bench/media.py`) is images, audio and video from Wikimedia Commons by `filemime`
search, EPUB from Project Gutenberg, MP3 chapters from LibriVox and audio and video from NASA, the types no
crawl holds. Both are cache-only like every other corpus.

```bash
EZMD_CCGOV=D:/corpora/ccgov EZMD_CC_INDEX=D:/corpora/cc-index/CC-MAIN-2026-43 uv run python -m tools.bench fetch --only ccgov
EZMD_MEDIA=D:/corpora/media uv run python -m tools.bench fetch --only media
uv run python -m tools.bench run --corpus ccgov --tools ezmd-main --workers 8 --timeout 120 --date D
```

`qa` loads `openai/gpt-oss-20b` through `lms` with a 131k context (`--context` lowers it on a smaller GPU) unless
`--model`/`--base-url` (or `EZMD_BENCH_LLM_MODEL`/`EZMD_BENCH_LLM_URL`) point it elsewhere. Questions are
written from the text layer, never from a tool's output, two per 8,000-token segment of it so that a paper's
tail is asked about as much as its abstract, and each must quote the sentence that answers it; a quote that is
not in its segment drops the question, and every question records where in the paper its evidence lies. The
answering model reads each tool's whole output (an output longer than the context is cut, and the answer record
says so), and the scorer reports accuracy on questions from the second half of the papers as its own category.
Questions are cached under the corpus and shared by every tool and run, and so are
the grader's verdicts, keyed by document, question and answer text: a sampled model grades the same answer
differently on another day, which would read as a change in accuracy between two runs that produced the same
answers. `qa seed --date D` puts an already graded run's verdicts in that cache; `qa ungrade --date D` drops a
run's verdicts so `qa grade` decides again, from the cache where it can. The tool rows
`ezmd-main`, `ezmd-main-compact` and `ezmd-main-rag` are this checkout's code (`local = true` builds the
wheels) under three profiles; `ezmd` stays the published release.

Everything large lives in `~/.cache/ezmd-bench` (override with `EZMD_BENCH_CACHE`): `venvs/<tool>`, `bin/`,
`models/`, `corpora/`, `runs/<date>/<corpus>/` (raw outputs, `results.jsonl`, `scores.json`, worker logs).

How a run works (`runner.py`): each tool runs in a worker process inside its own environment
(`adapters/worker.py`, standard library only, one adapter per tool calling the tool's documented default
API). The worker loads the tool and converts a generated warm-up file before it reports ready, so model loading
counts as start-up, not as the first document. Then the harness sends one document at a time, measures wall
time, samples the RSS of the worker's process tree every 50 ms (plus `docker stats` of any container the tool
starts), and kills and restarts the worker on a timeout (default 300 s) or crash. `results.jsonl` is appended
per document, so an interrupted run resumes.

Scoring (`scoring/`) uses each benchmark's official code: olmOCR-Bench's `olmocr.bench.tests` (in its own venv),
OmniDocBench's `pdf_validation.py` (in a pinned container, `docker/omnidocbench-eval.Dockerfile`), the
article-extraction benchmark's `evaluate.py`, and `ezmd.testing.score` for the fixtures. A leading YAML
frontmatter block is removed from every output before scoring.
