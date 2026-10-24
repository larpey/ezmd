"""Damaged arXiv papers (tools/bench/damage.py): known loss, measured against the intact paper's text layer.

Per document: `text recall` of the original's words (a tool with OCR can recover a rendered page; one without
cannot), `silent loss` as in scoring/arxiv.py (lost more than LOSS_THRESHOLD and said nothing), and for ezmd on
the image variants `page accuracy`: the Jaccard overlap between the pages its `pages_without_text` warning names
and the pages that were actually replaced. A tool with no warning channel scores None there, not zero: the
category measures how precise a warning is, and the silent-loss category already charges for having none.

Categories are reported per damage kind and pooled. The primary metric is the pooled silent-loss rate (lower
is better): the share of damaged documents a tool converted, lost content on, and said nothing about. A
conversion that fails outright is loud and counts as neither lost nor silent; the report's failure column
shows it.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from tools.bench.damage import KINDS, textless_pages
from tools.bench.schema import DocResult
from tools.bench.scoring.arxiv import LOSS_THRESHOLD, count_tokens, declared_loss, recall, witness, words
from tools.bench.scoring.common import attempted, by_tool, summarize
from tools.bench.scoring.text import is_ezmd, read_output


def warned_pages(result: DocResult, run_dir: Path) -> set[int] | None:
    """Pages ezmd's `pages_without_text` warning names (1-based), None for a tool without a warning channel."""
    if not is_ezmd(result.tool) or not result.output:
        return None
    path = run_dir / (result.output + ".warnings.json")
    if not path.exists():
        return None
    pages: set[int] = set()
    for w in json.loads(path.read_text(encoding="utf-8")).get("warnings", []):
        if w.get("kind") != "pages_without_text":
            continue
        listed = str((w.get("detail") or {}).get("pages", "") or "")
        pages.update(int(p) for p in listed.split(",") if p.strip().isdigit())
        if not listed and w.get("page") is not None:
            pages.add(int(w["page"]))
    return pages


def page_accuracy(warned: set[int] | None, damaged: Sequence[int], textless: Sequence[int] = ()) -> float | None:
    """Jaccard overlap of the pages a warning names with the pages that have no text: the damaged ones plus
    any the intact paper never had text on (full-page figures), which a correct warning also names."""
    if warned is None or not damaged:
        return None
    truth = set(damaged) | set(textless)
    union = warned | truth
    return len(warned & truth) / len(union) if union else 1.0


def score_doc(result: DocResult, run_dir: Path, doc: dict[str, Any]) -> dict[str, float | None]:
    w = witness(str(doc["paper"]), Path(str(doc["source"])))
    md = read_output(result, run_dir)
    ok = result.status == "ok"
    rec = recall(w.words, words(md)) if ok else 0.0
    lost = rec < 1.0 - LOSS_THRESHOLD
    declared = declared_loss(result, run_dir)
    kind = str(doc["kind"])
    damaged = [int(p) for p in doc.get("damaged_pages", [])]
    textless = [int(p) for p in doc.get("textless_pages", [])]
    out: dict[str, float | None] = {f"damaged-{k}-text-recall": None for k in KINDS}
    out.update({f"damaged-{k}-silent-loss": None for k in KINDS})
    out[f"damaged-{kind}-text-recall"] = round(rec, 4)
    out[f"damaged-{kind}-silent-loss"] = float(ok and lost and not declared)
    out["damaged-silent-loss"] = float(ok and lost and not declared)
    out["damaged-page-accuracy"] = (
        page_accuracy(warned_pages(result, run_dir), damaged, textless) if ok and kind in ("scan", "pages") else None
    )
    out["lost"] = float(lost)
    out["declared"] = None if declared is None else float(declared)
    out["failed"] = float(not ok)
    out["tokens"] = float(count_tokens(md)) if ok else None
    return out


def _docs(run_dir: Path) -> dict[str, dict[str, Any]]:
    docs = json.loads((run_dir / "docs.json").read_text(encoding="utf-8"))
    out: dict[str, dict[str, Any]] = {}
    for d in docs["documents"]:
        if "textless_pages" not in d:  # a run manifest written before the corpus recorded them
            d = {**d, "textless_pages": textless_pages(Path(str(d["source"])))}
        out[d["id"]] = d
    return out


CATEGORIES = (
    "damaged-silent-loss",
    *(f"damaged-{k}-silent-loss" for k in KINDS),
    *(f"damaged-{k}-text-recall" for k in KINDS),
    "damaged-page-accuracy",
)
DIRECTION = {c: "silent-loss" not in c for c in CATEGORIES}


def score(results: list[DocResult], run_dir: Path) -> dict[str, Any]:
    docs = _docs(run_dir)
    tools: dict[str, Any] = {}
    for tool, rs in sorted(by_tool(results).items()):
        rs = attempted(rs)
        if not rs:
            continue
        per_doc = {r.doc_id: score_doc(r, run_dir, docs[r.doc_id]) for r in rs}
        cats: dict[str, Any] = {}
        for cat in CATEGORIES:
            values = {d: v[cat] for d, v in per_doc.items() if v[cat] is not None}
            cats[cat] = {**summarize(list(values.values())), "per_doc": values}
        lost = [v for v in per_doc.values() if v["lost"]]
        declared_when_lost = [v["declared"] for v in lost if v["declared"] is not None]
        secondary = {
            "lost_rate": {"value": round(len(lost) / len(per_doc), 4)},
            "failed_rate": {"value": round(sum(v["failed"] for v in per_doc.values()) / len(per_doc), 4)},
            "declared_when_lost": {
                "value": round(sum(declared_when_lost) / len(declared_when_lost), 4) if declared_when_lost else None
            },
        }
        tools[tool] = {
            "primary": {k: cats["damaged-silent-loss"][k] for k in ("value", "ci", "n")},
            "categories": cats,
            "per_doc": cats["damaged-silent-loss"]["per_doc"],
            "secondary": secondary,
        }
    return {
        "corpus": "arxiv-damaged",
        "metric": "silent_loss",
        "higher_is_better": False,
        "category_direction": DIRECTION,
        "tools": tools,
    }
