"""ezmd.testing.fixtures: discover, run, and score golden fixtures (docs/spec/part1.md 2.4, part4 4.14.2).

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
requires = ["docs"]               # optional extras the fixture needs; skipped when not installed
requires_modules = ["pyarrow"]    # optional importable modules the fixture needs; skipped when missing
requires_binaries = ["soffice"]   # optional executables on PATH the fixture needs; skipped when missing
must_contain = ["kept phrase"]    # optional; each must appear in the rendered Markdown (case-sensitive)
must_not_contain = ["payload"]    # optional; none may appear (case-insensitive; raw match too, for invisibles)
exact_numbers = false             # optional; only to turn the numeric-token invariant off, with a reason
exact_numbers_reason = "why the numbers legitimately vary"

[provenance]                       # required (part4 4.14.7)
origin = "self-generated"         # self-generated | public-domain | cc0 | cc-by
license = "CC0-1.0"
source = ""                       # URL when not self-generated
```

`fixtures/thresholds.toml` holds `default = 0.85` and `[converters]` per-id thresholds, plus an `[invariants]`
table (`exact_numbers = true`) that a family `thresholds.toml` may override.

A fixture passes when its score reaches the threshold AND it has no hard failure. Hard failures: a conversion
error, an unexpected error-severity warning, exceeding `max_seconds`, any `ezmd.testing.invariants` mismatch
against the golden (math, block counts, list nesting, table spans, links, images, frontmatter `warnings`,
`injection_risk` and `truncated`, and the numeric-token multiset when `exact_numbers` is on), a broken
`must_contain` or `must_not_contain` entry, or a sidecar that differs from `expected.sidecar.json`.

`must_contain` and `must_not_contain` are lists of TOML strings; write invisible characters as TOML escapes
(`"\\u200b"`, `"\\U000e0069"`). List every hidden or secret payload of the input in `must_not_contain`,
so a leak fails even when it barely moves the score.

Sidecars are compared exactly after `normalize_sidecar` (`metrics` timing removed, `frontmatter` versions
replaced by a placeholder), and `write_golden` writes them normalized.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
import time
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ezmd.inputs import InputRef
from ezmd.ir import ConversionResult
from ezmd.pipeline import convert_ref
from ezmd.registry import ConversionError, ConvertOptions, ExtraValue
from ezmd.testing.invariants import check as check_invariants
from ezmd.testing.invariants import check_text
from ezmd.testing.score import Score, parse, score

PINNED_TIME = "2026-01-01T00:00:00Z"
ALLOWED_ORIGINS = frozenset({"self-generated", "public-domain", "cc0", "cc-by"})
NORMALIZED = "<normalized>"
"""Placeholder for sidecar fields that change on every release (versions)."""
VOLATILE_TIMING = ("duration_seconds", "fetch_seconds")
"""`metrics` timing fields, removed from sidecars before they are written or compared."""
VOLATILE_VERSIONS = ("converter_version", "ezmd_version")
"""`frontmatter` version fields, replaced by NORMALIZED before sidecars are written or compared."""


EXTRA_PROBES: dict[str, str] = {"docs": "docling", "data": "pyarrow", "7z": "py7zr"}
"""Optional extra -> module whose presence means the extra is installed (`requires = [...]`)."""


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
    def skip_reason(self) -> str | None:
        """Why this fixture cannot run here (a required extra or module is missing), else None."""
        return missing_requirements(self.meta)

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


@dataclass(frozen=True, slots=True)
class Verdict:
    """The judgement of one rendering against a fixture's goldens."""

    score: Score
    threshold: float
    failures: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not self.failures and self.score.overall >= self.threshold


def _importable(module: str) -> bool:
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError):
        return False


def missing_requirements(meta: dict[str, Any]) -> str | None:
    """Skip reason for `requires` (extras, probed through EXTRA_PROBES), `requires_modules`, and
    `requires_binaries` (executables looked up on PATH)."""
    extras = meta.get("requires", [])
    modules = meta.get("requires_modules", [])
    binaries = meta.get("requires_binaries", [])
    if not all(isinstance(v, list) for v in (extras, modules, binaries)):
        return "meta.toml `requires`, `requires_modules` and `requires_binaries` must be lists of strings"
    for binary in binaries:
        if shutil.which(str(binary)) is None:
            return f"requires the {binary!r} executable on PATH"
    for extra in extras:
        probe = EXTRA_PROBES.get(str(extra))
        if probe is None:
            return f"requires unknown extra {extra!r} (no import probe is defined for it)"
        if not _importable(probe):
            return f"requires the {extra!r} extra (module {probe!r} is not installed)"
    for module in modules:
        if not _importable(str(module)):
            return f"requires module {module!r}, which is not installed"
    return None


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
    """Root `thresholds.toml` sets the default; each `fixtures/<family>/thresholds.toml` adds a
    `[converters]` table for that family's converter ids (D-0020). An id defined twice is an error."""
    data = tomllib.loads((root / "thresholds.toml").read_text(encoding="utf-8"))
    per = {k: float(v) for k, v in data.get("converters", {}).items()}
    for fam in sorted(root.glob("*/thresholds.toml")):
        extra = tomllib.loads(fam.read_text(encoding="utf-8")).get("converters", {})
        for k, v in extra.items():
            if k in per:
                raise FixtureError(f"threshold for {k} defined twice ({fam})")
            per[k] = float(v)
    return float(data.get("default", 0.85)), per


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


def exact_numbers_for(fx: Fixture, root: Path) -> bool:
    """`[invariants] exact_numbers` from the root thresholds.toml, overridden by the family's, then by meta.toml
    (turning it off there needs `exact_numbers_reason`)."""
    value = True
    for path in (root / "thresholds.toml", root / fx.path.parent.name / "thresholds.toml"):
        if path.exists():
            table = tomllib.loads(path.read_text(encoding="utf-8")).get("invariants", {})
            if "exact_numbers" in table:
                value = bool(table["exact_numbers"])
    if "exact_numbers" in fx.meta:
        own = fx.meta["exact_numbers"]
        if not isinstance(own, bool):
            raise FixtureError(f"{fx.id}: exact_numbers must be a boolean")
        if not own and not fx.meta.get("exact_numbers_reason"):
            raise FixtureError(f"{fx.id}: exact_numbers = false needs exact_numbers_reason")
        value = own
    return value


def _strings(fx: Fixture, key: str) -> list[str]:
    raw = fx.meta.get(key, [])
    if not isinstance(raw, list) or not all(isinstance(v, str) and v for v in raw):
        raise FixtureError(f"{fx.id}: {key} must be a list of non-empty strings")
    return [str(v) for v in raw]


def normalize_sidecar(sidecar: dict[str, Any]) -> dict[str, Any]:
    """A copy of `sidecar` without volatile fields: `metrics` timing removed, `frontmatter` versions set to
    NORMALIZED. Everything else is kept as is."""
    out = dict(sidecar)
    metrics = out.get("metrics")
    if isinstance(metrics, dict):
        out["metrics"] = {k: v for k, v in metrics.items() if k not in VOLATILE_TIMING}
    fm = out.get("frontmatter")
    if isinstance(fm, dict):
        out["frontmatter"] = {k: (NORMALIZED if k in VOLATILE_VERSIONS else v) for k, v in fm.items()}
    return out


def _first_difference(expected: object, actual: object, path: str = "$") -> str | None:
    if isinstance(expected, dict) and isinstance(actual, dict):
        for key in sorted(set(expected) | set(actual), key=str):
            if key not in actual:
                return f"{path}.{key} missing"
            if key not in expected:
                return f"{path}.{key} unexpected"
            found = _first_difference(expected[key], actual[key], f"{path}.{key}")
            if found:
                return found
        return None
    if isinstance(expected, list) and isinstance(actual, list):
        for i, (e, a) in enumerate(zip(expected, actual, strict=False)):
            found = _first_difference(e, a, f"{path}[{i}]")
            if found:
                return found
        if len(expected) != len(actual):
            return f"{path} has {len(actual)} items, expected {len(expected)}"
        return None
    if _within_bbox_tolerance(path, expected, actual):
        return None
    if expected != actual:
        return f"{path}: expected {expected!r}, got {actual!r}"
    return None


# PDF engines report glyph boxes with small per-platform float differences: pdfium's Windows and Linux
# wheels differ by about 0.1 pt on a left edge and up to about 0.5 pt on a right edge (glyph advances add up
# along a line). Provenance boxes locate text on a page, so coordinates match within 1 pt (0.35 mm);
# everything else in the sidecar is exact.
BBOX_TOLERANCE_PT = 1.0


def _within_bbox_tolerance(path: str, expected: object, actual: object) -> bool:
    if ".bbox." not in path:
        return False
    numeric = (int, float)
    if not isinstance(expected, numeric) or not isinstance(actual, numeric):
        return False
    if isinstance(expected, bool) or isinstance(actual, bool):
        return False
    return abs(float(expected) - float(actual)) <= BBOX_TOLERANCE_PT


def _jsonable(sidecar: dict[str, Any]) -> dict[str, Any]:
    """The sidecar as it reads back from disk (tuples become lists, keys become strings)."""
    loaded: dict[str, Any] = json.loads(json.dumps(sidecar, ensure_ascii=False))
    return loaded


def compare_sidecar(fx: Fixture, actual: dict[str, Any]) -> list[str]:
    """Exact comparison of the normalized sidecar with the normalized `expected.sidecar.json`."""
    if not fx.expected_sidecar.exists():
        return ["expected.sidecar.json missing (run ezmd-golden --write, then get Skeptic review)"]
    expected = normalize_sidecar(json.loads(fx.expected_sidecar.read_text(encoding="utf-8")))
    diff = _first_difference(expected, normalize_sidecar(_jsonable(actual)))
    return [f"sidecar differs from expected.sidecar.json at {diff}"] if diff else []


def evaluate(fx: Fixture, root: Path, markdown: str, sidecar: dict[str, Any] | None = None) -> Verdict:
    """Judge a rendering against the fixture's goldens: score, invariants, the must lists and, when `sidecar`
    is given, the sidecar. The Markdown golden must exist."""
    expected = fx.expected_md.read_text(encoding="utf-8")
    failures = check_invariants(expected, markdown, exact_numbers=exact_numbers_for(fx, root))
    failures += check_text(
        markdown, must_contain=_strings(fx, "must_contain"), must_not_contain=_strings(fx, "must_not_contain")
    )
    if sidecar is not None:
        failures += compare_sidecar(fx, sidecar)
    return Verdict(score=score(expected, markdown), threshold=threshold_for(fx, root), failures=tuple(failures))


def convert_fixture(fx: Fixture) -> ConversionResult:
    """Convert a fixture input. `[input] url = "https://..."` in meta.toml makes the input behave like a
    fetched URL (frozen body, `ref.url` and display set to the URL) so web converters can resolve links;
    `[input] options = {...}` passes ConvertOptions fields (`extra.*` keys go to options.extra)."""
    ref = InputRef.from_path(fx.input_path)
    ref.display = fx.input_path.name
    spec = fx.meta.get("input", {})
    url = spec.get("url") if isinstance(spec, dict) else None
    if isinstance(url, str) and url:
        ref.url = url
        ref.display = url
    options = _options(spec.get("options", {}) if isinstance(spec, dict) else {})
    try:
        return convert_ref(ref, options, converter_id=fx.converter)
    finally:
        ref.cleanup()


def _options(raw: object) -> ConvertOptions:
    if not isinstance(raw, dict):
        raise FixtureError("[input] options must be a table")
    from ezmd.cli.options import split_options

    flat: dict[str, ExtraValue] = {str(k): v for k, v in raw.items() if isinstance(v, str | int | float | bool)}
    if len(flat) != len(raw):
        raise FixtureError('[input] options values must be scalars (use dotted keys like "extra.x")')
    options, profile = split_options(flat)
    if profile:
        raise FixtureError(f"unknown [input] options: {sorted(profile)}")
    return options


def render_full(result: ConversionResult) -> tuple[str, dict[str, object] | None]:
    from ezmd.render import render

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
        run.hard_failures.append("expected.full.md missing (run ezmd-golden --write, then get Skeptic review)")
        return run
    expected = fx.expected_md.read_text(encoding="utf-8")
    if not result.document.blocks and _has_blocks(expected):
        run.hard_failures.append("document has zero blocks but the golden has content")
    verdict = evaluate(fx, root, run.markdown, run.sidecar or {})
    run.score = verdict.score
    run.hard_failures.extend(verdict.failures)
    return run


def _has_blocks(md: str) -> bool:
    p = parse(md)
    return bool(p.headings or p.paragraphs or p.tables or sum(p.counts.values()))


def write_golden(fx: Fixture) -> tuple[Path, Path]:
    result = convert_fixture(fx)
    md, sidecar = render_full(result)
    fx.expected_md.write_text(md, encoding="utf-8", newline="\n")
    fx.expected_sidecar.write_text(
        json.dumps(normalize_sidecar(_jsonable(sidecar or {})), indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return fx.expected_md, fx.expected_sidecar
