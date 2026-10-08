from __future__ import annotations

import sys
from pathlib import Path

import pytest

from ezmd.core import sandbox
from ezmd.core.sandbox import SandboxError, SandboxTimeout, run

PY = sys.executable


def test_rejects_string_argv() -> None:
    with pytest.raises(SandboxError):
        run("echo hi", timeout=5)  # type: ignore[arg-type]
    with pytest.raises(SandboxError):
        run([], timeout=5)
    with pytest.raises(SandboxError):
        run([PY, "-c", "print(1)\x00"], timeout=5)


def test_missing_binary() -> None:
    with pytest.raises(SandboxError, match="not found"):
        run(["definitely-not-a-real-binary-xyz"], timeout=5)


def test_runs_and_captures() -> None:
    r = run([PY, "-c", "import sys; print('out'); print('err', file=sys.stderr); sys.exit(3)"], timeout=30)
    assert r.returncode == 3 and r.stdout.strip() == b"out" and r.stderr.strip() == b"err"
    with pytest.raises(SandboxError):
        r.check()


def test_timeout_kills() -> None:
    with pytest.raises(SandboxTimeout) as ei:
        run([PY, "-c", "import time; time.sleep(5)"], timeout=1)
    assert ei.value.result.timed_out
    assert ei.value.result.duration_seconds < 4


def test_output_capped() -> None:
    r = run([PY, "-c", "import sys; sys.stdout.write('x' * 300000)"], timeout=30, output_cap=1000)
    assert len(r.stdout) == 1000 and r.stdout_truncated


def test_minimal_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EZMD_SECRET_THING", "leak")
    r = run([PY, "-c", "import os; print(os.environ.get('EZMD_SECRET_THING'))"], timeout=30)
    assert r.stdout.strip() == b"None"
    r2 = run([PY, "-c", "import os; print(os.environ['X'])"], timeout=30, env={"X": "y"})
    assert r2.stdout.strip() == b"y"


def test_stdin_and_cwd(tmp_path: Path) -> None:
    code = "import sys, os; print(sys.stdin.read(), os.getcwd())"
    r = run([PY, "-c", code], timeout=30, cwd=tmp_path, stdin_data=b"abc")
    out = r.stdout.decode()
    assert out.startswith("abc ")
    assert Path(out.split(" ", 1)[1].strip()).resolve() == tmp_path.resolve()


def test_ffmpeg_flag_injection() -> None:
    out = sandbox._inject_ffmpeg_flags(["/usr/bin/ffmpeg", "-i", "a.wav", "b.wav"])
    assert out[:4] == ["/usr/bin/ffmpeg", "-nostdin", "-protocol_whitelist", "file,pipe"]
    probe = sandbox._inject_ffmpeg_flags(["ffprobe", "a.wav"])
    assert "-nostdin" not in probe and "-protocol_whitelist" in probe
    assert sandbox._inject_ffmpeg_flags(["pandoc", "x"]) == ["pandoc", "x"]


@pytest.mark.skipif(not sandbox.bwrap_available(), reason="bubblewrap not installed")
def test_bwrap_wraps() -> None:
    r = run(["/bin/true"], timeout=10)
    assert r.sandboxed_with == "bwrap"
