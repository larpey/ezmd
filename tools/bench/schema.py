"""Result records written by the harness (results.jsonl per corpus run, results.json per dated run)."""

from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
_APPEND = threading.Lock()
"""Parallel shards of one run append to the same results file."""
STATUSES = ("ok", "error", "timeout", "crash", "unsupported")
"""ok: output written. error: the tool raised. timeout: killed after the per-document limit. crash: the worker
process died. unsupported: the tool does not claim the input format, so it was not attempted."""


@dataclass(frozen=True, slots=True)
class Doc:
    corpus: str
    id: str
    input: Path
    category: str
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class DocResult:
    corpus: str
    doc_id: str
    category: str
    tool: str
    tool_version: str
    status: str
    seconds: float | None = None
    peak_rss_mb: float | None = None
    output: str | None = None
    error_class: str | None = None
    error: str | None = None
    chars: int | None = None
    where: str | None = None
    """The frame that raised, `path:line function`, innermost frame of the tool's own code when there is one:
    what a crash cluster is keyed on."""
    cause: str | None = None
    """Class of the exception a declared error was raised from (ezmd's registry wraps the converter's)."""

    def __post_init__(self) -> None:
        if self.status not in STATUSES:
            raise ValueError(f"unknown status {self.status!r}")
        if self.status == "ok" and not self.output:
            raise ValueError("an ok result needs an output path")

    @property
    def failed(self) -> bool:
        return self.status in ("error", "timeout", "crash")

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, sort_keys=True)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DocResult:
        names = {f.name for f in fields(cls)}
        unknown = set(data) - names
        if unknown:
            raise ValueError(f"unknown DocResult fields: {sorted(unknown)}")
        return cls(**data)


def read_results(path: Path) -> list[DocResult]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            out.append(DocResult.from_dict(json.loads(line)))
    return out


def append_result(path: Path, result: DocResult) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with _APPEND, path.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write(result.to_json() + "\n")
