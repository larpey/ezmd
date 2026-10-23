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

Corpora: `smoke` (10 fixtures), `fixtures` (all 94), `olmocr`, `omnidoc`, `web`.

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
