"""tools/scorecard.py: aggregation, rendering, and an end-to-end run on a small family."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("scorecard", ROOT / "tools" / "scorecard.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


sc = _load()


def _results() -> list[object]:
    r = sc.FixtureResult
    return [
        r("fam/a", "fam", "fam.one", 0.9, "pass", 1.0),
        r("fam/b", "fam", "fam.one", 0.8, "fail", 0.7, detail="score 0.7 below threshold 0.8"),
        r("fam/c", "fam", "fam.two", 0.95, "fail", None, detail="conversion failed: boom | pipe"),
        r("fam/d", "fam", "fam.two", 0.95, "skip", detail="requires module 'x'"),
        r("other/e", "other", "other.x", 0.85, "skip", detail="requires extra"),
    ]


def test_aggregate_by_converter() -> None:
    rows = {r.converter: r for r in sc.aggregate(_results(), "converter")}
    one, two, x = rows["fam.one"], rows["fam.two"], rows["other.x"]
    assert (one.fixtures, one.passed, one.failed, one.mean, one.min, one.threshold) == (2, 1, 1, 0.85, 0.7, 0.8)
    assert one.status == "FAIL"
    assert (two.fixtures, two.failed, two.skipped, two.mean, two.status) == (2, 1, 1, 0.0, "FAIL")
    assert (x.mean, x.min, x.status) == (None, None, "SKIP")


def test_aggregate_by_family() -> None:
    rows = {r.family: r for r in sc.aggregate(_results(), "family")}
    assert rows["fam"].converter == "*"
    assert (rows["fam"].fixtures, rows["fam"].passed, rows["fam"].failed, rows["fam"].skipped) == (4, 1, 2, 1)
    assert rows["other"].status == "SKIP"


def test_render_markdown_lists_problems_and_escapes_pipes() -> None:
    md = sc.render_markdown(_results())
    assert "5 fixtures: 1 passed, 2 failed, 2 skipped." in md
    assert "| fam / `fam.one` | 2 | 1 | 1 | 0 | 0.8500 | 0.7000 | 0.80 | FAIL |" in md
    assert "| fam | 4 | 1 | 2 | 1 |" in md
    assert "conversion failed: boom / pipe" in md
    assert "fam/a" not in md.split("## Failed and skipped fixtures")[1]


def test_render_json_shape() -> None:
    data = json.loads(sc.render_json(_results()))
    assert data["schema"] == 1
    assert data["totals"] == {"pass": 1, "fail": 2, "skip": 2}
    assert {r["converter"] for r in data["converters"]} == {"fam.one", "fam.two", "other.x"}
    assert len(data["fixtures"]) == 5


def test_main_runs_text_family(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert sc.main(["--family", "text", "--out", str(tmp_path), "--strict"]) == 0
    data = json.loads((tmp_path / "scorecard.json").read_text(encoding="utf-8"))
    assert data["totals"]["fail"] == 0
    assert data["totals"]["pass"] >= 4
    assert {r["family"] for r in data["families"]} == {"text"}
    md = (tmp_path / "scorecard.md").read_text(encoding="utf-8")
    assert "text / `text.plain`" in md
    assert md == capsys.readouterr().out


def test_strict_exit_code_on_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sc, "run_all", lambda root, families: _results())
    assert sc.main(["--out", str(tmp_path)]) == 0
    assert sc.main(["--out", str(tmp_path), "--strict"]) == 1
