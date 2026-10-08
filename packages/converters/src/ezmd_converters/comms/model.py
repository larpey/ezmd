"""The intermediate every email source (EML, MBOX member, Outlook MSG) is read into (part2 9c step 7).

`build.build_message` turns a ParsedMessage into IR blocks and child Documents, so the three converters share
headers, body selection, quote handling, and attachment conversion.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from ezmd.ir import Warning

HEADER_FIELDS = (
    "From",
    "To",
    "Cc",
    "Bcc",
    "Date",
    "Subject",
    "Message-ID",
    "In-Reply-To",
    "References",
    "Reply-To",
    "List-Id",
)
"""Headers rendered in the headers Table, in this order, when present (part2 9c step 1)."""


@dataclass(slots=True)
class Attachment:
    """One attachment or inline part.

    data: decoded bytes (None for an embedded Outlook message, which carries `message` instead).
    content_id: the `Content-ID` without angle brackets, used to resolve `cid:` references.
    inline_image: an image part referenced from the HTML body by `cid:` (rendered in place, not converted).
    kind: "file", "message" (message/rfc822 or embedded .msg), "tnef", "smime", "signature".
    """

    name: str
    mime: str
    data: bytes | None
    size: int
    content_id: str | None = None
    disposition: str | None = None
    kind: str = "file"
    inline_image: bool = False
    message: ParsedMessage | None = None


@dataclass(slots=True)
class ParsedMessage:
    """Headers, body candidates, and attachments of one message.

    headers: decoded values of HEADER_FIELDS (and X-Gmail-Labels) that are present.
    raw_headers: every header as (name, decoded value), for the sidecar and `all_headers`.
    date: the parsed Date header (timezone-aware when the header had an offset).
    html / text: decoded body candidates; `text_flowed` / `text_delsp` record format=flowed.
    """

    headers: dict[str, str] = field(default_factory=dict)
    raw_headers: list[tuple[str, str]] = field(default_factory=list)
    date: datetime | None = None
    html: str | None = None
    text: str | None = None
    text_flowed: bool = False
    text_delsp: bool = False
    body_charset: str | None = None
    body_charset_confidence: float | None = None
    attachments: list[Attachment] = field(default_factory=list)
    warnings: list[Warning] = field(default_factory=list)
    truncated: bool = False
    labels: list[str] = field(default_factory=list)

    @property
    def subject(self) -> str:
        return self.headers.get("Subject", "").strip()

    @property
    def message_id(self) -> str | None:
        value = self.headers.get("Message-ID", "").strip()
        return value or None

    @property
    def sender(self) -> str:
        return self.headers.get("From", "").strip()
