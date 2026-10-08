"""intomd_api.rendering: render a cached ConversionResult for a (profile, format, overrides) triple
and cache the output per job in the blob store (docs/spec/part1.md section 7.3).

All rendering goes through `intomd.render.render`; this module only adapts its output to HTTP
bodies and headers, builds the zip bundle, and stores attachments under safe blob keys.
"""

from __future__ import annotations

import io
import json
import re
import zipfile
from dataclasses import dataclass, field
from typing import Any

from intomd.ir import ConversionResult
from intomd_api.blobs import BlobStore
from intomd_api.util import canonical_json, sha256_hex

PROFILES = ("full", "compact", "rag", "agent")
FORMATS = ("md", "json", "txt", "zip")
UNIMPLEMENTED_FORMATS = ("docx",)
_SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_INLINE_ATTACHMENT_MIMES = frozenset({"image/png", "image/jpeg", "image/gif", "image/webp", "text/csv"})

MEDIA_TYPES = {
    "md": "text/markdown; charset=utf-8",
    "json": "application/json",
    "txt": "text/plain; charset=utf-8",
    "zip": "application/zip",
}


class RenderUnavailable(Exception):
    """The renderer package is not importable in this deployment."""


@dataclass(slots=True)
class Rendered:
    body: bytes
    media_type: str
    tokens: int = 0
    truncated: bool = False
    warnings_count: int = 0
    injection_risk: str = "none"
    attachments: list[tuple[str, str]] = field(default_factory=list)

    def headers(self, fmt: str, job_id: str) -> dict[str, str]:
        h = {
            "X-Markdown-Tokens": str(self.tokens),
            "X-Intomd-Truncated": "true" if self.truncated else "false",
            "X-Intomd-Warnings": str(self.warnings_count),
            "X-Intomd-Injection-Risk": self.injection_risk,
            "X-Content-Type-Options": "nosniff",
        }
        if fmt == "zip":
            h["Content-Disposition"] = f'attachment; filename="{job_id}.zip"'
        return h

    def meta(self) -> dict[str, Any]:
        return {
            "media_type": self.media_type,
            "tokens": self.tokens,
            "truncated": self.truncated,
            "warnings_count": self.warnings_count,
            "injection_risk": self.injection_risk,
            "attachments": self.attachments,
        }


def validate_profile(profile: str, overrides: dict[str, Any]) -> None:
    """Raise ValueError for an unknown profile or an invalid dotted override."""
    if profile not in PROFILES:
        raise ValueError(f"unknown profile {profile!r}; expected one of {', '.join(PROFILES)}")
    try:
        from intomd.profiles import get_profile
    except ImportError:
        if overrides:
            raise ValueError("profile overrides are not supported by this deployment") from None
        return
    get_profile(profile, **overrides)


def overrides_hash(overrides: dict[str, Any]) -> str:
    return sha256_hex(canonical_json(overrides))[:12]


def safe_attachment_path(path: str) -> str | None:
    """Relative attachment path with only safe segments, or None."""
    segments = path.replace("\\", "/").split("/")
    if not segments or len(segments) > 6 or not all(_SAFE_SEGMENT.match(s) and s != ".." for s in segments):
        return None
    return "/".join(segments)


def attachment_media_type(mime: str) -> tuple[str, bool]:
    """(media type to serve, whether it may be shown inline). SVG and anything unknown is forced
    to a download so no active content is ever rendered from our origin."""
    base = mime.split(";", 1)[0].strip().lower()
    if base in _INLINE_ATTACHMENT_MIMES:
        return base, True
    return "application/octet-stream", False


def _call_renderer(result: ConversionResult, profile: str, fmt: str, overrides: dict[str, Any]) -> Any:
    try:
        from intomd.render import render
    except ImportError as e:
        raise RenderUnavailable("intomd.render is not available") from e
    return render(result, profile=profile, format=fmt, **overrides)


def _zip(out: Any, job_id: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(f"{job_id}.md", str(out.markdown))
        if getattr(out, "sidecar", None) is not None:
            zf.writestr(f"{job_id}.json", json.dumps(out.sidecar, ensure_ascii=False, indent=2, default=str))
        for att in getattr(out, "attachments", []) or []:
            rel = safe_attachment_path(str(att.path))
            if rel is not None:
                zf.writestr(rel, bytes(att.data))
    return buf.getvalue()


def render_result(
    result: ConversionResult, job_id: str, profile: str, fmt: str, overrides: dict[str, Any]
) -> tuple[Rendered, list[Any]]:
    """Render without caching. Returns the HTTP payload and the renderer's attachments."""
    render_fmt = "md" if fmt == "zip" else fmt
    out = _call_renderer(result, profile, render_fmt, overrides)
    body = _zip(out, job_id) if fmt == "zip" else str(out.markdown).encode("utf-8")
    attachments = list(getattr(out, "attachments", []) or [])
    rendered = Rendered(
        body=body,
        media_type=MEDIA_TYPES[fmt],
        tokens=int(getattr(out, "tokens", 0) or 0),
        truncated=bool(getattr(out, "truncated", False)),
        warnings_count=len(getattr(out, "warnings", []) or []),
        injection_risk=str(getattr(out, "injection_risk", "none") or "none"),
    )
    return rendered, attachments


def _keys(job_id: str, profile: str, fmt: str, overrides: dict[str, Any]) -> tuple[str, str]:
    stem = f"jobs/{job_id}/results/{profile}-{overrides_hash(overrides)}.{fmt}"
    return stem, stem + ".meta.json"


def store_attachments(blobs: BlobStore, job_id: str, attachments: list[Any]) -> list[tuple[str, str]]:
    stored: list[tuple[str, str]] = []
    for att in attachments:
        rel = safe_attachment_path(str(att.path))
        if rel is None:
            continue
        blobs.put_bytes(f"jobs/{job_id}/attachments/{rel}", bytes(att.data))
        stored.append((rel, str(att.mime)))
    if stored:
        index_key = f"jobs/{job_id}/attachments.json"
        existing: dict[str, str] = {}
        if blobs.exists(index_key):
            existing = dict(json.loads(blobs.get_bytes(index_key)))
        existing.update(dict(stored))
        blobs.put_bytes(index_key, json.dumps(existing, sort_keys=True).encode())
    return stored


def attachment_index(blobs: BlobStore, job_id: str) -> dict[str, str]:
    key = f"jobs/{job_id}/attachments.json"
    if not blobs.exists(key):
        return {}
    return dict(json.loads(blobs.get_bytes(key)))


def load_ir(blobs: BlobStore, key: str) -> ConversionResult:
    return ConversionResult.model_validate_json(blobs.get_bytes(key))


def render_cached(
    blobs: BlobStore, job_id: str, ir_key: str, profile: str, fmt: str, overrides: dict[str, Any]
) -> Rendered:
    body_key, meta_key = _keys(job_id, profile, fmt, overrides)
    if blobs.exists(body_key) and blobs.exists(meta_key):
        meta = json.loads(blobs.get_bytes(meta_key))
        return Rendered(
            body=blobs.get_bytes(body_key),
            media_type=str(meta["media_type"]),
            tokens=int(meta["tokens"]),
            truncated=bool(meta["truncated"]),
            warnings_count=int(meta["warnings_count"]),
            injection_risk=str(meta["injection_risk"]),
            attachments=[(str(a), str(b)) for a, b in meta.get("attachments", [])],
        )
    rendered, attachments = render_result(load_ir(blobs, ir_key), job_id, profile, fmt, overrides)
    rendered.attachments = store_attachments(blobs, job_id, attachments)
    blobs.put_bytes(body_key, rendered.body)
    blobs.put_bytes(meta_key, json.dumps(rendered.meta()).encode())
    return rendered
