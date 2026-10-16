"""olmOCR-Bench: official unit tests (olmocr.bench.tests) on each tool's Markdown.

The sampled PDFs' tests are copied into a sample bench directory, and `olmocr_eval.py` runs every test's
official `run()` inside the olmocr scoring venv. The headline is olmOCR-Bench's own: the mean over test files
(arxiv_math, headers_footers, ..., plus `baseline`) of the fraction of tests passed. The 95% interval follows
olmocr.bench.utils.calculate_bootstrap_ci with splits: tests are resampled within each test file. Per-document
values (fraction of a PDF's tests passed) feed the paired comparisons.
"""

from __future__ import annotations

import json
import os
import random
import subprocess
from collections import defaultdict
from pathlib import Path
from typing import Any

from tools.bench.config import BENCH_DIR, cache_dir, venv_python
from tools.bench.corpora import olmocr_root
from tools.bench.schema import DocResult
from tools.bench.scoring.common import attempted, by_tool
from tools.bench.scoring.text import read_output
from tools.bench.stats import BOOTSTRAP_SAMPLES, BOOTSTRAP_SEED, percentile

HELPER = BENCH_DIR / "scoring" / "olmocr_eval.py"


def playwright_browsers() -> Path:
    """olmOCR's math tests render KaTeX in headless Chromium (playwright); `fetch` installs it here."""
    return cache_dir() / "models" / "ms-playwright"


def _prepare(results: list[DocResult], run_dir: Path) -> tuple[Path, Path]:
    docs = json.loads((run_dir / "docs.json").read_text(encoding="utf-8"))["documents"]
    pdfs = {d["pdf"] for d in docs}
    bench = run_dir / "olmocr_eval" / "bench"
    bench.mkdir(parents=True, exist_ok=True)
    for jsonl in sorted(olmocr_root().glob("*.jsonl")):
        kept = [
            ln for ln in jsonl.read_text(encoding="utf-8").splitlines() if ln.strip() and json.loads(ln)["pdf"] in pdfs
        ]
        (bench / jsonl.name).write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")
    cands = run_dir / "olmocr_eval" / "candidates"
    for r in results:
        if r.status == "unsupported":
            continue
        pdf = _pdf_of(r.doc_id)
        dst = cands / r.tool / (pdf.removesuffix(".pdf") + ".md")
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(read_output(r, run_dir), encoding="utf-8")
    return bench, cands


def _pdf_of(doc_id: str) -> str:
    cat, stem = doc_id.split("__", 1)
    return f"{cat}/{stem}.pdf"


def _headline(groups: dict[str, list[float]]) -> float:
    return sum(sum(v) / len(v) for v in groups.values()) / len(groups)


def _stratified_ci(groups: dict[str, list[float]]) -> tuple[float, float]:
    rng = random.Random(BOOTSTRAP_SEED)
    boots = []
    for _ in range(BOOTSTRAP_SAMPLES):
        means = []
        for v in groups.values():
            n = len(v)
            means.append(sum(v[rng.randrange(n)] for _ in range(n)) / n)
        boots.append(sum(means) / len(means))
    return percentile(boots, 2.5), percentile(boots, 97.5)


def score(results: list[DocResult], run_dir: Path) -> dict[str, Any]:
    bench, cands = _prepare(results, run_dir)
    out = run_dir / "olmocr_eval" / "tests.jsonl"
    python = venv_python(cache_dir() / "venvs" / "score-olmocr")
    subprocess.run(
        [str(python), "-I", str(HELPER), "--bench", str(bench), "--candidates", str(cands), "--out", str(out)],
        check=True,
        env={**os.environ, "PLAYWRIGHT_BROWSERS_PATH": str(playwright_browsers())},
    )
    by_tool_tests: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for line in out.read_text(encoding="utf-8").splitlines():
        rec = json.loads(line)
        by_tool_tests[rec["tool"]].append(rec)
    attempted_tools = {t for t, rs in by_tool(results).items() if attempted(rs)}
    tools: dict[str, Any] = {}
    for tool, recs in sorted(by_tool_tests.items()):
        if tool not in attempted_tools:
            continue
        groups: dict[str, list[float]] = defaultdict(list)
        types: dict[str, list[float]] = defaultdict(list)
        per_pdf: dict[str, list[float]] = defaultdict(list)
        for rec in sorted(recs, key=lambda r: (r["jsonl"], r["test"])):
            v = 1.0 if rec["passed"] else 0.0
            groups[rec["jsonl"]].append(v)
            types[rec["type"]].append(v)
            per_pdf[rec["pdf"]].append(v)
        lo, hi = _stratified_ci(groups)
        tools[tool] = {
            "primary": {"value": round(_headline(groups), 4), "ci": [round(lo, 4), round(hi, 4)], "n": len(per_pdf)},
            "tests": len(recs),
            "secondary": {g: {"value": round(sum(v) / len(v), 4), "n": len(v)} for g, v in sorted(groups.items())},
            "test_types": {t: {"value": round(sum(v) / len(v), 4), "n": len(v)} for t, v in sorted(types.items())},
            "per_doc": {
                pdf.removesuffix(".pdf").replace("/", "__"): round(sum(v) / len(v), 4) for pdf, v in per_pdf.items()
            },
        }
    return {"corpus": "olmocr", "metric": "olmocr_pass_rate", "higher_is_better": True, "tools": tools}
