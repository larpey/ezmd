"""Parse RFC 5322 / MIME bytes into a ParsedMessage (docs/spec/part2.md 9c steps 1, 2, 4).

stdlib `email` with `policy.default`. Header values are length-capped before the structured header parser
sees them, raw 8-bit header bytes are repaired as UTF-8, and the MIME tree walk is bounded in depth and part
count. Body bytes are decoded by `comms.decode` (declared charset, then UTF-8, then charset-normalizer).
"""

from __future__ import annotations

import codecs
import mimetypes
import re
from email import policy
from email.header import decode_header
from email.message import EmailMessage, Message
from email.parser import BytesParser
from email.utils import parsedate_to_datetime
from pathlib import PurePosixPath, PureWindowsPath

from ezmd.core.textclean import CleanStats, clean_text
from ezmd.ir import Warning, WarningKind
from ezmd_converters.comms.decode import REPLACEMENT, decode_bytes, repair_header
from ezmd_converters.comms.model import HEADER_FIELDS, Attachment, ParsedMessage
from ezmd_converters.comms.options import MAX_MIME_DEPTH, CommsOptions

_WANTED = {name.lower(): name for name in (*HEADER_FIELDS, "X-Gmail-Labels")}
_WORD_CHARSET = re.compile(r"=\?([^?*]+)(?:\*[^?]*)?\?[bBqQ]\?")
_WS = re.compile(r"\s+")
_CID_REF = re.compile(r"""cid:([^"'\s>)]+)""", re.IGNORECASE)
MAX_NAME_CHARS = 200
TNEF_MIMES = frozenset({"application/ms-tnef", "application/vnd.ms-tnef"})
SMIME_MIMES = frozenset({"application/pkcs7-mime", "application/x-pkcs7-mime"})
SIGNATURE_MIMES = frozenset(
    {"application/pkcs7-signature", "application/x-pkcs7-signature", "application/pgp-signature"}
)


class EmailParseError(Exception):
    """The bytes could not be parsed as a message at all."""


def parse_message_bytes(raw: bytes, opts: CommsOptions) -> ParsedMessage:
    try:
        msg = BytesParser(policy=policy.default).parsebytes(raw)
    except RecursionError as e:
        raise EmailParseError("MIME structure nests too deeply") from e
    except Exception as e:  # the stdlib parser is lenient; anything raised here is a broken input
        raise EmailParseError(f"unparseable message: {type(e).__name__}") from e
    return parse_message(msg, opts)


def parse_message(msg: Message, opts: CommsOptions) -> ParsedMessage:
    out = ParsedMessage()
    _headers(msg, out, opts)
    walker = _Walker(out, opts)
    try:
        walker.walk(msg, 0)
    except RecursionError:
        out.warnings.append(
            Warning(
                kind=WarningKind.TRUNCATED, message="The MIME structure nests too deeply; deeper parts were skipped."
            )
        )
        out.truncated = True
    walker.finish()
    return out


# ---------------------------------------------------------------------------
# Headers
# ---------------------------------------------------------------------------


def decode_header_value(name: str, value: str, stats: CleanStats | None = None) -> str:
    """RFC 2047 decoding through the policy's structured headers; falls back to `email.header`. Encoded words
    in an unknown charset (the policy yields U+FFFD) are re-decoded from their bytes by detection. Control,
    bidi, and invisible characters are removed (counted in `stats`, decoded CR/LF as control characters) and
    whitespace collapses, so a header value is always one line."""
    value = repair_header(value)
    try:
        text = str(policy.default.header_factory(name, value))
    except Exception:
        text = _decode_words(value)
    if REPLACEMENT in text and "=?" in value:
        text = _decode_words(value)
    local = stats if stats is not None else CleanStats()
    cleaned = clean_text(text, local)
    local.control += cleaned.count("\n")
    return _WS.sub(" ", cleaned).strip()


ADDRESS_HEADERS = frozenset({"from", "to", "cc", "bcc", "reply-to", "sender", "resent-to", "resent-cc"})
MARKER_ROOM = 80
"""Characters kept free under the cap for the inline truncation marker."""


def cut_header(name: str, raw: str, limit: int) -> tuple[str, str]:
    """Cut an over-long raw header value at an address (or word) boundary below `limit`. Returns the kept
    part and the inline marker to append after decoding."""
    budget = max(1, limit - MARKER_ROOM)
    head = raw[:budget]
    if name.lower() in ADDRESS_HEADERS:
        comma = head.rfind(",")
        if comma > 0:
            head = head[:comma]
        rest = raw[len(head) :]
        more = rest.count(",")
        return head, f" … ({more} more recipients truncated)"
    space = head.rfind(" ")
    if space > budget // 2:
        head = head[:space]
    return head, f" … ({len(raw) - len(head)} characters truncated)"


def _decode_words(value: str) -> str:
    try:
        parts = decode_header(value)
    except Exception:
        return value
    out: list[str] = []
    for chunk, charset in parts:
        if isinstance(chunk, str):
            out.append(chunk)
        else:
            out.append(_word_bytes(chunk, charset))
    return "".join(out)


def _word_bytes(chunk: bytes, charset: str | None) -> str:
    """An encoded word: its declared charset strictly, else UTF-8, else Windows-1252 (header words are too short
    for statistical detection)."""
    for enc in (charset, "utf-8", "cp1252"):
        text = _try_decode(chunk, enc)
        if text is not None:
            return text
    return chunk.decode("latin-1")


def _known_codec(name: str) -> bool:
    try:
        codecs.lookup(name)
    except LookupError:
        return False
    return True


def _try_decode(chunk: bytes, enc: str | None) -> str | None:
    if not enc:
        return None
    try:
        return chunk.decode(enc)
    except (LookupError, UnicodeDecodeError):
        return None  # unknown codec or wrong charset: the caller tries the next candidate


def _headers(msg: Message, out: ParsedMessage, opts: CommsOptions) -> None:
    cut = 0
    unknown: set[str] = set()
    stats = CleanStats()
    for name, value in msg.raw_items():
        raw = str(value)
        marker = ""
        if len(raw) > opts.max_header_chars:
            raw, marker = cut_header(name, raw, opts.max_header_chars)
            cut += 1
        unknown.update(c for c in _WORD_CHARSET.findall(raw) if not _known_codec(c))
        decoded = decode_header_value(name, raw, stats) + marker
        out.raw_headers.append((name, decoded))
        canonical = _WANTED.get(name.lower())
        if canonical is not None and canonical not in out.headers:
            out.headers[canonical] = decoded
    if cut:
        out.truncated = True
        out.warnings.append(
            Warning(
                kind=WarningKind.TRUNCATED,
                message=f"{cut} header value(s) longer than {opts.max_header_chars} characters were cut.",
                count=cut,
                detail={"reason": "header_too_long", "max_chars": opts.max_header_chars},
            )
        )
    if stats.total:
        out.warnings.append(
            Warning(
                kind=WarningKind.REMOVED_HIDDEN_ELEMENTS,
                message=f"{stats.total} control, line-break, bidi, or invisible character(s) removed from headers.",
                count=stats.total,
                detail={"where": "headers", "control": stats.control, "invisible": stats.invisible},
            )
        )
    if unknown:
        out.warnings.append(
            Warning(
                kind=WarningKind.ENCODING_UNCERTAIN,
                message=(
                    "Header encoded words name an unknown charset ("
                    + ", ".join(sorted(unknown))[:200]
                    + "); they were decoded as UTF-8 or Windows-1252."
                ),
                count=len(unknown),
                detail={"reason": "unknown_header_charset", "charsets": ", ".join(sorted(unknown))[:200]},
            )
        )
    date = out.headers.get("Date")
    if date:
        try:
            out.date = parsedate_to_datetime(date)
        except (TypeError, ValueError, IndexError):
            out.date = None
        if out.date is not None:
            out.headers["Date"] = out.date.isoformat()
    labels = out.headers.pop("X-Gmail-Labels", "")
    out.labels = [x.strip() for x in labels.split(",") if x.strip()]


# ---------------------------------------------------------------------------
# MIME walk
# ---------------------------------------------------------------------------


def safe_name(raw: str | None, index: int, mime: str) -> str:
    """A display name for an attachment: the basename only, cleaned and length-capped."""
    name = clean_text(raw or "").strip()
    if name:
        name = PureWindowsPath(PurePosixPath(name).name).name.strip().lstrip(".")
    name = _WS.sub(" ", name)[:MAX_NAME_CHARS]
    if not name:
        ext = mimetypes.guess_extension(mime) or ".bin"
        name = f"attachment-{index}{ext}"
    return name


class _Walker:
    def __init__(self, out: ParsedMessage, opts: CommsOptions) -> None:
        self.out = out
        self.opts = opts
        self.parts = 0
        self.html: list[str] = []
        self.text: list[str] = []
        self.capped = False
        self.deep = False
        self.uncertain = 0
        self.mislabeled: list[str] = []

    def walk(self, part: Message, depth: int) -> None:
        self.parts += 1
        if self.parts > self.opts.max_parts:
            self.capped = True
            return
        if part.is_multipart() and part.get_content_maintype() == "multipart":
            if depth >= MAX_MIME_DEPTH:
                self.deep = True
                return
            payload = part.get_payload()
            if isinstance(payload, list):
                for sub in payload:
                    if isinstance(sub, Message):
                        self.walk(sub, depth + 1)
            return
        self._leaf(part)

    def _leaf(self, part: Message) -> None:
        mime = part.get_content_type().lower()
        disposition = (part.get_content_disposition() or "").lower() or None
        try:
            filename = part.get_filename()
        except Exception:
            filename = None
        named = bool(filename)
        if mime == "message/rfc822" or (mime == "message/global"):
            self._message(part, filename, disposition)
            return
        is_body = mime in ("text/plain", "text/html") and disposition != "attachment" and not named
        if is_body:
            self._body(part, mime)
            return
        data = _payload_bytes(part)
        index = len(self.out.attachments) + 1
        name = safe_name(filename, index, mime)
        kind = "file"
        if mime in TNEF_MIMES or name.lower() == "winmail.dat":
            kind = "tnef"
        elif mime in SMIME_MIMES or name.lower().endswith(".p7m"):
            kind = "smime"
        elif mime in SIGNATURE_MIMES:
            kind = "signature"
        cid = part.get("Content-ID")
        content_id = str(cid).strip().strip("<>").strip() if cid else None
        self.out.attachments.append(
            Attachment(
                name=name,
                mime=mime,
                data=data,
                size=len(data),
                content_id=content_id or None,
                disposition=disposition,
                kind=kind,
            )
        )

    def _message(self, part: Message, filename: str | None, disposition: str | None) -> None:
        payload = part.get_payload()
        inner = payload[0] if isinstance(payload, list) and payload else None
        data = b""
        if isinstance(inner, Message):
            try:
                data = inner.as_bytes(policy=policy.default) if isinstance(inner, EmailMessage) else inner.as_bytes()
            except Exception:
                data = b""
        subject = ""
        if isinstance(inner, Message):
            raw_subject = inner.get("Subject")
            subject = decode_header_value("Subject", str(raw_subject)) if raw_subject else ""
        index = len(self.out.attachments) + 1
        base = filename or (f"{subject[:80]}.eml" if subject else "")
        name = safe_name(base, index, "message/rfc822")
        if not name.lower().endswith((".eml", ".msg")) and not filename:
            name += ".eml"
        self.out.attachments.append(
            Attachment(
                name=name, mime="message/rfc822", data=data, size=len(data), disposition=disposition, kind="message"
            )
        )

    def _body(self, part: Message, mime: str) -> None:
        raw = _payload_bytes(part)
        declared = part.get_content_charset()
        decoded = decode_bytes(raw, declared)
        if decoded.replacements or decoded.declared_failed:
            self.uncertain += max(1, decoded.replacements)
            if decoded.declared_failed and declared:
                self.mislabeled.append(f"{declared} (decoded as {decoded.encoding})")
        text = clean_text(decoded.text)
        if mime == "text/html":
            self.html.append(text)
        else:
            if not self.text:
                self.out.text_flowed = str(part.get_param("format") or "").lower() == "flowed"
                self.out.text_delsp = str(part.get_param("delsp") or "").lower() == "yes"
            self.text.append(text)
        if self.out.body_charset is None:
            self.out.body_charset = decoded.encoding
            self.out.body_charset_confidence = decoded.confidence

    def finish(self) -> None:
        out = self.out
        out.html = "\n".join(self.html) if self.html else None
        out.text = "\n\n".join(self.text) if self.text else None
        if out.html:
            refs = {m.group(1).strip("<>").lower() for m in _CID_REF.finditer(out.html)}
            for att in out.attachments:
                if att.content_id and att.content_id.lower() in refs and att.mime.startswith("image/"):
                    att.inline_image = True
        if self.uncertain:
            out.warnings.append(
                Warning(
                    kind=WarningKind.ENCODING_UNCERTAIN,
                    message=(
                        "A body part's declared charset did not match its bytes"
                        + (f" ({', '.join(self.mislabeled[:3])})" if self.mislabeled else "")
                        + "; the text was decoded by detection."
                    ),
                    count=self.uncertain,
                    detail={
                        "reason": "declared_charset_mismatch" if self.mislabeled else "replacement_characters",
                        "encoding": out.body_charset or "unknown",
                    },
                )
            )
        if self.capped or self.deep:
            out.truncated = True
            reason = "max_parts" if self.capped else "mime_depth"
            msg = (
                f"The message has more than {self.opts.max_parts} MIME parts; the rest were skipped."
                if self.capped
                else f"MIME parts nested deeper than {MAX_MIME_DEPTH} levels were skipped."
            )
            out.warnings.append(Warning(kind=WarningKind.TRUNCATED, message=msg, detail={"reason": reason}))


def _payload_bytes(part: Message) -> bytes:
    try:
        data = part.get_payload(decode=True)
    except Exception:
        data = None
    if isinstance(data, bytes):
        return data
    raw = part.get_payload()
    if isinstance(raw, str):
        return raw.encode("utf-8", errors="surrogateescape")
    return b""
