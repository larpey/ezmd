"""Download the public corpora and set up the official scorers, all pinned, into the cache directory.

    uv run python -m tools.bench fetch [--only olmocr,omnidoc,web]

- olmOCR-Bench: Hugging Face dataset allenai/olmOCR-bench at OLMOCR_REVISION (bench_data/*.jsonl and pdfs).
- OmniDocBench: OmniDocBench.json from main at OMNIDOC_GT_REVISION; original PDF page slices (ori_pdfs) from
  the v1_0 branch at OMNIDOC_PDF_REVISION. Evaluation code: github.com/opendatalab/OmniDocBench at
  OMNIDOC_EVAL_COMMIT, run in the image built from tools/bench/docker/omnidocbench-eval.Dockerfile.
- ScrapingHub article-extraction-benchmark: git checkout at AEB_REVISION (HTML, ground truth, evaluate.py).
- olmOCR scorer: `olmocr[bench]==OLMOCR_SCORER` in its own venv.

Hugging Face rate-limits anonymous downloads; snapshot downloads are retried with a back-off.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from tools.bench.config import BENCH_DIR, cache_dir, venv_python
from tools.bench.corpora import (
    AEB_REVISION,
    OLMOCR_REVISION,
    OMNIDOC_GT_REVISION,
    OMNIDOC_PDF_REVISION,
    aeb_root,
    corpora_dir,
    omnidoc_root,
)
from tools.bench.runner import docker_exe
from tools.bench.scoring.olmocr import playwright_browsers
from tools.bench.scoring.omnidoc import EVAL_REPO_COMMIT, IMAGE

OLMOCR_SCORER = "0.4.27"
HF_HUB = "0.36.0"
_HF_SCRIPT = """
import sys, time
from huggingface_hub import snapshot_download
repo, rev, out, *patterns = sys.argv[1:]
for attempt in range(40):
    try:
        snapshot_download(
            repo, repo_type="dataset", revision=rev, local_dir=out, allow_patterns=patterns, max_workers=2
        )
        break
    except Exception as exc:
        print("retrying after", type(exc).__name__, flush=True)
        time.sleep(90)
else:
    sys.exit(1)
"""


def _uv() -> str:
    found = shutil.which("uv")
    if not found:
        raise SystemExit("uv not found on PATH")
    return found


def _venv(name: str, *requirements: str) -> Path:
    venv = cache_dir() / "venvs" / name
    py = venv_python(venv)
    if not py.exists():
        subprocess.run([_uv(), "venv", "--python", "3.12", str(venv)], check=True)
        subprocess.run([_uv(), "pip", "install", "--python", str(py), *requirements], check=True)
    return py


def _snapshot(repo: str, revision: str, out: Path, *patterns: str) -> None:
    py = _venv("hf", f"huggingface_hub=={HF_HUB}")
    script = cache_dir() / "venvs" / "hf" / "snapshot.py"
    script.write_text(_HF_SCRIPT, encoding="utf-8")
    subprocess.run([str(py), "-I", str(script), repo, revision, str(out), *patterns], check=True)


def _git_at(url: str, commit: str, dest: Path) -> None:
    if not dest.exists():
        subprocess.run(["git", "clone", "-q", url, str(dest)], check=True)
    subprocess.run(["git", "-C", str(dest), "fetch", "-q", "origin", commit], check=False)
    subprocess.run(["git", "-C", str(dest), "checkout", "-q", commit], check=True)


def fetch_olmocr() -> None:
    _snapshot(
        "allenai/olmOCR-bench",
        OLMOCR_REVISION,
        corpora_dir() / "olmocr-bench",
        "bench_data/*.jsonl",
        "bench_data/pdfs/**",
        "README.md",
    )
    # olmocr.bench.tests imports numpy without declaring it.
    py = _venv("score-olmocr", f"olmocr[bench]=={OLMOCR_SCORER}", "numpy==2.3.5")
    env = {**os.environ, "PLAYWRIGHT_BROWSERS_PATH": str(playwright_browsers())}
    subprocess.run([str(py), "-m", "playwright", "install", "chromium"], check=True, env=env)


def fetch_omnidoc() -> None:
    root = omnidoc_root()
    _snapshot("opendatalab/OmniDocBench", OMNIDOC_GT_REVISION, root / "main", "OmniDocBench.json")
    _snapshot("opendatalab/OmniDocBench", OMNIDOC_PDF_REVISION, root / "v1_0", "ori_pdfs/**", "OmniDocBench.json")
    repo = cache_dir() / "omnidocbench-eval"
    _git_at("https://github.com/opendatalab/OmniDocBench.git", EVAL_REPO_COMMIT, repo)
    docker = docker_exe()
    if docker is None:
        raise SystemExit("docker is required for the OmniDocBench evaluation image")
    dockerfile = BENCH_DIR / "docker" / "omnidocbench-eval.Dockerfile"
    subprocess.run([docker, "build", "-q", "-t", IMAGE, "-f", str(dockerfile), str(repo)], check=True)


def fetch_web() -> None:
    _git_at("https://github.com/scrapinghub/article-extraction-benchmark.git", AEB_REVISION, aeb_root())


FETCHERS = {"olmocr": fetch_olmocr, "omnidoc": fetch_omnidoc, "web": fetch_web}


def main(only: list[str] | None) -> int:
    for name in only or list(FETCHERS):
        t0 = time.perf_counter()
        print(f"fetch {name} ...", flush=True)
        try:
            FETCHERS[name]()
        except (subprocess.CalledProcessError, OSError) as exc:
            print(f"fetch {name} FAILED: {exc}", file=sys.stderr)
            return 1
        print(f"fetch {name}: done in {time.perf_counter() - t0:.0f}s", flush=True)
    return 0
