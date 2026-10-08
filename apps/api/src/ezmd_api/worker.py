"""ezmd_api.worker: RQ worker entry and the job runner (docs/spec/part1.md sections 7.1, 7.2, 8.1).

`process_job(services, job_id)` drives one job through fetching (`fetching.py`; a fetched body is
always re-enqueued, so parsing never runs in the egress-capable fetch worker), converting (in a spawn
child, see `isolation.py`), IR caching, and rendering of the requested profile. RQ calls
`rq_entry(job_id)`; inline mode calls `process_job` on a thread. Run a worker with
`python -m ezmd_api.worker --queues default media` (or `fetch`).
"""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import tempfile
from pathlib import Path
from typing import Any

from ezmd_api import ircache
from ezmd_api import queue as q
from ezmd_api.fetching import fetch_job, follow_fetch_required, hand_off, input_key, ir_key, route_residential
from ezmd_api.isolation import ChildRequest, run_isolated
from ezmd_api.jobs import (
    CONVERTING,
    DONE,
    EXPIRED,
    FAILED,
    FETCHING,
    NEEDS_USER_ACTION,
    QUEUED,
    RENDERING,
    InvalidTransition,
    JobGone,
)
from ezmd_api.metrics import record_conversion
from ezmd_api.rendering import RenderUnavailable, render_cached
from ezmd_api.services import Services
from ezmd_api.settings import Settings
from ezmd_api.util import sanitize_filename

__all__ = ["input_key", "ir_key", "main", "process_job", "route_residential", "rq_entry"]

log = logging.getLogger("ezmd.api.worker")

MAX_WARNING_EVENTS = 50
_FINISHED = (DONE, FAILED, EXPIRED, NEEDS_USER_ACTION)


def process_job(services: Services, job_id: str) -> None:
    """Run one job. Never raises: failures are recorded on the job."""
    try:
        _process(services, job_id)
    except JobGone:
        log.info("job vanished while processing", extra={"job_id": job_id})
    except InvalidTransition as e:
        log.warning("stale job state: %s", e, extra={"job_id": job_id})
    except Exception:
        log.exception("job crashed", extra={"job_id": job_id})
        services.jobs.fail(job_id, "conversion_failed", "Conversion failed.")


def _process(services: Services, job_id: str) -> None:
    row = services.jobs.require(job_id)
    if row.state in _FINISHED or row.state == RENDERING:
        return
    if row.blob_input is None:
        if row.input_kind != "url" or not row.input_url:
            services.jobs.fail(job_id, "invalid_request", "The job has no input.")
            return
        fetch_job(services, job_id)
        return
    if row.queue in (q.FETCH, q.FETCH_RESIDENTIAL):
        # Never parse in the egress-capable worker: send the stored body on to a conversion queue.
        if row.state in (QUEUED, FETCHING):
            services.jobs.transition(job_id, CONVERTING, stage_message="Queued for conversion")
        hand_off(services, job_id, q.queue_for_mime(row.mime or row.declared_mime))
        return
    _convert(services, job_id)


def _detect_fetched(services: Services, job_id: str, body: Path) -> str | None:
    """Detect a fetched body's type here, outside the fetch worker. Returns the mime, or None when
    the job was failed or handed to another queue."""
    from ezmd.detect import detect, is_executable
    from ezmd.inputs import InputRef

    row = services.jobs.require(job_id)
    if row.mime:
        return row.mime
    path_part = (row.input_url or "").split("?", 1)[0]
    name = sanitize_filename(path_part.rsplit("/", 1)[-1], fallback="download")
    probe = InputRef(kind="bytes", display=name, local_path=body, declared_mime=row.declared_mime)
    mime = detect(probe).mime
    if is_executable(mime):
        services.jobs.fail(job_id, "unsupported_media_type", "Executable files are not accepted.")
        return None
    services.jobs.update(job_id, mime=mime)
    target = q.queue_for_mime(mime)
    if target != row.queue and target == q.MEDIA and services.queue.mode == "rq":
        hand_off(services, job_id, target)
        return None
    return mime


def _convert(services: Services, job_id: str) -> None:
    jobs, settings = services.jobs, services.settings
    row = jobs.require(job_id)
    if row.state in (QUEUED, FETCHING):
        row = jobs.transition(job_id, CONVERTING)
    workdir = Path(tempfile.mkdtemp(prefix="ezmd-job-"))
    try:
        body = workdir / "input"
        services.blobs.download(row.blob_input or input_key(job_id), body)
        if row.input_kind == "url" and _detect_fetched(services, job_id, body) is None:
            return
        row = jobs.require(job_id)
        jobs.progress(job_id, 15, "Converting")
        options = json.loads(row.options_json or "{}")
        max_seconds = float(settings.queue_timeout(row.queue))
        req = ChildRequest(
            input_path=str(body),
            out_path=str(workdir / "result.json"),
            display=row.input_display,
            kind=row.input_kind,
            url=row.input_url,
            declared_mime=row.declared_mime,
            convert_options=dict(options.get("convert", {})),
            converter_id=row.converter_id,
            max_seconds=max_seconds,
            mem_mb=settings.media_job_mem_mb if row.queue == q.MEDIA else settings.job_mem_mb,
            max_bytes=max(row.input_size or 0, settings.max_upload_bytes),
            max_result_bytes=settings.max_result_bytes,
        )

        def tick(elapsed: float) -> None:
            pct = 15 + int(70 * min(1.0, elapsed / max(1.0, max_seconds)))
            jobs.progress(job_id, pct, f"Converting ({int(elapsed)} s)")

        outcome = run_isolated(req, on_tick=tick)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
    if outcome.status == "fetch_required":
        follow_fetch_required(services, job_id, outcome.fetch_url, outcome.fetch_depth)
        return
    if outcome.status != "ok" or outcome.result_json is None:
        jobs.fail(job_id, outcome.code or "conversion_failed", outcome.message or "Conversion failed.")
        return
    _finish(services, job_id, outcome.result_json)


def warning_codes(warnings: list[Any]) -> list[str]:
    """Canonical warning codes in first-seen order, without duplicates (unknown codes become `other`)."""
    from ezmd.warnings.codes import normalize_code

    seen: dict[str, None] = {}
    for w in warnings:
        try:
            code = normalize_code(str(w.kind)).value
        except ValueError:
            code = "other"
        seen.setdefault(code, None)
    return list(seen)


def _finish(services: Services, job_id: str, result_json: str) -> None:
    from ezmd.ir import ConversionResult

    jobs = services.jobs
    result = ConversionResult.model_validate_json(result_json)
    services.blobs.put_bytes(ir_key(job_id), result_json.encode("utf-8"))
    warnings = result.all_warnings
    codes = warning_codes(warnings)
    record_conversion(services.state, result.converter_id, result.metrics.duration_seconds, codes)
    row = jobs.transition(
        job_id,
        RENDERING,
        progress=90,
        blob_ir=ir_key(job_id),
        content_hash=result.document.content_hash,
        converter_id=result.converter_id,
        ir_cache_key=ircache.ir_cache_key(str(result.document.schema_version), result.converter_id),
        mime=result.input_ref.mime,
        warnings_count=len(warnings),
        warning_codes=json.dumps(codes),
        truncated=result.truncated,
        metrics_json=result.metrics.model_dump_json(),
    )
    for w in warnings[:MAX_WARNING_EVENTS]:
        jobs.warning(job_id, w.model_dump(mode="json"))
    options = json.loads(row.options_json or "{}")
    try:
        rendered = render_cached(
            services.blobs,
            job_id,
            ir_key(job_id),
            row.profile,
            "md",
            options.get("render", {}),
            public_mode=services.settings.public_mode,
        )
    except RenderUnavailable:
        jobs.fail(job_id, "conversion_failed", "Rendering is not available on this instance.")
        return
    except Exception:
        log.exception("render failed", extra={"job_id": job_id})
        jobs.fail(job_id, "conversion_failed", "Rendering failed.")
        return
    jobs.transition(
        job_id,
        DONE,
        blob_result_prefix=f"jobs/{job_id}/results/",
        event_data={"tokens": rendered.tokens, "warnings_count": len(warnings)},
    )


# ---------------------------------------------------------------------------
# RQ entry points
# ---------------------------------------------------------------------------

_rq_services: Services | None = None


def _services() -> Services:
    global _rq_services
    if _rq_services is None:
        from ezmd_api.logs import configure_logging
        from ezmd_api.services import build_services

        settings = Settings()
        configure_logging(settings)
        _rq_services = build_services(settings)
        _rq_services.db.ensure_schema()
    return _rq_services


def rq_entry(job_id: str) -> None:
    """What RQ executes. The payload is the job id only."""
    process_job(_services(), job_id)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="ezmd-worker", description="Run an ezmd RQ worker.")
    parser.add_argument("--queues", nargs="+", default=[q.DEFAULT], choices=list(q.RQ_QUEUES))
    parser.add_argument("--burst", action="store_true", help="exit when the queues are empty")
    args = parser.parse_args(argv)
    from rq import Queue, Worker

    services = _services()
    queues = [Queue(name, connection=services.redis) for name in args.queues]
    Worker(queues, connection=services.redis).work(burst=args.burst, with_scheduler=False)


if __name__ == "__main__":
    main()
