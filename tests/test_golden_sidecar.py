"""Sidecar goldens: written without volatile fields and compared exactly by the fixture runner (audit fix)."""

from __future__ import annotations

import copy
import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from ezmd.testing.fixtures import (
    NORMALIZED,
    Fixture,
    discover,
    load_meta,
    normalize_sidecar,
    run_fixture,
    write_golden,
)

ROOT = Path(__file__).resolve().parents[1] / "fixtures"
SMALL = "text/plain-utf8"


def _load(path: Path) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data


def _copy_fixture(tmp_path: Path, fid: str) -> tuple[Fixture, Path]:
    root = tmp_path / "fixtures"
    family = fid.split("/")[0]
    shutil.copytree(ROOT / fid, root / fid)
    shutil.copy(ROOT / "thresholds.toml", root / "thresholds.toml")
    shutil.copy(ROOT / family / "thresholds.toml", root / family / "thresholds.toml")
    return Fixture(path=root / fid, meta=load_meta(root / fid)), root


def test_committed_sidecars_hold_no_volatile_fields() -> None:
    for fx in discover(ROOT):
        sidecar = _load(fx.expected_sidecar)
        assert normalize_sidecar(sidecar) == sidecar, f"{fx.id}: run ezmd-golden --write to normalize"
        assert "duration_seconds" not in sidecar["metrics"], fx.id
        assert sidecar["frontmatter"]["converter_version"] == NORMALIZED, fx.id


def test_normalize_sidecar_touches_only_volatile_fields() -> None:
    raw = {
        "metrics": {"duration_seconds": 0.25, "fetch_seconds": None, "input_bytes": 10},
        "frontmatter": {"converter_version": "1.2.3", "ezmd_version": "1.2.3", "title": "T"},
        "document": {"blocks": [{"type": "paragraph"}]},
    }
    before = copy.deepcopy(raw)
    out = normalize_sidecar(raw)
    assert raw == before  # the input is not mutated
    assert out == {
        "metrics": {"input_bytes": 10},
        "frontmatter": {"converter_version": NORMALIZED, "ezmd_version": NORMALIZED, "title": "T"},
        "document": {"blocks": [{"type": "paragraph"}]},
    }
    assert normalize_sidecar(out) == out


def test_unchanged_sidecar_passes(tmp_path: Path) -> None:
    fx, root = _copy_fixture(tmp_path, SMALL)
    run = run_fixture(fx, root)
    assert run.hard_failures == [] and run.passed


@pytest.mark.parametrize(
    "edit",
    [
        lambda s: s["document"]["blocks"][0].update(type="code"),
        lambda s: s["warnings"].append({"kind": "injection_suspected", "severity": "warning"}),
        lambda s: s["provenance"].pop(),
        lambda s: s["frontmatter"].update(injection_risk="high"),
        lambda s: s["metrics"]["counts"].update(paragraphs=99),
    ],
    ids=["block type", "extra warning", "provenance entry dropped", "frontmatter field", "metrics count"],
)
def test_sidecar_difference_is_a_hard_failure(tmp_path: Path, edit: Any) -> None:
    fx, root = _copy_fixture(tmp_path, SMALL)
    sidecar = _load(fx.expected_sidecar)
    edit(sidecar)
    fx.expected_sidecar.write_text(json.dumps(sidecar, indent=2), encoding="utf-8")
    run = run_fixture(fx, root)
    assert not run.passed
    assert any(f.startswith("sidecar differs") for f in run.hard_failures), run.hard_failures


def test_timing_and_version_drift_is_ignored(tmp_path: Path) -> None:
    fx, root = _copy_fixture(tmp_path, SMALL)
    sidecar = _load(fx.expected_sidecar)
    sidecar["metrics"]["duration_seconds"] = 12.5
    sidecar["frontmatter"]["converter_version"] = "9.9.9"
    sidecar["frontmatter"]["ezmd_version"] = "9.9.9"
    fx.expected_sidecar.write_text(json.dumps(sidecar, indent=2), encoding="utf-8")
    assert run_fixture(fx, root).passed


def test_write_golden_writes_a_normalized_sidecar(tmp_path: Path) -> None:
    fx, _ = _copy_fixture(tmp_path, SMALL)
    sidecar_before = fx.expected_sidecar.read_text(encoding="utf-8")
    fx.expected_sidecar.unlink()
    write_golden(fx)
    # Byte-identical to the committed sidecar, whatever the installed ezmd version and however long it took.
    assert fx.expected_sidecar.read_text(encoding="utf-8") == sidecar_before
    assert "duration_seconds" not in _load(fx.expected_sidecar)["metrics"]


def test_bbox_coordinates_match_within_tolerance_only() -> None:
    from ezmd.testing.fixtures import BBOX_TOLERANCE_PT, _first_difference

    def side(x0: float, page: int = 1) -> dict[str, Any]:
        return {"provenance": [{"page": page, "bbox": {"x0": x0, "y0": 10.0}}]}

    # pdfium's Windows and Linux wheels differ by up to about 0.5 pt on the same glyphs.
    assert _first_difference(side(72.38), side(72.25)) is None
    assert _first_difference(side(344.32), side(343.8)) is None
    assert _first_difference(side(72.0), side(72.0 + BBOX_TOLERANCE_PT + 0.01)) is not None
    # The tolerance is for bbox coordinates only: other numbers stay exact.
    assert _first_difference(side(72.0, page=1), side(72.0, page=2)) is not None
    assert _first_difference({"metrics": {"x0": 1.0}}, {"metrics": {"x0": 1.1}}) is not None
