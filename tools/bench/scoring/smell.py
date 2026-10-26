"""Structural smells of a converted document, scored with no ground truth.

An output can be written and still be wrong in ways a reader notices at once: nothing in it, a fifth of the
input, replacement characters, the same line fifty times, a page of pipes with empty cells, a bullet glyph on
a line of its own, a heading that is a bullet point, a heading truncated and then repeated as a paragraph.
Each smell is a boolean per document, so a corpus run reports a count per smell and per type, and the gate
can be zero on the ones that are never acceptable (`GATED`).

The smells come from the defects everyday documents surfaced (#28 to #33) and the Govdocs1 pilot, and are
tuned to stay quiet on correct output: thresholds are conservative, and a smell that fires on a known-good
fixture is a bug in the scorer, not the converter.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

from tools.bench.scoring.text import markdown_to_text

GATED = frozenset({"empty", "control_chars", "lone_bullet", "heading_bullet", "heading_repeated", "truncated_full"})
"""Smells no release should ship with: zero of each is the gate."""
REPORTED = frozenset(
    {"shrunk", "replacement_chars", "mojibake", "repeated_lines", "char_run", "empty_table", "injection"}
)
"""Smells worth a look; some have legitimate causes (a navigation-only page shrinks, a scan has no text)."""

MIN_CHARS = 20
PARSE_MAX_CHARS = 2_000_000
SHRINK_RATIO = 0.05
"""Output text shorter than this share of the input's text is `shrunk` (text-like inputs only)."""
TEXT_LIKE = frozenset({"txt", "text", "md", "markdown", "csv", "tsv", "json", "xml", "yaml", "yml", "log", "rtf"})
MARKUP_LIKE = frozenset({"html", "htm", "xhtml"})
MARKUP_SHRINK_RATIO = 0.02
"""HTML carries markup and navigation the web converter is meant to drop, so its bar is lower."""
REPEAT_RUN = 8
REPEAT_TOTAL = 40
REPEAT_MIN_CHARS = 12
CHAR_RUN = 200
TABLE_EMPTY_SHARE = 0.5
TABLE_MIN_CELLS = 12
_BULLET = "•◦▪▫●○■□–—‣⁃-*"
_LONE_BULLET = re.compile(rf"^\s*[{re.escape(_BULLET)}]\s*$")
_HEADING = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
_HEADING_BULLET = re.compile(rf"^#{{1,6}}\s+(?:\d+(?:\.\d+)*\s+)?[{re.escape('•◦▪▫●○■□‣⁃')}]")
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
_MOJIBAKE = re.compile(r"Ã[\x80-\xbf©¨ ¡¢£¤¥¦§ª«¬®¯°±²³´µ¶·¸¹º»¼½¾¿]|â€[™œ\x9d\x9c\"\x93\x94]|Â[ ¡¢£¤¥¦§¨©ª«¬®¯°±]")
_CHAR_RUN = re.compile(rf"(\S)\1{{{CHAR_RUN - 1},}}")
_PIPE_ROW = re.compile(r"^\s*\|.*\|\s*$")
_SEPARATOR = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")


def _lines(md: str) -> list[str]:
    return md.replace("\r\n", "\n").split("\n")


def lone_bullets(lines: list[str]) -> int:
    return sum(1 for ln in lines if _LONE_BULLET.match(ln))


def heading_bullets(lines: list[str]) -> int:
    return sum(1 for ln in lines if _HEADING_BULLET.match(ln))


def repeated_headings(lines: list[str]) -> int:
    """A heading cut with `...` whose text is then emitted again as the next paragraph (#33)."""
    hits = 0
    for i, ln in enumerate(lines[:-1]):
        m = _HEADING.match(ln)
        if not m:
            continue
        text = m.group(2).rstrip(".…").strip()
        if len(text) < 40:
            continue
        nxt = next((x.strip() for x in lines[i + 1 : i + 4] if x.strip()), "")
        if nxt.startswith(text[:40]):
            hits += 1
    return hits


def repeated_lines(lines: list[str]) -> bool:
    counts: Counter[str] = Counter()
    run = 0
    prev = None
    for ln in lines:
        key = ln.strip()
        if not key:
            continue  # blank lines between repeats do not break the run
        if len(key) < REPEAT_MIN_CHARS or _SEPARATOR.match(key):
            prev = None
            run = 0
            continue
        counts[key] += 1
        run = run + 1 if key == prev else 1
        prev = key
        if run >= REPEAT_RUN:
            return True
    return any(n >= REPEAT_TOTAL for n in counts.values())


def empty_tables(lines: list[str]) -> int:
    """Pipe tables (at least TABLE_MIN_CELLS body cells) with more than half their cells empty."""
    tables = 0
    cells = 0
    empty = 0
    in_table = False
    for ln in [*lines, ""]:
        if _PIPE_ROW.match(ln):
            if _SEPARATOR.match(ln):
                continue
            row = [c.strip() for c in ln.strip().strip("|").split("|")]
            if not in_table:  # the header row
                in_table = True
                continue
            cells += len(row)
            empty += sum(1 for c in row if not c)
        elif in_table:
            if cells >= TABLE_MIN_CELLS and empty / cells > TABLE_EMPTY_SHARE:
                tables += 1
            in_table = False
            cells = empty = 0
    return tables


def input_text_length(data: bytes) -> int:
    """How much text a text-like input holds: decoded leniently, whitespace runs collapsed."""
    text = data.decode("utf-8", errors="replace")
    return len(" ".join(text.split()))


def smells(
    md: str,
    category: str,
    sidecar: dict[str, Any] | None = None,
    input_bytes: bytes | None = None,
    profile: str = "full",
) -> list[str]:
    """The smells of one output (frontmatter already removed). `category` is the input's extension or MIME
    slug; `sidecar` is ezmd's `<output>.warnings.json`; `input_bytes` enables `shrunk` for text-like inputs."""
    found: list[str] = []
    lines = _lines(md)
    # markdown-it is not linear on a huge single paragraph; past the cap the raw text is close enough for size.
    text = md if len(md) > PARSE_MAX_CHARS else markdown_to_text(md) if md.strip() else ""
    compact = " ".join(text.split())
    if len(compact) < MIN_CHARS:
        found.append("empty")
    if _CONTROL.search(md):
        found.append("control_chars")
    if lone_bullets(lines):
        found.append("lone_bullet")
    if heading_bullets(lines):
        found.append("heading_bullet")
    if repeated_headings(lines):
        found.append("heading_repeated")
    if sidecar and sidecar.get("truncated") and profile == "full":
        found.append("truncated_full")
    if "�" in md and md.count("�") >= max(3, len(md) // 1000):
        found.append("replacement_chars")
    if _MOJIBAKE.search(md):
        found.append("mojibake")
    if repeated_lines(lines):
        found.append("repeated_lines")
    if _CHAR_RUN.search(md):
        found.append("char_run")
    if empty_tables(lines) >= 1:
        found.append("empty_table")
    if input_bytes is not None and "empty" not in found:
        ext = category.lower().rsplit("-", 1)[-1]
        ratio = SHRINK_RATIO if ext in TEXT_LIKE else MARKUP_SHRINK_RATIO if ext in MARKUP_LIKE else None
        if ratio is not None:
            src = input_text_length(input_bytes)
            if src >= 200 and len(compact) < ratio * src:
                found.append("shrunk")
    if sidecar and any("injection" in str(w.get("kind", "")) for w in sidecar.get("warnings", [])):
        found.append("injection")
    return found
