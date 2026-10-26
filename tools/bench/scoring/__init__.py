"""Scoring: turn raw tool outputs of one corpus run into per-document scores and a per-tool summary.

Each scorer writes `<run_dir>/scores.json`:

    {"corpus": ..., "metric": <primary metric name>, "higher_is_better": bool,
     "tools": {tool: {"primary": {"value", "ci", "n"}, "secondary": {...}, "per_doc": {doc_id: value}}}}

Official benchmark code does the scoring wherever it exists (olmOCR-Bench, OmniDocBench, the ScrapingHub
article-extraction evaluate.py); the ezmd fixture corpus uses ezmd's own scorer (ezmd.testing.score).
ezmd's leading YAML frontmatter block is removed before scoring (it is metadata, not page content, and only ezmd
writes one); other tools' output is scored as written. On olmOCR-Bench a document the tool failed to convert
(error, timeout, crash) fails every one of its tests, as upstream olmocr counts a missing candidate.
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
    elif corpus == "arxiv":
        from tools.bench.scoring.arxiv import score
    elif corpus == "arxiv-damaged":
        from tools.bench.scoring.damaged import score
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
        metric = s.get("metric", scores["metric"])
        if p["value"] is None:
            print(f"{tool:14s} {metric}: n/a")
            continue
        print(f"{tool:14s} {metric}={p['value']:.4f} CI=[{p['ci'][0]:.4f}, {p['ci'][1]:.4f}] n={p['n']}")
    return 0
