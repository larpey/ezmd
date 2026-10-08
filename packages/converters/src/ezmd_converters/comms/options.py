"""Email option parsing (docs/spec/part2.md 9h). Options arrive as `options.extra["comms.<name>"]`."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ezmd.registry import ConvertOptions

BodyChoice = Literal["auto", "html", "text"]
QuoteMode = Literal["mark", "strip", "keep"]
AttachmentMode = Literal["convert", "list", "skip"]

DEFAULT_MAX_MESSAGES = 5000
DEFAULT_MAX_ATTACHMENT_BYTES = 100 * 1024 * 1024
"""Local per-attachment cap (part2 13.4, Email/MBOX row); the public profile passes 10 MB."""
DEFAULT_MAX_ATTACHMENTS = 200
"""Attachments converted per message; the rest are listed only."""
DEFAULT_MAX_HEADER_CHARS = 16 * 1024
"""Longest header value parsed; longer values are cut (hostile 1 MB To: lines)."""
DEFAULT_MAX_PARTS = 1000
"""MIME parts walked per message; a message with more is truncated."""
MAX_MIME_DEPTH = 32
"""Multipart nesting walked; deeper parts are not visited."""


@dataclass(frozen=True, slots=True)
class CommsOptions:
    body: BodyChoice = "auto"
    strip_quotes: QuoteMode = "mark"
    all_headers: bool = False
    max_messages: int = DEFAULT_MAX_MESSAGES
    attachments: AttachmentMode = "convert"
    max_attachment_depth: int = 3
    max_attachment_bytes: int = DEFAULT_MAX_ATTACHMENT_BYTES
    max_attachments: int = DEFAULT_MAX_ATTACHMENTS
    max_header_chars: int = DEFAULT_MAX_HEADER_CHARS
    max_parts: int = DEFAULT_MAX_PARTS


def _get(options: ConvertOptions, name: str) -> object:
    return options.extra.get(f"comms.{name}")


def _choice(value: object, allowed: tuple[str, ...], default: str) -> str:
    return value if isinstance(value, str) and value in allowed else default


def _positive(value: object, default: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return default
    return int(value) if value >= 1 else default


def _flag(value: object, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return default


def read_options(options: ConvertOptions) -> CommsOptions:
    """Validated email options; unknown or malformed values fall back to the defaults."""
    body = _choice(_get(options, "body"), ("auto", "html", "text"), "auto")
    quotes = _choice(_get(options, "strip_quotes"), ("mark", "strip", "keep"), "mark")
    attachments = _choice(_get(options, "attachments"), ("convert", "list", "skip"), "convert")
    depth = _positive(_get(options, "max_attachment_depth"), options.max_attachment_depth)
    return CommsOptions(
        body=body,  # type: ignore[arg-type]
        strip_quotes=quotes,  # type: ignore[arg-type]
        all_headers=_flag(_get(options, "all_headers"), False),
        max_messages=_positive(_get(options, "max_messages"), DEFAULT_MAX_MESSAGES),
        attachments=attachments,  # type: ignore[arg-type]
        max_attachment_depth=min(depth, options.max_attachment_depth),
        max_attachment_bytes=_positive(_get(options, "max_attachment_bytes"), DEFAULT_MAX_ATTACHMENT_BYTES),
        max_attachments=_positive(_get(options, "max_attachments"), DEFAULT_MAX_ATTACHMENTS),
        max_header_chars=_positive(_get(options, "max_header_chars"), DEFAULT_MAX_HEADER_CHARS),
        max_parts=_positive(_get(options, "max_parts"), DEFAULT_MAX_PARTS),
    )
