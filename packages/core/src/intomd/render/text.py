"""intomd.render.text: text normalization and Markdown escaping helpers (docs/spec/part3.md section 14).

- NFC normalization everywhere; non-printing characters (zero-width, joiners, BOM, bidi controls, Unicode
  tag characters, soft hyphen) are removed and counted.
- Whitespace runs collapse to one space outside verbatim contexts.
- Characters that would start Markdown syntax at a line start are backslash-escaped.
- Inline `*`, `_`, backticks, brackets, `<` and `&` are escaped only when a CommonMark round-trip of the run
  shows they would form markup (markdown-it-py, loaded lazily; a conservative regex fallback is used when it
  is unavailable).
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

__all__ = [
    "TextStats",
    "clean_text",
    "code_span",
    "collapse_ws",
    "escape_dollars",
    "escape_inline",
    "escape_line_start",
    "fence_for",
    "fmt_time",
    "slugify",
]

_BIDI = re.compile("[\u202a-\u202e\u2066-\u2069]")
_TAGS = re.compile("[\U000e0000-\U000e007f]")
_NONPRINTING = re.compile("[\u200b\u200c\u200d\u2060\ufeff\u00ad\u202a-\u202e\u2066-\u2069\U000e0000-\U000e007f]")
_WS = re.compile(r"\s+")
_INLINE_SPECIAL = re.compile(r"[*_`\[\]<&\\]")
_LINE_START_ALWAYS = ("#", ">", "|")
_LIST_MARKER = re.compile(r"^([-+*])(\s|$)")
_ORDERED_MARKER = re.compile(r"^(\d{1,9})([.)])(\s|$)")
_FENCE_START = re.compile(r"^(`{3,}|~{3,})")
_FALLBACK_MARKUP = re.compile(r"\*\S|\S\*|(^|\W)_\S|`|\[[^\]]*\]\(|<[A-Za-z/!?]|&[#A-Za-z0-9]+;|\\[!-/:-@\[-`{-~]")
_THEMATIC = re.compile(r"^([-*_=])(\s*\1){2,}\s*$")


@dataclass(slots=True)
class TextStats:
    removed_nonprinting: int = 0
    bidi_or_tags: bool = False


def clean_text(text: str, stats: TextStats | None = None) -> str:
    """NFC-normalize and strip non-printing characters, recording counts in `stats`."""
    text = unicodedata.normalize("NFC", text)
    if stats is not None:
        if _BIDI.search(text) or _TAGS.search(text):
            stats.bidi_or_tags = True
        text, n = _NONPRINTING.subn("", text)
        stats.removed_nonprinting += n
        return text
    return _NONPRINTING.sub("", text)


def collapse_ws(text: str) -> str:
    return _WS.sub(" ", text)


def escape_line_start(line: str) -> str:
    """Backslash-escape a prose line that would otherwise start a Markdown construct."""
    if not line:
        return line
    if line.startswith(_LINE_START_ALWAYS):
        return "\\" + line
    if _THEMATIC.match(line) or _LIST_MARKER.match(line) or _FENCE_START.match(line):
        return "\\" + line
    m = _ORDERED_MARKER.match(line)
    if m:
        return m.group(1) + "\\" + line[len(m.group(1)) :]
    return line


@lru_cache(maxsize=1)
def _md() -> Any:
    try:
        from markdown_it import MarkdownIt
    except Exception:  # markdown-it-py missing: callers use the regex fallback
        return None
    return MarkdownIt("commonmark")


def _forms_markup(text: str) -> bool:
    md = _md()
    if md is None:
        return bool(_FALLBACK_MARKUP.search(text))
    tokens = md.parseInline(text)
    for tok in tokens:
        for child in tok.children or []:
            if child.type != "text":
                return True
    return False


@lru_cache(maxsize=4096)
def escape_inline(text: str) -> str:
    """Escape inline Markdown metacharacters in a prose run, only when they would form markup."""
    if not _INLINE_SPECIAL.search(text) or not _forms_markup(text):
        return text

    def esc(m: re.Match[str]) -> str:
        i = m.start()
        intraword = m.group(0) == "_" and 0 < i < len(text) - 1 and text[i - 1].isalnum() and text[i + 1].isalnum()
        return m.group(0) if intraword else "\\" + m.group(0)

    return _INLINE_SPECIAL.sub(esc, text)


def escape_dollars(text: str) -> str:
    return text.replace("$", "\\$")


def code_span(text: str) -> str:
    """An inline code span whose delimiter is longer than any backtick run inside it."""
    text = text.replace("\n", " ")
    runs = [len(r) for r in re.findall(r"`+", text)]
    ticks = "`" * (max(runs) + 1 if runs else 1)
    pad = " " if text.startswith("`") or text.endswith("`") or (text.startswith(" ") and text.strip()) else ""
    return f"{ticks}{pad}{text}{pad}{ticks}"


def fence_for(content: str, char: str = "`") -> str:
    """A code fence longer than any run of `char` at a line start inside `content` (minimum three)."""
    runs = [len(r) for r in re.findall(re.escape(char) + "{3,}", content)]
    return char * max(3, (max(runs) + 1) if runs else 3)


def fmt_time(seconds: float | None) -> str:
    """`HH:MM:SS`, fixed width so timestamps grep and sort."""
    total = max(0, int(seconds or 0))
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")
