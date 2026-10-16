"""Scoring: turn raw tool outputs of one corpus run into per-document scores and a per-tool summary.

Each scorer writes `<run_dir>/scores.json`:

    {"corpus": ..., "metric": <primary metric name>, "higher_is_better": bool,
     "tools": {tool: {"primary": {"value", "ci", "n"}, "secondary": {...}, "per_doc": {doc_id: value}}}}

Official benchmark code does the scoring wherever it exists (olmOCR-Bench, OmniDocBench, the ScrapingHub
article-extraction evaluate.py); the ezmd fixture corpus uses ezmd's own scorer (ezmd.testing.score).
Every tool's output is normalized the same way before scoring: a leading YAML frontmatter block is removed
(only ezmd writes one; it is metadata, not page content).
"""

from __future__ import annotations

import json
from pathlib import Path

from tools.bench.schema import read_results


def score_corpus(corpus: str, run_dir: Path, tools: list[str] | None) -> int:
    results = [r for r in read_results(run_dir / "results.jsonl") if tools is None or r.tool in tools]
    if not results:
        print(f"no results under {run_dir}")
        return 1
    if corpus in ("fixtures", "smoke"):
        from tools.bench.scoring.fixtures import score
    elif corpus == "web":
        from tools.bench.scoring.web import score
    elif corpus == "olmocr":
        from tools.bench.scoring.olmocr import score
    elif corpus == "omnidoc":
        from tools.bench.scoring.omnidoc import score
    else:
        print(f"no scorer for corpus {corpus}")
        return 2
    scores = score(results, run_dir)
    existing: dict[str, object] = {}
    path = run_dir / "scores.json"
    if path.exists() and tools is not None:
        existing = json.loads(path.read_text(encoding="utf-8"))
        merged = dict(existing.get("tools", {}))  # type: ignore[call-overload]
        merged.update(scores["tools"])
        scores["tools"] = merged
    path.write_text(json.dumps(scores, indent=1, sort_keys=True), encoding="utf-8")
    for tool, s in sorted(scores["tools"].items()):
        p = s["primary"]
        if p["value"] is None:
            print(f"{tool:14s} {scores['metric']}: n/a")
            continue
        print(f"{tool:14s} {scores['metric']}={p['value']:.4f} CI=[{p['ci'][0]:.4f}, {p['ci'][1]:.4f}] n={p['n']}")
    return 0
