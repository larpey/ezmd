"""Helpers shared by the scorers: grouping results, summarizing per-document values."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable

from tools.bench.schema import DocResult
from tools.bench.stats import bootstrap_ci, mean


def by_tool(results: Iterable[DocResult]) -> dict[str, list[DocResult]]:
    out: dict[str, list[DocResult]] = defaultdict(list)
    for r in results:
        out[r.tool].append(r)
    return dict(out)


def summarize(values: list[float]) -> dict[str, object]:
    if not values:
        return {"value": None, "ci": None, "n": 0}
    lo, hi = bootstrap_ci(values)
    return {"value": round(mean(values), 4), "ci": [round(lo, 4), round(hi, 4)], "n": len(values)}


def attempted(results: Iterable[DocResult]) -> list[DocResult]:
    """Results the tool attempted (it claims the format); failures stay in and score as zero."""
    return [r for r in results if r.status != "unsupported"]
