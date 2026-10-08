"""intomd_api.isolation: run one conversion in a `multiprocessing` spawn child
(docs/spec/part1.md section 8.1).

The child applies POSIX resource limits (address space, CPU, process count, file size) before it
imports any engine, converts through `intomd.pipeline.convert_ref`, and writes the IR as JSON
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


@dataclass(slots=True)
class ChildOutcome:
    status: Literal["ok", "error", "fetch_required", "timeout", "crash"]
    code: str = ""
    message: str = ""
    result_json: str | None = None
    fetch_url: str | None = None
    residential: bool = False
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
    from intomd.core.logging import install

    logging.basicConfig(level=logging.WARNING)
    for h in logging.getLogger().handlers:
        install(h)

    from intomd.inputs import FetchRequired, InputRef, InputTooLarge
    from intomd.pipeline import UnsupportedMediaType, convert_ref
    from intomd.registry import ConversionError, ConvertOptions

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
        options = ConvertOptions(**req.convert_options, max_seconds=req.max_seconds)
        result = convert_ref(ref, options, converter_id=req.converter_id)
        Path(req.out_path).write_text(result.model_dump_json(), encoding="utf-8")
        _write_status(req, {"status": "ok"})
    except UnsupportedMediaType as e:
        _write_status(req, {"status": "error", "code": "unsupported_media_type", "message": e.user_message})
    except ConversionError as e:
        _write_status(req, {"status": "error", "code": "conversion_failed", "message": e.user_message})
    except InputTooLarge:
        _write_status(req, {"status": "error", "code": "input_too_large", "message": "The input is too large."})
    except FetchRequired as e:
        _write_status(req, {"status": "fetch_required", "url": e.url, "residential": e.residential})
    except MemoryError:
        _write_status(req, {"status": "error", "code": "conversion_failed", "message": "Conversion ran out of memory."})
    except Exception:
        logging.getLogger("intomd.api.child").exception("conversion crashed")
        _write_status(req, {"status": "error", "code": "conversion_failed", "message": "Conversion failed."})


def _read_outcome(req: ChildRequest, exitcode: int | None) -> ChildOutcome:
    status_path = Path(req.out_path + ".status.json")
    if not status_path.is_file():
        return ChildOutcome("crash", "conversion_failed", f"The converter process exited unexpectedly ({exitcode}).")
    status = json.loads(status_path.read_text(encoding="utf-8"))
    kind = status.get("status")
    if kind == "ok":
        return ChildOutcome("ok", result_json=Path(req.out_path).read_text(encoding="utf-8"))
    if kind == "fetch_required":
        return ChildOutcome("fetch_required", fetch_url=status.get("url"), residential=bool(status.get("residential")))
    return ChildOutcome("error", str(status.get("code", "conversion_failed")), str(status.get("message", "")))


def run_isolated(
    req: ChildRequest,
    *,
    on_tick: Callable[[float], None] | None = None,
    kill_after: float | None = None,
) -> ChildOutcome:
    """Run `child_main(req)` in a spawn child and wait for it under the wall-clock limit."""
    ctx = multiprocessing.get_context("spawn")
    proc = ctx.Process(target=child_main, args=(asdict(req),), name="intomd-convert", daemon=True)
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
