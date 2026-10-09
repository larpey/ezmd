"""The CLI writes UTF-8 even when the platform gives it a legacy stream encoding (Windows pipes use cp1252)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

CHECK = chr(0x2713)


@pytest.mark.parametrize("encoding", ["cp1252", "ascii"])
def test_convert_to_a_pipe_writes_utf8_under_a_legacy_encoding(tmp_path: Path, encoding: str) -> None:
    src = tmp_path / "note.txt"
    src.write_text(f"Checklist{chr(10)}{chr(10)}{CHECK} done and caf{chr(0xE9)}{chr(10)}", encoding="utf-8")
    env = {**os.environ, "PYTHONIOENCODING": encoding, "PYTHONUTF8": "0"}
    proc = subprocess.run(
        [sys.executable, "-c", "from ezmd.cli import app; app()", "convert", str(src), "--profile", "compact"],
        capture_output=True,
        env=env,
        check=False,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr.decode("utf-8", "replace")
    out = proc.stdout.decode("utf-8")
    assert f"{CHECK} done" in out and f"caf{chr(0xE9)}" in out
