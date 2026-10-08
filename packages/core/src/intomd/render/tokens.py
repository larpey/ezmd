"""intomd.render.tokens: token counting (docs/spec/part3.md section 20).

Encodings load lazily on first use (never at import). When tiktoken or its BPE files are unavailable
(air-gapped install without the cache) counts fall back to len/3.8 for Latin and len/1.6 for CJK text and
`tokens_estimated()` reports True so the sidecar can label them.
"""

from __future__ import annotations

import threading
from typing import Protocol

__all__ = [
    "TiktokenCounter",
    "claude_approx",
    "count_o200k",
    "count_tokens",
    "dominant_script",
    "tokens_estimated",
]


class _Encoding(Protocol):
    def encode(self, text: str, *, disallowed_special: tuple[()] = ()) -> list[int]: ...


_RATIO_BY_SCRIPT: dict[str, float] = {"latin": 1.08, "cjk": 1.25, "cyrillic": 1.15, "arabic": 1.2, "mixed": 1.12}
_ENCODINGS: dict[str, _Encoding | None] = {}
_LOCK = threading.Lock()


def _enc(name: str) -> _Encoding | None:
    with _LOCK:
        if name not in _ENCODINGS:
            try:
                import tiktoken

                _ENCODINGS[name] = tiktoken.get_encoding(name)
            except Exception:  # offline first run or missing package: fall back to estimates
                _ENCODINGS[name] = None
        return _ENCODINGS[name]


def tokens_estimated() -> bool:
    """True when any encoding failed to load and counts are estimates."""
    return any(v is None for v in _ENCODINGS.values())


def dominant_script(text: str) -> str:
    counts = {"latin": 0, "cjk": 0, "cyrillic": 0, "arabic": 0}
    for ch in text:
        cp = ord(ch)
        if ch.isascii():
            if ch.isalpha():
                counts["latin"] += 1
        elif 0x0400 <= cp <= 0x052F:
            counts["cyrillic"] += 1
        elif 0x0600 <= cp <= 0x06FF or 0x0750 <= cp <= 0x077F:
            counts["arabic"] += 1
        elif 0x3040 <= cp <= 0x30FF or 0x3400 <= cp <= 0x9FFF or 0xAC00 <= cp <= 0xD7AF or 0xF900 <= cp <= 0xFAFF:
            counts["cjk"] += 1
        elif ch.isalpha():
            counts["latin"] += 1
    total = sum(counts.values())
    if total == 0:
        return "latin"
    script, n = max(counts.items(), key=lambda kv: kv[1])
    return script if n / total >= 0.8 else "mixed"


def _estimate(text: str) -> int:
    if not text:
        return 0
    divisor = 1.6 if dominant_script(text) == "cjk" else 3.8
    return max(1, round(len(text) / divisor))


def _count(name: str, text: str) -> int:
    enc = _enc(name)
    if enc is None:
        return _estimate(text)
    return len(enc.encode(text, disallowed_special=()))


def count_o200k(text: str) -> int:
    return _count("o200k_base", text)


def claude_approx(text: str, o200k: int) -> int:
    """Anthropic's tokenizer is not public; apply the shipped per-script ratio to the o200k count."""
    ratio = _RATIO_BY_SCRIPT.get(dominant_script(text), 1.08)
    return round(o200k * ratio)


def count_tokens(text: str) -> dict[str, int]:
    """The frontmatter `tokens` map: o200k_base, cl100k_base and claude_approx."""
    o200k = _count("o200k_base", text)
    cl100k = _count("cl100k_base", text)
    return {"o200k_base": o200k, "cl100k_base": cl100k, "claude_approx": claude_approx(text, o200k)}


class TiktokenCounter:
    """TokenCounter over one tiktoken encoding (cl100k_base by default), with the estimate fallback."""

    def __init__(self, encoding: str = "cl100k_base") -> None:
        self.encoding = encoding

    def count(self, text: str) -> int:
        return _count(self.encoding, text)
