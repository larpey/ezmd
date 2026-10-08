"""Document scaffolding shared by the data converters."""

from __future__ import annotations

from pathlib import PurePath

from ezmd.context import Limits
from ezmd.core.textclean import CleanStats
from ezmd.inputs import InputRef
from ezmd.ir import CodeBlock, Document, Heading, InlineSpan, Metadata, Paragraph, SourceType, Warning
from ezmd.registry import ConversionError
from ezmd_converters.data._common import hidden_chars_warning, prov

DATA_LIMITS = Limits(max_bytes=50 * 1024 * 1024, max_rows=1000, max_cols=50, max_depth=64, timeout_s=120.0)
DB_LIMITS = Limits(max_rows=120, max_cols=50, timeout_s=120.0)
CSV_LIMITS = Limits(max_bytes=200 * 1024 * 1024, max_rows=10_000, max_cols=256, timeout_s=120.0)


def mime_of(ref: InputRef) -> str | None:
    return ref.detected.mime if ref.detected else None


def suffix_of(ref: InputRef) -> str:
    return PurePath(ref.display.split("?")[0]).suffix.lower()


def read_capped(ref: InputRef, max_bytes: int, what: str) -> bytes:
    """The whole body, refusing inputs over `max_bytes` with a message that names the cap."""
    size = ref.size()
    if size > max_bytes:
        raise ConversionError(
            f"{what} input is {size} bytes, over the {max_bytes} byte cap",
            user_message=f"This {what} file is larger than the {max_bytes // (1024 * 1024)} MB limit. "
            "Split it or raise data.max_bytes.",
            retryable_with_fallback=False,
        )
    return ref.read()


def new_document(ref: InputRef, *, encoding: str | None = None, confidence: float | None = None) -> Document:
    title = PurePath(ref.display.split("?")[0]).name or ref.display
    meta = Metadata(
        title=title,
        source=ref.display,
        source_type=SourceType.DATA,
        mime=mime_of(ref),
        encoding=encoding,
        encoding_confidence=confidence,
    )
    doc = Document(metadata=meta)
    doc.blocks.append(Heading(level=1, spans=[InlineSpan(text=title)], provenance=prov(ref.display, "/")))
    return doc


def summary(doc: Document, text: str, path: str = "/") -> None:
    doc.blocks.append(Paragraph(spans=[InlineSpan(text=text)], provenance=prov(doc.metadata.source, path)))


MAX_SOURCE_BLOCK_CHARS = 64 * 1024
"""Raw sources up to this size are kept as a code block (Part 2 10c steps 8, 9, 11)."""


def source_block(doc: Document, text: str, language: str) -> None:
    """`## Source` with the raw (cleaned) source as a code block, or a note when it is too large."""
    source = doc.metadata.source
    doc.blocks.append(Heading(level=2, spans=[InlineSpan(text="Source")], provenance=prov(source, "/")))
    body = text.rstrip("\n")
    if len(body) > MAX_SOURCE_BLOCK_CHARS:
        summary(doc, f"(The {len(body):,}-character source is not repeated here; it is over the 64 KB limit.)")
        return
    lines = body.count("\n") + 1
    doc.blocks.append(
        CodeBlock(
            code=body,
            language=language,
            provenance=prov(source, "/", line_start=1, line_end=lines),
        )
    )


def finish(doc: Document, stats: CleanStats, warnings: list[Warning] | None = None) -> Document:
    if warnings:
        doc.warnings.extend(warnings)
    hidden = hidden_chars_warning(stats)
    if hidden is not None:
        doc.warnings.append(hidden)
    return doc.finalize()
