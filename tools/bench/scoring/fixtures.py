"""ezmd fixture corpus: every tool's output scored against ezmd's goldens with ezmd.testing.score.

Self-graded and biased toward ezmd's output conventions (the goldens are ezmd's reviewed `full` renderings), so
this is supporting evidence only. Primary metric: the scorer's `overall` (0.25 heading, 0.25 table, 0.30 text,
0.20 structure). A failed conversion scores 0; formats a tool does not claim are excluded from its mean.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

from ezmd.testing.score import score as fixture_score
from tools.bench.config import ROOT
from tools.bench.schema import DocResult
from tools.bench.scoring.common import attempted, by_tool, summarize
from tools.bench.scoring.text import read_output, strip_frontmatter

SUB_SCORES = ("heading", "table", "text", "structure")


def _expected(doc_id: str) -> str:
    family, name = doc_id.split("__", 1)
    return strip_frontmatter((ROOT / "fixtures" / family / name / "expected.full.md").read_text(encoding="utf-8"))


def score(results: list[DocResult], run_dir: Path) -> dict[str, Any]:
    tools: dict[str, Any] = {}
    for tool, rs in sorted(by_tool(results).items()):
        per_doc: dict[str, dict[str, float]] = {}
        by_cat: dict[str, list[float]] = defaultdict(list)
        for r in attempted(rs):
            if r.status == "ok":
                s = fixture_score(_expected(r.doc_id), read_output(r, run_dir)).as_dict()
            else:
                s = dict.fromkeys((*SUB_SCORES, "overall"), 0.0)
            per_doc[r.doc_id] = s
            by_cat[r.category].append(s["overall"])
        tools[tool] = {
            "primary": summarize([s["overall"] for s in per_doc.values()]),
            "secondary": {k: summarize([s[k] for s in per_doc.values()]) for k in SUB_SCORES},
            "categories": {c: summarize(v) for c, v in sorted(by_cat.items())},
            "per_doc": {d: s["overall"] for d, s in per_doc.items()},
        }
    return {"corpus": "fixtures", "metric": "fixture_overall", "higher_is_better": True, "tools": tools}
