"""ezmd.core.textclean: body-text sanitation shared by every converter (docs/spec/part1.md 8.2).

Removes NUL and C0/C1 control characters (keeping tab and newline), bidi overrides and isolates,
zero-width and other invisible format characters, the BOM, and the Unicode Tags block, and counts
what it removed so converters can attach `removed_hidden_elements` / `removed_invisible_chars`.
Unpaired surrogates are replaced with U+FFFD.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")
_INVISIBLE = re.compile("[\u200b-\u200f\u202a-\u202e\u2060-\u2064\u2066-\u2069\ufeff\U000e0000-\U000e007f]")
_SURROGATE = re.compile("[\ud800-\udfff]")


@dataclass(slots=True)
class CleanStats:
    control: int = 0
    invisible: int = 0
    surrogates: int = 0

    @property
    def total(self) -> int:
        return self.control + self.invisible + self.surrogates

    def add(self, other: CleanStats) -> None:
        self.control += other.control
        self.invisible += other.invisible
        self.surrogates += other.surrogates


def clean_text(text: str, stats: CleanStats | None = None) -> str:
    """Return `text` with hidden and control characters removed; update `stats` in place."""
    s = stats if stats is not None else CleanStats()
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text, n = _CONTROL.subn("", text)
    s.control += n
    text, n = _INVISIBLE.subn("", text)
    s.invisible += n
    text, n = _SURROGATE.subn("\ufffd", text)
    s.surrogates += n
    return text
