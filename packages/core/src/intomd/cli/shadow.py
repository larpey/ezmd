"""`intomd shadow-run`: convert inputs with every engine that can handle them and compare the outputs.

For each input the registry is asked which converters claim it: the registry's own order first (chain
members and specialists, as `intomd convert` would try them), then every other available converter whose
`can_handle` is above zero. Unavailable converters (missing extra or binary) are listed with their reason
and skipped. Each engine runs through `intomd.convert` with the converter forced, so there is still one
conversion path. The reference engine is the first engine in the registry's order that succeeded, which is
the one an automatic conversion would have used. Every other output is scored against it with the golden
scorer (`intomd.testing.score`): text similarity and structure similarity; all pairs go in `--json`.

Directories are walked recursively. A directory tree that holds fixtures (`meta.toml`) contributes only the
fixtures' `input.*` files, so `intomd shadow-run fixtures` compares engines on the golden corpus. The exit
code is 0 whatever the engines did; only usage errors (unknown profile or engine, missing path) exit 2.
"""

from __future__ import annotations

import glob as globlib
import logging
import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Annotated, Any

import typer

from intomd.cli.config import ConfigError, check_profile
from intomd.cli.convert import emit_json, fail
from intomd.cli.exitcodes import EXIT_INTERRUPTED, EXIT_OK, classify
from intomd.cli.output import err_console
from intomd.registry import Converter, ConverterRegistry, ConvertOptions, default_registry

__all__ = ["EngineRun", "FileReport", "discover", "engine_plan", "select_engines", "shadow_file", "shadow_run"]

log = logging.getLogger(__name__)
_GLOB_CHARS = set("*?[")
DEFAULT_TIMEOUT = 600.0
_PIPE_WIDTH = 120


@dataclass(frozen=True, slots=True)
class EngineRun:
    """One engine's result on one input. Similarities are against the file's reference engine."""

    engine: str
    status: str
    """"ok" or "failed"."""
    seconds: float
    blocks: int = 0
    headings: int = 0
    tables: int = 0
    warnings: int = 0
    error: str | None = None
    markdown: str = ""
    text_similarity: float | None = None
    structure_similarity: float | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "engine": self.engine,
            "status": self.status,
            "seconds": round(self.seconds, 3),
            "blocks": self.blocks,
            "headings": self.headings,
            "tables": self.tables,
            "warnings": self.warnings,
            "error": self.error,
            "text_similarity": _round(self.text_similarity),
            "structure_similarity": _round(self.structure_similarity),
        }


@dataclass(frozen=True, slots=True)
class FileReport:
    path: str
    mime: str | None
    reference: str | None
    runs: tuple[EngineRun, ...] = ()
    skipped: tuple[tuple[str, str], ...] = ()
    """(converter id, reason) for converters that would claim the input but are not installed."""
    pairs: tuple[dict[str, object], ...] = ()
    error: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "mime": self.mime,
            "reference": self.reference,
            "engines": [r.as_dict() for r in self.runs],
            "skipped": [{"engine": e, "reason": why} for e, why in self.skipped],
            "pairs": list(self.pairs),
            "error": self.error,
        }


def _round(v: float | None) -> float | None:
    return None if v is None else round(v, 4)


def _fixture_inputs(root: Path) -> list[Path] | None:
    """Inputs of every fixture under `root`, or None when `root` holds no fixtures."""
    from intomd.testing.fixtures import Fixture, FixtureError

    dirs = sorted({m.parent for m in root.rglob("meta.toml")})
    if not dirs:
        return None
    found: list[Path] = []
    for d in dirs:
        try:
            found.append(Fixture(path=d, meta={}).input_path)
        except FixtureError as e:
            log.info("shadow-run skips fixture without input: %s", e)
    return found


def _walk(root: Path) -> list[Path]:
    fixtures = _fixture_inputs(root)
    if fixtures is not None:
        return fixtures
    out = []
    for p in root.rglob("*"):
        rel = p.relative_to(root)
        if p.is_file() and not any(part.startswith(".") for part in rel.parts) and not p.name.endswith(".intomd.json"):
            out.append(p)
    return out


def discover(targets: list[str]) -> list[Path]:
    """Files named by paths, directories (recursive, fixture-aware), and globs; sorted and deduplicated.
    Raises FileNotFoundError naming the first target that matches nothing."""
    files: dict[str, Path] = {}
    for target in targets:
        if any(c in target for c in _GLOB_CHARS):
            matched = [Path(p) for p in globlib.glob(target, recursive=True)]
            found = [f for m in matched for f in ([m] if m.is_file() else _walk(m) if m.is_dir() else [])]
        elif Path(target).is_file():
            found = [Path(target)]
        elif Path(target).is_dir():
            found = _walk(Path(target))
        else:
            found = []
        if not found:
            raise FileNotFoundError(target)
        for f in found:
            files.setdefault(f.resolve().as_posix(), f)
    return sorted(files.values(), key=lambda q: q.as_posix())


def _confidence(conv: Converter, ref: Any) -> float:
    try:
        return float(conv.can_handle(ref))
    except Exception:
        return 0.0


def engine_plan(ref: Any, reg: ConverterRegistry, options: ConvertOptions) -> tuple[list[str], list[tuple[str, str]]]:
    """Converter ids that can handle `ref` (registry order first, then the rest by confidence) and
    (id, reason) pairs for unavailable converters that would claim it."""
    ordered = [c.id for _, c in reg.candidates(ref, options)]
    rest = [
        (score, c)
        for c in reg.available()
        if c.id not in ordered and (options.experimental or not c.experimental) and (score := _confidence(c, ref)) > 0
    ]
    rest.sort(key=lambda sc: (-sc[0], -sc[1].priority, sc[1].id))
    skipped = [(u.id, u.reason) for u in reg.unavailable_for(ref)]
    return [*ordered, *(c.id for _, c in rest)], skipped


def select_engines(spec: str | None, known: list[str]) -> frozenset[str] | None:
    """`--engines a,b`: each token is a converter id or its last segment (`plain` for `text.plain`).
    Raises ValueError for a token that names no registered converter."""
    if not spec:
        return None
    chosen: set[str] = set()
    for token in (t.strip() for t in spec.split(",")):
        if not token:
            continue
        hits = [k for k in known if k == token or k.split(".")[-1] == token]
        if not hits:
            raise ValueError(f"--engines: no converter matches {token!r}; see `intomd capabilities`")
        chosen.update(hits)
    if not chosen:
        raise ValueError("--engines needs at least one converter id")
    return frozenset(chosen)


def _run_engine(path: Path, engine: str, profile: str, timeout: float) -> EngineRun:
    import intomd.library as lib

    start = time.perf_counter()
    try:
        result = lib.convert(path, profile=profile, options=lib.Options(converter=engine, max_seconds=timeout))
        markdown = result.markdown
        warnings = len(result.warnings)
    except KeyboardInterrupt:
        raise
    except Exception as e:
        return EngineRun(engine=engine, status="failed", seconds=time.perf_counter() - start, error=classify(e).message)
    doc = result.document
    counts = doc.counts(include_children=True)
    return EngineRun(
        engine=engine,
        status="ok",
        seconds=time.perf_counter() - start,
        blocks=len(doc.blocks) + sum(len(c.blocks) for c in doc.children),
        headings=counts.headings,
        tables=counts.tables,
        warnings=warnings,
        markdown=markdown,
    )


def _compare(runs: list[EngineRun]) -> tuple[str | None, list[EngineRun], list[dict[str, object]]]:
    from intomd.testing.score import score

    ok = [r for r in runs if r.status == "ok"]
    if not ok:
        return None, runs, []
    reference = ok[0]
    scored = []
    for r in runs:
        if r.status != "ok":
            scored.append(r)
            continue
        s = score(reference.markdown, r.markdown)
        scored.append(replace(r, text_similarity=s.text, structure_similarity=s.structure))
    pairs: list[dict[str, object]] = []
    for i, a in enumerate(ok):
        for b in ok[i + 1 :]:
            pairs.append({"a": a.engine, "b": b.engine, **score(a.markdown, b.markdown).as_dict()})
    return reference.engine, scored, pairs


def shadow_file(
    path: Path, *, profile: str = "full", timeout: float = DEFAULT_TIMEOUT, engines: frozenset[str] | None = None
) -> FileReport:
    """Run every engine that can handle `path` (restricted to `engines` when given) and compare them."""
    import intomd.library as lib
    from intomd.detect import detect
    from intomd.inputs import InputRef

    reg = default_registry()
    opts = lib.Options(max_seconds=timeout)
    ref = InputRef.from_path(path, max_bytes=opts.max_bytes)
    try:
        detect(ref)
        mime = ref.detected.mime if ref.detected else None
        plan, skipped = engine_plan(ref, reg, opts.to_convert_options())
    except Exception as e:
        return FileReport(path=path.as_posix(), mime=None, reference=None, error=classify(e).message)
    finally:
        ref.cleanup()
    if engines is not None:
        plan = [e for e in plan if e in engines]
        skipped = [(e, why) for e, why in skipped if e in engines]
    if not plan:
        return FileReport(
            path=path.as_posix(),
            mime=mime,
            reference=None,
            skipped=tuple(skipped),
            error="no engine can handle this file",
        )
    runs = [_run_engine(path, e, profile, timeout) for e in plan]
    reference, scored, pairs = _compare(runs)
    return FileReport(
        path=path.as_posix(),
        mime=mime,
        reference=reference,
        runs=tuple(scored),
        skipped=tuple(skipped),
        pairs=tuple(pairs),
    )


@dataclass(slots=True)
class _Acc:
    files: int = 0
    ok: int = 0
    failed: int = 0
    reference: int = 0
    seconds: list[float] = field(default_factory=list)
    text: list[float] = field(default_factory=list)
    structure: list[float] = field(default_factory=list)


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 4) if values else None


def summarize(reports: list[FileReport]) -> dict[str, object]:
    """Per-engine totals. Mean similarities leave out files where the engine was the reference."""
    acc: dict[str, _Acc] = {}
    for rep in reports:
        for r in rep.runs:
            a = acc.setdefault(r.engine, _Acc())
            a.files += 1
            a.seconds.append(r.seconds)
            if r.status != "ok":
                a.failed += 1
                continue
            a.ok += 1
            if r.engine == rep.reference:
                a.reference += 1
            elif r.text_similarity is not None and r.structure_similarity is not None:
                a.text.append(r.text_similarity)
                a.structure.append(r.structure_similarity)
    engines = [
        {
            "engine": name,
            "files": a.files,
            "ok": a.ok,
            "failed": a.failed,
            "reference": a.reference,
            "mean_seconds": _mean(a.seconds),
            "mean_text_similarity": _mean(a.text),
            "mean_structure_similarity": _mean(a.structure),
        }
        for name, a in sorted(acc.items())
    ]
    return {
        "files": len(reports),
        "files_compared": sum(1 for r in reports if sum(x.status == "ok" for x in r.runs) > 1),
        "files_failed": sum(1 for r in reports if r.reference is None),
        "engines": engines,
    }


def _fmt(v: object, digits: int = 3) -> str:
    return "-" if v is None else f"{v:.{digits}f}" if isinstance(v, float) else str(v)


def _print_notes(con: Any, rep: FileReport) -> None:
    for r in rep.runs:
        if r.error:
            con.print(f"  {r.engine} failed: {r.error}", markup=False)
    for engine, why in rep.skipped:
        con.print(f"  skipped {engine}: {why}", markup=False)
    if rep.error:
        con.print(f"  {rep.error}", markup=False)


def print_tables(reports: list[FileReport], summary: dict[str, object]) -> None:
    from rich.console import Console
    from rich.table import Table

    con = Console(highlight=False, soft_wrap=False)
    if not con.is_terminal:
        con = Console(highlight=False, soft_wrap=False, width=_PIPE_WIDTH)
    for rep in reports:
        if not rep.runs:
            con.print(f"{rep.path} ({rep.mime or 'unknown'})", markup=False)
            _print_notes(con, rep)
            continue
        t = Table(title=f"{rep.path} ({rep.mime or 'unknown'})", title_justify="left")
        for col in ("engine", "status", "time s", "blocks", "headings", "tables", "warnings", "text", "structure"):
            t.add_column(col, justify="left" if col in ("engine", "status") else "right", no_wrap=True)
        for r in rep.runs:
            name = f"{r.engine} *" if r.engine == rep.reference else r.engine
            t.add_row(name, r.status, f"{r.seconds:.2f}", str(r.blocks), str(r.headings), str(r.tables),
                      str(r.warnings), _fmt(r.text_similarity), _fmt(r.structure_similarity))  # fmt: skip
        con.print(t)
        _print_notes(con, rep)
    s = Table(title=f"summary: {summary['files']} files, {summary['files_compared']} with 2+ engines",
              title_justify="left")  # fmt: skip
    for col in ("engine", "files", "ok", "failed", "reference", "mean s", "mean text", "mean structure"):
        s.add_column(col, justify="left" if col == "engine" else "right", no_wrap=True)
    rows = summary["engines"]
    for e in rows if isinstance(rows, list) else []:
        s.add_row(str(e["engine"]), str(e["files"]), str(e["ok"]), str(e["failed"]), str(e["reference"]),
                  _fmt(e["mean_seconds"], 2), _fmt(e["mean_text_similarity"]),
                  _fmt(e["mean_structure_similarity"]))  # fmt: skip
    con.print(s)
    con.print("* reference engine (the registry's choice); text and structure are similarity to it", markup=False)


def shadow_run(
    inputs: Annotated[list[str], typer.Argument(help="Files, directories, or globs (quote globs).")],
    engines: Annotated[
        str | None, typer.Option("--engines", "-e", help="Only these converters (comma-separated ids).")
    ] = None,
    profile: Annotated[str, typer.Option("--profile", "-p", help="full | compact | rag | agent")] = "full",
    timeout: Annotated[float, typer.Option("--timeout", help="Per-engine time limit in seconds.")] = DEFAULT_TIMEOUT,
    as_json: Annotated[bool, typer.Option("--json", help="One JSON object on stdout.")] = False,
) -> None:
    """Convert inputs with every engine that handles them and compare the outputs."""
    try:
        chosen_profile = check_profile(profile, "--profile")
        if timeout <= 0:
            raise ConfigError("--timeout must be greater than 0")
        known = [r.converter.id for r in default_registry().registrations()]
        selected = select_engines(engines, known)
        files = discover(inputs)
    except FileNotFoundError as e:
        raise fail(f"no such file, directory, or glob match: {e.args[0]}", as_json=as_json) from e
    except ValueError as e:
        raise fail(str(e), as_json=as_json) from e
    reports: list[FileReport] = []
    try:
        for path in files:
            if not as_json and err_console().is_terminal:
                err_console().print(f"shadow-run {path.as_posix()}", markup=False, highlight=False)
            reports.append(shadow_file(path, profile=chosen_profile, timeout=timeout, engines=selected))
    except KeyboardInterrupt:
        err_console().print("interrupted", markup=False)
        raise typer.Exit(EXIT_INTERRUPTED) from None
    summary = summarize(reports)
    if as_json:
        emit_json({"profile": chosen_profile, "exit_code": EXIT_OK, "summary": summary,
                   "files": [r.as_dict() for r in reports]})  # fmt: skip
    else:
        print_tables(reports, summary)
    raise typer.Exit(EXIT_OK)
