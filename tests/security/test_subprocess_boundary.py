"""docs/spec/part1.md 8.4: `subprocess` is imported only in intomd.core.sandbox."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ALLOWED = {ROOT / "packages/core/src/intomd/core/sandbox.py"}
PATTERN = re.compile(r"^\s*(import subprocess|from subprocess import)|os\.system\(|os\.popen\(", re.M)


def test_subprocess_only_in_sandbox() -> None:
    offenders = []
    for base in ("packages", "apps"):
        for p in (ROOT / base).rglob("*.py"):
            if {"tests", ".venv", "node_modules"} & set(p.parts) or p in ALLOWED:
                continue
            if PATTERN.search(p.read_text(encoding="utf-8", errors="replace")):
                offenders.append(str(p.relative_to(ROOT)))
    assert offenders == [], offenders
