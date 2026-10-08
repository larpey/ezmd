"""Fetch-node routes: claim, heartbeat, upload, fail (docs/spec/part1.md 7.2-7.4).

Mounted only when INTOMD_FETCH_NODE_SECRET is set. Every route requires the bearer secret AND a
source address inside INTOMD_FETCH_NODE_CIDR. Claims are bound to a per-job claim token (stored
hashed) and expire after 10 minutes without an upload or heartbeat.
"""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy import or_, select

from intomd_api import queue as q
from intomd_api.auth import require_fetch_node
from intomd_api.db import JobRow
from intomd_api.errors import ApiError
from intomd_api.jobs import CONVERTING, FETCHING
from intomd_api.purge import MAX_CLAIM_ATTEMPTS, needs_upload
from intomd_api.ratelimit import enforce
from intomd_api.routes.common import enqueue_or_fail, load_json_field, services_of
from intomd_api.schemas import FetchNodeClaimRequest, FetchNodeClaimResponse, FetchNodeFail, FetchNodeHeartbeat
from intomd_api.services import Services
from intomd_api.uploads import parse_multipart
from intomd_api.util import iso, keyed_hash, new_claim_token, utcnow
from intomd_api.worker import input_key

router = APIRouter(prefix="/v1/fetch-node", tags=["fetch-node"], dependencies=[Depends(require_fetch_node)])

CLAIM_TTL = timedelta(minutes=10)
MEDIA_MAX_BYTES = 500 * 1024 * 1024


def _claim_hash(services: Services, token: str) -> str:
    return keyed_hash(services.settings.ip_salt, "claim|" + token)


def _job_for_claim(services: Services, token: str) -> JobRow:
    digest = _claim_hash(services, token)
    with services.db.session() as s:
        row = s.execute(select(JobRow).where(JobRow.claim_token_hash == digest)).scalar_one_or_none()
    if row is None or row.state != FETCHING or row.claim_expires_at is None:
        raise ApiError("forbidden", "The claim token is invalid or expired.")
    from intomd_api.util import as_utc

    if as_utc(row.claim_expires_at) <= utcnow():
        raise ApiError("forbidden", "The claim token is invalid or expired.")
    return row


@router.post(
    "/claim",
    response_model=FetchNodeClaimResponse,
    responses={204: {"description": "The queue is empty"}},
    summary="Claim the next residential fetch job",
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
    )
    return JSONResponse(resp.model_dump(mode="json"))


@router.post("/heartbeat", status_code=204, summary="Liveness and capabilities; extends an active claim")
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
    summary="Upload fetched media for a claimed job",
    openapi_extra={
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
        }
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
        from intomd_api.routes.convert import _detect_upload

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


@router.post("/fail", status_code=204, summary="Report a failed fetch with a reason code")
def fail(body: FetchNodeFail, request: Request) -> Response:
    services = services_of(request)
    row = _job_for_claim(services, body.claim_token)
    if row.claim_attempts < MAX_CLAIM_ATTEMPTS:
        services.jobs.update(row.id, claim_token_hash=None, claim_expires_at=None, claim_node_id=None)
    else:
        needs_upload(services, row.id, f"The residential fetch failed ({body.reason_code}).")
    return Response(status_code=204)
