"""Repository hygiene: catch stray files that shell redirections create (e.g. `-> str` in a one-liner)."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
ALLOWED_EMPTY = {"__init__.py", "py.typed", ".gitkeep"}


def test_no_empty_tracked_files() -> None:
    proc = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=False)
    if proc.returncode != 0:
        # e.g. a git worktree mounted into a container without its parent gitdir (tools/linux_gates.sh)
        pytest.skip(f"git ls-files unavailable: {proc.stderr.decode(errors='replace').strip()[:200]}")
    out = proc.stdout
    empty = [
        name
        for name in out.decode("utf-8").split("\0")
        if name
        and Path(name).name not in ALLOWED_EMPTY
        and (ROOT / name).is_file()
        and (ROOT / name).stat().st_size == 0
    ]
    assert empty == [], f"empty tracked files (probably shell-redirect junk): {empty}"
