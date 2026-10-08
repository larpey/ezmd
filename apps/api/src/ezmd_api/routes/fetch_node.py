"""Fetch-node routes: claim, heartbeat, upload, fail (docs/spec/part1.md 7.2-7.4).

Mounted only when EZMD_FETCH_NODE_SECRET is set. Every route requires the bearer secret AND a
source address inside EZMD_FETCH_NODE_CIDR. Claims are bound to a per-job claim token (stored
hashed) and expire after 10 minutes without an upload or heartbeat.

At claim time the VPS re-validates the job URL with netguard (and resolves it) and returns the
matching `platform` and the `resolved_ip`. These are hints: the node must re-run netguard on the URL
and on every redirect itself before fetching (Phase 3), because DNS can change between the two.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy import or_, select

from ezmd_api import queue as q
from ezmd_api.apidoc import FETCH_NODE_AUTH, errors
from ezmd_api.auth import require_fetch_node
from ezmd_api.db import JobRow
from ezmd_api.errors import ApiError
from ezmd_api.fetching import input_key
from ezmd_api.fetchpolicy import platform_for
from ezmd_api.jobs import CONVERTING, FETCHING
from ezmd_api.purge import MAX_CLAIM_ATTEMPTS, needs_upload
from ezmd_api.ratelimit import enforce
from ezmd_api.routes.common import enqueue_or_fail, load_json_field, services_of
from ezmd_api.schemas import FetchNodeClaimRequest, FetchNodeClaimResponse, FetchNodeFail, FetchNodeHeartbeat
from ezmd_api.services import Services
from ezmd_api.uploads import parse_multipart
from ezmd_api.util import iso, keyed_hash, new_claim_token, utcnow

router = APIRouter(prefix="/v1/fetch-node", tags=["fetch-node"], dependencies=[Depends(require_fetch_node)])

CLAIM_TTL = timedelta(minutes=10)
MEDIA_MAX_BYTES = 500 * 1024 * 1024
_AUTH = {"security": FETCH_NODE_AUTH}
_NODE_ERRORS = ("unauthorized", "forbidden")
RESOLVER: Callable[[str, int], list[str]] | None = None
"""DNS resolver for claim-time validation; None means `netguard.system_resolver`. Tests replace it."""


class _ClaimBlocked(Exception):
    pass


def _claim_target(services: Services, url: str) -> tuple[str | None, str | None]:
    """(platform, resolved_ip) for a claimed URL. Raises _ClaimBlocked when netguard rejects it."""
    from ezmd.core import netguard

    allow_private = services.settings.allow_private_networks
    try:
        validated = netguard.validate_url(url, allow_private=allow_private)
    except netguard.UrlBlocked:
        raise _ClaimBlocked from None
    resolver = RESOLVER or netguard.system_resolver
    try:
        ip: str | None = netguard.resolve_checked(validated, resolver=resolver, allow_private=allow_private)
    except netguard.UrlBlocked:
        raise _ClaimBlocked from None
    except netguard.NetguardError:
        ip = None
    return platform_for(services.settings, validated.host), ip


def _claim_hash(services: Services, token: str) -> str:
    return keyed_hash(services.settings.ip_salt, "claim|" + token)


def _job_for_claim(services: Services, token: str) -> JobRow:
    digest = _claim_hash(services, token)
    with services.db.session() as s:
        row = s.execute(select(JobRow).where(JobRow.claim_token_hash == digest)).scalar_one_or_none()
    if row is None or row.state != FETCHING or row.claim_expires_at is None:
        raise ApiError("forbidden", "The claim token is invalid or expired.")
    from ezmd_api.util import as_utc

    if as_utc(row.claim_expires_at) <= utcnow():
        raise ApiError("forbidden", "The claim token is invalid or expired.")
    return row


@router.post(
    "/claim",
    response_model=FetchNodeClaimResponse,
    responses={204: {"description": "The queue is empty"}, **errors(*_NODE_ERRORS, "rate_limited")},
    operation_id="fetchNodeClaim",
    summary="Claim the next residential fetch job",
    description=(
        "Returns the oldest unclaimed `fetch_residential` job with a single-use claim token (valid 10 minutes, "
        "extended by heartbeats), or 204 when there is none. The URL is re-validated by the SSRF guard at claim "
        "time; `platform` and `resolved_ip` are hints the node must re-check itself."
    ),
    openapi_extra=_AUTH,
)
def claim(body: FetchNodeClaimRequest, request: Request) -> Response:
    services = services_of(request)
    s = services.settings
    enforce(request, "fetch-claim", body.node_id, s.fetch_node_claims_per_minute, 60)
    services.state.node_heartbeat(body.node_id, {"capabilities": body.capabilities})
    now = utcnow()
    token = new_claim_token()
    with services.db.session() as sess:
        stmt = (
            select(JobRow)
            .where(
                JobRow.queue == q.FETCH_RESIDENTIAL,
                JobRow.state == FETCHING,
                JobRow.claim_attempts < MAX_CLAIM_ATTEMPTS,
                or_(JobRow.claim_expires_at.is_(None), JobRow.claim_expires_at <= now),
            )
            .order_by(JobRow.created_at)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        row = sess.execute(stmt).scalar_one_or_none()
        if row is None:
            return Response(status_code=204)
        row.claim_token_hash = _claim_hash(services, token)
        row.claim_node_id = body.node_id
        row.claim_expires_at = now + CLAIM_TTL
        row.claim_attempts = (row.claim_attempts or 0) + 1
        row.stage_message = "Fetching on a residential node"
        row.updated_at = now
        job_id, url = row.id, row.input_url or ""
    try:
        platform, resolved_ip = _claim_target(services, url)
    except _ClaimBlocked:
        services.jobs.update(job_id, claim_token_hash=None, claim_expires_at=None, claim_node_id=None)
        services.jobs.fail(job_id, "url_blocked", "This URL is not allowed.")
        return Response(status_code=204)
    max_duration = min(body.max_duration_seconds or s.anon_max_duration_s, s.anon_max_duration_s)
    resp = FetchNodeClaimResponse(
        job_id=job_id,
        claim_token=token,
        url=url,
        want="audio",
        max_bytes=min(MEDIA_MAX_BYTES, s.max_upload_bytes),
        max_duration_seconds=max_duration,
        upload_url="/v1/fetch-node/upload",
        claim_expires_at=iso(now + CLAIM_TTL) or "",
        platform=platform,
        resolved_ip=resolved_ip,
    )
    return JSONResponse(resp.model_dump(mode="json"))


@router.post(
    "/heartbeat",
    status_code=204,
    operation_id="fetchNodeHeartbeat",
    response_class=Response,
    summary="Liveness and capabilities; extends an active claim",
    description="Marks the node online for 60 s and, with `claim_token`, pushes that claim's expiry 10 minutes out.",
    responses={204: {"description": "Recorded"}, **errors(*_NODE_ERRORS)},
    openapi_extra=_AUTH,
)
def heartbeat(body: FetchNodeHeartbeat, request: Request) -> Response:
    services = services_of(request)
    services.state.node_heartbeat(body.node_id, {"capabilities": body.capabilities})
    if body.claim_token:
        row = _job_for_claim(services, body.claim_token)
        services.jobs.update(row.id, claim_expires_at=utcnow() + CLAIM_TTL)
    return Response(status_code=204)


@router.post(
    "/upload",
    status_code=202,
    operation_id="fetchNodeUpload",
    response_class=Response,
    summary="Upload fetched media for a claimed job",
    description="Stores the media under the job and enqueues it on `media` (or `default`); consumes the claim token.",
    responses={
        202: {"description": "Accepted for conversion"},
        **errors(*_NODE_ERRORS, "input_too_large", "unsupported_media_type", "queue_unavailable"),
    },
    openapi_extra={
        "security": FETCH_NODE_AUTH,
        "requestBody": {
            "required": True,
            "content": {
                "multipart/form-data": {
                    "schema": {
                        "type": "object",
                        "required": ["claim_token", "media"],
                        "properties": {
                            "claim_token": {"type": "string"},
                            "media": {"type": "string", "format": "binary"},
                            "meta": {"type": "string", "description": "JSON: title, uploader, duration, ..."},
                        },
                    }
                }
            },
        },
    },
)
async def upload(request: Request) -> Response:
    services = services_of(request)
    form = await parse_multipart(
        request, max_file_bytes=min(MEDIA_MAX_BYTES, services.settings.max_upload_bytes), file_fields=("media",)
    )
    try:
        token = form.fields.get("claim_token", "")
        row = _job_for_claim(services, token)
        media = form.files.get("media")
        if media is None:
            raise ApiError("invalid_request", "Multipart body is missing the `media` part.")
        load_json_field(form.fields.get("meta"), "meta")
        from ezmd_api.routes.convert import _detect_upload

        mime = _detect_upload(media)
        services.blobs.put_file(input_key(row.id), media.path)
    finally:
        form.cleanup()
    queue = q.queue_for_mime(mime)
    services.jobs.transition(
        row.id,
        CONVERTING,
        blob_input=input_key(row.id),
        mime=mime,
        declared_mime=media.content_type,
        input_size=media.size,
        queue=queue,
        claim_token_hash=None,
        claim_expires_at=None,
        stage_message="Queued for conversion",
    )
    enqueue_or_fail(services, row.id, queue)
    return Response(status_code=202)


@router.post(
    "/fail",
    status_code=204,
    operation_id="fetchNodeFail",
    response_class=Response,
    summary="Report a failed fetch with a reason code",
    description="Returns the job to the queue once; after that the job moves to `needs_user_action`.",
    responses={204: {"description": "Recorded"}, **errors(*_NODE_ERRORS)},
    openapi_extra=_AUTH,
)
def fail(body: FetchNodeFail, request: Request) -> Response:
    services = services_of(request)
    row = _job_for_claim(services, body.claim_token)
    if row.claim_attempts < MAX_CLAIM_ATTEMPTS:
        services.jobs.update(row.id, claim_token_hash=None, claim_expires_at=None, claim_node_id=None)
    else:
        needs_upload(services, row.id, f"The residential fetch failed ({body.reason_code}).")
    return Response(status_code=204)
