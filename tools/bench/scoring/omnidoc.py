"""OmniDocBench end-to-end evaluation (official pdf_validation.py, quick_match), run in a pinned container.

Inputs are the original PDF page slices (v1_0 `ori_pdfs`) and the ground truth is the current OmniDocBench.json
restricted to the sampled pages. CDM needs TeX Live, Ghostscript and ImageMagick on Linux and is disabled, so
display formulas are scored by normalized edit distance only; BLEU/METEOR are off (they download metric code
at run time). Four categories come out of one evaluation:

- omnidoc-text: 1 - text-block normalized edit distance (page average)
- omnidoc-reading-order: 1 - reading-order normalized edit distance (page average)
- omnidoc-table: table TEDS (mean over GT tables)
- omnidoc-formula: 1 - display-formula normalized edit distance (page average)

Values are the official aggregates; 95% intervals bootstrap the official per-page (per-table for TEDS) values.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from tools.bench.config import cache_dir
from tools.bench.corpora import omnidoc_root
from tools.bench.runner import docker_exe
from tools.bench.schema import DocResult
from tools.bench.scoring.common import attempted, by_tool
from tools.bench.scoring.text import read_output
from tools.bench.stats import bootstrap_ci, mean

IMAGE = "ezmd-bench/omnidocbench-eval:f133a71"
EVAL_REPO_COMMIT = "f133a71e9e91c3621c7ce8994200a7b394a06eb3"
CATEGORIES = {
    "omnidoc-text": ("text_block", "Edit_dist", "ALL_page_avg"),
    "omnidoc-reading-order": ("reading_order", "Edit_dist", "ALL_page_avg"),
    "omnidoc-table": ("table", "TEDS", "all"),
    "omnidoc-formula": ("display_formula", "Edit_dist", "ALL_page_avg"),
}


def _config(tool: str) -> str:
    return f"""end2end_eval:
  metrics:
    text_block:
      metric: [Edit_dist]
    display_formula:
      metric: [Edit_dist]
    table:
      metric: [TEDS, Edit_dist]
      teds_workers: 12
    reading_order:
      metric: [Edit_dist]
  dataset:
    dataset_name: end2end_dataset
    ground_truth:
      data_path: /data/gt.json
    prediction:
      data_path: /data/pred/{tool}
    match_method: quick_match
    match_workers: 12
    quick_match_truncated_timeout_sec: 300
    match_timeout_sec: 420
    timeout_fallback_max_chunk_span: 10
    timeout_fallback_order_penalty: 0.10
"""


def _prepare(results: list[DocResult], run_dir: Path) -> Path:
    work = run_dir / "omnidoc_eval"
    work.mkdir(parents=True, exist_ok=True)
    docs = json.loads((run_dir / "docs.json").read_text(encoding="utf-8"))["documents"]
    wanted = {d["image_path"] for d in docs}
    gt = json.loads((omnidoc_root() / "main" / "OmniDocBench.json").read_text(encoding="utf-8"))
    subset = [p for p in gt if p["page_info"]["image_path"] in wanted]
    (work / "gt.json").write_text(json.dumps(subset, ensure_ascii=False), encoding="utf-8")
    for r in results:
        if r.status == "unsupported":
            continue
        dst = work / "pred" / r.tool / f"{r.doc_id}.md"
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(read_output(r, run_dir), encoding="utf-8")
    return work


def _evaluate(work: Path, tool: str) -> Path:
    docker = docker_exe()
    if docker is None:
        raise RuntimeError("docker is required for the OmniDocBench evaluation")
    result = work / f"result_{tool}"
    if result.exists():
        shutil.rmtree(result)
    result.mkdir(parents=True)
    (work / f"{tool}.yaml").write_text(_config(tool), encoding="utf-8")
    repo = cache_dir() / "omnidocbench-eval"
    cmd = [
        docker,
        "run",
        "--rm",
        "-v",
        f"{repo.resolve()}:/eval",
        "-v",
        f"{work.resolve()}:/data",
        "-v",
        f"{result.resolve()}:/eval/result",
        "-v",
        f"{(cache_dir() / 'models' / 'omnidoc-hf').resolve()}:/hf",
        IMAGE,
        "python",
        "pdf_validation.py",
        "--config",
        f"/data/{tool}.yaml",
    ]
    log = work / f"{tool}.log"
    with log.open("w", encoding="utf-8") as fh:
        subprocess.run(cmd, stdout=fh, stderr=subprocess.STDOUT, check=True)
    return result


def _save(result: Path) -> str:
    return result.name.removeprefix("result_") + "_quick_match"


def _per_unit(result: Path, element: str) -> dict[str, float]:
    """Official per-unit values on a higher-is-better scale: per page (1 - edit), per GT table (TEDS)."""
    if element == "table":
        path = result / f"{_save(result)}_table_result.json"
        if not path.exists():
            return {}
        tables = json.loads(path.read_text(encoding="utf-8"))
        return {
            f"{Path(t['image_name']).stem}#{'-'.join(str(i) for i in t.get('gt_idx', []))}": float(t["metric"]["TEDS"])
            for t in tables
            if "TEDS" in t.get("metric", {})
        }
    path = result / f"{_save(result)}_{element}_per_page_edit.json"
    if not path.exists():
        return {}
    return {Path(k).stem: 1.0 - float(v) for k, v in json.loads(path.read_text(encoding="utf-8")).items()}


def _summaries(result: Path) -> dict[str, Any]:
    metrics = json.loads((result / f"{_save(result)}_metric_result.json").read_text(encoding="utf-8"))
    out: dict[str, Any] = {}
    for cat, (element, metric, key) in CATEGORIES.items():
        value = metrics.get(element, {}).get("all", {}).get(metric, {}).get(key)
        units = _per_unit(result, element)
        samples = list(units.values())
        ci = bootstrap_ci(samples) if samples else None
        if value is not None and element != "table":
            value = 1.0 - float(value)
        out[cat] = {
            "value": None if value is None else round(float(value), 4),
            "ci": None if ci is None else [round(ci[0], 4), round(ci[1], 4)],
            "n": len(samples),
            "sample_mean": round(mean(samples), 4) if samples else None,
            "per_doc": {k: round(v, 4) for k, v in units.items()},
        }
    return out


def score(results: list[DocResult], run_dir: Path) -> dict[str, Any]:
    work = _prepare(results, run_dir)
    tools: dict[str, Any] = {}
    for tool, rs in sorted(by_tool(results).items()):
        if not attempted(rs):
            continue
        result = _evaluate(work, tool)
        cats = _summaries(result)
        tools[tool] = {"primary": cats["omnidoc-text"], "categories": cats, "per_doc": cats["omnidoc-text"]["per_doc"]}
    return {"corpus": "omnidoc", "metric": "text_edit_similarity", "higher_is_better": True, "tools": tools}
