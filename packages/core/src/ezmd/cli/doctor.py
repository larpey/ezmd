"""`ezmd doctor`: environment checks with a one-line fix for each problem (docs/spec/part4.md 4.2.2 item 5).

Each row is OK, WARN, or MISSING. A row may be `required_by` an extra (or `core`, or `configured` for
services the user configured); the command exits 2 only when a MISSING row is required by core, by an
installed extra, or by configuration, so a machine without ffmpeg exits 0 unless the `media` extra is
installed.
"""

from __future__ import annotations

import importlib
import importlib.metadata as md
import importlib.util
import os
import re
import shutil
import sys
import tempfile
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Annotated

import typer

from ezmd import __version__
from ezmd.cli.exitcodes import EXIT_ARGS, EXIT_OK

__all__ = ["PLANNED_EXTRAS", "Check", "declared_extras", "doctor", "installed_extras", "run_checks"]

OK, WARN, MISSING = "OK", "WARN", "MISSING"

SELFHOST_DOCS = "https://larpey.github.io/ezmd/selfhost/"

PLANNED_EXTRAS: dict[str, str] = {
    "media": "audio and video transcription",
    "ocr": "OCR for scanned PDFs and images",
    "web": "browser-rendered web pages",
    "fetch": "media fetching",
    "server": "the API server (self-host it with Docker Compose for now: " + SELFHOST_DOCS + ")",
}
"""Extras the spec names (docs/spec/part4.md 4.3.3) that are not published yet. Doctor lists them as coming
in a later release instead of printing a pip command that would fail; tests/test_extras_hints.py keeps this
in step with its PENDING list. The published extras are read from the installed `ezmd` metadata."""

_EXTRA_NOTES = {"nonfree": " (GPL-3.0 extract-msg; read docs/licenses.md first)"}
_FALLBACK_EXTRAS = ("7z", "data", "docs", "mcp", "nonfree")
"""Only used when the `ezmd` distribution metadata cannot be read (for example a bare source tree)."""

_EXTRA_MARKER = re.compile(r"""extra\s*==\s*["']([^"']+)["']""")
_REQ_NAME = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*(?:\[([^\]]*)\])?")

_BINARIES: tuple[tuple[str, tuple[str, ...], str | None, str], ...] = (
    (
        "ffmpeg",
        ("ffmpeg",),
        "media",
        "Install ffmpeg: apt install ffmpeg / brew install ffmpeg / winget install ffmpeg",
    ),
    ("ffprobe", ("ffprobe",), "media", "ffprobe ships with ffmpeg: install ffmpeg"),
    ("pandoc", ("pandoc",), None, "Optional: install pandoc (https://pandoc.org/installing.html)"),
    (
        "libreoffice",
        ("soffice", "libreoffice"),
        None,
        "Optional, for legacy Office files: install LibreOffice (apt install libreoffice-core)",
    ),
)


@dataclass(frozen=True, slots=True)
class Check:
    name: str
    status: str
    detail: str
    fix: str = ""
    required_by: str | None = None


def _which(name: str) -> str | None:
    return shutil.which(name)


def _has_module(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def declared_extras() -> list[str]:
    """The extras the installed `ezmd` publishes (its `Provides-Extra` metadata), without the `all` bundle."""
    try:
        names = md.distribution("ezmd").metadata.get_all("Provides-Extra") or []
    except md.PackageNotFoundError:
        names = list(_FALLBACK_EXTRAS)
    return sorted({n for n in names if n != "all"})


def _extra_requirements(dist: str, extra: str) -> list[tuple[str, tuple[str, ...]]] | None:
    """(name, extras) for each requirement `dist` declares only for `extra`; None if `dist` is missing.
    Requirements with other environment markers (platform, Python version) are left out."""
    try:
        requires = md.distribution(dist).requires or []
    except md.PackageNotFoundError:
        return None
    out = []
    for req in requires:
        spec, _, marker = req.partition(";")
        if _EXTRA_MARKER.findall(marker) != [extra] or _EXTRA_MARKER.sub("", marker).strip(" ()"):
            continue
        m = _REQ_NAME.match(spec)
        if m:
            subs = tuple(x.strip() for x in (m.group(2) or "").split(",") if x.strip())
            out.append((m.group(1), subs))
    return out


def _extra_installed(dist: str, extra: str, depth: int = 0) -> bool:
    """Every distribution `dist[extra]` pulls in is installed, following nested extras a few levels."""
    reqs = _extra_requirements(dist, extra)
    if not reqs:
        return False
    for name, subs in reqs:
        if not _dist_installed(name):
            return False
        if depth < 3 and any(
            _extra_requirements(name, sub) and not _extra_installed(name, sub, depth + 1) for sub in subs
        ):
            return False
    return True


def installed_extras() -> set[str]:
    """Published `ezmd` extras whose requirements (including the forwarded `ezmd-converters[...]` extras)
    are all installed."""
    names = [*declared_extras(), "all"]
    return {extra for extra in names if _extra_installed("ezmd", extra)}


def _dist_installed(name: str) -> bool:
    try:
        md.distribution(name)
    except md.PackageNotFoundError:
        return False
    return True


def _binary_version(path: str) -> str:
    from ezmd.core.sandbox import run

    try:
        res = run([path, "-version"], timeout=10)
    except Exception:
        return ""
    first = res.stdout.decode("utf-8", "replace").strip().splitlines()
    return first[0][:80] if first else ""


def _python() -> Check:
    v = sys.version_info
    ver = f"{v.major}.{v.minor}.{v.micro}"
    if v < (3, 12):
        return Check("python", MISSING, ver, "ezmd needs Python 3.12 or newer", "core")
    return Check("python", OK, ver)


def _extras(installed: set[str]) -> list[Check]:
    rows = []
    for extra in declared_extras():
        if extra in installed:
            rows.append(Check(f"extra: {extra}", OK, "installed"))
        else:
            fix = f"pip install 'ezmd[{extra}]'" + _EXTRA_NOTES.get(extra, "")
            rows.append(Check(f"extra: {extra}", WARN, "not installed", fix))
    for extra, what in PLANNED_EXTRAS.items():
        rows.append(Check(f"extra: {extra}", WARN, f"not released yet: {what}", "coming in a later release"))
    return rows


def _binaries() -> list[Check]:
    rows = []
    for label, names, extra, fix in _BINARIES:
        path = next((p for p in (_which(n) for n in names) if p), None)
        if path is None:
            rows.append(Check(label, MISSING if extra else WARN, "not on PATH", fix, extra))
        else:
            version = _binary_version(path) if label in ("ffmpeg", "ffprobe", "pandoc") else ""
            rows.append(Check(label, OK, version or path, required_by=extra))
    return rows


def _libmagic() -> Check:
    try:
        from ezmd.detect import import_magic

        magic = import_magic()
        magic.from_buffer(b"hello world", mime=True)
    except Exception as e:
        fix = "Install libmagic (apt install libmagic1 / brew install libmagic); detection falls back to Magika"
        return Check("libmagic", WARN, type(e).__name__, fix)
    return Check("libmagic", OK, "loaded")


def _magika() -> Check:
    try:
        importlib.import_module("magika").Magika()
    except Exception as e:
        return Check("magika model", MISSING, type(e).__name__, "Reinstall magika: pip install -U magika", "core")
    try:
        version = md.version("magika")
    except md.PackageNotFoundError:
        version = "present"
    return Check("magika model", OK, version)


def _writable(label: str, directory: Path, required_by: str | None, fix: str, *, create: bool = True) -> Check:
    """Write a temp file into `directory` (created when `create`; otherwise its nearest existing ancestor
    is tested, so doctor never creates the config directory)."""
    probe = directory
    if not create:
        while not probe.exists() and probe.parent != probe:
            probe = probe.parent
    try:
        if create:
            probe.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=probe, prefix=".ezmd-doctor-", delete=True):
            pass
    except OSError as e:
        status = MISSING if required_by else WARN
        return Check(label, status, f"{directory}: {e.strerror or type(e).__name__}", fix, required_by)
    return Check(label, OK, str(directory), required_by=required_by)


def _dirs() -> list[Check]:
    from ezmd.cli.config import config_path
    from ezmd.core.licensing import cache_dir

    cache = cache_dir()
    free = ""
    try:
        cache.mkdir(parents=True, exist_ok=True)
        free = f", {shutil.disk_usage(cache).free // (1024**3)} GiB free"
    except OSError:
        pass
    row = _writable("cache dir", cache, "core", "Set EZMD_CACHE_DIR to a writable directory")
    if row.status == OK:
        row = Check(row.name, OK, row.detail + free, required_by="core")
    cfg_dir = config_path().parent
    return [row, _writable("config dir", cfg_dir, None, "Set EZMD_CONFIG to a writable path", create=False)]


_REDIS_FIX = "pip install redis, or self-host the API with Docker Compose (" + SELFHOST_DOCS + ")"


def _redis() -> Check | None:
    url = os.environ.get("EZMD_REDIS_URL")
    if not url:
        return None
    try:
        redis = importlib.import_module("redis")
    except ImportError:
        return Check("redis", MISSING, "redis client not installed", _REDIS_FIX, "configured")
    try:
        client = redis.Redis.from_url(url, socket_connect_timeout=2, socket_timeout=2)
        client.ping()
    except Exception as e:
        return Check(
            "redis", MISSING, f"unreachable ({type(e).__name__})", "Start Redis or fix EZMD_REDIS_URL", "configured"
        )
    return Check("redis", OK, "reachable", required_by="configured")


def _docling(installed: set[str]) -> Check | None:
    if "docs" not in installed:
        return None
    try:
        importlib.import_module("docling")
    except Exception as e:
        return Check("docling", MISSING, f"import failed ({type(e).__name__})", "pip install -U 'ezmd[docs]'", "docs")
    return Check(
        "docling", OK, md.version("docling") if _dist_installed("docling") else "importable", required_by="docs"
    )


def run_checks(extra_checks: list[Callable[[], Check | None]] | None = None) -> tuple[list[Check], set[str]]:
    installed = installed_extras()
    rows: list[Check] = [_python(), Check("ezmd", OK, __version__), *_extras(installed), *_binaries()]
    rows += [_libmagic(), _magika(), *_dirs()]
    for maybe in (_redis(), _docling(installed), *(f() for f in extra_checks or [])):
        if maybe is not None:
            rows.append(maybe)
    return rows, installed


def is_fatal(row: Check, installed: set[str]) -> bool:
    if row.status != MISSING:
        return False
    return row.required_by in ("core", "configured") or (row.required_by in installed)


def doctor(
    as_json: Annotated[bool, typer.Option("--json", help="Checks as JSON on stdout.")] = False,
    quiet: Annotated[bool, typer.Option("--quiet", "-q", help="Print only problems.")] = False,
) -> None:
    """Check the environment: Python, extras, ffmpeg, pandoc, models, cache, Redis."""
    rows, installed = run_checks()
    fatal = [r for r in rows if is_fatal(r, installed)]
    code = EXIT_ARGS if fatal else EXIT_OK
    if as_json:
        import json

        payload = {
            "ok": not fatal,
            "exit_code": code,
            "installed_extras": sorted(installed),
            "checks": [{**asdict(r), "fatal": is_fatal(r, installed)} for r in rows],
        }
        sys.stdout.write(json.dumps(payload, indent=2) + "\n")
        raise typer.Exit(code)
    from rich.console import Console
    from rich.markup import escape
    from rich.table import Table

    t = Table("check", "status", "detail", "fix", title=f"ezmd doctor ({__version__})")
    style = {OK: "green", WARN: "yellow", MISSING: "red"}
    for r in rows:
        if quiet and r.status == OK:
            continue
        t.add_row(escape(r.name), f"[{style[r.status]}]{r.status}[/]", escape(r.detail), escape(r.fix))
    Console(soft_wrap=False).print(t)
    if fatal:
        names = ", ".join(r.name for r in fatal)
        Console(stderr=True).print(f"[red]missing required: {names}[/]")
    raise typer.Exit(code)
