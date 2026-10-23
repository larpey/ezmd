"""Web articles: ScrapingHub article-extraction-benchmark, scored with its own evaluate.py.

Each tool's Markdown is reduced to plain text (markup and link targets removed) and compared with the
ground-truth `articleBody` by the benchmark's 4-gram shingle matching. The corpus metric is the benchmark's F1
(mean precision and mean recall over documents, then F1); the 95% interval resamples documents. A failed
conversion is an empty prediction; tools that cannot read HTML are not scored here.
"""

from __future__ import annotations

import importlib.util
import json
from collections.abc import Sequence
from pathlib import Path
from types import ModuleType
from typing import Any

from tools.bench.corpora import aeb_root
from tools.bench.schema import DocResult
from tools.bench.scoring.common import attempted, by_tool
from tools.bench.scoring.text import markdown_to_text, read_output
from tools.bench.stats import bootstrap_ci

TpFpFn = tuple[float, float, float]


def _evaluate_module() -> ModuleType:
    path = aeb_root() / "evaluate.py"
    spec = importlib.util.spec_from_file_location("aeb_evaluate", path)
    if spec is None or spec.loader is None:
        raise FileNotFoundError(path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _doc_f1(t: TpFpFn, ev: ModuleType) -> float:
    p, r = ev.precision_score(*t), ev.recall_score(*t)
    return 0.0 if p + r == 0 else 2 * p * r / (p + r)


def score(results: list[DocResult], run_dir: Path) -> dict[str, Any]:
    ev = _evaluate_module()
    truth = json.loads((aeb_root() / "ground-truth.json").read_text(encoding="utf-8"))
    tools: dict[str, Any] = {}

    def corpus_f1(sample: Sequence[TpFpFn]) -> float:
        return float(ev.metrics_from_tp_fp_fns(list(sample))["f1"])

    for tool, rs in sorted(by_tool(results).items()):
        rs = attempted(rs)
        if not rs:
            continue
        per_doc: dict[str, TpFpFn] = {}
        for r in rs:
            pred = markdown_to_text(read_output(r, run_dir))
            per_doc[r.doc_id] = ev.string_shingle_matching(true=truth[r.doc_id].get("articleBody", ""), pred=pred)
        values = list(per_doc.values())
        metrics = ev.metrics_from_tp_fp_fns(values)
        lo, hi = bootstrap_ci(values, stat=corpus_f1)
        tools[tool] = {
            "primary": {"value": round(metrics["f1"], 4), "ci": [round(lo, 4), round(hi, 4)], "n": len(values)},
            "secondary": {
                "precision": {"value": round(metrics["precision"], 4)},
                "recall": {"value": round(metrics["recall"], 4)},
            },
            "per_doc": {d: round(_doc_f1(t, ev), 4) for d, t in per_doc.items()},
        }
    return {"corpus": "web", "metric": "article_body_f1", "higher_is_better": True, "tools": tools}
