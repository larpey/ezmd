"""extract-msg adapter (GPL-3.0; only in the `nonfree` extra). Importing this module shows the license notice.

The optional second engine for Outlook .msg (docs/spec/part2.md 9b step 2): used when the native olefile
reader (`comms.msg_native`) fails and the extra is installed. It fills the same `MapiMessage` as the native
reader. Embedded messages become nested ParsedMessages up to the attachment depth.
"""

from __future__ import annotations

import mimetypes
from datetime import datetime
from typing import Any

import extract_msg  # type: ignore[import-not-found,unused-ignore]

from ezmd.core.licensing import notify_once
from ezmd.ir import Warning, WarningKind
from ezmd_converters.comms.decode import decode_bytes
from ezmd_converters.comms.model import Attachment, ParsedMessage
from ezmd_converters.comms.msg_common import OUTLOOK_MIME, MapiMessage, assemble
from ezmd_converters.comms.options import CommsOptions
from ezmd_converters.comms.parse_eml import safe_name

notify_once("extract-msg")

ENGINE_VERSION = str(getattr(extract_msg, "__version__", "unknown"))


def open_msg(path: str) -> Any:
    return extract_msg.openMsg(path, strict=False)


def _s(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return decode_bytes(value, None).text
    return str(value)


def to_parsed(m: Any, opts: CommsOptions, depth: int = 0) -> ParsedMessage:
    mapi = MapiMessage(
        headers={
            "From": _s(getattr(m, "sender", None)),
            "To": _s(getattr(m, "to", None)),
            "Cc": _s(getattr(m, "cc", None)),
            "Bcc": _s(getattr(m, "bcc", None)),
            "Subject": _s(getattr(m, "subject", None)),
            "Message-ID": _s(getattr(m, "messageId", None)),
            "In-Reply-To": _s(getattr(m, "inReplyTo", None)),
        },
        transport=_s(getattr(m, "headerText", None) or ""),
        message_class=_s(getattr(m, "classType", "")),
    )
    date = getattr(m, "date", None)
    if isinstance(date, datetime):
        mapi.date = date
    elif date:
        mapi.headers["Date"] = _s(date)
    html = getattr(m, "htmlBody", None)
    if html:
        mapi.html = html if isinstance(html, bytes) else str(html)
    body = getattr(m, "body", None)
    if body:
        mapi.text = _s(body)
    _attachments(m, mapi, opts, depth)
    return assemble(mapi, opts)


def _attachments(m: Any, mapi: MapiMessage, opts: CommsOptions, depth: int) -> None:
    for n, a in enumerate(getattr(m, "attachments", None) or [], start=1):
        raw_name = _s(getattr(a, "longFilename", None) or getattr(a, "shortFilename", None) or "")
        data = getattr(a, "data", None)
        cid = _s(getattr(a, "cid", None) or getattr(a, "contentId", None) or "").strip("<> ") or None
        if isinstance(data, bytes):
            mime = _s(getattr(a, "mimetype", None)) or mimetypes.guess_type(raw_name)[0] or "application/octet-stream"
            name = safe_name(raw_name, n, mime)
            kind = "smime" if name.lower().endswith(".p7m") else "file"
            mapi.attachments.append(
                Attachment(name=name, mime=mime.lower(), data=data, size=len(data), content_id=cid, kind=kind)
            )
            continue
        if data is not None and hasattr(data, "attachments"):
            subject = _s(getattr(data, "subject", None))
            name = safe_name(raw_name or (f"{subject[:80]}.msg" if subject else ""), n, OUTLOOK_MIME)
            nested = to_parsed(data, opts, depth + 1) if depth + 1 <= opts.max_attachment_depth else None
            mapi.attachments.append(
                Attachment(name=name, mime=OUTLOOK_MIME, data=None, size=0, kind="message", message=nested)
            )
            continue
        mapi.warnings.append(
            Warning(
                kind=WarningKind.MSG_PARTIAL,
                message=f"Attachment {n} of the Outlook message could not be read.",
                detail={"index": n},
            )
        )
