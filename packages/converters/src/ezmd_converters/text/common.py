"""The size cap shared by the plain text and Markdown converters (docs/internal/spec/part2.md 13.4)."""

from __future__ import annotations

from ezmd.inputs import InputRef
from ezmd.ir import Document, Warning, WarningKind
from ezmd.registry import ConvertOptions

DEFAULT_MAX_TEXT_BYTES = 50 * 1024 * 1024
"""Part 2 13.4: plain text, Markdown and LaTeX cap at 50 MB locally and truncate with a warning. The whole
text, its decoded copy and the block tree sit in memory at once, so an uncapped 150 MB file needed more than
a worker's 3 GB. Override with `--opt extra.text.max_bytes=N`."""


def max_text_bytes(options: ConvertOptions) -> int:
    value = options.extra.get("text.max_bytes")
    if isinstance(value, bool) or not isinstance(value, int | str):
        return DEFAULT_MAX_TEXT_BYTES
    try:
        n = int(value)
    except ValueError:
        return DEFAULT_MAX_TEXT_BYTES
    return n if n > 0 else DEFAULT_MAX_TEXT_BYTES


def read_capped(ref: InputRef, options: ConvertOptions) -> tuple[bytes, int | None]:
    """The input's bytes, cut at the last line break within the cap. Returns (raw, cap) where cap is the
    limit that applied, or None when the whole input fit."""
    limit = max_text_bytes(options)
    if ref.size() <= limit:
        return ref.read(), None
    raw = ref.head(limit)
    cut = raw.rfind(b"\n")
    return (raw[: cut + 1] if cut > 0 else raw), limit


def mark_truncated(doc: Document, limit: int) -> None:
    doc.truncated = True
    doc.warnings.append(
        Warning(
            kind=WarningKind.SIZE_CAP,
            message=f"The file is larger than {limit:,} bytes; only the first {limit:,} bytes were converted.",
            detail={"reason": "max_bytes", "max_bytes": limit},
        )
    )
