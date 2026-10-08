"""Shared assembly of an Outlook message into a ParsedMessage (docs/spec/part2.md 9c step 7).

Both MSG engines (the native olefile reader and the optional extract-msg adapter) fill a `MapiMessage`;
`assemble` parses the transport headers (property 0x007D) as the real RFC 5322 headers when present, lets the
MAPI properties fill whatever those lack, picks the bodies, and marks `cid:`-referenced inline images.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from email.utils import format_datetime

from ezmd.core.textclean import clean_text
from ezmd.ir import Warning, WarningKind
from ezmd_converters.comms.decode import decode_bytes
from ezmd_converters.comms.model import Attachment, ParsedMessage
from ezmd_converters.comms.options import CommsOptions
from ezmd_converters.comms.parse_eml import EmailParseError, decode_header_value, parse_message_bytes

OUTLOOK_MIME = "application/vnd.ms-outlook"


@dataclass(slots=True)
class MapiMessage:
    headers: dict[str, str] = field(default_factory=dict)
    """MAPI-derived header values (From, To, Cc, Bcc, Subject, Message-ID, In-Reply-To, References)."""
    date: datetime | None = None
    transport: str = ""
    html: bytes | str | None = None
    text: str | None = None
    message_class: str = ""
    attachments: list[Attachment] = field(default_factory=list)
    warnings: list[Warning] = field(default_factory=list)
    extra_headers: list[tuple[str, str]] = field(default_factory=list)
    """Outlook-specific values worth keeping in the sidecar (importance, categories, ...)."""


def _transport(text: str, opts: CommsOptions) -> ParsedMessage:
    if not text.strip():
        return ParsedMessage()
    try:
        return parse_message_bytes(text.strip().encode("utf-8", errors="replace") + b"\r\n\r\n", opts)
    except EmailParseError:
        return ParsedMessage()


def assemble(m: MapiMessage, opts: CommsOptions) -> ParsedMessage:
    pm = _transport(m.transport, opts)
    pm.text = None
    pm.html = None
    for name, value in m.headers.items():
        if value.strip() and not pm.headers.get(name):
            pm.headers[name] = decode_header_value(name, value)
    if pm.date is None and m.date is not None:
        pm.date = m.date
        pm.headers["Date"] = m.date.isoformat()
    if not pm.raw_headers:
        pm.raw_headers = list(pm.headers.items())
        if pm.date is not None:
            pm.raw_headers = [(k, v) for k, v in pm.raw_headers if k != "Date"]
            pm.raw_headers.append(("Date", format_datetime(pm.date)))
    pm.raw_headers.extend(m.extra_headers)
    if m.html:
        raw = m.html if isinstance(m.html, bytes) else m.html.encode("utf-8")
        decoded = decode_bytes(raw, None)
        pm.html = clean_text(decoded.text)
        pm.body_charset, pm.body_charset_confidence = decoded.encoding, decoded.confidence
    if m.text:
        pm.text = clean_text(m.text)
    pm.attachments.extend(m.attachments)
    pm.warnings.extend(m.warnings)
    if "smime" in m.message_class.lower():
        pm.warnings.append(
            Warning(kind=WarningKind.SMIME_NOT_DECRYPTED, message="The Outlook message is S/MIME signed or encrypted.")
        )
    if pm.html:
        lowered = pm.html.lower()
        for att in pm.attachments:
            if att.content_id and f"cid:{att.content_id.lower()}" in lowered and att.mime.startswith("image/"):
                att.inline_image = True
    return pm
