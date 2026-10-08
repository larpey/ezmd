"""ezmd_api.options: REST conversion options derived from the library's `ezmd.library.Options`.

The API never re-declares option types. `ConvertOptionsIn` is generated from the client-settable
subset of `Options` fields (same annotations and constraints, every field optional so the library
default applies when a client omits it), plus a few API-only tightenings for hostile input. The
conversion child turns the stored options back into `Options` and calls
`Options.to_convert_options()`, so REST and library options cannot drift
(`apps/api/tests/test_api_options_drift.py` fails when a library field is neither classified as
client-settable nor server-controlled).
"""

from __future__ import annotations

from typing import Annotated, Any

from annotated_types import MaxLen
from pydantic import BaseModel, ConfigDict, Field, create_model

from ezmd.library import Options
from ezmd.registry import ConvertOptions

CLIENT_FIELDS: tuple[str, ...] = (
    "max_pages",
    "max_duration_seconds",
    "ocr",
    "asr_model",
    "diarize",
    "languages",
    "extract_images",
    "tracked_changes",
    "comments",
    "formulas",
)
"""`Options` fields a REST client may set in `options`."""

SERVER_FIELDS: dict[str, str] = {
    "max_seconds": "set from the queue's job timeout (EZMD_JOB_TIMEOUT_S)",
    "max_bytes": "the caller's upload cap is enforced before the job exists",
    "experimental": "instance policy (Part 2 13.7), not a client choice",
    "converter": "forcing a converter is a library/CLI feature; the API routes by detected content",
    "allow_private_networks": "SSRF guard; only EZMD_ALLOW_PRIVATE_NETWORKS may loosen it",
    "extra": "family-specific engine options are not exposed over HTTP yet",
    "render": "dotted profile overrides (`chunks.chunk_tokens`) are split off before validation",
}
"""`Options` fields the server controls, with the reason. Every `Options` field is in exactly one of
CLIENT_FIELDS or SERVER_FIELDS (the drift test enforces it)."""

API_TIGHTENING: dict[str, tuple[Any, ...]] = {
    "asr_model": (MaxLen(64),),
    "languages": (MaxLen(10),),
}
"""Extra constraints the public API adds on top of the library's (bounded strings and lists)."""

FIELD_DOCS: dict[str, tuple[str, Any]] = {
    "max_pages": ("Stop after this many pages; clamped to the caller's page limit.", 200),
    "max_duration_seconds": ("Audio/video duration cap in seconds; clamped to the caller's limit.", 900),
    "ocr": ("Allow OCR when a page has no text layer.", True),
    "asr_model": ("Speech-recognition model id (for example `small`).", "small"),
    "diarize": ("Label speakers in transcripts when supported.", True),
    "languages": ("BCP-47 language hints; empty means auto-detect.", ["en"]),
    "extract_images": ("Extract embedded images as attachments.", True),
    "tracked_changes": ("Include tracked insertions and deletions (Office).", True),
    "comments": ("Include document comments.", True),
    "formulas": ("Keep spreadsheet formulas next to their values.", False),
}


def _client_field(name: str) -> tuple[Any, Any]:
    info = Options.model_fields[name]
    annotation: Any = info.annotation
    metadata = (*info.metadata, *API_TIGHTENING.get(name, ()))
    typed: Any = Annotated[(annotation | None, *metadata)] if metadata else annotation | None
    description, example = FIELD_DOCS[name]
    return typed, Field(default=None, description=description, examples=[example])


_FIELDS: dict[str, Any] = {name: _client_field(name) for name in CLIENT_FIELDS}
ConvertOptionsIn: type[BaseModel] = create_model(
    "ConvertOptionsIn",
    __config__=ConfigDict(extra="forbid"),
    __doc__=(
        "Conversion options a client may set (a subset of `ezmd.library.Options`; omitted fields use the "
        "library default). Dotted keys such as `chunks.chunk_tokens` are profile overrides and are accepted "
        "alongside these fields in the same object."
    ),
    **_FIELDS,
)


def validate_client_options(raw: dict[str, Any]) -> dict[str, Any]:
    """Validate client options (raises pydantic.ValidationError) and return the explicitly set fields."""
    model = ConvertOptionsIn.model_validate(raw)
    convert = model.model_dump(exclude_none=True)
    Options.model_validate(convert)  # the library must accept exactly what the API accepted
    return convert


def library_options(convert: dict[str, Any], *, max_seconds: float) -> Options:
    """The library `Options` for a stored job's convert options plus the server-controlled budget."""
    return Options.model_validate({**convert, "max_seconds": max_seconds})


def to_convert_options(convert: dict[str, Any], *, max_seconds: float) -> ConvertOptions:
    """What the conversion child passes to `ezmd.pipeline.convert_ref`."""
    return library_options(convert, max_seconds=max_seconds).to_convert_options()


DOTTED_KEY_PATTERN = "^[a-z_]+([.][a-z_]+)+$"
"""Profile override keys (`chunks.chunk_tokens`) that may sit beside the ConvertOptionsIn fields."""


def link_options_schema(components: dict[str, Any]) -> None:
    """OpenAPI: let ConvertOptionsIn admit dotted override keys and make `ConvertUrlRequest.options` use it."""
    opts = components.get("ConvertOptionsIn")
    req = components.get("ConvertUrlRequest")
    if opts is None or req is None:
        return
    opts["patternProperties"] = {
        DOTTED_KEY_PATTERN: {"description": "Profile override, for example `chunks.chunk_tokens`: 512"}
    }
    field = req.get("properties", {}).get("options", {})
    req["properties"]["options"] = {
        "allOf": [{"$ref": "#/components/schemas/ConvertOptionsIn"}],
        "description": field.get("description", ""),
        "default": {},
    }
