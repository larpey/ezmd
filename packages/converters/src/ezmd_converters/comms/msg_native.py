"""Native Outlook .msg reader on olefile (BSD-2-Clause), the default MSG path (docs/spec/part2.md 9b step 2).

Reads the documented MS-OXMSG property streams: `__substg1.0_<id><type>` (`001F` UTF-16LE, `001E` 8-bit in the
message code page, `0102` binary), fixed-size values from `__properties_version1.0` (dates, recipient type,
attach method, code page), `__recip_version1.0_#` recipients, `__attach_version1.0_#` attachments (`3701`
data, `3707`/`3704` names, `370E` mime, `3712` content id) and embedded messages (`3701000D` storages). The
body is `1000` text, `1013` HTML, or `1009` compressed RTF, which is decompressed (MS-OXRTFCP) and
de-encapsulated to HTML when it carries `\\fromhtml1` (MS-OXRTFEX), else reduced to text.
"""

from __future__ import annotations

import mimetypes
import struct
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import olefile  # type: ignore[import-untyped]

from ezmd.ir import Warning, WarningKind
from ezmd_converters.comms.model import Attachment, ParsedMessage
from ezmd_converters.comms.msg_common import OUTLOOK_MIME, MapiMessage, assemble
from ezmd_converters.comms.options import CommsOptions
from ezmd_converters.comms.parse_eml import safe_name
from ezmd_converters.comms.rtf import RtfError, decompress, html_from_rtf, text_from_rtf

ENGINE_VERSION = f"olefile {getattr(olefile, '__version__', 'unknown')}"
MAX_CHILDREN = 1000
"""Recipients or attachments read per message; a hostile file cannot make us walk more."""
MAX_STRING_BYTES = 16 * 1024 * 1024
PT_LONG, PT_SYSTIME = 0x0003, 0x0040
_EPOCH = datetime(1601, 1, 1, tzinfo=UTC)
RECIPIENT_FIELD = {1: "To", 2: "Cc", 3: "Bcc"}


class MsgReadError(Exception):
    """Not an Outlook message, or the compound file is unreadable."""


@dataclass(slots=True)
class _Ole:
    ole: object
    names: dict[tuple[str, ...], tuple[str, ...]] = field(default_factory=dict)
    """Lower-cased path -> actual path for every stream and storage."""

    def children(self, prefix: tuple[str, ...], startswith: str) -> list[tuple[str, ...]]:
        n = len(prefix)
        low = tuple(p.lower() for p in prefix)
        out = [
            actual
            for key, actual in self.names.items()
            if len(key) == n + 1 and key[:n] == low and key[n].startswith(startswith.lower())
        ]
        return sorted(out)

    def stream(self, path: tuple[str, ...], limit: int = MAX_STRING_BYTES) -> bytes | None:
        actual = self.names.get(tuple(p.lower() for p in path))
        if actual is None:
            return None
        ole = self.ole
        if ole.get_type(list(actual)) != olefile.STGTY_STREAM:  # type: ignore[attr-defined]
            return None
        if ole.get_size(list(actual)) > limit:  # type: ignore[attr-defined]
            return None
        data: bytes = ole.openstream(list(actual)).read()  # type: ignore[attr-defined]
        return data

    def size(self, path: tuple[str, ...]) -> int:
        actual = self.names.get(tuple(p.lower() for p in path))
        return int(self.ole.get_size(list(actual))) if actual else 0  # type: ignore[attr-defined]

    def tree_size(self, prefix: tuple[str, ...]) -> int:
        """Total bytes of every stream under a storage (the size of an embedded message)."""
        low = tuple(p.lower() for p in prefix)
        total = 0
        ole = self.ole
        for key, actual in self.names.items():
            inside = len(key) > len(low) and key[: len(low)] == low
            if inside and ole.get_type(list(actual)) == olefile.STGTY_STREAM:  # type: ignore[attr-defined]
                total += int(ole.get_size(list(actual)))  # type: ignore[attr-defined]
        return total

    def exists(self, path: tuple[str, ...]) -> bool:
        return tuple(p.lower() for p in path) in self.names


def open_ole(data: bytes) -> _Ole:
    # olefile treats a bytes argument shorter than MINIMAL_OLEFILE_SIZE as a *file name*: check first.
    if len(data) < olefile.MINIMAL_OLEFILE_SIZE or not data.startswith(olefile.MAGIC):
        raise MsgReadError("not an OLE2 compound file")
    try:
        ole = olefile.OleFileIO(data)
        paths = ole.listdir(streams=True, storages=True)
    except Exception as e:  # olefile raises many types on corrupt sectors/FAT chains
        raise MsgReadError(f"unreadable compound file: {type(e).__name__}") from e
    names = {tuple(p.lower() for p in path): tuple(path) for path in paths}
    reader = _Ole(ole=ole, names=names)
    if not any(k[-1].startswith("__substg1.0_") for k in names):
        raise MsgReadError("the compound file has no MAPI property streams")
    return reader


class _Props:
    """Fixed-size values from a `__properties_version1.0` stream."""

    def __init__(self, raw: bytes | None, header: int) -> None:
        self.values: dict[int, tuple[int, bytes]] = {}
        if not raw:
            return
        for off in range(header, len(raw) - 15, 16):
            tag = struct.unpack_from("<I", raw, off)[0]
            self.values[tag >> 16] = (tag & 0xFFFF, raw[off + 8 : off + 16])

    def long(self, pid: int) -> int | None:
        v = self.values.get(pid)
        return struct.unpack_from("<I", v[1])[0] if v and v[0] == PT_LONG else None

    def time(self, pid: int) -> datetime | None:
        v = self.values.get(pid)
        if not v or v[0] != PT_SYSTIME:
            return None
        ticks = struct.unpack_from("<Q", v[1])[0]
        try:
            return _EPOCH + timedelta(microseconds=ticks // 10)
        except OverflowError:
            return None


class _Reader:
    def __init__(self, ole: _Ole, opts: CommsOptions) -> None:
        self.ole = ole
        self.opts = opts
        self.partial: list[str] = []

    def string(self, prefix: tuple[str, ...], pid: int, codepage: str) -> str:
        raw = self.ole.stream((*prefix, f"__substg1.0_{pid:04X}001F"))
        if raw is not None:
            return raw.decode("utf-16-le", errors="replace").rstrip(chr(0))
        raw = self.ole.stream((*prefix, f"__substg1.0_{pid:04X}001E"))
        if raw is not None:
            return raw.decode(codepage, errors="replace").rstrip(chr(0))
        return ""

    def binary(self, prefix: tuple[str, ...], pid: int, limit: int = MAX_STRING_BYTES) -> bytes | None:
        return self.ole.stream((*prefix, f"__substg1.0_{pid:04X}0102"), limit)

    def message(self, prefix: tuple[str, ...], depth: int) -> ParsedMessage:
        props = _Props(self.ole.stream((*prefix, "__properties_version1.0")), 32 if not prefix else 24)
        cp = _codepage(props)

        def s(pid: int) -> str:
            return self.string(prefix, pid, cp)

        mapi = MapiMessage(transport=s(0x007D), message_class=s(0x001A))
        name, email = s(0x0C1A), s(0x5D01) or _smtp(s(0x0C1F)) or _smtp(s(0x0065))
        mapi.headers["From"] = f"{name} <{email}>" if name and email else (name or email)
        mapi.headers["Subject"] = s(0x0037)
        mapi.headers["Message-ID"] = s(0x1035)
        mapi.headers["In-Reply-To"] = s(0x1042)
        mapi.headers["References"] = s(0x1039)
        self._recipients(prefix, mapi, cp, {"To": s(0x0E04), "Cc": s(0x0E03), "Bcc": s(0x0E02)})
        mapi.date = props.time(0x0039) or props.time(0x0E06)
        importance = props.long(0x0017)
        if importance is not None:
            mapi.extra_headers.append(("X-MS-Importance", ("low", "normal", "high")[min(importance, 2)]))
        self._bodies(prefix, mapi, cp)
        self._attachments(prefix, mapi, cp, depth)
        if self.partial:
            mapi.warnings.append(
                Warning(
                    kind=WarningKind.MSG_PARTIAL,
                    message="Parts of the Outlook message could not be read: " + ", ".join(self.partial[:5]) + ".",
                    count=len(self.partial),
                )
            )
            self.partial = []
        return assemble(mapi, self.opts)

    def _recipients(self, prefix: tuple[str, ...], mapi: MapiMessage, cp: str, display: dict[str, str]) -> None:
        found: dict[str, list[str]] = {}
        for path in self.ole.children(prefix, "__recip_version1.0_#")[:MAX_CHILDREN]:
            props = _Props(self.ole.stream((*path, "__properties_version1.0")), 8)
            field_name = RECIPIENT_FIELD.get(props.long(0x0C15) or 1, "To")
            name = self.string(path, 0x3001, cp)
            addr = self.string(path, 0x39FE, cp) or _smtp(self.string(path, 0x3003, cp))
            entry = f"{name} <{addr}>" if name and addr and name != addr else (addr or name)
            if entry:
                found.setdefault(field_name, []).append(entry)
        for key in ("To", "Cc", "Bcc"):
            mapi.headers[key] = ", ".join(found[key]) if key in found else display.get(key, "")

    def _bodies(self, prefix: tuple[str, ...], mapi: MapiMessage, cp: str) -> None:
        mapi.text = self.string(prefix, 0x1000, cp) or None
        html = self.binary(prefix, 0x1013)
        mapi.html = html or (self.string(prefix, 0x1013, cp) or None)
        if mapi.html or mapi.text:
            return
        blob = self.binary(prefix, 0x1009)
        if not blob:
            return
        try:
            rtf, crc_ok = decompress(blob)
        except RtfError as e:
            self.partial.append(f"compressed RTF body ({e})")
            return
        if not crc_ok:
            self.partial.append("compressed RTF body (CRC mismatch)")
        encapsulated = html_from_rtf(rtf)
        if encapsulated is not None:
            mapi.html = encapsulated
        else:
            mapi.text = text_from_rtf(rtf)

    def _attachments(self, prefix: tuple[str, ...], mapi: MapiMessage, cp: str, depth: int) -> None:
        cap = self.opts.max_attachment_bytes
        for n, path in enumerate(self.ole.children(prefix, "__attach_version1.0_#")[:MAX_CHILDREN], start=1):
            raw_name = self.string(path, 0x3707, cp) or self.string(path, 0x3704, cp) or self.string(path, 0x3001, cp)
            embedded = (*path, "__substg1.0_3701000D")
            if self.ole.exists(embedded):
                nested = None
                if depth + 1 <= self.opts.max_attachment_depth:
                    nested = _Reader(self.ole, self.opts).message(embedded, depth + 1)
                subject = nested.subject if nested else ""
                name = safe_name(raw_name or (f"{subject[:80]}.msg" if subject else ""), n, OUTLOOK_MIME)
                mapi.attachments.append(
                    Attachment(
                        name=name,
                        mime=OUTLOOK_MIME,
                        data=None,
                        size=self.ole.tree_size(embedded),
                        kind="message",
                        message=nested,
                    )
                )
                continue
            mime = self.string(path, 0x370E, cp) or mimetypes.guess_type(raw_name)[0] or "application/octet-stream"
            name = safe_name(raw_name, n, mime.lower())
            size = self.ole.size((*path, "__substg1.0_37010102"))
            data = self.binary(path, 0x3701, limit=cap)
            if data is None and size > cap:
                data = b""  # listed; the attachment runner reports it as too large
            elif data is None:
                self.partial.append(f"attachment {n}")
                continue
            cid = self.string(path, 0x3712, cp).strip("<> ") or None
            kind = "smime" if name.lower().endswith(".p7m") else "file"
            att = Attachment(name=name, mime=mime.lower(), data=data or None, size=size, content_id=cid, kind=kind)
            mapi.attachments.append(att)


def _smtp(value: str) -> str:
    return value if "@" in value else ""


def _codepage(props: _Props) -> str:
    cp = props.long(0x3FFD) or props.long(0x3FDE)
    if cp in (1200, 65001):
        return "utf-8"
    name = f"cp{cp}" if cp else "cp1252"
    try:
        b"".decode(name)
    except LookupError:
        return "cp1252"
    return name


def read_msg(data: bytes, opts: CommsOptions) -> ParsedMessage:
    ole = open_ole(data)
    try:
        return _Reader(ole, opts).message((), 0)
    finally:
        close = getattr(ole.ole, "close", None)
        if callable(close):
            close()
