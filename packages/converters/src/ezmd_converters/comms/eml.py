"""comms.eml: one RFC 5322 message (.eml, message/rfc822) to a Document (docs/spec/part2.md 9c steps 1-6)."""

from __future__ import annotations

import re
from pathlib import Path

from ezmd.context import Limits
from ezmd.detect import looks_like_rfc822
from ezmd.inputs import InputRef
from ezmd.ir import Document, Metadata, SourceType
from ezmd.registry import ConversionError, ConvertOptions
from ezmd_converters.comms.build import MessageBuild, MessageSpec, build_message
from ezmd_converters.comms.model import ParsedMessage
from ezmd_converters.comms.options import read_options
from ezmd_converters.comms.parse_eml import EmailParseError, parse_message_bytes

EML_MIMES = ("message/rfc822", "message/global")
EML_EXTS = (".eml", ".mht.eml", ".emlx")
DEFAULT_MAX_BYTES = 200 * 1024 * 1024
"""One message: the largest attachment cap (100 MB) plus base64 overhead and the body."""
_HEADER_LINE = re.compile(rb"^[!-9;-~]{1,76}:[ \t]?", re.MULTILINE)
_KEY_HEADERS = re.compile(rb"(?im)^(from|received|return-path|message-id|subject|date|mime-version):")
SIDECAR_KEY = "email_headers"


def looks_like_message(head: bytes) -> bool:
    """RFC 5322 headers at the start: the first line is a header and From:/Received:/Return-Path: (or two
    of the usual headers) appear in the first 2 KB (part2 9a)."""
    sample = head[:2048].lstrip(b"\r\n")
    if not _HEADER_LINE.match(sample):
        return False
    return len({m.group(1).lower() for m in _KEY_HEADERS.finditer(sample)}) >= 2


def is_mbox(head: bytes) -> bool:
    if not head.startswith(b"From "):
        return False
    nl = head.find(b"\n")
    return nl > 0 and looks_like_message(head[nl + 1 :])


def message_metadata(msg: ParsedMessage, built: MessageBuild, source: str, mime: str | None) -> Metadata:
    sender = msg.sender
    name = sender.split("<", 1)[0].strip().strip('"') if "<" in sender else sender
    meta = Metadata(
        title=msg.subject or "(no subject)",
        source=source,
        source_type=SourceType.EMAIL,
        mime=mime,
        author=name or None,
        published=msg.date,
        encoding=msg.body_charset,
        encoding_confidence=msg.body_charset_confidence,
    )
    extra = meta.extra
    if msg.message_id:
        extra["message_id"] = msg.message_id
    if msg.headers.get("In-Reply-To"):
        extra["in_reply_to"] = msg.headers["In-Reply-To"]
    extra["body_source"] = built.body_source
    extra["body_alternatives"] = built.body_alternatives
    extra["attachments"] = built.attachment_count
    if msg.labels:
        extra["labels"] = ", ".join(msg.labels)
    return meta


class EmlConverter:
    id = "comms.eml"
    family = "comms"
    priority = 10
    experimental = False
    requires_extras: tuple[str, ...] = ()
    mimes: tuple[str, ...] = EML_MIMES
    limits = Limits(max_bytes=DEFAULT_MAX_BYTES, max_depth=3, timeout_s=300.0)

    def can_handle(self, ref: InputRef) -> float:
        mime = ref.detected.mime if ref.detected else None
        if not ref.has_body:
            return 0.0
        head = ref.head(4096)
        if is_mbox(head):
            return 0.2
        name = ref.display.lower()
        if mime in EML_MIMES:
            return 1.0
        textual = mime is not None and (mime.startswith("text/") or mime == "application/octet-stream")
        if textual and name.endswith(EML_EXTS):
            return 0.95
        if textual and looks_like_rfc822(head, Path(name).suffix or None):
            # Detection can call a message `text/html` (an HTML body after the headers); headers win.
            return 0.95
        return 0.0

    def convert(self, ref: InputRef, options: ConvertOptions) -> Document:
        cap = options.ctx.limits.max_bytes or DEFAULT_MAX_BYTES
        if ref.size() > cap:
            raise ConversionError(
                f"{ref.display} is {ref.size()} bytes, over the {cap} byte email cap",
                user_message="This email is larger than the size limit.",
                retryable_with_fallback=False,
            )
        opts = read_options(options)
        options.ctx.progress("parse", 0.1, "parsing message")
        try:
            msg = parse_message_bytes(ref.read(), opts)
        except EmailParseError as e:
            raise ConversionError(str(e), user_message="This email could not be parsed.") from e
        if not msg.raw_headers:
            raise ConversionError(
                f"{ref.display} has no RFC 5322 headers", user_message="This file is not an email message."
            )
        source = ref.display or Path(str(ref.local_path or "message.eml")).name

        built = build_message(msg, MessageSpec(source=source), options, opts)
        doc = Document(
            metadata=message_metadata(msg, built, source, ref.detected.mime if ref.detected else None),
            blocks=built.blocks,
            warnings=built.warnings,
            children=built.children,
            truncated=msg.truncated,
        )
        if built.headers_sidecar:
            doc.sidecar_extra[SIDECAR_KEY] = built.headers_sidecar
        options.ctx.progress("done", 1.0, "converted")
        return doc.finalize()
