"""intomd_api.schemas: request and response models (docs/spec/part1.md section 7.3)."""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from intomd_api.db import JobRow
from intomd_api.jobs import FAILED, JobStore, result_url
from intomd_api.util import iso


class ConvertOptionsIn(BaseModel):
    """The ConvertOptions a client may set. Dotted keys (`chunks.chunk_tokens`) are profile overrides
    and are split off before this model validates the rest."""

    model_config = ConfigDict(extra="forbid")

    max_pages: int | None = Field(default=None, ge=1)
    max_duration_seconds: float | None = Field(default=None, gt=0)
    ocr: bool | None = None
    asr_model: str | None = Field(default=None, max_length=64)
    diarize: bool | None = None
    languages: list[str] | None = Field(default=None, max_length=10)
    extract_images: bool | None = None
    tracked_changes: bool | None = None
    comments: bool | None = None
    formulas: bool | None = None


class ConvertUrlRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str = Field(max_length=8192)
    profile: str = "full"
    options: dict[str, Any] = Field(default_factory=dict)
    turnstile_token: str | None = Field(default=None, max_length=4096)
    prefer_residential: bool = False


class InputOut(BaseModel):
    kind: str
    display: str
    mime: str | None = None
    size_bytes: int | None = None
    sha256: str | None = None


class JobOut(BaseModel):
    id: str
    state: str
    progress: int
    stage_message: str
    queue: str
    converter_id: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    expires_at: str | None = None
    input: InputOut
    profile: str
    warnings_count: int = 0
    truncated: bool = False
    needs_action: dict[str, Any] | None = None
    error: dict[str, Any] | None = None


class LinksOut(BaseModel):
    self: str
    events: str
    result: str


class ConvertResponse(BaseModel):
    job: JobOut
    deduplicated: bool
    links: LinksOut


class FetchNodeClaimRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    node_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._-]+$")
    capabilities: list[str] = Field(default_factory=list, max_length=32)
    max_duration_seconds: int | None = Field(default=None, ge=1)


class FetchNodeClaimResponse(BaseModel):
    job_id: str
    claim_token: str
    url: str
    want: str
    max_bytes: int
    max_duration_seconds: int
    upload_url: str
    claim_expires_at: str


class FetchNodeHeartbeat(BaseModel):
    model_config = ConfigDict(extra="ignore")

    node_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._-]+$")
    capabilities: list[str] = Field(default_factory=list, max_length=32)
    claim_token: str | None = Field(default=None, max_length=256)


class FetchNodeFail(BaseModel):
    model_config = ConfigDict(extra="ignore")

    claim_token: str = Field(max_length=256)
    reason_code: str = Field(max_length=64, pattern=r"^[a-z0-9_]+$")
    message: str | None = Field(default=None, max_length=500)


class SupplyCaptions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    captions: list[dict[str, Any]] = Field(max_length=100_000)
    meta: dict[str, Any] = Field(default_factory=dict)


def job_out(row: JobRow, *, include_sha: bool = True) -> JobOut:
    error = None
    if row.state == FAILED:
        error = JobStore.error_payload(row)["error"]
    return JobOut(
        id=row.id,
        state=row.state,
        progress=row.progress,
        stage_message=row.stage_message,
        queue=row.queue,
        converter_id=row.converter_id,
        created_at=iso(row.created_at),
        updated_at=iso(row.updated_at),
        expires_at=iso(row.expires_at),
        input=InputOut(
            kind=row.input_kind,
            display=row.input_display,
            mime=row.mime,
            size_bytes=row.input_size,
            sha256=row.input_sha256 if include_sha and row.input_kind != "url" else None,
        ),
        profile=row.profile,
        warnings_count=row.warnings_count,
        truncated=row.truncated,
        needs_action=JobStore.needs_action_payload(row),
        error=error,
    )


def convert_response(row: JobRow, *, deduplicated: bool, profile: str | None = None) -> ConvertResponse:
    prof = profile or row.profile
    return ConvertResponse(
        job=job_out(row, include_sha=False),
        deduplicated=deduplicated,
        links=LinksOut(
            self=f"/v1/jobs/{row.id}",
            events=f"/v1/jobs/{row.id}/events",
            result=result_url(row.id, prof),
        ),
    )


def compact_json(model: BaseModel) -> str:
    return json.dumps(model.model_dump(mode="json"), separators=(",", ":"))


class ErrorDetail(BaseModel):
    code: str
    message: str
    status: int
    request_id: str
    detail: dict[str, Any] = Field(default_factory=dict)
    docs: str


class ErrorResponse(BaseModel):
    """The error schema of docs/spec/part1.md section 7.5."""

    error: ErrorDetail


EXTRA_SCHEMA_MODELS: tuple[type[BaseModel], ...] = (ConvertUrlRequest, SupplyCaptions, ErrorResponse)
