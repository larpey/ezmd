"""ezmd_api.isolation: run one conversion in a `multiprocessing` spawn child
(docs/spec/part1.md section 8.1).

The child applies POSIX resource limits (address space, CPU, process count, file size) before it
imports any engine, builds `ezmd.library.Options` from the stored options, converts through
`ezmd.pipeline.convert_ref`, and writes the IR as JSON
(never pickle) plus a small status file. The parent enforces the wall-clock limit with SIGKILL
(TerminateProcess on Windows) after `max_seconds + 30`, so a hung or crashing engine only takes
down the child.
"""

from __future__ import annotations

import json
import logging
import multiprocessing
import sys
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

KILL_GRACE_SECONDS = 30
TICK_SECONDS = 5.0
FSIZE_LIMIT_BYTES = 2 * 1024 * 1024 * 1024
NPROC_LIMIT = 64
DEFAULT_MAX_RESULT_BYTES = 256 * 1024 * 1024
MAX_STATUS_BYTES = 64 * 1024
# ConversionError codes the child may report as-is; anything else becomes conversion_failed.
PASSTHROUGH_CONVERSION_CODES = frozenset({"experimental_disabled"})


@dataclass(slots=True)
class ChildRequest:
    input_path: str
    out_path: str
    display: str
    kind: str
    url: str | None
    declared_mime: str | None
    convert_options: dict[str, Any]
    converter_id: str | None
    max_seconds: float
    mem_mb: int
    max_bytes: int
    max_result_bytes: int = DEFAULT_MAX_RESULT_BYTES


@dataclass(slots=True)
class ChildOutcome:
    status: Literal["ok", "error", "fetch_required", "timeout", "crash"]
    code: str = ""
    message: str = ""
    result_json: str | None = None
    fetch_url: str | None = None
    residential: bool = False
    """What the child claimed. Advisory only: the parent never routes on it (D-0017 item 4)."""
    fetch_depth: int = 0
    extra: dict[str, Any] = field(default_factory=dict)


def _apply_limits(req: ChildRequest) -> None:  # pragma: no cover - POSIX only, runs in the child
    if sys.platform == "win32":
        return
    import resource

    def setlim(which: int, value: int) -> None:
        try:
            _soft, hard = resource.getrlimit(which)
            cap = value if hard == resource.RLIM_INFINITY else min(value, hard)
            resource.setrlimit(which, (cap, cap))
        except (ValueError, OSError):
            pass

    setlim(resource.RLIMIT_AS, req.mem_mb * 1024 * 1024)
    setlim(resource.RLIMIT_CPU, int(req.max_seconds) + 5)
    setlim(resource.RLIMIT_NPROC, NPROC_LIMIT)
    setlim(resource.RLIMIT_FSIZE, FSIZE_LIMIT_BYTES)


def _write_status(req: ChildRequest, payload: dict[str, Any]) -> None:
    Path(req.out_path + ".status.json").write_text(json.dumps(payload), encoding="utf-8")


def child_main(raw: dict[str, Any]) -> None:
    """Entry point of the spawned child. Everything it reports goes through files in its workdir."""
    req = ChildRequest(**raw)
    _apply_limits(req)
    from ezmd.core.logging import install

    logging.basicConfig(level=logging.WARNING)
    for h in logging.getLogger().handlers:
        install(h)

    from ezmd.inputs import FetchRequired, InputRef, InputTooLarge
    from ezmd.pipeline import UnsupportedMediaType, convert_ref
    from ezmd.registry import ConversionError
    from ezmd_api.options import to_convert_options

    try:
        body = Path(req.input_path)
        fetched = req.kind in ("url", "residential_fetch")
        ref = InputRef(
            kind=req.kind,  # type: ignore[arg-type]
            display=req.display,
            local_path=None if fetched else body,
            fetched_path=body if fetched else None,
            url=req.url,
            declared_mime=req.declared_mime,
            max_bytes=req.max_bytes,
        )
        options = to_convert_options(req.convert_options, max_seconds=req.max_seconds)
        result = convert_ref(ref, options, converter_id=req.converter_id)
        Path(req.out_path).write_text(result.model_dump_json(), encoding="utf-8")
        _write_status(req, {"status": "ok"})
    except UnsupportedMediaType as e:
        _write_status(req, {"status": "error", "code": "unsupported_media_type", "message": e.user_message})
    except ConversionError as e:
        code = str(getattr(e, "code", "conversion_failed") or "conversion_failed")
        if code not in PASSTHROUGH_CONVERSION_CODES:
            code = "conversion_failed"
        _write_status(req, {"status": "error", "code": code, "message": e.user_message})
    except InputTooLarge:
        _write_status(req, {"status": "error", "code": "input_too_large", "message": "The input is too large."})
    except FetchRequired as e:
        depth = getattr(e, "fetch_depth", 0)
        _write_status(
            req,
            {
                "status": "fetch_required",
                "url": e.url,
                "residential": e.residential,
                "fetch_depth": depth if isinstance(depth, int) else 0,
            },
        )
    except MemoryError:
        _write_status(req, {"status": "error", "code": "conversion_failed", "message": "Conversion ran out of memory."})
    except Exception:
        logging.getLogger("ezmd.api.child").exception("conversion crashed")
        _write_status(req, {"status": "error", "code": "conversion_failed", "message": "Conversion failed."})


def _read_outcome(req: ChildRequest, exitcode: int | None) -> ChildOutcome:
    status_path = Path(req.out_path + ".status.json")
    if not status_path.is_file():
        return ChildOutcome("crash", "conversion_failed", f"The converter process exited unexpectedly ({exitcode}).")
    if status_path.stat().st_size > MAX_STATUS_BYTES:
        return ChildOutcome("crash", "conversion_failed", "The converter process reported an invalid status.")
    try:
        status = json.loads(status_path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return ChildOutcome("crash", "conversion_failed", "The converter process reported an invalid status.")
    if not isinstance(status, dict):
        return ChildOutcome("crash", "conversion_failed", "The converter process reported an invalid status.")
    kind = status.get("status")
    if kind == "ok":
        return _read_result(req)
    if kind == "fetch_required":
        url = status.get("url")
        depth = status.get("fetch_depth", 0)
        return ChildOutcome(
            "fetch_required",
            fetch_url=url if isinstance(url, str) else None,
            residential=bool(status.get("residential")),
            fetch_depth=depth if isinstance(depth, int) and not isinstance(depth, bool) else 0,
        )
    return ChildOutcome("error", str(status.get("code", "conversion_failed")), str(status.get("message", "")))


def _read_result(req: ChildRequest) -> ChildOutcome:
    """Read the IR JSON, refusing anything over `max_result_bytes` before it is loaded."""
    out = Path(req.out_path)
    if not out.is_file():
        return ChildOutcome("crash", "conversion_failed", "The converter process wrote no result.")
    size = out.stat().st_size
    if size > req.max_result_bytes:
        limit_mb = req.max_result_bytes // (1024 * 1024)
        return ChildOutcome(
            "error",
            "result_too_large",
            f"The conversion result exceeds the {limit_mb} MB limit.",
            extra={"limit_bytes": req.max_result_bytes, "result_bytes": size},
        )
    with out.open("rb") as fh:
        data = fh.read(req.max_result_bytes + 1)
    if len(data) > req.max_result_bytes:
        return ChildOutcome("error", "result_too_large", "The conversion result exceeds the size limit.")
    return ChildOutcome("ok", result_json=data.decode("utf-8"))


def run_isolated(
    req: ChildRequest,
    *,
    on_tick: Callable[[float], None] | None = None,
    kill_after: float | None = None,
) -> ChildOutcome:
    """Run `child_main(req)` in a spawn child and wait for it under the wall-clock limit."""
    ctx = multiprocessing.get_context("spawn")
    proc = ctx.Process(target=child_main, args=(asdict(req),), name="ezmd-convert", daemon=True)
    limit = kill_after if kill_after is not None else req.max_seconds + KILL_GRACE_SECONDS
    t0 = time.monotonic()
    proc.start()
    try:
        while True:
            remaining = limit - (time.monotonic() - t0)
            if remaining <= 0:
                proc.kill()
                proc.join(10)
                return ChildOutcome("timeout", "timeout", "The conversion exceeded its time limit.")
            proc.join(min(TICK_SECONDS, remaining))
            if not proc.is_alive():
                break
            if on_tick is not None:
                on_tick(time.monotonic() - t0)
    finally:
        if proc.is_alive():
            proc.kill()
            proc.join(10)
    return _read_outcome(req, proc.exitcode)
