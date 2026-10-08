"""Charset handling for email bodies and headers (part2 9e step 4 and 13.2).

Declared charsets are tried strictly; a wrong or unknown declaration falls back to strict UTF-8, then
charset-normalizer, then UTF-8 with replacement characters (reported as `encoding_uncertain`).
"""

from __future__ import annotations

import codecs
from dataclasses import dataclass

MAX_SNIFF_BYTES = 1 << 20
REPLACEMENT = chr(0xFFFD)
PREFERRED_FALLBACK = "cp1252"
CLOSE_CHAOS = 0.1
_ALIASES = {"utf8": "utf-8", "us-ascii": "ascii", "ascii": "ascii", "unicode-1-1-utf-7": "utf-7"}


@dataclass(frozen=True, slots=True)
class Decoded:
    text: str
    encoding: str
    confidence: float
    declared_failed: bool
    """A charset was declared but did not decode the bytes (or named an unknown codec)."""
    replacements: int


def _codec(name: str | None) -> str | None:
    if not name:
        return None
    clean = name.strip().strip("\"'").lower()
    clean = _ALIASES.get(clean, clean)
    try:
        codecs.lookup(clean)
    except LookupError:
        return None
    return clean


def decode_bytes(raw: bytes, declared: str | None) -> Decoded:
    """Decode a body part. Declared charset (strict), then UTF-8, then charset-normalizer, then replace."""
    codec = _codec(declared)
    failed = declared is not None and codec is None
    if codec is not None:
        if codec in ("ascii", "us-ascii"):
            codec = "utf-8"  # 8bit bodies routinely mislabel UTF-8 as us-ascii; UTF-8 is a superset
        try:
            return Decoded(raw.decode(codec), codec, 1.0, False, 0)
        except (UnicodeDecodeError, LookupError):
            failed = True
    try:
        return Decoded(raw.decode("utf-8"), "utf-8", 1.0 if not failed else 0.9, failed, 0)
    except UnicodeDecodeError:
        pass
    from charset_normalizer import from_bytes

    results = from_bytes(raw[:MAX_SNIFF_BYTES])
    best = results.best()
    if best is not None:
        # Short mislabeled bodies are ambiguous between single-byte code pages; mail clients that mislabel
        # (Outlook, webmail) overwhelmingly send Windows-1252, so prefer it when it scores close to the best.
        for r in results:
            if r.encoding == PREFERRED_FALLBACK and r.chaos <= best.chaos + CLOSE_CHAOS:
                best = r
                break
        enc = best.encoding
        text = raw.decode(enc, errors="replace")
        confidence = max(0.0, min(1.0, 1.0 - float(best.chaos)))
        return Decoded(text, enc, confidence, failed, text.count(REPLACEMENT))
    text = raw.decode("utf-8", errors="replace")
    return Decoded(text, "utf-8", 0.0, failed, text.count(REPLACEMENT))


def has_surrogates(value: str) -> bool:
    return any(0xDC80 <= ord(ch) <= 0xDCFF for ch in value)


def repair_header(value: str) -> str:
    """Raw 8-bit header bytes arrive surrogate-escaped from the parser; decode them as UTF-8 (or sniffed)."""
    if not has_surrogates(value):
        return value
    raw = value.encode("ascii", errors="surrogateescape")
    return decode_bytes(raw, None).text
