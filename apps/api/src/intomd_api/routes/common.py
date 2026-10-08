"""Helpers shared by the route modules."""

from __future__ import annotations

import json
from typing import Any

from fastapi import Request
from pydantic import ValidationError

from intomd_api.auth import Caller
from intomd_api.db import JobRow
from intomd_api.errors import ApiError
from intomd_api.jobs import FAILED, JobGone
from intomd_api.options import validate_client_options
from intomd_api.rendering import validate_profile
from intomd_api.services import Services
from intomd_api.util import canonical_json, is_job_id


def services_of(request: Request) -> Services:
    services: Services = request.app.state.services
    return services


def parse_options(raw: Any, caller: Caller, services: Services, default_profile: str = "full") -> tuple[str, str]:
    """Validate client options. Returns (profile, canonical options_json) where options_json holds
    `{"convert": {...}, "render": {...}}`. Caps are clamped to the caller's limits."""
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ApiError("invalid_request", "`options` must be a JSON object.")
    opts = dict(raw)
    profile = opts.pop("profile", default_profile)
    if not isinstance(profile, str):
        raise ApiError("invalid_request", "`profile` must be a string.")
    render = {k: opts.pop(k) for k in list(opts) if "." in k}
    try:
        convert = validate_client_options(opts)
        validate_profile(profile, render)
    except ValidationError as e:
        fields = [{"field": ".".join(str(p) for p in err["loc"]), "problem": err["msg"]} for err in e.errors()[:20]]
        raise ApiError("invalid_request", "Invalid conversion options.", detail={"fields": fields}) from None
    except (ValueError, TypeError) as e:
        raise ApiError("invalid_request", f"Invalid profile options: {str(e)[:200]}") from None
    s = services.settings
    key = caller.api_key
    # Keyed callers get their key's limits, not the anonymous caps (D-0017 item 6).
    max_pages = int(key.max_pages) if key is not None else s.anon_max_pages
    max_duration = float(key.max_audio_seconds if key is not None else s.anon_max_duration_s)
    convert["max_pages"] = min(int(convert.get("max_pages", max_pages)), max_pages)
    convert["max_duration_seconds"] = min(float(convert.get("max_duration_seconds", max_duration)), max_duration)
    return profile, canonical_json({"convert": convert, "render": render})


def load_json_field(raw: str | None, name: str) -> Any:
    if raw is None or raw.strip() == "":
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        raise ApiError("invalid_request", f"Form field `{name}` must be valid JSON.") from None


def job_for_caller(services: Services, job_id: str, caller: Caller) -> JobRow:
    """The job id is the capability; keyed jobs additionally require the same key. Mismatches look
    exactly like a missing job so ids cannot be probed."""
    if not is_job_id(job_id):
        raise ApiError("not_found", "Job not found.")
    row = services.jobs.get(job_id)
    if row is None or (row.api_key_id is not None and row.api_key_id != caller.key_id):
        raise ApiError("not_found", "Job not found.")
    return row


def max_upload_for(caller: Caller, services: Services) -> int:
    if caller.api_key is not None:
        return int(caller.api_key.max_upload_bytes)
    return services.settings.max_upload_bytes


def enqueue_or_fail(services: Services, job_id: str, queue: str) -> None:
    try:
        rq_id = services.queue.enqueue(job_id, queue, timeout_s=services.settings.queue_timeout(queue))
    except Exception as e:
        services.jobs.fail(job_id, "queue_unavailable", "The job queue is unavailable.")
        raise ApiError("queue_unavailable", "The job queue is unavailable.", headers={"Retry-After": "30"}) from e
    if rq_id:
        try:
            services.jobs.update(job_id, rq_job_id=rq_id)
        except JobGone:
            pass


def job_error(row: JobRow) -> ApiError:
    if row.state == FAILED:
        code = row.error_code or "conversion_failed"
        return ApiError(code, row.error_message or "Conversion failed.")
    return ApiError("job_not_ready", "The job is not done yet.", detail={"state": row.state})
