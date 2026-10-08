"""Output handling shared by `convert` and `batch`: the rendered outcome, file writing, warnings, progress.

Human output (progress, warnings, tables) goes to stderr; stdout carries only the converted document or,
with `--json`, one JSON object.
"""

from __future__ import annotations

import json
import re
import sys
import unicodedata
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rich.console import Console

__all__ = [
    "EXTENSIONS",
    "Outcome",
    "ProgressSink",
    "err_console",
    "failure_payload",
    "outcome_from_result",
    "print_warnings",
    "progress_display",
    "safe_stem",
    "sidecar_path",
    "write_outcome",
]

EXTENSIONS = {"md": ".md", "txt": ".txt", "json": ".json"}
_UNSAFE = re.compile(r"[^\w.\- ]+", re.UNICODE)
_RESERVED = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(10)), *(f"lpt{i}" for i in range(10))}
_STAGE_LABELS = {
    "queued": "Queued",
    "fetching": "Fetching",
    "converting": "Converting",
    "rendering": "Rendering",
    "done": "Done",
}
"""Labels for the job states the web UI and the SSE stream use (Part 3)."""


def err_console() -> Console:
    return Console(stderr=True, highlight=False, soft_wrap=True)


@dataclass(slots=True)
class Outcome:
    """One rendered conversion, local or remote, in the requested profile and format."""

    source: str
    text: str
    """The output file content (Markdown, plain text, or the JSON payload text)."""
    profile: str
    format: str
    frontmatter: dict[str, object] = field(default_factory=dict)
    sidecar: dict[str, object] | None = None
    warnings: list[dict[str, object]] = field(default_factory=list)
    tokens: int = 0
    truncated: bool = False
    stem: str = "output"

    @property
    def status(self) -> str:
        return "partial" if any(w.get("severity") == "error" for w in self.warnings) else "ok"

    @property
    def title(self) -> str | None:
        t = self.frontmatter.get("title")
        return str(t) if t else None


def _stem_of(source: str) -> str:
    tail = source.split("?", 1)[0].split("#", 1)[0].rstrip("/")
    return safe_stem(Path(tail).stem) or "output"


def outcome_from_result(result: Any, *, source: str, profile: str, fmt: str) -> Outcome:
    """Build an Outcome from an `intomd.Result` (the library is the only conversion path)."""
    rendered = result.render(profile, fmt)
    return Outcome(
        source=source,
        text=str(rendered.markdown),
        profile=profile,
        format=fmt,
        frontmatter=dict(rendered.frontmatter),
        sidecar=dict(rendered.sidecar) if rendered.sidecar is not None else None,
        warnings=[w.model_dump(mode="json") for w in rendered.warnings],
        tokens=int(rendered.tokens),
        truncated=bool(rendered.truncated),
        stem=_stem_of(source),
    )


def safe_stem(name: str, limit: int = 80) -> str:
    """A filesystem-safe file stem: no separators, control characters, reserved names, or leading dots."""
    norm = unicodedata.normalize("NFKC", name)
    cleaned = _UNSAFE.sub("-", norm).strip(" .-")
    cleaned = re.sub(r"[\s-]{2,}", "-", cleaned)[:limit].strip(" .-")
    if not cleaned or cleaned.lower() in _RESERVED:
        return ""
    return cleaned


def sidecar_path(target: Path) -> Path:
    return target.with_name(target.stem + ".intomd.json")


def _is_dir_target(out: Path) -> bool:
    return out.is_dir() or str(out).endswith(("/", "\\"))


def write_outcome(outcome: Outcome, out: Path, *, sidecar: bool, stem: str | None = None) -> Path:
    """Write the output to `out` (a file, or a directory to write `<title>.<ext>` into) and, when `sidecar`
    is true, the profile produced a sidecar, and the format is not json (which embeds it), the sidecar
    beside it. Returns the path written."""
    ext = EXTENSIONS.get(outcome.format, ".md")
    if _is_dir_target(out):
        name = stem or safe_stem(outcome.title or "") or outcome.stem
        target = out / f"{name}{ext}"
    else:
        target = out
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(outcome.text, encoding="utf-8", newline="\n")
    if sidecar and outcome.sidecar is not None and outcome.format != "json":
        text = json.dumps(outcome.sidecar, indent=2, ensure_ascii=False) + "\n"
        sidecar_path(target).write_text(text, encoding="utf-8", newline="\n")
    return target


def print_warnings(warnings: list[dict[str, object]], console: Console | None = None) -> None:
    """Every warning, verbatim, as `WARN [code] message` (Part 4 4.0 rule 2)."""
    con = console or err_console()
    for w in warnings:
        con.print(f"WARN [{w.get('kind')}] {w.get('message', '')}", markup=False, highlight=False)


def failure_payload(source: str, code: str, message: str, kind: str, exit_code: int) -> dict[str, object]:
    """The `--json` object for a failed conversion: still valid JSON, with the failure as a warning."""
    return {
        "source": source,
        "status": "failed",
        "exit_code": exit_code,
        "error": {"code": code, "message": message},
        "warnings": [{"kind": kind, "severity": "error", "message": message}],
    }


ProgressSink = Callable[[str, float | None, str], None]
"""(stage, fraction or None, message) -> None."""


@contextmanager
def progress_display(enabled: bool, initial: str) -> Iterator[ProgressSink]:
    """A Rich progress bar on stderr with stage labels; a no-op sink when disabled or stderr is not a TTY."""
    if not enabled or not sys.stderr.isatty():
        yield lambda stage, fraction, message: None
        return
    from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TimeElapsedColumn

    columns = (SpinnerColumn(), TextColumn("{task.description}"), BarColumn(), TimeElapsedColumn())
    with Progress(*columns, console=err_console(), transient=True) as bar:
        task = bar.add_task(_STAGE_LABELS.get(initial, initial.capitalize()), total=None)

        def sink(stage: str, fraction: float | None, message: str) -> None:
            label = _STAGE_LABELS.get(stage, stage.replace("_", " ").capitalize())
            desc = f"{label}: {message}" if message else label
            if fraction is None:
                bar.update(task, description=desc, total=None)
            else:
                bar.update(task, description=desc, total=1.0, completed=max(0.0, min(1.0, fraction)))

        yield sink
