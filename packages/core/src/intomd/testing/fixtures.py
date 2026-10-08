"""intomd.testing.fixtures: discover, run, and score golden fixtures (docs/spec/part1.md 2.4, part4 4.14.2).

Layout: `fixtures/<family>/<name>/` with `input.<ext>` (or `input.url` plus a frozen `input.html`),
`expected.full.md`, `expected.sidecar.json`, and `meta.toml`:

```toml
converter = "text.plain"          # required: the converter id this fixture exercises
threshold = 0.9                   # optional; only lower than the converter threshold, with threshold_reason
threshold_reason = "deliberately broken scan"
max_seconds = 30                  # hard failure when exceeded
hand_edited = false               # true when the golden was hand-edited after review
notes = "what this fixture tests"
expected_errors = []              # error-severity warning codes that are expected (others are hard failures)

[provenance]                       # required (part4 4.14.7)
origin = "self-generated"         # self-generated | public-domain | cc0 | cc-by
license = "CC0-1.0"
source = ""                       # URL when not self-generated
```

`fixtures/thresholds.toml` holds `default = 0.85` and `[converters]` per-id thresholds.
"""

from __future__ import annotations

import json
import time
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from intomd.inputs import InputRef
from intomd.ir import ConversionResult
from intomd.pipeline import convert_ref
from intomd.registry import ConversionError, ConvertOptions
from intomd.testing.score import Score, parse, score

PINNED_TIME = "2026-01-01T00:00:00Z"
ALLOWED_ORIGINS = frozenset({"self-generated", "public-domain", "cc0", "cc-by"})


class FixtureError(Exception):
    """A fixture is malformed (bad meta.toml, missing input)."""


@dataclass(slots=True)
class Fixture:
    path: Path
    meta: dict[str, Any]

    @property
    def id(self) -> str:
        return f"{self.path.parent.name}/{self.path.name}"

    @property
    def converter(self) -> str:
        return str(self.meta["converter"])

    @property
    def input_path(self) -> Path:
        inputs = sorted(p for p in self.path.iterdir() if p.name.startswith("input.") and p.suffix != ".url")
        if not inputs:
            raise FixtureError(f"{self.id}: no input.* file")
        return inputs[0]

    @property
    def expected_md(self) -> Path:
        return self.path / "expected.full.md"

    @property
    def expected_sidecar(self) -> Path:
        return self.path / "expected.sidecar.json"


@dataclass(slots=True)
class FixtureRun:
    fixture: Fixture
    threshold: float
    score: Score | None = None
    markdown: str = ""
    sidecar: dict[str, object] | None = None
    seconds: float = 0.0
    hard_failures: list[str] = field(default_factory=list)
    result: ConversionResult | None = None

    @property
    def passed(self) -> bool:
        return not self.hard_failures and self.score is not None and self.score.overall >= self.threshold


def fixtures_root(start: Path | None = None) -> Path:
    here = (start or Path.cwd()).resolve()
    for d in (here, *here.parents):
        if (d / "fixtures" / "thresholds.toml").exists():
            return d / "fixtures"
    raise FixtureError("could not find fixtures/thresholds.toml above the current directory")


def load_meta(path: Path) -> dict[str, Any]:
    meta = tomllib.loads((path / "meta.toml").read_text(encoding="utf-8"))
    if "converter" not in meta:
        raise FixtureError(f"{path}: meta.toml lacks `converter`")
    prov = meta.get("provenance")
    if not isinstance(prov, dict) or prov.get("origin") not in ALLOWED_ORIGINS or not prov.get("license"):
        raise FixtureError(f"{path}: meta.toml needs [provenance] origin in {sorted(ALLOWED_ORIGINS)} and a license")
    return meta


def discover(root: Path) -> list[Fixture]:
    return [Fixture(path=m.parent, meta=load_meta(m.parent)) for m in sorted(root.glob("*/*/meta.toml"))]


def thresholds(root: Path) -> tuple[float, dict[str, float]]:
    data = tomllib.loads((root / "thresholds.toml").read_text(encoding="utf-8"))
    return float(data.get("default", 0.85)), {k: float(v) for k, v in data.get("converters", {}).items()}


def threshold_for(fx: Fixture, root: Path) -> float:
    default, per = thresholds(root)
    base = per.get(fx.converter, default)
    if "threshold" in fx.meta:
        t = float(fx.meta["threshold"])
        if t > base:
            raise FixtureError(f"{fx.id}: per-fixture threshold may only lower the converter threshold")
        if t < base and not fx.meta.get("threshold_reason"):
            raise FixtureError(f"{fx.id}: a lowered threshold needs threshold_reason")
        return t
    return base


def convert_fixture(fx: Fixture) -> ConversionResult:
    ref = InputRef.from_path(fx.input_path)
    ref.display = fx.input_path.name
    try:
        return convert_ref(ref, ConvertOptions(), converter_id=fx.converter)
    finally:
        ref.cleanup()


def render_full(result: ConversionResult) -> tuple[str, dict[str, object] | None]:
    from intomd.render import render

    out = render(result, "full", "md", converted_at=PINNED_TIME, fetched_at=PINNED_TIME)
    return out.markdown, out.sidecar


def run_fixture(fx: Fixture, root: Path) -> FixtureRun:
    run = FixtureRun(fixture=fx, threshold=threshold_for(fx, root))
    t0 = time.monotonic()
    try:
        result = convert_fixture(fx)
    except ConversionError as e:
        run.hard_failures.append(f"conversion failed: {e}")
        return run
    except Exception as e:
        run.hard_failures.append(f"exception: {type(e).__name__}: {e}")
        return run
    run.seconds = time.monotonic() - t0
    run.result = result
    run.markdown, run.sidecar = render_full(result)
    max_seconds = float(fx.meta.get("max_seconds", 120))
    if run.seconds > max_seconds:
        run.hard_failures.append(f"runtime {run.seconds:.1f}s exceeds max_seconds {max_seconds}")
    expected_errors = set(fx.meta.get("expected_errors", []))
    for w in result.all_warnings:
        if w.severity == "error" and str(w.kind) not in expected_errors:
            run.hard_failures.append(f"unexpected error warning {w.kind}: {w.message}")
    if not fx.expected_md.exists():
        run.hard_failures.append("expected.full.md missing (run intomd-golden --write, then get Skeptic review)")
        return run
    expected = fx.expected_md.read_text(encoding="utf-8")
    if not result.document.blocks and _has_blocks(expected):
        run.hard_failures.append("document has zero blocks but the golden has content")
    run.score = score(expected, run.markdown)
    return run


def _has_blocks(md: str) -> bool:
    p = parse(md)
    return bool(p.headings or p.paragraphs or p.tables or sum(p.counts.values()))


def write_golden(fx: Fixture) -> tuple[Path, Path]:
    result = convert_fixture(fx)
    md, sidecar = render_full(result)
    fx.expected_md.write_text(md, encoding="utf-8", newline="\n")
    fx.expected_sidecar.write_text(
        json.dumps(sidecar or {}, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n"
    )
    return fx.expected_md, fx.expected_sidecar
