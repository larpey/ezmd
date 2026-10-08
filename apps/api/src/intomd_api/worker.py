"""intomd_api.worker: RQ worker entry and the job runner (docs/spec/part1.md sections 7.1, 7.2, 8.1).

`process_job(services, job_id)` drives one job through fetching, converting (in a sandboxed spawn
child, see `isolation.py`), IR caching, and rendering of the requested profile. RQ calls
`rq_entry(job_id)`; inline mode calls `process_job` on a thread. Run a worker with
`python -m intomd_api.worker --queues default media` (or `fetch`).
"""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from intomd_api import queue as q
from intomd_api.isolation import ChildRequest, run_isolated
from intomd_api.jobs import (
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
from intomd_api.rendering import RenderUnavailable, render_cached
from intomd_api.services import Services
from intomd_api.settings import Settings
from intomd_api.util import sanitize_filename

log = logging.getLogger("intomd.api.worker")

FETCH_TIMEOUT_SECONDS = 60.0
MAX_WARNING_EVENTS = 50
_FINISHED = (DONE, FAILED, EXPIRED, NEEDS_USER_ACTION)


def input_key(job_id: str) -> str:
    return f"jobs/{job_id}/input"


def ir_key(job_id: str) -> str:
    return f"jobs/{job_id}/ir.json"


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
        if not _fetch(services, job_id):
            return
    _convert(services, job_id)


def _fetch(services: Services, job_id: str) -> bool:
    """Fetch the URL body into the blob store. Returns True when conversion should continue here."""
    from intomd.core import netguard
    from intomd.detect import detect, is_executable
    from intomd.inputs import InputRef

    jobs, settings = services.jobs, services.settings
    row = jobs.require(job_id)
    if row.state == QUEUED:
        row = jobs.transition(job_id, FETCHING, stage_message="Fetching")
    policy = netguard.PlatformPolicy.load(settings.platforms_file) if settings.platforms_file else None
    url = row.input_url or ""
    try:
        res = netguard.fetch(
            url,
            max_bytes=settings.max_url_bytes,
            total_timeout=FETCH_TIMEOUT_SECONDS,
            policy=policy,
            allow_private=settings.allow_private_networks,
        )
    except netguard.ResidentialOnly:
        route_residential(services, job_id)
        return False
    except netguard.ResponseTooLarge:
        jobs.fail(job_id, "input_too_large", f"The page exceeds the {settings.anon_max_html_mb} MB fetch limit.")
        return False
    except netguard.NetguardError as e:
        code = e.code if e.code in ("url_blocked", "platform_disabled") else "fetch_failed"
        messages = {
            "url_blocked": "This URL is not allowed.",
            "platform_disabled": "This site is disabled on this instance.",
            "fetch_failed": "The URL could not be fetched.",
        }
        jobs.fail(job_id, code, messages[code])
        return False
    name = sanitize_filename(urlsplit(res.url).path.rsplit("/", 1)[-1], fallback="download")
    probe = InputRef.from_bytes(res.body, filename=name, declared_mime=res.content_type)
    mime = detect(probe).mime
    if is_executable(mime):
        jobs.fail(job_id, "unsupported_media_type", "Executable files are not accepted.")
        return False
    services.blobs.put_bytes(input_key(job_id), res.body)
    jobs.update(
        job_id, blob_input=input_key(job_id), mime=mime, declared_mime=res.content_type, input_size=len(res.body)
    )
    jobs.transition(job_id, CONVERTING, stage_message="Queued for conversion", progress=10)
    target = q.queue_for_mime(mime)
    if target == q.MEDIA and services.queue.mode == "rq":
        jobs.update(job_id, queue=target)
        rq_id = services.queue.enqueue(job_id, target, timeout_s=settings.queue_timeout(target))
        jobs.update(job_id, rq_job_id=rq_id)
        return False
    return True


def route_residential(services: Services, job_id: str) -> None:
    """Hand the job to the fetch-node queue (fetch nodes claim it from the job store)."""
    row = services.jobs.require(job_id)
    fields: dict[str, Any] = {"queue": q.FETCH_RESIDENTIAL, "claim_attempts": 0, "claim_expires_at": None}
    message = "Waiting for a residential fetch node"
    if row.state == FETCHING:
        services.jobs.update(job_id, stage_message=message, **fields)
    else:
        services.jobs.transition(job_id, FETCHING, stage_message=message, **fields)


def _convert(services: Services, job_id: str) -> None:
    jobs, settings = services.jobs, services.settings
    row = jobs.require(job_id)
    if row.state in (QUEUED, FETCHING):
        row = jobs.transition(job_id, CONVERTING)
    jobs.progress(job_id, 15, "Converting")
    options = json.loads(row.options_json or "{}")
    max_seconds = float(settings.queue_timeout(row.queue))
    workdir = Path(tempfile.mkdtemp(prefix="intomd-job-"))
    try:
        body = workdir / "input"
        services.blobs.download(row.blob_input or input_key(job_id), body)
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
        )

        def tick(elapsed: float) -> None:
            pct = 15 + int(70 * min(1.0, elapsed / max(1.0, max_seconds)))
            jobs.progress(job_id, pct, f"Converting ({int(elapsed)} s)")

        outcome = run_isolated(req, on_tick=tick)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
    if outcome.status == "fetch_required":
        if outcome.residential:
            route_residential(services, job_id)
        else:
            jobs.fail(job_id, "fetch_failed", "The input needs a fetch that this job cannot perform.")
        return
    if outcome.status != "ok" or outcome.result_json is None:
        jobs.fail(job_id, outcome.code or "conversion_failed", outcome.message or "Conversion failed.")
        return
    _finish(services, job_id, outcome.result_json)


def _finish(services: Services, job_id: str, result_json: str) -> None:
    from intomd.ir import ConversionResult

    jobs = services.jobs
    result = ConversionResult.model_validate_json(result_json)
    services.blobs.put_bytes(ir_key(job_id), result_json.encode("utf-8"))
    warnings = result.all_warnings
    row = jobs.transition(
        job_id,
        RENDERING,
        progress=90,
        blob_ir=ir_key(job_id),
        content_hash=result.document.content_hash,
        converter_id=result.converter_id,
        mime=result.input_ref.mime,
        warnings_count=len(warnings),
        truncated=result.truncated,
        metrics_json=result.metrics.model_dump_json(),
    )
    for w in warnings[:MAX_WARNING_EVENTS]:
        jobs.warning(job_id, w.model_dump(mode="json"))
    options = json.loads(row.options_json or "{}")
    try:
        rendered = render_cached(services.blobs, job_id, ir_key(job_id), row.profile, "md", options.get("render", {}))
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
        from intomd_api.logs import configure_logging
        from intomd_api.services import build_services

        settings = Settings()
        configure_logging(settings)
        _rq_services = build_services(settings)
        _rq_services.db.create_all()
    return _rq_services


def rq_entry(job_id: str) -> None:
    """What RQ executes. The payload is the job id only."""
    process_job(_services(), job_id)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="intomd-worker", description="Run an intomd RQ worker.")
    parser.add_argument("--queues", nargs="+", default=[q.DEFAULT], choices=list(q.RQ_QUEUES))
    parser.add_argument("--burst", action="store_true", help="exit when the queues are empty")
    args = parser.parse_args(argv)
    from rq import Queue, Worker

    services = _services()
    queues = [Queue(name, connection=services.redis) for name in args.queues]
    Worker(queues, connection=services.redis).work(burst=args.burst, with_scheduler=False)


if __name__ == "__main__":
    main()
