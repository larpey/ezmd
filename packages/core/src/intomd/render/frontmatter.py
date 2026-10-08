"""intomd.render.frontmatter: frontmatter dict and a small deterministic YAML emitter (part3.md section 13).

Keys are emitted in the spec order (never alphabetical); null/empty optional keys are omitted. Free-text
string keys are always double-quoted; identifier-like values (enums, codes, language tags) are bare unless
YAML would misread them. Dates are ISO 8601 and unquoted. Lists and maps of short scalars use flow style.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any

from intomd.ir import ConversionResult, Slide
from intomd.render.source_types import frontmatter_source_type

__all__ = ["FrontmatterInputs", "RawScalar", "build_frontmatter", "dump_yaml", "fmt_datetime"]

KEY_ORDER: tuple[str, ...] = (
    "title",
    "source",
    "source_type",
    "source_url",
    "platform",
    "converter",
    "converter_version",
    "intomd_version",
    "schema_version",
    "profile",
    "provenance",
    "created_at",
    "modified_at",
    "fetched_at",
    "converted_at",
    "author",
    "language",
    "language_confidence",
    "duration",
    "duration_seconds",
    "pages",
    "slides",
    "sheets",
    "word_count",
    "tokens",
    "content_hash",
    "source_hash",
    "truncated",
    "truncation",
    "warnings",
    "license",
    "description",
    "tags",
    "transcript_source",
    "asr_engine",
    "diarization",
    "speakers",
    "ocr_engine",
    "chapters_source",
    "summary_source",
    "injection_risk",
    "untrusted_content_id",
    "chunks",
    "chunk_tokens",
    "sidecar",
    "exports",
    "extra",
)
COMPACT_KEYS: tuple[str, ...] = (
    "title",
    "source",
    "source_type",
    "language",
    "word_count",
    "tokens",
    "content_hash",
    "truncated",
    "warnings",
    "injection_risk",
    "profile",
)
REQUIRED = {
    "title",
    "source",
    "source_type",
    "converter",
    "converter_version",
    "intomd_version",
    "schema_version",
    "profile",
    "provenance",
    "fetched_at",
    "converted_at",
    "word_count",
    "tokens",
    "content_hash",
    "truncated",
    "warnings",
    "injection_risk",
}
_ALWAYS_QUOTE = {
    "title",
    "source",
    "source_url",
    "converter_version",
    "intomd_version",
    "author",
    "license",
    "description",
    "asr_engine",
    "diarization",
    "ocr_engine",
    "content_hash",
    "source_hash",
    "untrusted_content_id",
    "sidecar",
    "duration",
    "speakers",
    "tags",
    "exports",
    "sheets",
}
_EXTRA_SLOTS = {
    "source_url",
    "platform",
    "converter_version",
    "language_confidence",
    "sheets",
    "transcript_source",
    "asr_engine",
    "diarization",
    "ocr_engine",
    "chapters_source",
    "summary_source",
    "source_type",
}
_BARE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.\-]*$")
_YAML_WORDS = {"true", "false", "yes", "no", "on", "off", "null", "~", "y", "n"}


class RawScalar(str):
    """A pre-formatted scalar emitted without quotes (timestamps)."""

    __slots__ = ()


@dataclass(slots=True)
class FrontmatterInputs:
    title: str
    word_count: int
    tokens: dict[str, int]
    content_hash: str
    injection_risk: str
    warnings: list[str]
    converted_at: datetime
    truncated: bool
    fetched_at: datetime | None = None
    truncation: dict[str, object] = field(default_factory=dict)
    fence_id: str | None = None
    chunks: int | None = None
    chunk_tokens: int | None = None
    sidecar_path: str | None = None
    exports: dict[str, object] = field(default_factory=dict)
    speakers: list[str] = field(default_factory=list)


def fmt_datetime(value: datetime | date, *, allow_date: bool = True) -> str:
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            value = value.astimezone(UTC).replace(tzinfo=None)
        value = value.replace(microsecond=0)
        if allow_date and value.hour == value.minute == value.second == 0:
            return value.date().isoformat()
        return value.isoformat() + "Z"
    return value.isoformat()


def _converter(result: ConversionResult) -> tuple[str, str]:
    from intomd import __version__

    cid = result.converter_id or result.document.converter_id or "unknown"
    if "@" in cid:
        name, ver = cid.split("@", 1)
        return name, ver
    extra_ver = result.document.metadata.extra.get("converter_version")
    if extra_ver:
        return cid, str(extra_ver)
    engine = result.metrics.engine or ""
    if "@" in engine:
        return cid, engine.split("@", 1)[1]
    return cid, __version__


def _hms(seconds: float) -> str:
    total = round(seconds)
    return f"{total // 3600:02d}:{total % 3600 // 60:02d}:{total % 60:02d}"


def build_frontmatter(
    result: ConversionResult, profile_name: str, minimal: bool, inp: FrontmatterInputs, include_extra: bool
) -> dict[str, object]:
    from intomd import __version__

    doc = result.document
    m = doc.metadata
    extra = dict(m.extra)
    if m.encoding and "encoding" not in extra:
        extra["encoding"] = m.encoding
    name, version = _converter(result)
    slides = m.slides or sum(1 for b in doc.blocks if isinstance(b, Slide))
    sheets = list(m.sheets) or (
        [s.strip() for s in str(extra["sheets"]).split(",") if s.strip()] if extra.get("sheets") else []
    )
    authors: object = m.authors if len(m.authors) > 1 else (m.authors[0] if m.authors else m.author)
    description = m.description
    if description and len(description) > 1000:
        description = description[:997].rstrip() + "..."
    sha = result.input_ref.sha256
    values: dict[str, object] = {
        "title": inp.title,
        "source": m.source,
        "source_type": frontmatter_source_type(doc),
        "source_url": extra.get("source_url"),
        "platform": extra.get("platform"),
        "converter": name,
        "converter_version": version,
        "intomd_version": __version__,
        "schema_version": 1,
        "profile": profile_name,
        "provenance": "block" if doc.blocks else "none",
        "created_at": RawScalar(fmt_datetime(m.published)) if m.published else None,
        "modified_at": RawScalar(fmt_datetime(m.modified)) if m.modified else None,
        "fetched_at": RawScalar(fmt_datetime(inp.fetched_at or m.fetched or inp.converted_at, allow_date=False)),
        "converted_at": RawScalar(fmt_datetime(inp.converted_at, allow_date=False)),
        "author": authors,
        "language": m.language,
        "language_confidence": extra.get("language_confidence"),
        "duration": _hms(m.duration_seconds) if m.duration_seconds else None,
        "duration_seconds": m.duration_seconds,
        "pages": m.pages,
        "slides": slides or None,
        "sheets": sheets or None,
        "word_count": inp.word_count,
        "tokens": inp.tokens,
        "content_hash": inp.content_hash,
        "source_hash": (sha if sha.startswith("sha256:") else f"sha256:{sha}") if sha else None,
        "truncated": inp.truncated,
        "truncation": inp.truncation or None,
        "warnings": inp.warnings,
        "license": m.license,
        "description": description,
        "tags": m.keywords or None,
        "transcript_source": extra.get("transcript_source"),
        "asr_engine": extra.get("asr_engine"),
        "diarization": extra.get("diarization"),
        "speakers": (m.speakers or inp.speakers) or None,
        "ocr_engine": extra.get("ocr_engine"),
        "chapters_source": extra.get("chapters_source"),
        "summary_source": extra.get("summary_source"),
        "injection_risk": inp.injection_risk,
        "untrusted_content_id": inp.fence_id,
        "chunks": inp.chunks,
        "chunk_tokens": inp.chunk_tokens,
        "sidecar": inp.sidecar_path,
        "exports": inp.exports or None,
        "extra": {k: v for k, v in sorted(extra.items()) if k not in _EXTRA_SLOTS and v is not None} or None,
    }
    if not include_extra:
        values["extra"] = None
    keys = COMPACT_KEYS if minimal else KEY_ORDER
    out: dict[str, object] = {}
    for key in keys:
        value = values.get(key)
        if minimal and key == "truncated" and not value:
            continue
        if value is None or (value in ("", [], {}) and key not in REQUIRED):
            continue
        out[key] = value
    return out


# ---------------------------------------------------------------------------- YAML emitter


def _quote(text: str) -> str:
    out = []
    for ch in text:
        if ch == "\\":
            out.append("\\\\")
        elif ch == '"':
            out.append('\\"')
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\t":
            out.append("\\t")
        elif ord(ch) < 0x20 or ord(ch) == 0x7F:
            out.append(f"\\x{ord(ch):02x}")
        else:
            out.append(ch)
    return '"' + "".join(out) + '"'


def _needs_quotes(text: str) -> bool:
    if not text or not _BARE.match(text) or text.lower() in _YAML_WORDS:
        return True
    return bool(re.match(r"^[-+]?(\d[\d_]*)?(\.\d+)?([eE][-+]?\d+)?$", text)) or not text.isascii()


def _scalar(value: Any, force_quote: bool) -> str:
    if isinstance(value, RawScalar):
        return str(value)
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(round(value, 6))
    if isinstance(value, datetime | date):
        return fmt_datetime(value)
    text = str(value)
    return _quote(text) if force_quote or _needs_quotes(text) else text


def _is_scalar(value: Any) -> bool:
    return value is None or isinstance(value, str | int | float | bool | datetime | date)


def _flow(value: Any, quote: bool) -> str | None:
    if _is_scalar(value):
        return "null" if value is None else _scalar(value, quote)
    if isinstance(value, list) and all(_is_scalar(v) for v in value):
        return "[" + ", ".join("null" if v is None else _scalar(v, quote) for v in value) + "]"
    if isinstance(value, dict):
        parts = []
        for k, v in value.items():
            inner = _flow(v, quote)
            if inner is None:
                return None
            parts.append(f"{_scalar(str(k), False)}: {inner}")
        return "{" + ", ".join(parts) + "}"
    return None


def _emit(key: str, value: Any, indent: int, quote: bool, lines: list[str]) -> None:
    pad = " " * indent
    flow = _flow(value, quote)
    if flow is not None and len(pad) + len(key) + len(flow) + 2 <= 160:
        lines.append(f"{pad}{key}: {flow}")
        return
    lines.append(f"{pad}{key}:")
    if isinstance(value, dict):
        for k, v in value.items():
            _emit(_scalar(str(k), False), v, indent + 2, quote, lines)
    elif isinstance(value, list):
        for v in value:
            inner = _flow(v, quote)
            lines.append(f"{pad}  - {inner if inner is not None else _quote(str(v))}")
    else:
        lines.append(f"{pad}  {_scalar(value, True)}")


def dump_yaml(data: dict[str, object]) -> str:
    """Serialize the frontmatter between `---` lines."""
    lines: list[str] = ["---"]
    for key, value in data.items():
        _emit(key, value, 0, key in _ALWAYS_QUOTE, lines)
    lines.append("---")
    return "\n".join(lines) + "\n"
