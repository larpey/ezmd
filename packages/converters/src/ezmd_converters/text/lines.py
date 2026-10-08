"""Line joining for plain text, shared by `text.plain` and the email bodies (docs/spec/part2.md section 2 step
22(7) and failure mode 10).

Within one blank-line-separated run, a line continues the previous line (a hard wrap) when the previous line is
full width (WRAP_MIN_CHARS or more) or the line starts lowercase. List items and indented code lines are never
joined into another line and never absorb one. Whatever does not join stays its own line: a short-line run
(verse, an address, `Key: value` lines) keeps its line structure, which callers express as one Paragraph with
`attrs["line_breaks"] = "hard"` and `\\n` between the lines. Blank lines are paragraph breaks and are handled by
the callers (they split runs before calling `join_lines`).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

WRAP_MIN_CHARS = 60
"""A line at least this long is a hard wrap (72-column mail and text), so the next line continues it."""
LINE_BREAKS_ATTR = "line_breaks"
LINE_BREAKS_HARD = "hard"
LineKind = Literal["prose", "list", "code"]

_LIST = re.compile(r"^\s{0,3}(?:[-*+•]|\d{1,3}[.)])\s+\S")
_CODE = re.compile(r"^(?: {4}|\t)")


@dataclass(frozen=True, slots=True)
class Line:
    text: str
    kind: LineKind


def line_kind(line: str) -> LineKind:
    if _LIST.match(line):
        return "list"
    if _CODE.match(line):
        return "code"
    return "prose"


def join_lines(lines: list[str], *, flowed: bool = False) -> list[Line]:
    """Logical lines of one run. `flowed` text (RFC 3676) is already unwrapped: nothing is joined."""
    out: list[Line] = []
    for raw in lines:
        kind = line_kind(raw)
        text = raw.rstrip() if kind == "code" else raw.strip()
        if not text:
            continue
        prev = out[-1] if out else None
        joins = (
            not flowed
            and prev is not None
            and prev.kind == "prose"
            and kind == "prose"
            and (len(prev.text) >= WRAP_MIN_CHARS or text[:1].islower())
        )
        if joins and prev is not None:
            out[-1] = Line(f"{prev.text} {text}", "prose")
        else:
            out.append(Line(text, kind))
    return out
