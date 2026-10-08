"""intomd.core.sandbox: the only place in intomd that starts external processes.

Implemented from docs/spec/part1.md section 8.1. Every external binary (ffmpeg, pandoc, deno, yt-dlp,
tesseract, ...) goes through `run()`:

- argv must be a list of strings; a plain string is rejected (no shell, ever).
- `shell=False`, `stdin=DEVNULL`, a minimal environment built from an allowlist.
- stdout and stderr are each capped (default 10 MB); excess output is drained and discarded.
- a wall-clock timeout kills the process tree.
- on POSIX, resource limits (address space, CPU, file size, process count) are applied in the child.
- when `bwrap` (bubblewrap) is on PATH and the platform is Linux, the command runs inside it with a
  read-only /usr, a private /tmp, all namespaces unshared, and only the working directory bound.
- ffmpeg/ffprobe invocations get `-nostdin -protocol_whitelist file,pipe` injected.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import threading
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import IO

DEFAULT_OUTPUT_CAP = 10 * 1024 * 1024
DEFAULT_ENV_ALLOWLIST: tuple[str, ...] = ("PATH", "LANG", "LC_ALL", "TZ", "SYSTEMROOT", "TEMP", "TMP", "HOME")
_FFMPEG_NAMES = frozenset({"ffmpeg", "ffprobe", "ffmpeg.exe", "ffprobe.exe"})


class SandboxError(Exception):
    """Raised for invalid invocations (string argv, missing binary)."""


class SandboxTimeout(SandboxError):
    def __init__(self, argv0: str, timeout: float, result: SandboxResult) -> None:
        super().__init__(f"{argv0} exceeded {timeout}s")
        self.result = result


@dataclass(slots=True, frozen=True)
class Limits:
    """Per-process POSIX resource limits. None leaves the inherited limit in place."""

    mem_mb: int | None = 4096
    cpu_seconds: int | None = None
    fsize_mb: int | None = 2048
    nproc: int | None = 64


@dataclass(slots=True)
class SandboxResult:
    argv: list[str]
    returncode: int
    stdout: bytes
    stderr: bytes
    stdout_truncated: bool
    stderr_truncated: bool
    duration_seconds: float
    timed_out: bool = False
    sandboxed_with: str = "none"
    """'bwrap' when bubblewrap wrapped the command, else 'none'."""

    def check(self) -> SandboxResult:
        if self.returncode != 0:
            raise SandboxError(f"{Path(self.argv[0]).name} exited with {self.returncode}")
        return self


class _CappedReader(threading.Thread):
    def __init__(self, stream: IO[bytes], cap: int) -> None:
        super().__init__(daemon=True)
        self.stream = stream
        self.cap = cap
        self.buf = bytearray()
        self.truncated = False

    def run(self) -> None:
        while True:
            chunk = self.stream.read(65536)
            if not chunk:
                break
            room = self.cap - len(self.buf)
            if room > 0:
                self.buf.extend(chunk[:room])
            if len(chunk) > room:
                self.truncated = True
        self.stream.close()


_bwrap_ok: bool | None = None


def bwrap_available() -> bool:
    """True only when bubblewrap is installed AND can actually create its namespaces here. Inside a
    hardened container (no capabilities, mount denied by seccomp) bwrap exists but cannot run, and
    wrapping every command with it would make every external tool fail. Probed once per process."""
    global _bwrap_ok
    if _bwrap_ok is None:
        bw = shutil.which("bwrap") if sys.platform.startswith("linux") else None
        if bw is None:
            _bwrap_ok = False
        else:
            try:
                probe = subprocess.run(  # noqa: S603 - fixed argv
                    [bw, "--ro-bind", "/", "/", "--unshare-all", "--die-with-parent", "true"],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=5,
                    check=False,
                )
                _bwrap_ok = probe.returncode == 0
            except (OSError, subprocess.SubprocessError):
                _bwrap_ok = False
    return _bwrap_ok


def _bwrap_prefix(cwd: Path | None, extra_ro: Sequence[Path]) -> list[str]:
    bw = shutil.which("bwrap")
    assert bw is not None
    argv = [bw, "--ro-bind", "/usr", "/usr", "--tmpfs", "/tmp", "--proc", "/proc", "--dev", "/dev"]  # noqa: S108
    for d in ("/bin", "/lib", "/lib64", "/sbin", "/etc"):
        if Path(d).exists():
            argv += ["--ro-bind", d, d]
    for p in extra_ro:
        argv += ["--ro-bind", str(p), str(p)]
    if cwd is not None:
        argv += ["--bind", str(cwd), str(cwd), "--chdir", str(cwd)]
    argv += ["--unshare-all", "--die-with-parent", "--new-session"]
    return argv


def _inject_ffmpeg_flags(argv: list[str]) -> list[str]:
    if Path(argv[0]).name.lower() not in _FFMPEG_NAMES:
        return argv
    rest = argv[1:]
    inject: list[str] = []
    if "-nostdin" not in rest and Path(argv[0]).name.lower().startswith("ffmpeg"):
        inject.append("-nostdin")
    if "-protocol_whitelist" not in rest:
        inject += ["-protocol_whitelist", "file,pipe"]
    return [argv[0], *inject, *rest]


def _minimal_env(allowlist: Sequence[str], extra: Mapping[str, str] | None) -> dict[str, str]:
    env = {k: os.environ[k] for k in allowlist if k in os.environ}
    if extra:
        env.update(extra)
    return env


def _preexec(limits: Limits) -> None:  # pragma: no cover - runs in the forked child on POSIX
    if sys.platform == "win32":
        return
    import resource

    def setlim(which: int, value: int | None) -> None:
        if value is None:
            return
        try:
            resource.setrlimit(which, (value, value))
        except (ValueError, OSError):
            pass

    setlim(resource.RLIMIT_AS, limits.mem_mb * 1024 * 1024 if limits.mem_mb else None)
    setlim(resource.RLIMIT_CPU, limits.cpu_seconds)
    setlim(resource.RLIMIT_FSIZE, limits.fsize_mb * 1024 * 1024 if limits.fsize_mb else None)
    setlim(resource.RLIMIT_NPROC, limits.nproc)
    os.setsid()


def run(
    argv: list[str],
    *,
    timeout: float,
    cwd: str | Path | None = None,
    env_allowlist: Sequence[str] = DEFAULT_ENV_ALLOWLIST,
    env: Mapping[str, str] | None = None,
    output_cap: int = DEFAULT_OUTPUT_CAP,
    limits: Limits | None = None,
    use_bwrap: bool | None = None,
    ro_binds: Sequence[Path] = (),
    stdin_data: bytes | None = None,
) -> SandboxResult:
    """Run an external command safely. See the module docstring for guarantees.

    Raises SandboxError for a non-list argv or a missing binary, and SandboxTimeout (carrying the
    partial result) when `timeout` is exceeded. A non-zero exit code is returned, not raised; call
    `.check()` to raise.
    """
    if isinstance(argv, (str, bytes)) or not isinstance(argv, list):
        raise SandboxError("argv must be a list of strings; shell strings are not allowed")
    if not argv or not all(isinstance(a, str) for a in argv):
        raise SandboxError("argv must be a non-empty list of strings")
    if any("\x00" in a for a in argv):
        raise SandboxError("argv contains a NUL byte")
    exe = shutil.which(argv[0]) if not Path(argv[0]).is_absolute() else argv[0]
    if exe is None or not Path(exe).exists():
        raise SandboxError(f"executable not found: {argv[0]}")
    full = _inject_ffmpeg_flags([exe, *argv[1:]])
    cwd_path = Path(cwd) if cwd is not None else None
    wrapped_with = "none"
    if use_bwrap is None:
        use_bwrap = bwrap_available()
    if use_bwrap:
        full = [*_bwrap_prefix(cwd_path, ro_binds), *full]
        wrapped_with = "bwrap"
    posix = os.name == "posix"
    lim = limits or Limits()
    t0 = time.monotonic()
    proc = subprocess.Popen(  # noqa: S603 - list argv, shell=False, validated above
        full,
        stdin=subprocess.PIPE if stdin_data is not None else subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(cwd_path) if cwd_path else None,
        env=_minimal_env(env_allowlist, env),
        shell=False,
        preexec_fn=(lambda: _preexec(lim)) if posix else None,
        creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) if os.name == "nt" else 0,
    )
    assert proc.stdout is not None and proc.stderr is not None
    out_r = _CappedReader(proc.stdout, output_cap)
    err_r = _CappedReader(proc.stderr, output_cap)
    out_r.start()
    err_r.start()
    if stdin_data is not None:
        assert proc.stdin is not None
        try:
            proc.stdin.write(stdin_data)
        except (BrokenPipeError, OSError):
            pass
        finally:
            proc.stdin.close()
    timed_out = False
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        _kill_tree(proc)
        proc.wait()
    out_r.join(5)
    err_r.join(5)
    result = SandboxResult(
        argv=full,
        returncode=proc.returncode,
        stdout=bytes(out_r.buf),
        stderr=bytes(err_r.buf),
        stdout_truncated=out_r.truncated,
        stderr_truncated=err_r.truncated,
        duration_seconds=time.monotonic() - t0,
        timed_out=timed_out,
        sandboxed_with=wrapped_with,
    )
    if timed_out:
        raise SandboxTimeout(Path(argv[0]).name, timeout, result)
    return result


def _kill_tree(proc: subprocess.Popen[bytes]) -> None:
    if sys.platform != "win32":
        import signal

        try:
            os.killpg(proc.pid, signal.SIGKILL)
            return
        except (ProcessLookupError, PermissionError):
            pass
    proc.kill()
