"""Compressed RTF (MS-OXRTFCP) and HTML de-encapsulation from RTF (MS-OXRTFEX) for Outlook bodies.

`decompress` handles both the LZFu (compressed) and MELA (stored) forms with the 207-byte preloaded
dictionary. `html_from_rtf` returns the HTML an Outlook client encapsulated in RTF (`\\fromhtml1`), or None for
native RTF, whose text then comes from `text_from_rtf` (striprtf, already a default dependency).
"""

from __future__ import annotations

import re
import struct
import zlib

PREBUF = (
    r"{\rtf1\ansi\mac\deff0\deftab720{\fonttbl;}{\f0\fnil \froman \fswiss \fmodern \fscript \fdecor MS Sans "
    r"SerifSymbolArialTimes New RomanCourier{\colortbl\red0\green0\blue0"
    + "\r\n"
    + r"\par \pard\plain\f0\fs20\b\i\u\tab\tx"
).encode("ascii")
LZFU = 0x75465A4C
MELA = 0x414C454D
DICT_SIZE = 4096
MAX_RAW = 64 * 1024 * 1024
"""Refuse to expand a body beyond this (a hostile RAWSIZE cannot make us allocate more)."""


class RtfError(Exception):
    pass


def crc32_oxrtfcp(data: bytes) -> int:
    """MS-OXRTFCP 2.1.3.2: the standard CRC-32 table, initial value 0, no final inversion."""
    return (~zlib.crc32(data, 0xFFFFFFFF)) & 0xFFFFFFFF


def decompress(blob: bytes, *, max_raw: int = MAX_RAW) -> tuple[bytes, bool]:
    """Returns (rtf bytes, crc_ok). Raises RtfError on a malformed header."""
    if len(blob) < 16:
        raise RtfError("compressed RTF header too short")
    comp_size, raw_size, comp_type, crc = struct.unpack_from("<IIII", blob, 0)
    body = blob[16 : 4 + comp_size] if comp_size >= 12 else blob[16:]
    if comp_type == MELA:
        return body[: min(raw_size, max_raw)], True
    if comp_type != LZFU:
        raise RtfError(f"unknown compressed RTF type {comp_type:#x}")
    crc_ok = crc32_oxrtfcp(body) == crc
    limit = min(raw_size, max_raw)
    dictionary = bytearray(DICT_SIZE)
    dictionary[: len(PREBUF)] = PREBUF
    wp = len(PREBUF)
    out = bytearray()
    i = 0
    n = len(body)
    while i < n and len(out) < limit:
        control = body[i]
        i += 1
        for bit in range(8):
            if i >= n or len(out) >= limit:
                break
            if not control & (1 << bit):
                b = body[i]
                i += 1
                out.append(b)
                dictionary[wp] = b
                wp = (wp + 1) % DICT_SIZE
                continue
            if i + 1 >= n:
                i = n
                break
            ref = (body[i] << 8) | body[i + 1]
            i += 2
            offset, length = ref >> 4, (ref & 0xF) + 2
            if offset == wp:
                return bytes(out), crc_ok
            for k in range(length):
                b = dictionary[(offset + k) % DICT_SIZE]
                out.append(b)
                dictionary[wp] = b
                wp = (wp + 1) % DICT_SIZE
    return bytes(out[:limit]), crc_ok


# ---------------------------------------------------------------------------
# HTML de-encapsulation (MS-OXRTFEX 2.1.3)
# ---------------------------------------------------------------------------

_TOKEN = re.compile(rb"\\([a-zA-Z]+)(-?\d+)? ?|\\'([0-9a-fA-F]{2})|\\(.)|([{}])|(\r\n|\n|\r)|([^\\{}\r\n]+)", re.DOTALL)
_SKIP_DEST = frozenset({b"fonttbl", b"colortbl", b"stylesheet", b"info", b"pict", b"listtable", b"listoverridetable"})


def _codepage(rtf: bytes) -> str:
    m = re.search(rb"\\ansicpg(\d+)", rtf[:2048])
    name = f"cp{int(m.group(1))}" if m else "cp1252"
    try:
        b"".decode(name)
    except LookupError:
        return "cp1252"
    return name


def html_from_rtf(rtf: bytes) -> str | None:
    if b"\\fromhtml1" not in rtf[:4096]:
        return None
    cp = _codepage(rtf)
    out: list[str] = []
    pending = bytearray()
    # Per group: (in_htmltag, skip, suppressed). `suppressed` is \htmlrtf state, which groups inherit.
    stack: list[tuple[bool, bool, bool]] = [(False, False, False)]
    star = False
    skip_chars = 0

    def flush() -> None:
        if pending:
            out.append(pending.decode(cp, errors="replace"))
            pending.clear()

    def emit_bytes(data: bytes) -> None:
        tag, skip, suppressed = stack[-1]
        if skip or (suppressed and not tag):
            return
        pending.extend(data)

    def emit_text(text: str) -> None:
        tag, skip, suppressed = stack[-1]
        if skip or (suppressed and not tag):
            return
        flush()
        out.append(text)

    for m in _TOKEN.finditer(rtf):
        word, param, hexbyte, sym, brace, _newline, text = m.groups()
        if skip_chars and (text or hexbyte or sym):
            if text:
                text = text[skip_chars:] or None
                skip_chars = 0
                if text is None:
                    continue
            else:
                skip_chars -= 1
                continue
        if brace == b"{":
            stack.append(stack[-1])
            star = False
        elif brace == b"}":
            if len(stack) > 1:
                stack.pop()
        elif word is not None:
            tag, skip, suppressed = stack[-1]
            if star and word == b"htmltag":
                stack[-1] = (True, skip, suppressed)
            elif star or word in _SKIP_DEST:
                stack[-1] = (tag, True, suppressed)
            elif word == b"htmlrtf":
                stack[-1] = (tag, skip, param != b"0")
            elif word == b"par" or word == b"line":
                emit_text("\r\n")
            elif word == b"tab":
                emit_text("\t")
            elif word == b"u" and param is not None:
                value = int(param)
                emit_text(chr(value + 65536 if value < 0 else value))
                skip_chars = 1
            star = False
        elif sym is not None:
            if sym == b"*":
                star = True
            elif sym in (b"\\", b"{", b"}"):
                emit_bytes(sym)
            elif sym == b"~":
                emit_text(chr(0xA0))
        elif hexbyte is not None:
            emit_bytes(bytes([int(hexbyte, 16)]))
        elif text is not None:
            emit_bytes(text)
    flush()
    return "".join(out)


def text_from_rtf(rtf: bytes) -> str:
    from striprtf.striprtf import rtf_to_text

    return str(rtf_to_text(rtf.decode(_codepage(rtf), errors="replace"), errors="ignore"))  # type: ignore[no-untyped-call]
