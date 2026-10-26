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
    GOVDOCS1_THREADS,
    GOVDOCS1_URL,
    OLMOCR_REVISION,
    OMNIDOC_GT_REVISION,
    OMNIDOC_PDF_REVISION,
    aeb_root,
    arxiv_manifest,
    arxiv_root,
    arxiv_source_dir,
    corpora_dir,
    govdocs1_root,
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


def fetch_arxiv() -> None:
    """The papers of bench/corpora/arxiv-manifest.json from arxiv.org, one request every few seconds (arXiv asks
    that of bulk clients). Every paper is CC BY 4.0 per its arXiv abstract page."""
    import urllib.request

    out = arxiv_root() / "papers"
    out.mkdir(parents=True, exist_ok=True)
    for entry in arxiv_manifest():
        dest = out / f"{entry['id']}.pdf"
        if dest.exists() and dest.stat().st_size > 0:
            _check_digest(dest, entry)
            continue
        url = f"https://arxiv.org/pdf/{entry['id']}"
        req = urllib.request.Request(url, headers={"User-Agent": "ezmd-bench/1 (https://github.com/larpey/ezmd)"})
        with urllib.request.urlopen(req, timeout=120) as resp:  # noqa: S310 (https URL built from the manifest)
            data = resp.read()
        if not data.startswith(b"%PDF"):
            raise RuntimeError(f"{url}: not a PDF ({data[:40]!r})")
        dest.write_bytes(data)
        _check_digest(dest, entry)
        print(f"arxiv: {dest.name} ({len(data) // 1024} KB)", flush=True)
        time.sleep(3)


def _check_digest(pdf: Path, entry: dict[str, object], key: str = "sha256") -> None:
    """The manifest pins each paper by the sha256 of the bytes the results were measured on. arXiv may replace
    a PDF (a new version, a regenerated file); a different file is a different corpus, so it is an error."""
    import hashlib

    want = entry.get(key)
    if not want:
        return
    got = hashlib.sha256(pdf.read_bytes()).hexdigest()
    if got != want:
        pdf.unlink()  # never leave bytes on disk that `arxiv()` could mistake for the pinned paper
        raise RuntimeError(f"arxiv: {pdf.name} has sha256 {got[:12]}..., the manifest pins {str(want)[:12]}...")


def fetch_arxiv_source() -> None:
    """The LaTeX source (arXiv e-print) of every manifest paper, the witness for text recall that no PDF text
    layer produced (tools/bench/scoring/latex.py). A paper submitted as PDF only has no source; arXiv answers
    with the PDF, and an empty marker file records that so the paper is skipped, not refetched."""
    import urllib.request

    out = arxiv_source_dir()
    out.mkdir(parents=True, exist_ok=True)
    for entry in arxiv_manifest():
        dest = out / f"{entry['id']}.src"
        if dest.exists():
            if dest.stat().st_size > 0:
                _check_digest(dest, entry, "source_sha256")
            continue
        url = f"https://arxiv.org/e-print/{entry['id']}"
        req = urllib.request.Request(url, headers={"User-Agent": "ezmd-bench/1 (https://github.com/larpey/ezmd)"})
        with urllib.request.urlopen(req, timeout=120) as resp:  # noqa: S310 (https URL built from the manifest)
            data = resp.read()
        if data.startswith(b"%PDF"):
            dest.write_bytes(b"")
            print(f"arxiv source: {entry['id']} was submitted as PDF only", flush=True)
        else:
            dest.write_bytes(data)
            _check_digest(dest, entry, "source_sha256")
            print(f"arxiv source: {dest.name} ({len(data) // 1024} KB)", flush=True)
        time.sleep(3)


def fetch_govdocs1() -> None:
    """The ten Govdocs1 threads: each zip is downloaded once (about 300 MB) and its files extracted flat into
    `threads/<n>/` by basename (the zips nest them under the first three digits). A thread whose folder exists
    is left alone, so a copy made by hand on another drive (`EZMD_GOVDOCS1`) is used as it is."""
    import urllib.request
    import zipfile

    threads = govdocs1_root() / "threads"
    threads.mkdir(parents=True, exist_ok=True)
    for n in range(GOVDOCS1_THREADS):
        folder = threads / str(n)
        if folder.is_dir():
            continue
        archive = threads / f"thread{n}.zip"
        if not archive.exists() or archive.stat().st_size == 0:
            url = GOVDOCS1_URL.format(n=n)  # an https template; only the thread number varies
            req = urllib.request.Request(url, headers={"User-Agent": "ezmd-bench/1 (https://github.com/larpey/ezmd)"})  # noqa: S310
            with urllib.request.urlopen(req, timeout=600) as resp, archive.open("wb") as out:  # noqa: S310
                shutil.copyfileobj(resp, out)
            print(f"govdocs1: thread{n}.zip ({archive.stat().st_size // 2**20} MB)", flush=True)
        staging = threads / f"{n}.partial"
        if staging.exists():
            shutil.rmtree(staging)
        staging.mkdir()
        count = 0
        with zipfile.ZipFile(archive) as z:
            for info in z.infolist():
                if info.is_dir():
                    continue
                name = Path(info.filename).name
                with z.open(info) as src, (staging / name).open("wb") as dst:
                    shutil.copyfileobj(src, dst)
                count += 1
        _rename_when_released(staging, folder)
        print(f"govdocs1: thread {n}: {count} files", flush=True)


def _rename_when_released(src: Path, dst: Path, attempts: int = 10) -> None:
    """Windows refuses to rename a folder while the search indexer or a scanner still holds a file it just
    wrote; the handle goes away within seconds."""
    for attempt in range(attempts):
        try:
            src.rename(dst)
            return
        except PermissionError:
            if attempt == attempts - 1:
                raise
            time.sleep(1 + attempt)


FETCHERS = {
    "olmocr": fetch_olmocr,
    "omnidoc": fetch_omnidoc,
    "web": fetch_web,
    "arxiv": fetch_arxiv,
    "arxiv-source": fetch_arxiv_source,
    "govdocs1": fetch_govdocs1,
}


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
