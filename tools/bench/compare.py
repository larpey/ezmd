"""Before/after comparison of ezmd builds on the same documents.

    uv run python -m tools.bench compare --before 2026-10-13 --after rc5 [--rivals pymupdf4llm,unstructured]

For every category both runs scored, prints each ezmd config's value [95% CI] before and after, the paired
difference after - before, and the paired difference of the after build against each rival (scored in the
`before` run on the same documents). Writes bench/results/<after>/compare.json and compare.md.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tools.bench.config import RESULTS_DIR, cache_dir
from tools.bench.report import EZMD_TOOLS, MIN_N, _label
from tools.bench.stats import paired_diff_ci


def _categories(run: Path) -> tuple[dict[str, dict[str, Any]], dict[str, bool]]:
    """(category -> tool -> {value, ci, n, per_doc}, category -> higher is better), from every scores.json of a
    dated run."""
    out: dict[str, dict[str, Any]] = {}
    higher: dict[str, bool] = {}
    for scores_path in sorted(run.glob("*/scores.json")):
        corpus = scores_path.parent.name
        scores = json.loads(scores_path.read_text(encoding="utf-8"))
        directions: dict[str, bool] = scores.get("category_direction", {})
        for tool, s in scores["tools"].items():
            if corpus in ("omnidoc", "arxiv", "arxiv-damaged"):
                cats = s["categories"]
            elif corpus == "olmocr":
                cats = {"pdf-olmocr": {**s["primary"], "per_doc": s["per_doc"]}}
            elif corpus == "web":
                cats = {"web-articles": {**s["primary"], "per_doc": s["per_doc"]}}
            else:
                cats = {}
                for fam, v in s["categories"].items():
                    docs = {d: x for d, x in s["per_doc"].items() if d.startswith(f"{fam}__")}
                    cats[f"fixtures-{fam}"] = {**v, "per_doc": docs}
            for cat, v in cats.items():
                out.setdefault(cat, {})[tool] = v
                higher[cat] = directions.get(cat, bool(scores.get("higher_is_better", True)))
    return out, higher


def _paired(a: dict[str, float], b: dict[str, float], higher: bool = True) -> dict[str, Any] | None:
    common = sorted(set(a) & set(b))
    if len(common) < MIN_N:
        return None
    diff, (lo, hi) = paired_diff_ci([a[k] for k in common], [b[k] for k in common])
    if higher:
        verdict = "beats" if lo > 0 else "trails" if hi < 0 else "ties"
    else:
        verdict = "beats" if hi < 0 else "trails" if lo > 0 else "ties"
    return {"diff": round(diff, 4), "ci": [round(lo, 4), round(hi, 4)], "n": len(common), "verdict": verdict}


def compare(before: str, after: str, rivals: list[str]) -> dict[str, Any]:
    b, _ = _categories(cache_dir() / "runs" / before)
    a, higher = _categories(cache_dir() / "runs" / after)
    out: dict[str, Any] = {"before": before, "after": after, "categories": {}, "directions": higher}
    for cat in sorted(set(a) & set(b)):
        up = higher.get(cat, True)
        rows: dict[str, Any] = {}
        for ez in EZMD_TOOLS:
            if ez not in a[cat] or ez not in b[cat]:
                continue
            new, old = a[cat][ez], b[cat][ez]
            row: dict[str, Any] = {
                "before": {k: old.get(k) for k in ("value", "ci", "n")},
                "after": {k: new.get(k) for k in ("value", "ci", "n")},
                "after_minus_before": _paired(new.get("per_doc") or {}, old.get("per_doc") or {}, up),
                "vs": {},
            }
            for rival in rivals:
                if rival in b[cat]:
                    r = b[cat][rival]
                    row["vs"][rival] = {"value": r.get("value"), **(_paired(new["per_doc"], r["per_doc"], up) or {})}
            rows[ez] = row
        if rows:
            out["categories"][cat] = rows
    return out


def _ci(x: dict[str, Any]) -> str:
    if x.get("value") is None:
        return "n/a"
    ci = x.get("ci")
    return f"{x['value']:.3f} [{ci[0]:.3f}, {ci[1]:.3f}]" if ci else f"{x['value']:.3f}"


def render(result: dict[str, Any]) -> str:
    lines = [f"# ezmd {result['after']} vs {result['before']}", ""]
    for cat, rows in result["categories"].items():
        lines += [f"## {_label(cat)}", ""]
        for ez, row in rows.items():
            d = row["after_minus_before"]
            delta = f"{d['diff']:+.3f} [{d['ci'][0]:+.3f}, {d['ci'][1]:+.3f}] (n={d['n']})" if d else "n/a"
            lines.append(f"- {ez}: {_ci(row['before'])} -> {_ci(row['after'])}; after - before {delta}")
            for rival, v in row["vs"].items():
                if "diff" in v and not cat.startswith("fixtures"):  # self-graded: no claims vs rivals
                    lines.append(
                        f"  - vs {rival} ({v['value']:.3f}): {v['verdict']}, {v['diff']:+.3f} "
                        f"[{v['ci'][0]:+.3f}, {v['ci'][1]:+.3f}]"
                    )
        lines.append("")
    return "\n".join(lines)


def main(before: str, after: str, rivals: list[str]) -> int:
    result = compare(before, after, rivals)
    out = RESULTS_DIR / after
    out.mkdir(parents=True, exist_ok=True)
    (out / "compare.json").write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8", newline="\n")
    text = render(result)
    (out / "compare.md").write_text(text, encoding="utf-8", newline="\n")
    print(text)
    return 0
