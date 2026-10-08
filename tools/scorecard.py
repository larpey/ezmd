"""Golden-fixture scorecard: per-family and per-converter fixture count, mean/min score, threshold, pass/fail.

Runs every fixture under `fixtures/` the same way the pytest plugin does (intomd.testing.fixtures.run_fixture)
and writes `scorecard.md` and `scorecard.json` to `--out` (default `build/scorecard/`, git-ignored). The nightly
workflow runs it, appends the Markdown to the job summary, and uploads both files as an artifact.

    uv run python tools/scorecard.py [--out DIR] [--family NAME ...] [--strict]

Exit status is 0 unless `--strict` is given and a fixture failed (skips never fail the run).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = 1


@dataclass(frozen=True, slots=True)
class FixtureResult:
    id: str
    family: str
    converter: str
    threshold: float
    status: str  # "pass" | "fail" | "skip"
    score: float | None = None
    seconds: float = 0.0
    detail: str = ""


@dataclass(slots=True)
class Row:
    family: str
    converter: str
    threshold: float
    fixtures: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    scores: list[float] = field(default_factory=list)

    @property
    def mean(self) -> float | None:
        return round(sum(self.scores) / len(self.scores), 4) if self.scores else None

    @property
    def min(self) -> float | None:
        return round(min(self.scores), 4) if self.scores else None

    @property
    def status(self) -> str:
        if self.failed:
            return "FAIL"
        return "PASS" if self.passed else "SKIP"

    def as_dict(self) -> dict[str, object]:
        return {
            "family": self.family,
            "converter": self.converter,
            "fixtures": self.fixtures,
            "passed": self.passed,
            "failed": self.failed,
            "skipped": self.skipped,
            "mean": self.mean,
            "min": self.min,
            "threshold": self.threshold,
            "status": self.status,
        }


def run_all(root: Path, families: Sequence[str] = ()) -> list[FixtureResult]:
    """Convert and score every fixture under `root` (the fixtures directory)."""
    from intomd.testing.fixtures import discover, run_fixture, threshold_for

    results: list[FixtureResult] = []
    for fx in discover(root):
        family = fx.path.parent.name
        if families and family not in families:
            continue
        threshold = threshold_for(fx, root)
        reason = fx.skip_reason
        if reason:
            results.append(FixtureResult(fx.id, family, fx.converter, threshold, "skip", detail=reason))
            continue
        run = run_fixture(fx, root)
        overall = round(run.score.overall, 4) if run.score is not None else None
        detail = "; ".join(run.hard_failures)
        if not detail and not run.passed:
            detail = f"score {overall} below threshold {threshold}"
        status = "pass" if run.passed else "fail"
        seconds = round(run.seconds, 3)
        results.append(FixtureResult(fx.id, family, fx.converter, threshold, status, overall, seconds, detail))
    return results


def aggregate(results: Iterable[FixtureResult], key: str) -> list[Row]:
    """Group results by "converter" (family + converter id) or "family"; failed runs without a score count 0."""
    rows: dict[tuple[str, str], Row] = {}
    for r in results:
        conv = r.converter if key == "converter" else "*"
        row = rows.setdefault((r.family, conv), Row(r.family, conv, r.threshold))
        row.threshold = min(row.threshold, r.threshold)
        row.fixtures += 1
        if r.status == "skip":
            row.skipped += 1
            continue
        row.scores.append(r.score if r.score is not None else 0.0)
        if r.status == "pass":
            row.passed += 1
        else:
            row.failed += 1
    return [rows[k] for k in sorted(rows)]


def _fmt(v: float | None) -> str:
    return "-" if v is None else f"{v:.4f}"


def _table(rows: Sequence[Row], first: str) -> list[str]:
    lines = [
        f"| {first} | Fixtures | Passed | Failed | Skipped | Mean | Min | Threshold | Status |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for r in rows:
        name = r.family if r.converter == "*" else f"{r.family} / `{r.converter}`"
        lines.append(
            f"| {name} | {r.fixtures} | {r.passed} | {r.failed} | {r.skipped} | {_fmt(r.mean)} | {_fmt(r.min)} "
            f"| {r.threshold:.2f} | {r.status} |"
        )
    return lines


def render_markdown(results: Sequence[FixtureResult]) -> str:
    total = len(results)
    counts = {s: sum(1 for r in results if r.status == s) for s in ("pass", "fail", "skip")}
    out = [
        "# Golden fixture scorecard",
        "",
        f"{total} fixtures: {counts['pass']} passed, {counts['fail']} failed, {counts['skip']} skipped.",
        "Scores are the harness's overall golden score (intomd.testing.score); the threshold is the lowest",
        "applicable threshold in the group (converter threshold, or a per-fixture lowered one).",
        "",
        "## By family",
        "",
        *_table(aggregate(results, "family"), "Family"),
        "",
        "## By converter",
        "",
        *_table(aggregate(results, "converter"), "Family / converter"),
    ]
    problems = [r for r in results if r.status != "pass"]
    if problems:
        out += ["", "## Failed and skipped fixtures", "", "| Fixture | Status | Score | Detail |", "|---|---|---:|---|"]
        for r in problems:
            detail = r.detail.replace("|", "/").replace(chr(10), " ")[:300]
            out.append(f"| {r.id} | {r.status} | {_fmt(r.score)} | {detail} |")
    return chr(10).join(out) + chr(10)


def render_json(results: Sequence[FixtureResult]) -> str:
    payload = {
        "schema": SCHEMA,
        "totals": {s: sum(1 for r in results if r.status == s) for s in ("pass", "fail", "skip")},
        "families": [r.as_dict() for r in aggregate(results, "family")],
        "converters": [r.as_dict() for r in aggregate(results, "converter")],
        "fixtures": [asdict(r) for r in results],
    }
    return json.dumps(payload, indent=2, sort_keys=True) + chr(10)


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    ap.add_argument("--fixtures", type=Path, default=ROOT / "fixtures", help="fixtures directory")
    ap.add_argument("--out", type=Path, default=ROOT / "build" / "scorecard", help="output directory")
    ap.add_argument("--family", action="append", default=[], help="only this family (repeatable)")
    ap.add_argument("--strict", action="store_true", help="exit 1 when any fixture fails")
    args = ap.parse_args(argv)
    results = run_all(args.fixtures.resolve(), args.family)
    args.out.mkdir(parents=True, exist_ok=True)
    md = render_markdown(results)
    (args.out / "scorecard.md").write_text(md, encoding="utf-8", newline=chr(10))
    (args.out / "scorecard.json").write_text(render_json(results), encoding="utf-8", newline=chr(10))
    sys.stdout.write(md)
    failed = any(r.status == "fail" for r in results)
    return 1 if args.strict and failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
