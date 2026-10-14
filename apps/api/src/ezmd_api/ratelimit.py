"""ezmd_api.ratelimit: sliding-window limits and admission control (docs/spec/part1.md 7.6, 8.4).

Windows live in Redis (or memory in inline mode). The most restrictive window checked during a
request is reported in `X-RateLimit-Limit/Remaining/Reset` by the middleware in `main.py`.
"""

from __future__ import annotations

from fastapi import Request

from ezmd_api.auth import Caller
from ezmd_api.errors import ApiError
from ezmd_api.metrics import record_rate_limited
from ezmd_api.services import Services
from ezmd_api.state import RateResult

DAY = 86400
QUEUE_RETRY_AFTER_SECONDS = 30


def _services(request: Request) -> Services:
    services: Services = request.app.state.services
    return services


def rate_headers(result: RateResult) -> dict[str, str]:
    return {
        "X-RateLimit-Limit": str(result.limit),
        "X-RateLimit-Remaining": str(result.remaining),
        "X-RateLimit-Reset": str(result.reset_epoch),
    }


def _record(request: Request, result: RateResult) -> None:
    current: RateResult | None = getattr(request.state, "ratelimit", None)
    if current is None or result.remaining < current.remaining or not result.allowed:
        request.state.ratelimit = result


REFUNDED_CODES = frozenset({"rate_limited", "input_too_large", "queue_unavailable"})
"""A job-creation request that ends with one of these created nothing, so its window hits are given back."""


def enforce(request: Request, bucket: str, identity: str, limit: int, window_s: int) -> RateResult:
    result = _services(request).state.rate_hit(f"{bucket}:{window_s}:{identity}", limit, window_s)
    _record(request, result)
    if result.member:
        hits: list[RateResult] = getattr(request.state, "rate_hits", [])
        request.state.rate_hits = [*hits, result]
    if not result.allowed:
        record_rate_limited(_services(request).state, bucket)
        headers = {**rate_headers(result), "Retry-After": str(result.retry_after)}
        raise ApiError(
            "rate_limited",
            "Too many requests. Try again later.",
            detail={"reason": "rate", "limit": limit, "window_seconds": window_s},
            headers=headers,
        )
    return result


def limit_job_creation(request: Request, caller: Caller) -> None:
    services = _services(request)
    s = services.settings
    if caller.unlimited:
        return
    if caller.api_key is not None:
        key = caller.api_key
        enforce(request, "create", caller.identity, key.requests_per_window, key.window_s)
        enforce(request, "create", caller.identity, key.requests_per_day, DAY)
    else:
        enforce(request, "create", caller.identity, s.anon_ratelimit_max, s.anon_ratelimit_window_s)
        enforce(request, "create", caller.identity, s.anon_daily_max, DAY)


def refund_hits(request: Request) -> None:
    """Give back every window hit this request recorded (see REFUNDED_CODES)."""
    state = _services(request).state
    for hit in getattr(request.state, "rate_hits", []):
        state.rate_refund(hit.key, hit.member)
    request.state.rate_hits = []


def admit_job(request: Request, caller: Caller, *, created: bool = False) -> None:
    """Concurrency admission: per caller, the anonymous share of the global cap, then the global cap.

    Called twice per job (D-0051): before the row exists (`created=False`, a cheap early refusal) and
    right after it was inserted (`created=True`, the counts include it). Two parallel requests can both
    pass the first check, but whichever counts second sees both rows and is refused, so a burst never
    admits more than the limit. The caller deletes its row when the second check raises."""
    services = _services(request)
    s = services.settings

    def over(active: int, limit: int) -> bool:
        return active > limit if created else active >= limit

    if not caller.unlimited:
        if caller.api_key is not None:
            limit = caller.api_key.concurrency
            active = services.jobs.count_active(api_key_id=caller.api_key.id)
        else:
            limit = s.anon_concurrency
            active = services.jobs.count_active(client_ip_hash=caller.ip_hash)
        if over(active, limit):
            record_rate_limited(services.state, "concurrency")
            raise ApiError(
                "rate_limited",
                "Your previous conversion is still running. Try again when it finishes.",
                detail={"reason": "concurrency", "concurrent_limit": limit, "active": active},
                headers={"Retry-After": "5"},
            )
    anon_full = caller.api_key is None and over(services.jobs.count_active(anonymous=True), s.anon_active_job_cap)
    if anon_full or over(services.jobs.count_active(), s.active_job_cap):
        record_rate_limited(services.state, "active_job_cap")
        raise ApiError(
            "queue_unavailable",
            "The server is busy. Try again shortly.",
            headers={"Retry-After": str(QUEUE_RETRY_AFTER_SECONDS)},
        )


UPLOAD_SLOT_TTL_S = 3600
"""Upper bound on how long a crashed process can hold an upload slot (a slot is released in `finally`)."""


def upload_slot_key(identity: str) -> str:
    return f"upload:{identity}"


def take_upload_slot(request: Request, caller: Caller) -> str | None:
    """Reserve one in-flight upload for this caller before its body is read, so a caller cannot stream
    many large bodies to disk at once: at most its concurrency limit at a time (D-0051). Returns the slot
    key for `release_upload_slot`, or None for unlimited keys."""
    if caller.unlimited:
        return None
    services = _services(request)
    limit = caller.api_key.concurrency if caller.api_key is not None else services.settings.anon_concurrency
    key = upload_slot_key(caller.identity)
    if services.state.gauge_incr(key, UPLOAD_SLOT_TTL_S) > limit:
        services.state.gauge_decr(key)
        record_rate_limited(services.state, "upload_slot")
        raise ApiError(
            "rate_limited",
            "Another upload from you is still in progress. Try again when it finishes.",
            detail={"reason": "upload_in_progress", "concurrent_limit": limit},
            headers={"Retry-After": "5"},
        )
    return key


def release_upload_slot(request: Request, key: str | None) -> None:
    if key is not None:
        _services(request).state.gauge_decr(key)


def limit_result_fetch(request: Request, caller: Caller) -> None:
    if caller.unlimited:
        return
    s = _services(request).settings
    if caller.api_key is not None:
        enforce(request, "result", caller.identity, caller.api_key.requests_per_window, caller.api_key.window_s)
        return
    enforce(request, "result", caller.identity, s.anon_result_ratelimit_max, 60)


def sse_slot(request: Request, caller: Caller) -> str:
    """Take one SSE connection slot; the caller must release it with `release_sse_slot`."""
    services = _services(request)
    key = f"sse:{caller.identity}"
    count = services.state.gauge_incr(key, 3600)
    if not caller.unlimited and count > services.settings.anon_sse_max:
        services.state.gauge_decr(key)
        record_rate_limited(services.state, "sse")
        raise ApiError(
            "rate_limited",
            "Too many open event streams.",
            detail={"limit": services.settings.anon_sse_max},
            headers={"Retry-After": "15"},
        )
    return key


def release_sse_slot(services: Services, key: str) -> None:
    services.state.gauge_decr(key)
