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
```

`qa` loads `openai/gpt-oss-20b` through `lms` with a 32k context unless `--model`/`--base-url` (or
`EZMD_BENCH_LLM_MODEL`/`EZMD_BENCH_LLM_URL`) point it elsewhere. Questions are written from the text layer,
never from a tool's output, and each must quote the sentence that answers it; a quote that is not in the text
layer drops the question. Questions are cached under the corpus and shared by every tool and run, and so are
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
