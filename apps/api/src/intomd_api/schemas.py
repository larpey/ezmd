"""intomd_api.schemas: request and response models (docs/spec/part1.md section 7.3).

Field descriptions and examples here are what docs/api/openapi.json publishes.
"""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from intomd_api.db import JobRow
from intomd_api.jobs import FAILED, STATES, JobStore, result_url
from intomd_api.options import ConvertOptionsIn
from intomd_api.util import iso

JOB_ID_EXAMPLE = "job_7Kx2mQp9Lw3nRt5vYb8cDe"
JobState = Literal["queued", "fetching", "converting", "rendering", "done", "failed", "needs_user_action", "expired"]
assert set(JobState.__args__) == set(STATES)  # type: ignore[attr-defined]


class ConvertUrlRequest(BaseModel):
    """JSON body of `POST /v1/convert` for a URL input."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "url": "https://example.com/reports/q3-fleet.pdf",
                    "profile": "compact",
                    "options": {"max_pages": 100},
                    "prefer_residential": False,
                }
            ]
        },
    )

    url: str = Field(max_length=8192, description="http(s) URL to fetch and convert. Private addresses are refused.")
    profile: Literal["full", "compact", "rag", "agent"] = Field(default="full", description="Output profile.")
    options: dict[str, Any] = Field(
        default_factory=dict,
        description="ConvertOptionsIn fields plus dotted profile overrides such as `chunks.chunk_tokens`.",
    )
    turnstile_token: str | None = Field(
        default=None, max_length=4096, description="Cloudflare Turnstile token; required for anonymous URL jobs."
    )
    prefer_residential: bool = Field(
        default=False,
        description="Keyed callers with the residential permission only; ignored for anonymous callers (D-0017)",
    )


class InputOut(BaseModel):
    kind: str = Field(description="bytes, url, residential_fetch, or captions_json3", examples=["bytes"])
    display: str = Field(description="File name or redacted URL", examples=["q3-fleet.pdf"])
    mime: str | None = Field(default=None, description="Detected media type", examples=["application/pdf"])
    size_bytes: int | None = Field(default=None, examples=[1834022])
    sha256: str | None = Field(default=None, description="Input digest (uploads only, omitted on create)")


class JobOut(BaseModel):
    """A job's state and metadata (`GET /v1/jobs/{job_id}`)."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "id": JOB_ID_EXAMPLE,
                    "state": "done",
                    "progress": 100,
                    "stage_message": "Done",
                    "queue": "default",
                    "converter_id": "text.markdown",
                    "created_at": "2026-10-12T18:40:00Z",
                    "updated_at": "2026-10-12T18:40:02Z",
                    "expires_at": "2026-10-13T18:40:00Z",
                    "input": {"kind": "bytes", "display": "notes.md", "mime": "text/markdown", "size_bytes": 2048},
                    "profile": "full",
                    "warnings_count": 1,
                    "warnings": ["encoding_uncertain"],
                    "truncated": False,
                    "needs_action": None,
                    "error": None,
                }
            ]
        }
    )

    id: str = Field(description="Unguessable job id; possession is the capability", examples=[JOB_ID_EXAMPLE])
    state: JobState
    progress: int = Field(ge=0, le=100, description="Percent complete")
    stage_message: str = Field(description="Human-readable stage", examples=["Converting page 84 of 200"])
    queue: str = Field(description="default, media, fetch, or fetch_residential", examples=["default"])
    converter_id: str | None = Field(default=None, examples=["documents.docling_pdf"])
    created_at: str | None = None
    updated_at: str | None = None
    expires_at: str | None = Field(default=None, description="When the job and its results are purged")
    input: InputOut
    profile: str = Field(description="Requested profile", examples=["rag"])
    warnings_count: int = Field(default=0, description="Number of warnings the conversion emitted")
    warnings: list[str] = Field(
        default_factory=list,
        description="Canonical warning codes the conversion emitted, first-seen order (see GET /v1/warnings)",
    )
    truncated: bool = Field(default=False, description="True when part of the input or output was cut")
    needs_action: dict[str, Any] | None = Field(
        default=None, description="Present in needs_user_action: what the client must supply and where"
    )
    error: dict[str, Any] | None = Field(default=None, description="Present in failed: the error object (7.5)")


class LinksOut(BaseModel):
    self: str = Field(examples=[f"/v1/jobs/{JOB_ID_EXAMPLE}"])
    events: str = Field(examples=[f"/v1/jobs/{JOB_ID_EXAMPLE}/events"])
    result: str = Field(examples=[f"/v1/jobs/{JOB_ID_EXAMPLE}/result?profile=rag&format=md"])


class ConvertResponse(BaseModel):
    """The job envelope returned by `POST /v1/convert` (202, or 200 when deduplicated)."""

    job: JobOut
    deduplicated: bool = Field(description="True when an existing finished job with the same input was returned")
    links: LinksOut


class FetchNodeClaimRequest(BaseModel):
    model_config = ConfigDict(
        extra="ignore",
        json_schema_extra={
            "examples": [{"node_id": "pi-home-1", "capabilities": ["yt-dlp", "ffmpeg"], "max_duration_seconds": 10800}]
        },
    )

    node_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._-]+$")
    capabilities: list[str] = Field(default_factory=list, max_length=32)
    max_duration_seconds: int | None = Field(default=None, ge=1)


class FetchNodeClaimResponse(BaseModel):
    job_id: str
    claim_token: str
    url: str
    want: str = Field(description="audio, video, or page", examples=["audio"])
    max_bytes: int
    max_duration_seconds: int
    upload_url: str = Field(examples=["/v1/fetch-node/upload"])
    claim_expires_at: str
    platform: str | None = Field(
        default=None, description="The platform-policy entry matching the URL's host (for example youtube.com)"
    )
    resolved_ip: str | None = Field(
        default=None,
        description=(
            "Address the VPS resolved and validated at claim time (null when DNS failed). Advisory: the node "
            "must re-run netguard itself before fetching (Phase 3)."
        ),
    )


class FetchNodeHeartbeat(BaseModel):
    model_config = ConfigDict(extra="ignore")

    node_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9._-]+$")
    capabilities: list[str] = Field(default_factory=list, max_length=32)
    claim_token: str | None = Field(default=None, max_length=256, description="Extends this claim when present")


class FetchNodeFail(BaseModel):
    model_config = ConfigDict(extra="ignore")

    claim_token: str = Field(max_length=256)
    reason_code: str = Field(max_length=64, pattern=r"^[a-z0-9_]+$", examples=["bot_check"])
    message: str | None = Field(default=None, max_length=500)


class SupplyCaptions(BaseModel):
    """Caption JSON supplied by the browser extension for a needs_user_action job."""

    model_config = ConfigDict(extra="forbid")

    captions: list[dict[str, Any]] = Field(max_length=100_000)
    meta: dict[str, Any] = Field(default_factory=dict)


class ConverterOut(BaseModel):
    id: str = Field(examples=["text.markdown"])
    family: str = Field(examples=["text"])
    mimes: list[str]
    experimental: bool
    loaded: bool = Field(description="False when the converter's optional extra is not installed")
    extras: list[str] = Field(description="pip extras that provide the converter's engine")


class LimitsOut(BaseModel):
    max_upload_bytes: int
    max_url_bytes: int
    max_audio_seconds: int
    max_pages: int
    retention_hours: int


class CapabilitiesOut(BaseModel):
    """What this instance can do (`GET /v1/capabilities`). Limits are the anonymous caps."""

    version: str = Field(examples=["0.0.1"])
    converters: list[ConverterOut]
    profiles: list[str] = Field(examples=[["full", "compact", "rag", "agent"]])
    formats: list[str] = Field(examples=[["md", "json", "txt", "zip"]])
    limits: LimitsOut
    fetch_node_online: bool
    residential_platforms: list[str]
    public_mode: bool
    turnstile_site_key: str | None = None
    challenge: Literal["turnstile"] | None = None


class HealthOut(BaseModel):
    status: Literal["ok"] = "ok"


class ReadyOut(BaseModel):
    status: Literal["ready", "not_ready"]
    checks: dict[str, bool] = Field(examples=[{"database": True, "state": True, "workers": True}])


class WarningCodeOut(BaseModel):
    code: str = Field(examples=["encoding_uncertain"])
    severity: Literal["info", "warning", "error"] = Field(description="Default severity")
    family: str = Field(examples=["core"])
    description: str
    suggestion: str = Field(description="What the user can do about it")
    truncates: bool = Field(description="True when this warning means content was cut (sets `truncated`)")
    aliases: list[str] = Field(description="Retired spellings that still normalize to this code")


class WarningsOut(BaseModel):
    """The warning code registry (`intomd.warnings.codes`)."""

    warnings: list[WarningCodeOut]


def warning_codes_of(row: JobRow) -> list[str]:
    try:
        codes = json.loads(row.warning_codes or "[]")
    except (TypeError, json.JSONDecodeError):
        return []
    return [str(c) for c in codes] if isinstance(codes, list) else []


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
        warnings=warning_codes_of(row),
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
    code: str = Field(description="Stable machine-readable code (see the table in the API description)")
    message: str = Field(description="Human-readable; never contains stack traces or server paths")
    status: int
    request_id: str = Field(description="Matches the X-Request-Id response header")
    detail: dict[str, Any] = Field(default_factory=dict)
    docs: str


class ErrorResponse(BaseModel):
    """The error schema of docs/spec/part1.md section 7.5."""

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "error": {
                        "code": "input_too_large",
                        "message": "Upload exceeds the 25 MB limit for anonymous requests.",
                        "status": 413,
                        "request_id": "req_3fQ9xL2mVb7Kp1Zt",
                        "detail": {"limit_bytes": 26214400},
                        "docs": "https://intomd.example.com/docs/errors#input_too_large",
                    }
                }
            ]
        }
    )

    error: ErrorDetail


EXTRA_SCHEMA_MODELS: tuple[type[BaseModel], ...] = (ConvertUrlRequest, ConvertOptionsIn, SupplyCaptions, ErrorResponse)
