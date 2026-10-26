"""Aggregate one dated run into bench/results/<date>/results.json and summary.md.

For every category the scorecard row of each tool holds: the primary metric with its 95% interval and n, the
failure rate (error, timeout or crash over attempted documents), coverage (attempted over all documents in the
category), median and p95 wall seconds per attempted document, and the peak memory over the run. ezmd's
verdict against the best competitor uses a paired bootstrap over the documents (or tables) both tools scored:
"leads" when the whole 95% interval of (ezmd - best) is above zero, "trails" when it is below, else "ties".
The self-graded fixture categories get no verdict: ezmd's own fixtures cannot support a claim against others.
The best competitor is the highest primary value among tools with at least MIN_N scored documents.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from tools.bench.config import RESULTS_DIR, cache_dir, load_tools
from tools.bench.hardware import describe
from tools.bench.schema import SCHEMA_VERSION, DocResult, read_results
from tools.bench.scoring.text import is_ezmd
from tools.bench.stats import paired_diff_ci, percentile

EZMD_TOOLS = ("ezmd", "ezmd-docs", "ezmd-main", "ezmd-main-compact", "ezmd-main-rag")
"""Rows that are ezmd (verdicts are computed for each against the best non-ezmd tool)."""
MIN_N = 5
"""A competitor needs at least this many scored documents in a category to count as its best, and a verdict
needs this many documents both tools scored."""
CATEGORY_LABELS = {
    "pdf-olmocr": "PDF, olmOCR-Bench (unit-test pass rate)",
    "omnidoc-text": "PDF, OmniDocBench text (1 - edit distance)",
    "omnidoc-reading-order": "PDF, OmniDocBench reading order (1 - edit distance)",
    "omnidoc-table": "PDF, OmniDocBench tables (TEDS)",
    "omnidoc-formula": "PDF, OmniDocBench display formulas (1 - edit distance; CDM off)",
    "web-articles": "Web articles, ScrapingHub AEB (article-body F1)",
    "arxiv-qa": "arXiv papers, answer accuracy (local-model QA over the converted text)",
    "arxiv-qa-second-half": "arXiv papers, answer accuracy on questions whose evidence is in the paper's second half",
    "arxiv-text-recall": "arXiv papers, text recall (share of the PDF text layer's words kept)",
    "arxiv-silent-loss": "arXiv papers, silent loss (over 5% of words lost with no warning raised; lower is better)",
    "arxiv-outline-recall": "arXiv papers, outline recall (PDF bookmarks found as headings)",
    "arxiv-tokens-per-page": "arXiv papers, o200k tokens per page (lower is better)",
    "arxiv-claude-tokens-per-page": "arXiv papers, Claude tokens per page (Anthropic count_tokens; lower is better)",
    "arxiv-answers-per-10k-tokens": "arXiv papers, correct answers per 10k tokens of converted text",
    "arxiv-source-recall": "arXiv papers, source recall (share of the LaTeX source's words kept; independent witness)",
    "damaged-silent-loss": "Damaged arXiv papers, silent loss, all kinds (lost over 5%, no warning; lower is better)",
    "damaged-scan-silent-loss": "Damaged arXiv papers, scanned (every page an image): silent loss (lower is better)",
    "damaged-pages-silent-loss": "Damaged arXiv papers, a block of image-only pages: silent loss (lower is better)",
    "damaged-trunc-silent-loss": "Damaged arXiv papers, file truncated at 80%: silent loss (lower is better)",
    "damaged-scan-text-recall": "Damaged arXiv papers, scanned: text recall of the intact paper (OCR recovers it)",
    "damaged-pages-text-recall": "Damaged arXiv papers, a block of image-only pages: text recall of the intact paper",
    "damaged-trunc-text-recall": "Damaged arXiv papers, file truncated at 80%: text recall of the intact paper",
    "damaged-page-accuracy": "Damaged arXiv papers, pages named by the pages_without_text warning (Jaccard; ezmd only)",
}


def _speed(results: list[DocResult]) -> dict[str, Any]:
    attempted = [r for r in results if r.status != "unsupported"]
    secs = [r.seconds for r in attempted if r.seconds is not None]
    rss = [r.peak_rss_mb for r in attempted if r.peak_rss_mb is not None]
    failed = [r for r in attempted if r.failed]
    classes: dict[str, int] = defaultdict(int)
    for r in failed:
        classes[f"{r.status}:{r.error_class}"] += 1
    return {
        "attempted": len(attempted),
        "total": len(results),
        "failed": len(failed),
        "failure_rate": round(len(failed) / len(attempted), 4) if attempted else None,
        "failure_classes": dict(classes),
        "median_s": round(percentile(secs, 50), 3) if secs else None,
        "p95_s": round(percentile(secs, 95), 3) if secs else None,
        "median_rss_mb": round(percentile(rss, 50), 1) if rss else None,
        "peak_rss_mb": round(max(rss), 1) if rss else None,
    }


def _verdict(cat_scores: dict[str, Any], ezmd: str, higher: bool = True) -> dict[str, Any] | None:
    mine = cat_scores.get(ezmd)
    if not mine or mine.get("value") is None:
        return None
    rivals = {
        t: s for t, s in cat_scores.items() if not is_ezmd(t) and s.get("value") is not None and s.get("n", 0) >= MIN_N
    }
    if not rivals:
        return None
    best = max(rivals, key=lambda t: rivals[t]["value"] if higher else -rivals[t]["value"])
    a, b = mine.get("per_doc") or {}, rivals[best].get("per_doc") or {}
    common = sorted(set(a) & set(b))
    out: dict[str, Any] = {
        "ezmd": ezmd,
        "best_competitor": best,
        "ezmd_value": mine["value"],
        "best_value": rivals[best]["value"],
        "gap": round(mine["value"] - rivals[best]["value"], 4),
    }
    if len(common) >= MIN_N:
        diff, (lo, hi) = paired_diff_ci([a[k] for k in common], [b[k] for k in common])
        out.update({"paired_n": len(common), "paired_diff": round(diff, 4), "paired_ci": [round(lo, 4), round(hi, 4)]})
        if higher:
            out["verdict"] = "leads" if lo > 0 else "trails" if hi < 0 else "ties"
        else:
            out["verdict"] = "leads" if hi < 0 else "trails" if lo > 0 else "ties"
    else:
        out["verdict"] = f"not comparable (fewer than {MIN_N} shared documents)"
    return out


def _categories(corpus: str, scores: dict[str, Any], results: list[DocResult]) -> dict[str, dict[str, Any]]:
    """category -> tool -> {value, ci, n, per_doc, speed}"""
    by_tool: dict[str, list[DocResult]] = defaultdict(list)
    for r in results:
        by_tool[r.tool].append(r)
    cats: dict[str, dict[str, Any]] = defaultdict(dict)
    for tool, s in scores["tools"].items():
        rs = by_tool.get(tool, [])
        if corpus in ("omnidoc", "arxiv", "arxiv-damaged"):
            for cat, v in s["categories"].items():
                cats[cat][tool] = {**v, "speed": _speed(rs)}
        elif corpus == "olmocr":
            cats["pdf-olmocr"][tool] = {
                **s["primary"],
                "per_doc": s["per_doc"],
                "speed": _speed(rs),
                "by_test_file": s["secondary"],
            }
        elif corpus == "web":
            cats["web-articles"][tool] = {
                **s["primary"],
                "per_doc": s["per_doc"],
                "speed": _speed(rs),
                "secondary": s["secondary"],
            }
        else:
            for fam, v in s["categories"].items():
                fam_docs = {d: x for d, x in s["per_doc"].items() if d.startswith(f"{fam}__")}
                fam_rs = [r for r in rs if r.category == fam]
                cats[f"fixtures-{fam}"][tool] = {**v, "per_doc": fam_docs, "speed": _speed(fam_rs)}
            cats["fixtures-all"][tool] = {**s["primary"], "per_doc": s["per_doc"], "speed": _speed(rs)}
    # Tools that attempted nothing in a category still get their coverage row.
    for cat, rows in cats.items():
        for tool, rs in by_tool.items():
            if tool not in rows:
                sub = [
                    r
                    for r in rs
                    if not cat.startswith("fixtures-")
                    or cat == "fixtures-all"
                    or r.category == cat.removeprefix("fixtures-")
                ]
                rows[tool] = {"value": None, "ci": None, "n": 0, "per_doc": {}, "speed": _speed(sub)}
    return cats


def _startup(run_dir: Path) -> dict[str, float]:
    out = {}
    for path in (run_dir / "logs").glob("*.startup.jsonl"):
        vals = [json.loads(line)["startup_seconds"] for line in path.read_text(encoding="utf-8").splitlines() if line]
        if vals:
            out[path.name.removesuffix(".startup.jsonl")] = round(percentile(vals, 50), 2)
    return out


def _versions(results: list[DocResult]) -> dict[str, str]:
    out: dict[str, str] = {}
    for r in results:
        if r.tool_version:
            out[r.tool] = r.tool_version
    return out


def write_report(date: str) -> int:
    runs = cache_dir() / "runs" / date
    if not runs.exists():
        print(f"no runs for {date}")
        return 1
    tools = load_tools()
    report: dict[str, Any] = {
        "schema": SCHEMA_VERSION,
        "date": date,
        "hardware": describe(),
        "corpora": {},
        "tools": {},
        "scorecard": {},
        "verdicts": {},
        "directions": {},
    }
    versions: dict[str, str] = {}
    startup: dict[str, dict[str, float]] = {}
    for run_dir in sorted(p for p in runs.iterdir() if (p / "scores.json").exists()):
        corpus = run_dir.name
        scores = json.loads((run_dir / "scores.json").read_text(encoding="utf-8"))
        results = read_results(run_dir / "results.jsonl")
        docs = json.loads((run_dir / "docs.json").read_text(encoding="utf-8"))
        report["corpora"][corpus] = {
            "documents": len(docs["documents"]),
            "sample": docs.get("sample"),
            "doc_ids": [d["id"] for d in docs["documents"]],
        }
        versions.update(_versions(results))
        startup[corpus] = _startup(run_dir)
        directions: dict[str, bool] = scores.get("category_direction", {})
        for cat, rows in _categories(corpus, scores, results).items():
            higher = directions.get(cat, bool(scores.get("higher_is_better", True)))
            report["directions"][cat] = higher
            report["scorecard"][cat] = {
                t: {k: v for k, v in row.items() if k != "per_doc"} for t, row in sorted(rows.items())
            }
            if not cat.startswith("fixtures"):  # self-graded: scores only, no leads/trails claims
                report["verdicts"][cat] = {e: _verdict(rows, e, higher) for e in EZMD_TOOLS if e in rows}
    for name, tool in tools.items():
        freeze = tool.venv / "freeze.txt"
        report["tools"][name] = {
            "kind": tool.kind,
            "version": versions.get(name, tool.version or str(tool.extra.get("image_version", ""))),
            "requirements": list(tool.requirements) or [tool.url or str(tool.extra.get("image", ""))],
            "license": tool.license,
            "startup_seconds_median": {c: s[name] for c, s in startup.items() if name in s},
            "freeze": freeze.read_text(encoding="utf-8").splitlines() if freeze.exists() else None,
        }
    out = RESULTS_DIR / date
    out.mkdir(parents=True, exist_ok=True)
    notes = out / "notes.md"  # hand-written run conditions and skipped tools, rendered into summary.md
    report["notes"] = notes.read_text(encoding="utf-8") if notes.exists() else ""
    text = json.dumps(report, indent=1, sort_keys=True) + "\n"
    (out / "results.json").write_text(text, encoding="utf-8", newline="\n")
    (out / "summary.md").write_text(render_markdown(report), encoding="utf-8", newline="\n")
    print(f"wrote {out / 'results.json'} and {out / 'summary.md'}")
    return 0


def _label(cat: str) -> str:
    if cat in CATEGORY_LABELS:
        return CATEGORY_LABELS[cat]
    if cat.startswith("fixtures-"):
        return f"ezmd fixtures (self-graded, supporting evidence only): {cat.removeprefix('fixtures-')}"
    return cat


def _fmt(v: float | None, digits: int = 3) -> str:
    return "n/a" if v is None else f"{v:.{digits}f}"


def render_markdown(report: dict[str, Any]) -> str:
    hw = report["hardware"]
    lines = [
        f"# Benchmark baseline {report['date']}",
        "",
        f"Hardware: {hw['cpu']}, {hw['logical_cores']} logical cores, {hw['ram_gb']} GB RAM, "
        f"GPU {', '.join(hw['gpus']) or 'none'}, {hw['os']}.",
        "",
        "Each cell: primary metric [95% CI] (n). fail = error/timeout/crash share of attempted documents; "
        "cov = attempted/total; s/doc = median and p95 wall seconds; RSS = median and peak over documents of the "
        "per-document peak MB (process tree plus any containers the tool starts, models loaded). Rows marked * are "
        "ezmd.",
        "",
    ]
    if report.get("notes"):
        lines += [report["notes"].rstrip(), ""]
    for cat in sorted(report["scorecard"]):
        rows = report["scorecard"][cat]
        lines += [f"## {_label(cat)}", ""]
        lines += [
            "| tool | metric [95% CI] | n | fail | cov | s/doc med | s/doc p95 | RSS MB med | RSS MB peak |",
            "|---|---|---|---|---|---|---|---|---|",
        ]
        higher = report.get("directions", {}).get(cat, True)
        missing = -1.0 if higher else float("inf")
        ranked = sorted(
            rows.items(),
            key=lambda kv: (kv[1]["value"] if kv[1]["value"] is not None else missing) * (-1 if higher else 1),
        )
        skipped = sorted(t for t, r in ranked if not r["speed"]["attempted"])
        for tool, row in ranked:
            sp = row["speed"]
            if not sp["attempted"]:
                continue
            ci = row.get("ci")
            metric = (
                "n/a"
                if row["value"] is None
                else f"{row['value']:.3f} [{ci[0]:.3f}, {ci[1]:.3f}]"
                if ci
                else f"{row['value']:.3f}"
            )
            mark = "*" if is_ezmd(tool) else ""
            fail = "n/a" if sp["failure_rate"] is None else f"{sp['failure_rate']:.1%}"
            lines.append(
                f"| {tool}{mark} | {metric} | {row['n']} | {fail} | {sp['attempted']}/{sp['total']} | "
                f"{_fmt(sp['median_s'], 2)} | {_fmt(sp['p95_s'], 2)} | "
                f"{_fmt(sp.get('median_rss_mb'), 0)} | {_fmt(sp['peak_rss_mb'], 0)} |"
            )
        if skipped:
            lines.append(f"\nNot attempted (format not supported): {', '.join(skipped)}.")
        for ez, v in report["verdicts"].get(cat, {}).items():
            if v:
                extra = (
                    (
                        f"; paired diff {v['paired_diff']:+.3f} [{v['paired_ci'][0]:+.3f}, {v['paired_ci'][1]:+.3f}] "
                        f"over {v['paired_n']} shared"
                    )
                    if "paired_diff" in v
                    else ""
                )
                lines.append(f"\n{ez}: **{v['verdict']}** vs {v['best_competitor']} (gap {v['gap']:+.3f}{extra}).")
        lines.append("")
    return "\n".join(lines) + "\n"
