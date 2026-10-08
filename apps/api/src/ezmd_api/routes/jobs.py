"""Job routes: state, SSE events, results, attachments, supply, delete (docs/spec/part1.md 7.3)."""

from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from ezmd_api import queue as q
from ezmd_api.apidoc import OPTIONAL_API_KEY, errors, rate_limit_headers
from ezmd_api.auth import CallerDep
from ezmd_api.errors import ApiError
from ezmd_api.jobs import DONE, NEEDS_USER_ACTION, QUEUED, TERMINAL_EVENT_STATES, JobStore, result_url
from ezmd_api.purge import purge_job
from ezmd_api.ratelimit import limit_result_fetch, release_sse_slot, sse_slot
from ezmd_api.rendering import (
    FORMATS,
    PROFILES,
    RENDER_TIME_KEYS,
    RenderUnavailable,
    attachment_index,
    attachment_media_type,
    render_cached,
    safe_attachment_path,
    validate_profile,
)
from ezmd_api.routes.common import enqueue_or_fail, job_for_caller, load_json_field, max_upload_for, services_of
from ezmd_api.schemas import JobOut, SupplyCaptions, job_out
from ezmd_api.services import Services
from ezmd_api.state import Event
from ezmd_api.uploads import parse_multipart
from ezmd_api.worker import input_key

router = APIRouter(tags=["jobs"])

# Module-level so tests can shorten them.
SSE_KEEPALIVE_SECONDS = 15.0
SSE_MAX_SECONDS = 3600.0
SSE_POLL_SECONDS = 1.0
_TERMINAL_EVENTS = ("done", "failed", "needs_user_action")
_RESERVED_QUERY = frozenset({"profile", "format"})
_AUTH = {"security": OPTIONAL_API_KEY}
_JOB_ID_DOC = "The job id returned by POST /v1/convert"


@router.get(
    "/v1/jobs/{job_id}",
    response_model=JobOut,
    operation_id="getJob",
    summary="Job state and metadata",
    description=(
        "State, progress, input metadata, warning codes, and, depending on the state, `needs_action` (what the "
        "client must supply) or `error`. Unknown ids and ids owned by another API key both return 404."
    ),
    responses=errors("unauthorized", "forbidden", "not_found"),
    openapi_extra=_AUTH,
)
def get_job(job_id: str, request: Request, caller: CallerDep) -> JobOut:
    return job_out(job_for_caller(services_of(request), job_id, caller))


def _sse(ev: Event) -> bytes:
    return f"event: {ev.event}\nid: {ev.id}\ndata: {json.dumps(ev.data, separators=(',', ':'))}\n\n".encode()


def _synthetic_terminal(services: Services, job_id: str) -> Event | None:
    """When the buffer was lost (state backend restart), derive the terminal event from the row."""
    row = services.jobs.get(job_id)
    if row is None or row.state not in TERMINAL_EVENT_STATES:
        return None
    if row.state == DONE:
        return Event(0, "done", {"result_url": result_url(job_id, row.profile), "warnings_count": row.warnings_count})
    if row.state == NEEDS_USER_ACTION:
        return Event(0, "needs_user_action", JobStore.needs_action_payload(row) or {})
    return Event(0, "failed", JobStore.error_payload(row))


async def _event_stream(
    request: Request, services: Services, job_id: str, last_id: int, slot: str
) -> AsyncIterator[bytes]:
    sub = services.state.subscribe(job_id)
    started = last_ping = time.monotonic()
    try:
        while True:
            events = services.state.events_since(job_id, last_id)
            for ev in events:
                last_id = max(last_id, ev.id)
                yield _sse(ev)
                if ev.event in _TERMINAL_EVENTS:
                    return
            if not events:
                synthetic = _synthetic_terminal(services, job_id)
                if synthetic is not None and not services.state.events_since(job_id, last_id):
                    yield _sse(synthetic)
                    return
            now = time.monotonic()
            if now - started >= SSE_MAX_SECONDS or await request.is_disconnected():
                return
            if now - last_ping >= SSE_KEEPALIVE_SECONDS:
                last_ping = now
                yield b": keepalive\n\n"
            timeout = min(SSE_POLL_SECONDS, SSE_KEEPALIVE_SECONDS)
            await run_in_threadpool(sub.wait, timeout)
    finally:
        sub.close()
        release_sse_slot(services, slot)


@router.get(
    "/v1/jobs/{job_id}/events",
    operation_id="streamJobEvents",
    summary="Server-sent events: progress, state, warning, done, failed, needs_user_action",
    description=(
        "A `text/event-stream` of numbered events: `state`, `progress`, `warning` (a Warning JSON), and one terminal "
        "`done`, `failed`, or `needs_user_action`, after which the stream closes. A `: keepalive` comment is sent "
        "every 15 s. Reconnect with `Last-Event-ID` (or `last_event_id`) to resume; the buffer keeps 500 events."
    ),
    response_class=StreamingResponse,
    responses={
        200: {
            "description": "The event stream",
            "content": {
                "text/event-stream": {
                    "schema": {"type": "string"},
                    "example": "event: progress"
                    + chr(10)
                    + "id: 4"
                    + chr(10)
                    + 'data: {"progress":42,"stage_message":"Converting page 84 of 200"}'
                    + chr(10),
                }
            },
        },
        **errors("unauthorized", "forbidden", "not_found", "rate_limited"),
    },
    openapi_extra=_AUTH,
)
def job_events(
    job_id: str,
    request: Request,
    caller: CallerDep,
    last_event_id: int | None = Query(None, ge=0, description="Alternative to the Last-Event-ID header"),
) -> StreamingResponse:
    services = services_of(request)
    job_for_caller(services, job_id, caller)
    header = request.headers.get("last-event-id", "")
    last_id = int(header) if header.isdigit() else (last_event_id or 0)
    slot = sse_slot(request, caller)
    return StreamingResponse(
        _event_stream(request, services, job_id, last_id, slot),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _overrides_from_query(request: Request) -> dict[str, Any]:
    """`cursor` plus flat (`max_tokens`) and dotted (`chunks.chunk_tokens`) profile keys. Unknown keys
    are rejected by the renderer's ValueError (400)."""
    out: dict[str, Any] = {}
    for key, value in request.query_params.items():
        if key in _RESERVED_QUERY:
            continue
        out[key] = value if key in RENDER_TIME_KEYS else _coerce(value)
    return out


def _coerce(value: str) -> Any:
    low = value.lower()
    if low in ("true", "false"):
        return low == "true"
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value


@router.get(
    "/v1/jobs/{job_id}/result",
    operation_id="getJobResult",
    response_class=Response,
    summary="Rendered output",
    description=(
        "The job's output in any profile and format, rendered from the cached IR (other profiles render on demand "
        "without re-converting). Extra query keys are profile overrides, flat (`max_tokens=2000`) or dotted "
        "(`chunks.chunk_tokens=512`). Markdown responses carry `X-Markdown-Tokens`, `X-Ezmd-Truncated`, "
        "`X-Ezmd-Warnings`, and `X-Ezmd-Injection-Risk`. Returns 409 until the job is done."
    ),
    responses={
        200: {
            "description": "The rendered result",
            "content": {
                "text/markdown": {"schema": {"type": "string"}, "example": "---" + chr(10) + "title: Notes" + chr(10)},
                "application/json": {"schema": {"type": "object"}},
                "text/plain": {"schema": {"type": "string"}},
                "application/zip": {"schema": {"type": "string", "format": "binary"}},
            },
            "headers": {
                "X-Markdown-Tokens": {"description": "Token count of the body", "schema": {"type": "integer"}},
                "X-Ezmd-Truncated": {"description": "true when content was cut", "schema": {"type": "string"}},
                "X-Ezmd-Warnings": {"description": "Number of warnings", "schema": {"type": "integer"}},
                **rate_limit_headers(),
            },
        },
        **errors("unauthorized", "forbidden", "not_found", "job_not_ready", "rate_limited", "not_implemented"),
    },
    openapi_extra=_AUTH,
)
def job_result(
    job_id: str,
    request: Request,
    caller: CallerDep,
    profile: str | None = Query(
        None, description="full | compact | rag | agent (default: the job's profile)", examples=["rag"]
    ),
    format: str = Query("md", description="md | json | txt | zip | docx (501)", examples=["md"]),
    cursor: str | None = Query(
        None, description="Opaque pagination cursor from a previous response; other query keys are profile overrides"
    ),
) -> Response:
    services = services_of(request)
    limit_result_fetch(request, caller)
    row = job_for_caller(services, job_id, caller)
    if format == "docx":
        raise ApiError("not_implemented", "DOCX output is not available yet.")
    if format not in FORMATS:
        raise ApiError("invalid_request", f"Unknown format {format!r}; expected one of {', '.join(FORMATS)}.")
    prof = profile or row.profile
    if prof not in PROFILES:
        raise ApiError("invalid_request", f"Unknown profile {prof!r}.")
    if row.state != DONE or not row.blob_ir:
        raise ApiError("job_not_ready", "The job is not done yet.", detail={"state": row.state})
    query_overrides = _overrides_from_query(request)
    if cursor is not None:
        query_overrides["cursor"] = cursor
    profile_keys = {k: v for k, v in query_overrides.items() if k not in RENDER_TIME_KEYS}
    if profile_keys:
        overrides = query_overrides
    else:
        stored = json.loads(row.options_json or "{}").get("render", {})
        overrides = {**(dict(stored) if prof == row.profile else {}), **query_overrides}
    if query_overrides:
        try:
            validate_profile(prof, overrides)
        except (ValueError, TypeError) as e:
            raise ApiError("invalid_request", f"Invalid profile override: {str(e)[:200]}") from None
    try:
        rendered = render_cached(
            services.blobs, job_id, row.blob_ir, prof, format, overrides, public_mode=services.settings.public_mode
        )
    except RenderUnavailable:
        raise ApiError("conversion_failed", "Rendering is not available on this instance.") from None
    except ValueError as e:
        raise ApiError("invalid_request", f"Invalid render option: {str(e)[:200]}") from None
    if services.settings.retention_hours == 0:
        purge_job(services, job_id)
    return Response(rendered.body, media_type=rendered.media_type, headers=rendered.headers(format, job_id))


@router.get(
    "/v1/jobs/{job_id}/attachments/{path:path}",
    operation_id="getJobAttachment",
    response_class=Response,
    summary="CSV sidecars and extracted images",
    description=(
        "A file the conversion produced (table CSVs, extracted images), by the relative path listed in the sidecar. "
        "Images are served inline; everything else as an attachment with `nosniff`."
    ),
    responses={
        200: {
            "description": "The attachment bytes",
            "content": {"application/octet-stream": {"schema": {"type": "string", "format": "binary"}}},
        },
        **errors("unauthorized", "forbidden", "not_found", "rate_limited"),
    },
    openapi_extra=_AUTH,
)
def job_attachment(job_id: str, path: str, request: Request, caller: CallerDep) -> Response:
    services = services_of(request)
    limit_result_fetch(request, caller)
    row = job_for_caller(services, job_id, caller)
    rel = safe_attachment_path(path)
    if row.state != DONE or rel is None:
        raise ApiError("not_found", "Attachment not found.")
    index = attachment_index(services.blobs, job_id)
    if rel not in index:
        raise ApiError("not_found", "Attachment not found.")
    media_type, inline = attachment_media_type(index[rel])
    filename = rel.rsplit("/", 1)[-1]
    disposition = "inline" if inline else "attachment"
    data = services.blobs.get_bytes(f"jobs/{job_id}/attachments/{rel}")
    return Response(
        data,
        media_type=media_type,
        headers={"Content-Disposition": f'{disposition}; filename="{filename}"', "X-Content-Type-Options": "nosniff"},
    )


@router.post(
    "/v1/jobs/{job_id}/supply",
    status_code=202,
    response_model=JobOut,
    operation_id="supplyJobInput",
    summary="Supply a file or caption JSON for a needs_user_action job",
    description=(
        "When a job is in `needs_user_action` (for example no residential fetch node could fetch a video), upload "
        "the file as multipart `file`, or send caption JSON from the browser extension. The job returns to `queued`."
    ),
    responses=errors(
        "unauthorized",
        "forbidden",
        "not_found",
        "job_not_ready",
        "input_too_large",
        "unsupported_media_type",
        "queue_unavailable",
    ),
    openapi_extra={
        "security": OPTIONAL_API_KEY,
        "requestBody": {
            "required": True,
            "content": {
                "multipart/form-data": {
                    "schema": {"type": "object", "properties": {"file": {"type": "string", "format": "binary"}}}
                },
                "application/json": {"schema": {"$ref": "#/components/schemas/SupplyCaptions"}},
            },
        },
    },
)
async def supply(job_id: str, request: Request, caller: CallerDep) -> JSONResponse:
    services = services_of(request)
    row = job_for_caller(services, job_id, caller)
    if row.state != NEEDS_USER_ACTION:
        raise ApiError("job_not_ready", "This job is not waiting for input.", detail={"state": row.state})
    ctype = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    key = input_key(job_id)
    if ctype == "multipart/form-data":
        form = await parse_multipart(request, max_file_bytes=max_upload_for(caller, services))
        try:
            upload = form.files.get("file")
            if upload is None:
                raise ApiError("invalid_request", "Multipart body is missing the `file` part.")
            from ezmd_api.routes.convert import _detect_upload

            mime = await run_in_threadpool(_detect_upload, upload)
            load_json_field(form.fields.get("meta"), "meta")
            services.blobs.put_file(key, upload.path)
            fields: dict[str, Any] = {
                "input_kind": "bytes",
                "input_size": upload.size,
                "mime": mime,
                "declared_mime": upload.content_type,
            }
        finally:
            form.cleanup()
    elif ctype == "application/json":
        raw = await request.body()
        if len(raw) > max_upload_for(caller, services):
            raise ApiError("input_too_large", "Caption JSON is too large.")
        try:
            captions = SupplyCaptions.model_validate_json(raw)
        except ValidationError:
            raise ApiError("invalid_request", "Invalid caption JSON.") from None
        data = json.dumps(captions.model_dump(mode="json")).encode()
        services.blobs.put_bytes(key, data)
        fields = {
            "input_kind": "captions_json3",
            "input_size": len(data),
            "mime": "application/json",
            "declared_mime": "application/json",
        }
    else:
        raise ApiError("invalid_request", "Send multipart/form-data with `file`, or JSON with `captions`.")
    queue = q.queue_for_mime(fields["mime"])
    updated = services.jobs.transition(
        job_id, QUEUED, blob_input=key, queue=queue, needs_action=None, stage_message="Queued", progress=0, **fields
    )
    enqueue_or_fail(services, job_id, queue)
    return JSONResponse(job_out(updated).model_dump(mode="json"), status_code=202)


@router.delete(
    "/v1/jobs/{job_id}",
    status_code=204,
    operation_id="deleteJob",
    response_class=Response,
    summary="Purge the job and its blobs now",
    description="Deletes the job row, its input, IR, rendered results, attachments, and buffered events.",
    responses={204: {"description": "Purged"}, **errors("unauthorized", "forbidden", "not_found")},
    openapi_extra=_AUTH,
)
def delete_job(job_id: str, request: Request, caller: CallerDep) -> Response:
    services = services_of(request)
    job_for_caller(services, job_id, caller)
    purge_job(services, job_id)
    return Response(status_code=204)
