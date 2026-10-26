"""Outcome scoring for a corpus with no ground truth (govdocs1): did the conversion end the way it should.

Every result is one of three outcomes:

- `ok`: an output was written.
- `declared`: the tool raised one of the errors it documents (`DECLARED`), such as an unsupported media type or
  an input over the size limit. A refusal is a correct answer for a file the tool does not claim.
- `bug`: anything else. An undeclared exception, a timeout and a worker crash are converter defects whatever the
  input, because the contract is "a `Document` or a `ConversionError`".

The primary metric is the clean rate, ok plus declared over all attempted documents. Bugs are clustered by
exception class and the frame that raised (`DocResult.where`), declared errors by class and message shape, and
both are written to `<run_dir>/clusters.md` with sample documents: the list a fix pass works from.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from tools.bench.schema import DocResult
from tools.bench.stats import bootstrap_ci

DECLARED = frozenset({"ConversionError", "UnsupportedMediaType", "InputTooLarge"})
"""ezmd's documented failure classes (`ezmd.registry.ConversionError` and its subclasses, `ezmd.inputs`)."""
BUG_CAUSES = frozenset(
    {
        "AssertionError",
        "AttributeError",
        "IndexError",
        "KeyError",
        "MemoryError",
        "NameError",
        "NotImplementedError",
        "OverflowError",
        "RecursionError",
        "TypeError",
        "UnboundLocalError",
        "ValidationError",
        "ZeroDivisionError",
    }
)
"""A declared error raised from one of these is a converter crash the registry wrapped ("all converters
failed ... last error: 1 validation error for Heading"), not a parser's refusal."""
SAMPLES = 5
_DIGITS = re.compile(r"\d+")
_QUOTED = re.compile(r"'[^']*'|\"[^\"]*\"")


def outcome(r: DocResult) -> str:
    if r.status == "ok":
        return "ok"
    if r.status == "error" and r.error_class in DECLARED and r.cause not in BUG_CAUSES:
        return "declared"
    return "bug"


def message_shape(error: str | None, width: int = 80) -> str:
    """The first line of a message with numbers and quoted names blanked, so one cause is one key."""
    first = (error or "").splitlines()[0] if error else ""
    return _DIGITS.sub("#", _QUOTED.sub("'…'", first))[:width]


def bug_key(r: DocResult) -> tuple[str, str]:
    if r.status in ("timeout", "crash"):
        return (r.status, r.error_class or "")
    return (r.cause or r.error_class or "", r.where or message_shape(r.error))


def cluster(results: list[DocResult]) -> list[dict[str, Any]]:
    """Failure clusters, largest first: bugs keyed by (class, frame), declared errors by (class, message shape)."""
    groups: dict[tuple[str, str, str], list[DocResult]] = defaultdict(list)
    for r in results:
        kind = outcome(r)
        if kind == "ok":
            continue
        key = bug_key(r) if kind == "bug" else (r.error_class or "", message_shape(r.error))
        groups[(kind, *key)].append(r)
    out: list[dict[str, Any]] = []
    for (kind, cls, site), members in groups.items():
        cats = Counter(m.category for m in members)
        out.append(
            {
                "kind": kind,
                "error_class": cls,
                "where": site,
                "count": len(members),
                "categories": dict(cats.most_common()),
                "message": message_shape(members[0].error, 200),
                "samples": [m.doc_id for m in sorted(members, key=lambda m: m.doc_id)[:SAMPLES]],
            }
        )
    out.sort(key=lambda c: (c["kind"] != "bug", -c["count"], c["error_class"], c["where"]))
    return out


def by_category(results: list[DocResult]) -> dict[str, dict[str, int]]:
    table: dict[str, Counter[str]] = defaultdict(Counter)
    for r in results:
        table[r.category][outcome(r)] += 1
        table[r.category]["n"] += 1
    return {cat: dict(counts) for cat, counts in sorted(table.items(), key=lambda kv: -kv[1]["n"])}


def _tool_scores(results: list[DocResult]) -> dict[str, Any]:
    flags = {r.doc_id: 1.0 if outcome(r) != "bug" else 0.0 for r in results}
    values = list(flags.values())
    counts = Counter(outcome(r) for r in results)
    statuses = Counter(r.status for r in results)
    seconds = [r.seconds for r in results if r.seconds is not None]
    return {
        "primary": {"value": sum(values) / len(values), "ci": list(bootstrap_ci(values)), "n": len(values)},
        "secondary": {
            "ok": counts["ok"],
            "declared": counts["declared"],
            "bug": counts["bug"],
            "status": dict(statuses),
            "seconds_total": round(sum(seconds), 1),
            "categories": by_category(results),
            "clusters": cluster(results),
        },
        "per_doc": flags,
    }


def score(results: list[DocResult], run_dir: Path) -> dict[str, Any]:
    tools: dict[str, list[DocResult]] = defaultdict(list)
    for r in results:
        tools[r.tool].append(r)
    scores = {
        "corpus": results[0].corpus,
        "metric": "clean_rate",
        "higher_is_better": True,
        "tools": {name: _tool_scores(rs) for name, rs in tools.items()},
    }
    (run_dir / "clusters.md").write_text(clusters_markdown(scores), encoding="utf-8", newline="\n")
    return scores


def clusters_markdown(scores: dict[str, Any]) -> str:
    lines = [f"# {scores['corpus']}: outcomes and failure clusters", ""]
    for tool, s in sorted(scores["tools"].items()):
        sec = s["secondary"]
        p = s["primary"]
        lines += [
            f"## {tool}",
            "",
            f"Clean rate {p['value']:.4f} [{p['ci'][0]:.4f}, {p['ci'][1]:.4f}] over {p['n']} documents: "
            f"{sec['ok']} ok, {sec['declared']} declared, {sec['bug']} bugs "
            f"({', '.join(f'{k} {v}' for k, v in sorted(sec['status'].items()))}); "
            f"{sec['seconds_total']:.0f} s of conversion.",
            "",
            "| type | n | ok | declared | bug |",
            "|---|---|---|---|---|",
        ]
        for cat, counts in sec["categories"].items():
            lines.append(
                f"| {cat} | {counts['n']} | {counts.get('ok', 0)} | {counts.get('declared', 0)} | "
                f"{counts.get('bug', 0)} |"
            )
        lines += ["", "| kind | n | class | where | types | message | samples |", "|---|---|---|---|---|---|---|"]
        for c in sec["clusters"]:
            types = ", ".join(f"{k} {v}" for k, v in c["categories"].items())
            msg = c["message"].replace("|", "\\|")
            where = c["where"].replace("|", "\\|")
            lines.append(
                f"| {c['kind']} | {c['count']} | `{c['error_class']}` | `{where}` | {types} | {msg} | "
                f"{', '.join(c['samples'])} |"
            )
        lines.append("")
    return "\n".join(lines)
