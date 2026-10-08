"""POST /v1/convert: create a job from a multipart upload or a JSON URL request
(docs/spec/part1.md sections 7.1, 7.3, 8.2)."""

from __future__ import annotations

import time
from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse, Response
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from intomd_api import queue as q
from intomd_api.auth import CHALLENGE_COOKIE, Caller, CallerDep, require_url_challenge
from intomd_api.db import JobRow
from intomd_api.errors import ApiError, error_response
from intomd_api.jobs import DONE, FAILED, NEEDS_USER_ACTION, QUEUED
from intomd_api.ratelimit import admit_job, limit_job_creation
from intomd_api.rendering import FORMATS, RenderUnavailable, render_cached
from intomd_api.routes.common import (
    enqueue_or_fail,
    job_error,
    load_json_field,
    max_upload_for,
    parse_options,
    services_of,
)
from intomd_api.schemas import ConvertResponse, ConvertUrlRequest, compact_json, convert_response, job_out
from intomd_api.services import Services
from intomd_api.uploads import UploadedFile, parse_multipart
from intomd_api.util import keyed_hash, new_job_id, normalize_url, sha256_hex, strip_fragment, utcnow
from intomd_api.worker import input_key, route_residential

router = APIRouter(tags=["convert"])

MAX_WAIT_SECONDS = 60.0
_OPENAPI_BODY: dict[str, Any] = {
    "requestBody": {
        "required": True,
        "content": {
            "multipart/form-data": {
                "schema": {
                    "type": "object",
                    "required": ["file"],
                    "properties": {
                        "file": {"type": "string", "format": "binary"},
                        "options": {"type": "string", "description": "JSON object of options and profile"},
                        "profile": {"type": "string", "enum": ["full", "compact", "rag", "agent"]},
                    },
                }
            },
            "application/json": {"schema": {"$ref": "#/components/schemas/ConvertUrlRequest"}},
        },
    }
}


def _idempotency(request: Request, caller: Caller, services: Services) -> str | None:
    key = request.headers.get("idempotency-key")
    if not key:
        return None
    if len(key) > 255:
        raise ApiError("invalid_request", "Idempotency-Key must be at most 255 characters.")
    return keyed_hash(services.settings.ip_salt, f"{caller.identity}|{key}")


def _dedup_scope_ip(caller: Caller, services: Services) -> str | None:
    """Public mode never dedups anonymous requests across different client IP hashes."""
    if caller.api_key is None and services.settings.public_mode:
        return caller.ip_hash
    return None


def _find_existing(
    services: Services, caller: Caller, sha: str, options_json: str, profile: str, idem: str | None
) -> JobRow | None:
    return services.jobs.find_existing(
        api_key_id=caller.key_id,
        client_ip_hash=_dedup_scope_ip(caller, services),
        input_sha256=sha,
        options_json=options_json,
        profile=profile,
        idempotency_key=idem,
    )


def _new_row(caller: Caller, services: Services, **fields: Any) -> JobRow:
    now = utcnow()
    return JobRow(
        state=QUEUED,
        created_at=now,
        updated_at=now,
        expires_at=now + timedelta(seconds=services.settings.retention_seconds),
        client_ip_hash=caller.ip_hash,
        api_key_id=caller.key_id,
        progress=0,
        stage_message="Queued",
        warnings_count=0,
        truncated=False,
        claim_attempts=0,
        **fields,
    )


async def _wait_for(services: Services, job_id: str, timeout: float) -> JobRow | None:
    deadline = time.monotonic() + timeout
    sub = services.state.subscribe(job_id)
    try:
        while True:
            row = services.jobs.get(job_id)
            if row is None or row.state in (DONE, FAILED, NEEDS_USER_ACTION):
                return row
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return row
            await run_in_threadpool(sub.wait, min(1.0, remaining))
    finally:
        sub.close()


async def _respond(
    request: Request, services: Services, row: JobRow, *, deduplicated: bool, wait: float, fmt: str, profile: str
) -> Response:
    envelope = convert_response(row, deduplicated=deduplicated, profile=profile)
    if wait > 0:
        final = await _wait_for(services, row.id, min(wait, MAX_WAIT_SECONDS))
        if final is not None and final.state in (DONE, FAILED):
            header = {"X-Intomd-Job": compact_json(job_out(final, include_sha=False))}
            if final.state == FAILED:
                err = job_error(final)
                err.headers.update(header)
                return error_response(request, err)
            if fmt == "docx":
                raise ApiError("not_implemented", "DOCX output is not available yet.")
            try:
                overrides = _render_overrides(final)
                rendered = await run_in_threadpool(
                    render_cached, services.blobs, final.id, final.blob_ir or "", profile, fmt, overrides
                )
            except RenderUnavailable:
                raise ApiError("conversion_failed", "Rendering is not available on this instance.") from None
            headers = {**rendered.headers(fmt, final.id), **header}
            return Response(rendered.body, media_type=rendered.media_type, headers=headers)
        if final is not None:
            envelope = convert_response(final, deduplicated=deduplicated, profile=profile)
    return JSONResponse(envelope.model_dump(mode="json"), status_code=200 if deduplicated else 202)


def _render_overrides(row: JobRow) -> dict[str, Any]:
    import json

    return dict(json.loads(row.options_json or "{}").get("render", {}))


def _check_format(fmt: str) -> None:
    if fmt not in (*FORMATS, "docx"):
        raise ApiError("invalid_request", f"Unknown format {fmt!r}.")


@router.post(
    "/v1/convert",
    status_code=202,
    response_model=ConvertResponse,
    openapi_extra=_OPENAPI_BODY,
    summary="Create a conversion job from an upload (multipart) or a URL (JSON)",
)
async def create_job(
    request: Request,
    caller: CallerDep,
    wait: float = Query(0, ge=0, description="Block up to this many seconds (max 60) and return the result"),
    format: str = Query("md", description="Result format when `wait` returns a result"),
) -> Response:
    services = services_of(request)
    _check_format(format)
    limit_job_creation(request, caller)
    ctype = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if ctype == "multipart/form-data":
        return await _create_from_upload(request, services, caller, wait, format)
    if ctype == "application/json":
        return await _create_from_url(request, services, caller, wait, format)
    raise ApiError("invalid_request", "Send multipart/form-data with a `file` part, or JSON with a `url`.")


async def _create_from_upload(request: Request, services: Services, caller: Caller, wait: float, fmt: str) -> Response:
    form = await parse_multipart(request, max_file_bytes=max_upload_for(caller, services))
    try:
        upload = form.files.get("file")
        if upload is None:
            raise ApiError("invalid_request", "Multipart body is missing the `file` part.")
        options = load_json_field(form.fields.get("options"), "options") or {}
        if "profile" in form.fields and isinstance(options, dict):
            options.setdefault("profile", form.fields["profile"])
        profile, options_json = parse_options(options, caller, services)
        mime = await run_in_threadpool(_detect_upload, upload)
        idem = _idempotency(request, caller, services)
        existing = _find_existing(services, caller, upload.sha256, options_json, profile, idem)
        if existing is not None:
            return await _respond(request, services, existing, deduplicated=True, wait=wait, fmt=fmt, profile=profile)
        admit_job(request, caller)
        job_id = new_job_id()
        services.blobs.put_file(input_key(job_id), upload.path)
        queue = q.queue_for_mime(mime)
        row = _new_row(
            caller,
            services,
            id=job_id,
            input_kind="bytes",
            input_display=upload.filename,
            input_size=upload.size,
            input_sha256=upload.sha256,
            idempotency_key=idem,
            mime=mime,
            declared_mime=upload.content_type,
            profile=profile,
            options_json=options_json,
            queue=queue,
            blob_input=input_key(job_id),
        )
    finally:
        form.cleanup()
    services.jobs.create(row)
    enqueue_or_fail(services, job_id, queue)
    return await _respond(request, services, row, deduplicated=False, wait=wait, fmt=fmt, profile=profile)


def _detect_upload(upload: UploadedFile) -> str:
    from intomd.detect import detect, is_executable
    from intomd.inputs import InputRef

    ref = InputRef(kind="bytes", display=upload.filename, local_path=upload.path, declared_mime=upload.content_type)
    mime = detect(ref).mime
    if is_executable(mime):
        raise ApiError("unsupported_media_type", "Executable files are not accepted.", detail={"mime": mime})
    return mime


async def _create_from_url(request: Request, services: Services, caller: Caller, wait: float, fmt: str) -> Response:
    from intomd.core import netguard

    try:
        body = ConvertUrlRequest.model_validate_json(await _read_json_body(request))
    except ValidationError as e:
        fields = [{"field": ".".join(str(p) for p in err["loc"]), "problem": err["msg"]} for err in e.errors()[:20]]
        raise ApiError("invalid_request", "Invalid JSON body.", detail={"fields": fields}) from None
    settings = services.settings
    try:
        validated = netguard.validate_url(body.url, allow_private=settings.allow_private_networks)
    except netguard.UrlBlocked:
        raise ApiError("url_blocked", "This URL is not allowed.") from None
    residential = body.prefer_residential
    if settings.platforms_file:
        state = netguard.PlatformPolicy.load(settings.platforms_file).state(validated.host)
        if state == "disabled":
            raise ApiError("platform_disabled", "This site is disabled on this instance.")
        residential = residential or state == "residential_only"
    if residential and caller.api_key is not None and not caller.api_key.residential_allowed:
        raise ApiError("forbidden", "This API key may not use residential fetches.")
    challenge_jwt = require_url_challenge(request, caller, body.turnstile_token)
    options = dict(body.options)
    options.setdefault("profile", body.profile)
    profile, options_json = parse_options(options, caller, services)
    sha = sha256_hex("url:" + normalize_url(body.url))
    idem = _idempotency(request, caller, services)
    existing = _find_existing(services, caller, sha, options_json, profile, idem)
    if existing is not None:
        return await _respond(request, services, existing, deduplicated=True, wait=wait, fmt=fmt, profile=profile)
    admit_job(request, caller)
    queue = q.queue_for_url(residential)
    row = _new_row(
        caller,
        services,
        id=new_job_id(),
        input_kind="url",
        input_display=netguard.redact_url(body.url),
        input_url=strip_fragment(body.url),
        input_sha256=sha,
        idempotency_key=idem,
        profile=profile,
        options_json=options_json,
        queue=queue,
    )
    services.jobs.create(row)
    if queue == q.FETCH_RESIDENTIAL:
        route_residential(services, row.id)
        row = services.jobs.require(row.id)
    else:
        enqueue_or_fail(services, row.id, queue)
    response = await _respond(request, services, row, deduplicated=False, wait=wait, fmt=fmt, profile=profile)
    if challenge_jwt:
        response.set_cookie(
            CHALLENGE_COOKIE,
            challenge_jwt,
            max_age=settings.turnstile_jwt_ttl_s,
            httponly=True,
            secure=settings.public_url.startswith("https://"),
            samesite="strict",
        )
    return response


async def _read_json_body(request: Request, limit: int = 256 * 1024) -> bytes:
    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > limit:
            raise ApiError("input_too_large", "JSON body is too large.", detail={"limit_bytes": limit})
        chunks.append(chunk)
    return b"".join(chunks)
