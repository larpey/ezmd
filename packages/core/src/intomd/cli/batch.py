"""`intomd batch`: convert a directory or glob into a mirrored output tree, idempotently.

Idempotency: before converting, each input's SHA-256 is compared with the previous run's record, taken
from the previous manifest line for that input (`sha256`, plus matching profile and format) or, failing
that, from the output's sidecar (`frontmatter.source_hash` and `profile`). A match with the output still
present is reported as `skipped`. Conversion goes through `intomd.convert`, in-process for one worker and
in a process pool otherwise.
"""

from __future__ import annotations

import glob as globlib
import hashlib
import json
import multiprocessing
import os
import time
from concurrent.futures import FIRST_COMPLETED, Future, ProcessPoolExecutor, wait
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any

import typer

from intomd.cli.config import SUPPORTED_FORMATS, ConfigError, check_format, check_profile
from intomd.cli.convert import build_options, emit_json, fail, load_config_or_exit
from intomd.cli.exitcodes import EXIT_FAIL, EXIT_INTERRUPTED, EXIT_OK, EXIT_PARTIAL, classify
from intomd.cli.output import EXTENSIONS, err_console, outcome_from_result, sidecar_path, write_outcome

__all__ = ["Job", "batch", "convert_job", "default_workers", "plan"]

_GLOB_CHARS = set("*?[")
_HASH_CHUNK = 1024 * 1024


def default_workers() -> int:
    """CPU count minus one, at least 1, at most 8 (Part 4 4.2.2)."""
    return max(1, min((os.cpu_count() or 2) - 1, 8))


@dataclass(frozen=True, slots=True)
class Job:
    """One input to convert. Plain data so it pickles into worker processes."""

    src: str
    out: str
    profile: str
    format: str
    options: dict[str, object]
    sidecar: bool
    sha256: str


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(_HASH_CHUNK):
            h.update(chunk)
    return h.hexdigest()


def _hidden(rel: Path) -> bool:
    return any(part.startswith(".") for part in rel.parts)


def _within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def discover(
    target: str, recursive: bool, out_dir: Path, manifest: Path, exclude: frozenset[str] = frozenset()
) -> tuple[Path, list[Path]]:
    """Input files (sorted) and the base directory the output tree mirrors. Dotfiles, the output tree,
    the manifest, sidecar files, and `exclude` (previous outputs, as resolved posix paths) are never inputs."""
    out_root = out_dir.resolve()
    if any(c in target for c in _GLOB_CHARS):
        parts = Path(target).parts
        fixed = list(parts[: next(i for i, p in enumerate(parts) if any(c in p for c in _GLOB_CHARS))])
        base = Path(*fixed) if fixed else Path(".")
        found = [Path(p) for p in globlib.glob(target, recursive=recursive)]
    else:
        root = Path(target)
        if root.is_file():
            return root.parent, [root]
        if not root.is_dir():
            raise FileNotFoundError(target)
        base = root
        found = list(root.rglob("*") if recursive else root.iterdir())
    files: list[Path] = []
    for p in found:
        if not p.is_file():
            continue
        resolved = p.resolve()
        rel = resolved.relative_to(base.resolve()) if _within(resolved, base.resolve()) else Path(p.name)
        if _hidden(rel) or resolved == manifest.resolve() or p.name.endswith(".intomd.json"):
            continue
        if resolved.as_posix() in exclude:
            continue
        if _within(resolved, out_root) and out_root != base.resolve():
            continue
        files.append(p)
    return base, sorted(files, key=lambda q: q.as_posix())


def _key(path: Path | str) -> str:
    return Path(path).resolve().as_posix()


def read_manifest(path: Path) -> dict[str, dict[str, Any]]:
    """Previous manifest lines keyed by resolved input path. A corrupt line is ignored."""
    prev: dict[str, dict[str, Any]] = {}
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return prev
    for line in lines:
        try:
            rec = json.loads(line)
        except ValueError:
            rec = None
        if isinstance(rec, dict) and isinstance(rec.get("path"), str):
            prev[_key(rec["path"])] = rec
    return prev


def _sidecar_matches(target: Path, sha: str, profile: str) -> bool:
    side = sidecar_path(target)
    if not side.is_file():
        return False
    try:
        data = json.loads(side.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    front = data.get("frontmatter") if isinstance(data, dict) else None
    if not isinstance(front, dict):
        return False
    return front.get("source_hash") == f"sha256:{sha}" and data.get("profile") == profile


def unchanged(job: Job, prev: dict[str, Any] | None) -> bool:
    target = Path(job.out)
    if not target.is_file():
        return False
    if (
        prev is not None
        and prev.get("sha256") == job.sha256
        and prev.get("profile") == job.profile
        and prev.get("format") == job.format
        and prev.get("status") in ("converted", "partial", "skipped")
    ):
        return True
    return job.format != "json" and _sidecar_matches(target, job.sha256, job.profile)


def plan(base: Path, files: list[Path], out_dir: Path, fmt: str) -> list[tuple[Path, Path]]:
    """(input, output) pairs mirroring the input tree. Inputs whose stems collide in one directory
    (a.txt and a.md) keep their full name (a.txt.md, a.md.md) so no output overwrites another."""
    ext = EXTENSIONS[fmt]
    rels = []
    for f in files:
        resolved = f.resolve()
        b = base.resolve()
        rels.append(resolved.relative_to(b) if _within(resolved, b) else Path(f.name))
    stems: dict[Path, int] = {}
    for r in rels:
        stems[r.parent / r.stem] = stems.get(r.parent / r.stem, 0) + 1
    pairs = []
    for f, r in zip(files, rels, strict=True):
        name = r.stem if stems[r.parent / r.stem] == 1 else r.name
        pairs.append((f, out_dir / r.parent / f"{name}{ext}"))
    return pairs


def convert_job(job: Job) -> dict[str, Any]:
    """Convert one input and write it; never raises (runs in worker processes). Returns a manifest record."""
    import intomd.library as lib

    start = time.perf_counter()
    record: dict[str, Any] = {
        "path": job.src,
        "out": job.out,
        "sha256": job.sha256,
        "profile": job.profile,
        "format": job.format,
    }
    try:
        result = lib.convert(job.src, profile=job.profile, options=lib.Options(**job.options))
        outcome = outcome_from_result(result, source=job.src, profile=job.profile, fmt=job.format)
        write_outcome(outcome, Path(job.out), sidecar=job.sidecar)
        record.update(
            status="partial" if outcome.status == "partial" else "converted",
            warnings=outcome.warnings,
            tokens=outcome.tokens,
        )
    except Exception as e:
        f = classify(e)
        record.update(
            status="failed",
            out=None,
            warnings=[{"kind": f.warning_kind, "severity": "error", "message": f.message}],
            tokens=0,
            error={"code": f.code, "message": f.message, "exit_code": f.exit_code},
        )
    record["seconds"] = round(time.perf_counter() - start, 3)
    return record


class _Run:
    """Collects records, streams them to the manifest, and drives the progress bar."""

    def __init__(self, manifest: Path, show: bool, total: int) -> None:
        manifest.parent.mkdir(parents=True, exist_ok=True)
        self.fh = manifest.open("w", encoding="utf-8", newline="\n")
        self.records: list[dict[str, Any]] = []
        self.bar: Any = None
        self.task: Any = None
        if show and total and err_console().is_terminal:
            from rich.progress import BarColumn, MofNCompleteColumn, Progress, TextColumn, TimeElapsedColumn

            cols = (TextColumn("Converting"), BarColumn(), MofNCompleteColumn(), TimeElapsedColumn())
            self.bar = Progress(*cols, console=err_console(), transient=True)
            self.bar.start()
            self.task = self.bar.add_task("batch", total=total)

    def add(self, rec: dict[str, Any], advance: bool = True) -> None:
        self.records.append(rec)
        self.fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        self.fh.flush()
        if advance and self.bar is not None:
            self.bar.advance(self.task)

    def close(self) -> None:
        if self.bar is not None:
            self.bar.stop()
        self.fh.close()


def _execute(jobs: list[Job], workers: int, keep_going: bool, run: _Run) -> bool:
    """Run jobs; returns False when stopped early by a failure (without --continue-on-error)."""
    if workers <= 1 or len(jobs) <= 1:
        for i, job in enumerate(jobs):
            rec = convert_job(job)
            run.add(rec)
            if rec["status"] == "failed" and not keep_going:
                for rest in jobs[i + 1 :]:
                    run.add(_cancelled(rest), advance=False)
                return False
        return True
    # spawn, not fork: forking a process that already runs threads (Magika, tokenizers) can deadlock
    with ProcessPoolExecutor(max_workers=workers, mp_context=multiprocessing.get_context("spawn")) as pool:
        pending: dict[Future[dict[str, Any]], Job] = {pool.submit(convert_job, j): j for j in jobs}
        stopped = False
        while pending:
            done, _ = wait(pending, return_when=FIRST_COMPLETED)
            for fut in done:
                job = pending.pop(fut)
                if fut.cancelled():
                    run.add(_cancelled(job), advance=False)
                    continue
                rec = fut.result()
                run.add(rec)
                if rec["status"] == "failed" and not keep_going and not stopped:
                    stopped = True
                    for other in pending:
                        other.cancel()
        return not stopped


def _cancelled(job: Job) -> dict[str, Any]:
    return {"path": job.src, "status": "cancelled", "out": None, "sha256": job.sha256, "profile": job.profile,
            "format": job.format, "warnings": [], "seconds": 0.0, "tokens": 0}  # fmt: skip


def _summary(records: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"converted": 0, "skipped": 0, "failed": 0, "cancelled": 0}
    for r in records:
        status = "converted" if r["status"] == "partial" else str(r["status"])
        counts[status] = counts.get(status, 0) + 1
    counts["total_tokens"] = sum(int(r.get("tokens") or 0) for r in records)
    counts["total"] = len(records)
    return counts


def _print_table(summary: dict[str, int], records: list[dict[str, Any]], manifest: Path) -> None:
    from rich.table import Table

    con = err_console()
    for r in records:
        if r["status"] == "failed":
            con.print(f"FAIL {r['path']}: {r['error']['message']}", markup=False, highlight=False)
    t = Table("converted", "skipped", "failed", "total tokens", title="intomd batch")
    t.add_row(*(str(summary[k]) for k in ("converted", "skipped", "failed", "total_tokens")))
    con.print(t)
    con.print(f"manifest: {manifest}", markup=False, highlight=False)


def batch(
    inputs: Annotated[str, typer.Argument(help="Directory or glob (quote globs).")],
    out: Annotated[Path | None, typer.Option("--out", "-o", help="Output directory (mirrors the input tree).")] = None,
    recursive: Annotated[bool, typer.Option("--recursive", "-r", help="Descend into subdirectories.")] = False,
    workers: Annotated[int | None, typer.Option("--workers", "-w", min=1, help="Worker processes.")] = None,
    profile: Annotated[str | None, typer.Option("--profile", "-p", help="full | compact | rag | agent")] = None,
    fmt: Annotated[str | None, typer.Option("--format", "-f", help="md | txt | json")] = None,
    keep_going: Annotated[bool, typer.Option("--continue-on-error", help="Keep going after a failure.")] = False,
    manifest: Annotated[Path | None, typer.Option("--manifest", help="[default: <out>/manifest.jsonl]")] = None,
    sidecar: Annotated[bool | None, typer.Option("--sidecar/--no-sidecar", help="Write sidecars.")] = None,
    opt: Annotated[list[str] | None, typer.Option("--opt", help="key=value converter or profile option.")] = None,
    as_json: Annotated[bool, typer.Option("--json", help="Summary JSON on stdout.")] = False,
    quiet: Annotated[bool, typer.Option("--quiet", "-q", help="No progress or table on stderr.")] = False,
) -> None:
    """Convert many files; unchanged inputs are skipped on re-runs."""
    cfg = load_config_or_exit(as_json=as_json, quiet=quiet)
    try:
        chosen_fmt = check_format(fmt or cfg.format, "--format")
        if chosen_fmt not in SUPPORTED_FORMATS:
            raise ConfigError(f"--format {chosen_fmt} is not yet supported; use md, txt, or json")
        chosen_profile = check_profile(profile or cfg.profile or "full", "--profile")
        options = build_options(cfg, opt or [], None, None)
        import intomd.library as lib

        lib.Options(**options)  # validate once, before any work
        out_dir = out if out is not None else (Path(cfg.out_dir) if cfg.out_dir else None)
        if out_dir is None:
            raise ValueError("--out is required (or set defaults.out_dir in the config file)")
        manifest_path = manifest or out_dir / "manifest.jsonl"
        prev = read_manifest(manifest_path)
        outputs = frozenset(_key(r["out"]) for r in prev.values() if isinstance(r.get("out"), str))
        base, files = discover(inputs, recursive, out_dir, manifest_path, outputs)
    except FileNotFoundError as e:
        raise fail(f"no such file or directory: {inputs}", as_json=as_json, source=inputs) from e
    except ValueError as e:
        raise fail(str(e), as_json=as_json, source=inputs) from e
    write_sidecar = cfg.sidecar if sidecar is None else sidecar
    run = _Run(manifest_path, show=not quiet and not as_json, total=len(files))
    finished = True
    try:
        todo: list[Job] = []
        for src, target in plan(base, files, out_dir, chosen_fmt):
            job = Job(str(src), str(target), chosen_profile, chosen_fmt, options, write_sidecar, file_sha256(src))
            old = prev.get(_key(src))
            if unchanged(job, old):
                rec = {"path": job.src, "status": "skipped", "out": job.out, "sha256": job.sha256,
                       "profile": job.profile, "format": job.format,
                       "warnings": (old or {}).get("warnings", []), "seconds": 0.0,
                       "tokens": int((old or {}).get("tokens") or 0)}  # fmt: skip
                run.add(rec)
            else:
                todo.append(job)
        finished = _execute(todo, workers or default_workers(), keep_going, run)
    except KeyboardInterrupt:
        run.close()
        err_console().print("interrupted", markup=False)
        raise typer.Exit(EXIT_INTERRUPTED) from None
    run.close()
    summary = _summary(run.records)
    failed = summary["failed"] > 0
    code = EXIT_OK if not failed else (EXIT_PARTIAL if keep_going and finished else EXIT_FAIL)
    if as_json:
        emit_json({**summary, "exit_code": code, "manifest": str(manifest_path), "files": run.records})
    elif not quiet:
        _print_table(summary, run.records, manifest_path)
    raise typer.Exit(code)
