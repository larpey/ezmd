"""intomd_api.fetching: the fetch half of a job (docs/spec/part1.md 7.2, 8.3; DECISIONS.md D-0017).

The `fetch` queue worker is the only process with general egress, so it never parses what it
downloads: `fetch_job` validates and fetches the URL through `intomd.core.netguard`, stores the raw
body, and re-enqueues the job to `default` (or `media`, by the declared content type). Detection and
conversion happen in the egress-less workers.

`follow_fetch_required` handles a converter's `FetchRequired`: the requested URL is re-validated
with netguard and the platform policy (the child's `residential` flag is ignored), the fetch depth
is capped at `intomd.inputs.MAX_FETCH_DEPTH`, and the new URL is stored on the job before it goes
back to the fetch queue.
"""

from __future__ import annotations

import logging
from typing import Any

from intomd_api import queue as q
from intomd_api.db import ApiKeyRow
from intomd_api.fetchpolicy import DISABLED, RESIDENTIAL_ONLY, policy_state
from intomd_api.jobs import CONVERTING, FETCHING, QUEUED, JobGone
from intomd_api.services import Services
from intomd_api.util import strip_fragment

log = logging.getLogger("intomd.api.fetch")

FETCH_TIMEOUT_SECONDS = 60.0
DEFAULT_MAX_FETCH_DEPTH = 2
_FETCH_MESSAGES = {
    "url_blocked": "This URL is not allowed.",
    "platform_disabled": "This site is disabled on this instance.",
    "fetch_failed": "The URL could not be fetched.",
}


def input_key(job_id: str) -> str:
    return f"jobs/{job_id}/input"


def ir_key(job_id: str) -> str:
    return f"jobs/{job_id}/ir.json"


def max_fetch_depth() -> int:
    try:
        from intomd import inputs
    except ImportError:  # pragma: no cover - core is always installed with the API
        return DEFAULT_MAX_FETCH_DEPTH
    value = getattr(inputs, "MAX_FETCH_DEPTH", DEFAULT_MAX_FETCH_DEPTH)
    return value if isinstance(value, int) else DEFAULT_MAX_FETCH_DEPTH


def hand_off(services: Services, job_id: str, queue: str) -> None:
    """Move the job to `queue` and enqueue it there. Fails the job if the queue is down."""
    services.jobs.update(job_id, queue=queue)
    try:
        rq_id = services.queue.enqueue(job_id, queue, timeout_s=services.settings.queue_timeout(queue))
    except Exception:
        log.exception("enqueue failed", extra={"job_id": job_id})
        services.jobs.fail(job_id, "queue_unavailable", "The job queue is unavailable.")
        return
    if rq_id:
        try:
            services.jobs.update(job_id, rq_job_id=rq_id)
        except JobGone:
            pass


def route_residential(services: Services, job_id: str) -> None:
    """Hand the job to the fetch-node queue (fetch nodes claim it from the job store)."""
    row = services.jobs.require(job_id)
    fields: dict[str, Any] = {"queue": q.FETCH_RESIDENTIAL, "claim_attempts": 0, "claim_expires_at": None}
    message = "Waiting for a residential fetch node"
    if row.state == FETCHING:
        services.jobs.update(job_id, stage_message=message, **fields)
    else:
        services.jobs.transition(job_id, FETCHING, stage_message=message, **fields)


def fetch_job(services: Services, job_id: str) -> None:
    """Fetch the URL body into the blob store, then re-enqueue for conversion. Never parses."""
    from intomd.core import netguard

    jobs, settings = services.jobs, services.settings
    row = jobs.require(job_id)
    if row.state == QUEUED:
        row = jobs.transition(job_id, FETCHING, stage_message="Fetching")
    policy = netguard.PlatformPolicy.load(settings.platforms_file) if settings.platforms_file else None
    try:
        res = netguard.fetch(
            row.input_url or "",
            max_bytes=settings.max_url_bytes,
            total_timeout=FETCH_TIMEOUT_SECONDS,
            policy=policy,
            allow_private=settings.allow_private_networks,
        )
    except netguard.ResidentialOnly:
        if not _key_allows_residential(services, row.api_key_id):
            jobs.fail(job_id, "forbidden", "This API key may not use residential fetches.")
            return
        route_residential(services, job_id)
        return
    except netguard.ResponseTooLarge:
        jobs.fail(job_id, "input_too_large", f"The page exceeds the {settings.anon_max_html_mb} MB fetch limit.")
        return
    except netguard.NetguardError as e:
        code = e.code if e.code in ("url_blocked", "platform_disabled") else "fetch_failed"
        jobs.fail(job_id, code, _FETCH_MESSAGES[code])
        return
    services.blobs.put_bytes(input_key(job_id), res.body)
    jobs.transition(
        job_id,
        CONVERTING,
        stage_message="Queued for conversion",
        progress=10,
        blob_input=input_key(job_id),
        mime=None,
        declared_mime=res.content_type,
        input_size=len(res.body),
    )
    hand_off(services, job_id, q.queue_for_mime(res.content_type))


def _key_allows_residential(services: Services, api_key_id: str | None) -> bool:
    if api_key_id is None:
        return True  # anonymous jobs reach residential only through a residential_only policy
    with services.db.session() as s:
        key = s.get(ApiKeyRow, api_key_id)
        return bool(key is not None and key.residential_allowed)


def follow_fetch_required(services: Services, job_id: str, url: str | None, child_depth: int) -> None:
    """Act on a converter's FetchRequired without trusting the child (D-0017 item 4)."""
    from intomd.core import netguard

    jobs, settings = services.jobs, services.settings
    row = jobs.require(job_id)
    depth = max(int(row.fetch_depth or 0) + 1, child_depth)
    limit = max_fetch_depth()
    if depth > limit:
        jobs.fail(job_id, "fetch_depth_exceeded", f"The input asked for more than {limit} nested fetches.")
        return
    if not isinstance(url, str) or not url:
        jobs.fail(job_id, "fetch_failed", "The input needs a fetch that this job cannot perform.")
        return
    try:
        validated = netguard.validate_url(url, allow_private=settings.allow_private_networks)
    except netguard.UrlBlocked:
        jobs.fail(job_id, "url_blocked", _FETCH_MESSAGES["url_blocked"])
        return
    state = policy_state(settings, validated.host)
    if state == DISABLED:
        jobs.fail(job_id, "platform_disabled", _FETCH_MESSAGES["platform_disabled"])
        return
    residential = state == RESIDENTIAL_ONLY
    if residential and not _key_allows_residential(services, row.api_key_id):
        jobs.fail(job_id, "forbidden", "This API key may not use residential fetches.")
        return
    fields: dict[str, Any] = {
        "input_url": strip_fragment(url),
        "input_kind": "url",
        "blob_input": None,
        "mime": None,
        "declared_mime": None,
        "input_size": None,
        "fetch_depth": depth,
    }
    if residential:
        jobs.update(job_id, **fields)
        route_residential(services, job_id)
        return
    jobs.transition(job_id, FETCHING, stage_message="Fetching", **fields)
    hand_off(services, job_id, q.FETCH)
