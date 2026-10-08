"""intomd.profiles: output profile configuration objects.

Implements docs/spec/part1.md section 6, extended with the Part 3 section 17 options (Part 3 is
authoritative for the output format). Profiles are frozen dataclasses; `get_profile` applies scalar and
dotted overrides (API query params and CLI flags map here), coercing string values to the field type.
"""

from __future__ import annotations

import dataclasses
import types
import typing
from dataclasses import dataclass, field
from typing import Any, Literal

__all__ = [
    "AGENT",
    "COMPACT",
    "FULL",
    "PROFILES",
    "RAG",
    "ChunkRules",
    "ImageRules",
    "Profile",
    "ProfileName",
    "TableRules",
    "TranscriptRules",
    "apply_overrides",
    "get_profile",
]

ProfileName = Literal["full", "compact", "rag", "agent"]


@dataclass(frozen=True, slots=True)
class TableRules:
    max_pipe_columns: int = 6
    max_pipe_rows: int | None = 200
    """Data-row cap for pipe tables. None means unlimited. compact and rag use 50."""
    merged_cells: Literal["html", "flatten"] = "html"
    wide_fallback: Literal["kv", "transpose"] = "kv"
    """Only `kv` is implemented; `transpose` is accepted and treated as `kv`."""
    csv_sidecar: bool = False
    """Write a CSV attachment for every table (Part 3 `tables_csv`). Wide/long/sampled tables always get one."""
    pad_columns: bool = False
    """Accepted for compatibility; the renderer never pads (padding is pure token overhead)."""
    sample_threshold_rows: int = 1000
    sample_head_rows: int = 20
    sample_tail_rows: int = 5


@dataclass(frozen=True, slots=True)
class ImageRules:
    mode: Literal["reference_and_caption", "caption_only", "reference_only"] = "reference_and_caption"
    chart_table: bool = True
    min_pixels: int = 32
    """Images narrower or shorter than this are treated as decorative icons and dropped."""


@dataclass(frozen=True, slots=True)
class TranscriptRules:
    timestamps: Literal["paragraph", "sentence", "none"] = "paragraph"
    paragraph_gap_seconds: float = 1.75
    chapters: bool = True
    non_speech_cues: bool = True
    non_speech_italic: bool = False
    style: Literal["verbatim", "clean"] = "clean"
    confidence_marks: bool = False


@dataclass(frozen=True, slots=True)
class ChunkRules:
    enabled: bool = False
    chunk_tokens: int = 400
    overlap_tokens: int = 0
    min_chunk_tokens: int = 100
    table_chunk_tokens: int = 2048
    """Accepted for compatibility; table splitting follows Part 3 (split when > 4x chunk_tokens)."""
    breadcrumb: bool = True
    context_line: bool = False
    """Optional LLM-generated context line; not implemented (requires a model endpoint)."""


@dataclass(frozen=True, slots=True)
class Profile:
    name: ProfileName
    frontmatter: bool = True
    minimal_frontmatter: bool = False
    summary_blockquote: bool = True
    orientation: bool = True
    toc: Literal["auto", "always", "never"] = "auto"
    toc_min_headings: int = 5
    toc_min_tokens: int = 3000
    number_headings: bool = True
    anchors: bool = True
    page_markers: bool = True
    image_comments: bool = True
    footnotes: Literal["section_end", "document_end", "inline", "drop"] = "section_end"
    tracked_changes: Literal["annotate", "accept", "reject", "drop"] = "accept"
    comments: Literal["inline", "drop"] = "drop"
    links: Literal["inline", "numbered_list", "text_only"] = "inline"
    furniture: Literal["drop", "keep"] = "drop"
    compact_lists: bool = False
    """Ordered items all numbered `1.` and single-item lists flattened to a paragraph (compact)."""
    extended_markdown: bool = False
    formulas: Literal["cached", "inline"] = "cached"
    tables: TableRules = field(default_factory=TableRules)
    images: ImageRules = field(default_factory=ImageRules)
    transcript: TranscriptRules = field(default_factory=TranscriptRules)
    chunks: ChunkRules = field(default_factory=ChunkRules)
    untrusted_fence: bool = False
    agent_salt: Literal["deterministic", "random"] = "deterministic"
    section_ids: bool = False
    sidecar: bool = True
    include_extra_metadata: bool = False
    raw_blocks: Literal["fenced", "drop"] = "fenced"
    max_tokens: int | None = None
    """If set, the renderer truncates the body at a section boundary and sets truncated=true."""
    txt_header: bool = False


FULL = Profile(name="full", include_extra_metadata=True, transcript=TranscriptRules(non_speech_italic=True))

COMPACT = Profile(
    name="compact",
    minimal_frontmatter=True,
    orientation=False,
    toc="never",
    number_headings=False,
    anchors=False,
    page_markers=False,
    image_comments=False,
    links="numbered_list",
    compact_lists=True,
    tables=TableRules(max_pipe_rows=50, merged_cells="flatten"),
    images=ImageRules(mode="caption_only"),
    sidecar=False,
    max_tokens=16_000,
)

RAG = Profile(
    name="rag",
    summary_blockquote=False,
    orientation=False,
    toc="never",
    image_comments=False,
    footnotes="inline",
    links="text_only",
    tables=TableRules(max_pipe_rows=50, merged_cells="flatten"),
    images=ImageRules(mode="caption_only"),
    chunks=ChunkRules(enabled=True),
    section_ids=True,
)

AGENT = Profile(
    name="agent",
    toc="never",
    tables=TableRules(merged_cells="flatten", csv_sidecar=True),
    untrusted_fence=True,
    section_ids=True,
)

PROFILES: dict[str, Profile] = {"full": FULL, "compact": COMPACT, "rag": RAG, "agent": AGENT}

_ALIASES: dict[str, str] = {
    "numbered_headings": "number_headings",
    "track_changes": "tracked_changes",
    "token_budget": "max_tokens",
    "tables_csv": "tables.csv_sidecar",
    "chunk_tokens": "chunks.chunk_tokens",
    "overlap_tokens": "chunks.overlap_tokens",
    "min_chunk_tokens": "chunks.min_chunk_tokens",
    "timestamps": "transcript.timestamps",
    "confidence_marks": "transcript.confidence_marks",
}

_TRUE = {"true", "1", "yes", "on"}
_FALSE = {"false", "0", "no", "off"}
_NONE = {"none", "null", ""}


def _coerce(value: object, tp: Any, key: str) -> object:
    """Coerce `value` to the annotated type `tp`, accepting strings from query params and CLI flags."""
    origin = typing.get_origin(tp)
    if origin is typing.Union or origin is types.UnionType:
        args = typing.get_args(tp)
        if type(None) in args and (value is None or (isinstance(value, str) and value.strip().lower() in _NONE)):
            return None
        errors: list[str] = []
        for arg in args:
            if arg is type(None):
                continue
            try:
                return _coerce(value, arg, key)
            except ValueError as exc:
                errors.append(str(exc))
        raise ValueError(f"invalid value for {key!r}: {value!r} ({'; '.join(errors)})")
    if origin is Literal:
        allowed = typing.get_args(tp)
        if value in allowed:
            return value
        raise ValueError(f"invalid value for {key!r}: {value!r}; expected one of {', '.join(map(str, allowed))}")
    if tp is bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str) and value.strip().lower() in _TRUE | _FALSE:
            return value.strip().lower() in _TRUE
        if isinstance(value, int) and value in (0, 1):
            return bool(value)
        raise ValueError(f"invalid boolean for {key!r}: {value!r}")
    if tp is int:
        if isinstance(value, bool):
            raise ValueError(f"invalid integer for {key!r}: {value!r}")
        if isinstance(value, int):
            return value
        if isinstance(value, str):
            try:
                return int(value.strip())
            except ValueError:
                raise ValueError(f"invalid integer for {key!r}: {value!r}") from None
        raise ValueError(f"invalid integer for {key!r}: {value!r}")
    if tp is float:
        if isinstance(value, bool):
            raise ValueError(f"invalid number for {key!r}: {value!r}")
        if isinstance(value, int | float):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value.strip())
            except ValueError:
                raise ValueError(f"invalid number for {key!r}: {value!r}") from None
        raise ValueError(f"invalid number for {key!r}: {value!r}")
    if tp is str:
        if isinstance(value, str):
            return value
        raise ValueError(f"invalid string for {key!r}: {value!r}")
    if isinstance(tp, type) and isinstance(value, tp):
        return value
    raise ValueError(f"cannot set {key!r} to {value!r}")


def _replace(obj: Any, attrs: dict[str, object], prefix: str) -> Any:
    hints = typing.get_type_hints(type(obj))
    names = {f.name for f in dataclasses.fields(obj)}
    changes: dict[str, object] = {}
    for attr, value in attrs.items():
        key = f"{prefix}{attr}"
        if attr not in names or attr == "name":
            raise ValueError(f"unknown profile option {key!r}")
        changes[attr] = _coerce(value, hints[attr], key)
    return dataclasses.replace(obj, **changes)


def apply_overrides(profile: Profile, **overrides: object) -> Profile:
    """Return a copy of `profile` with overrides applied. Dotted keys address nested rules
    (`chunks.chunk_tokens=512`). Unknown keys and invalid values raise ValueError."""
    flat: dict[str, object] = {}
    nested: dict[str, dict[str, object]] = {}
    for raw_key, value in overrides.items():
        key = _ALIASES.get(raw_key, raw_key)
        if "." in key:
            group, attr = key.split(".", 1)
            nested.setdefault(group, {})[attr] = value
        else:
            flat[key] = value
    group_names = {"tables", "images", "transcript", "chunks"}
    for key in flat:
        if key in group_names:
            raise ValueError(f"profile option {key!r} is a group; use dotted keys such as {key}.<field>")
    result: Profile = _replace(profile, flat, "")
    for group, attrs in sorted(nested.items()):
        if group not in group_names:
            raise ValueError(f"unknown profile option group {group!r}")
        sub = getattr(result, group)
        result = dataclasses.replace(result, **{group: _replace(sub, attrs, f"{group}.")})
    return result


def get_profile(name: str, /, **overrides: object) -> Profile:
    """Look up a profile by name and apply overrides. Unknown profile names raise ValueError."""
    try:
        base = PROFILES[name]
    except KeyError:
        raise ValueError(f"unknown profile {name!r}; expected one of {', '.join(PROFILES)}") from None
    return apply_overrides(base, **overrides) if overrides else base
