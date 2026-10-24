"""Heading levels for text-layer lines, from (in precedence order) the structure tree, the outline, and font
size. `plan_headings` looks at the whole document first, so per-line decisions can use document facts: which
outline titles appear numbered in the body ("3.1 Encoder" for the bookmark "Encoder"), whether the outline
covers the body's headings, and which heading-sized lines are really prose (a three-line notice set in the
section-heading size)."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field

from ezmd_converters.pdf.layout import HEADING_RATIO, norm_text, size_levels
from ezmd_converters.pdf.textlayer import Line, PageText

SECTION_NUMBER = re.compile(r"^(\d{1,2}(?:\.\d{1,2}){0,4})\.?\s+(?=\S)")
"""A leading section number: "3", "3.2.1", "4." followed by the title."""
OUTLINE_MIN_MATCHES = 3
"""The outline drives headings when at least this many of its titles (or all of them, if fewer) are found."""
PROSE_RUN = 3
"""This many consecutive heading-sized, non-bold, tightly spaced lines are a paragraph, not a heading."""
NUMBERED_MAX_WORDS = 12
"""A bold body-size line with a section number is a heading only when its title is at most this many words,
starts with a capital, and does not end like a sentence."""
TURNED_MINORITY = 0.5
"""Turned lines are margin furniture (an arXiv stamp) only when under this share of their page's lines; on a
page typeset sideways they are the content and keep their headings."""


def section_number(text: str) -> tuple[int | None, str]:
    """(numbering depth, title without the number); depth is None when the text has no section number."""
    m = SECTION_NUMBER.match(text)
    if m is None:
        return None, text
    return m.group(1).count(".") + 1, text[m.end() :]


@dataclass(slots=True)
class HeadingSources:
    """Where heading levels come from, in precedence order."""

    struct: dict[tuple[int, int], int] = field(default_factory=dict)
    outline: dict[tuple[str, int | None], int] = field(default_factory=dict)
    outline_any: dict[str, int] = field(default_factory=dict)
    sizes: dict[float, int] = field(default_factory=dict)
    use_struct: bool = False
    struct_only: bool = False
    used: dict[str, int] = field(default_factory=dict)
    disagreements: int = 0
    body: float = 10.0
    prose: set[int] = field(default_factory=set)
    """`Line.order` of heading-sized lines that belong to a paragraph."""
    turned: set[int] = field(default_factory=set)
    """`Line.order` of turned lines that are a minority on their page (never headings)."""
    outline_mode: bool = False
    """The outline covers the body: only outline titles (plus the first-page title) become headings."""
    outline_left: Counter[str] = field(default_factory=Counter)
    """Outline titles not yet matched; each bookmark is used once, in reading order."""
    numbered_keys: set[str] = field(default_factory=set)
    """Outline titles that appear with a section number in the body: only the numbered line matches."""
    outline_sizes: dict[float, int] = field(default_factory=dict)
    """In outline mode, the outline level most often seen at each font size (for "Abstract", "References")."""
    title_orders: set[int] = field(default_factory=set)
    offset: int = 0
    """Added to outline levels when a first-page title sits above them."""
    _top: int = 2

    def level(self, ln: Line) -> int | None:
        """Heading level of `ln`, or None. Call once per line, in reading order: outline bookmarks are consumed
        and the depth of "3.1" headings is measured from the last top-level numbered heading."""
        if ln.order in self.turned or ln.order in self.prose:
            return None
        size_level = self.sizes.get(round(ln.size * 2) / 2)
        if len(ln.text) > 200:
            size_level = None
        if self.use_struct:
            hits = [self.struct[(ln.page - 1, m)] for m in ln.mcids if (ln.page - 1, m) in self.struct]
            if hits or (ln.mcids and self.struct_only):
                lvl = min(hits) if hits else None
                if lvl != size_level:
                    self.disagreements += 1
                return self._count("structure_tree", lvl)
            if self.struct_only:
                return None
        if self.outline_mode:
            return self._outline_mode_level(ln)
        key = norm_text(ln.text)
        lvl = self.outline.get((key, ln.page - 1)) or self.outline_any.get(key)
        if lvl is not None:
            return self._count("outline", lvl)
        if size_level is not None:
            depth, _ = section_number(ln.text)
            if depth == 1:
                self._top = size_level
            return self._count("font_size", size_level)
        return self._count("font_size", self._numbered_level(ln, base=self._top))

    def _outline_mode_level(self, ln: Line) -> int | None:
        if ln.order in self.title_orders:
            return self._count("font_size", 1)
        lvl = self._take_outline(ln)
        if lvl is not None:
            return self._count("outline", lvl + self.offset)
        lvl = self._outline_size_level(ln)
        if lvl is not None:
            return self._count("font_size", lvl + self.offset)
        return self._count("font_size", self._numbered_level(ln, base=1 + self.offset))

    def _outline_size_level(self, ln: Line) -> int | None:
        """An unbookmarked heading in an outlined document ("Abstract", or a heading a partial outline leaves
        out): heading-sized but no larger than the bookmarked headings, it takes the outline level seen at its
        size, else ranks among those sizes. Larger text (figure lettering) is not a heading."""
        if not self.outline_sizes or len(ln.text) > 120 or ln.size < self.body * HEADING_RATIO:
            return None
        size = round(ln.size * 2) / 2
        if size > max(self.outline_sizes) + 0.5:
            return None
        hit = self.outline_sizes.get(size)
        if hit is not None:
            return hit
        return min(1 + sum(1 for s in self.outline_sizes if s > size), 6)

    def _take_outline(self, ln: Line) -> int | None:
        key = outline_key(ln, self.body, self.outline_left, self.numbered_keys)
        if key is None:
            return None
        self.outline_left[key] -= 1
        return self.outline.get((key, ln.page - 1)) or self.outline_any.get(key)

    def _numbered_level(self, ln: Line, base: int) -> int | None:
        """A bold body-size line like "3.1 Encoder and Decoder Stacks": its level follows the numbering depth
        under `base`, the level of a top-level numbered heading. "2.5 million units shipped." is not one."""
        depth, rest = section_number(ln.text)
        if depth is None or depth < 2 or not ln.bold or not rest[:1].isupper():
            return None
        if len(rest.split()) > NUMBERED_MAX_WORDS or rest.rstrip().endswith((".", ",", ";", ":")):
            return None
        if abs(ln.size - self.body) > 0.1 * self.body:
            return None
        return min(base + depth - 1, 6)

    def _count(self, source: str, lvl: int | None) -> int | None:
        if lvl is not None:
            self.used[source] = self.used.get(source, 0) + 1
        return lvl


def outline_key(ln: Line, body: float, left: Counter[str], numbered: set[str]) -> str | None:
    """The outline title `ln` matches, or None. The line must look like a heading (bold, large, or numbered),
    so a figure label repeating a section title does not take the bookmark."""
    depth, rest = section_number(ln.text)
    if not (ln.bold or ln.size >= body * HEADING_RATIO or depth is not None):
        return None
    keys = [norm_text(ln.text)] + ([norm_text(rest)] if depth is not None else [])
    for key in keys:
        if left[key] <= 0:
            continue
        if depth is None and key in numbered:
            continue
        return key
    return None


def prose_runs(pages: Sequence[PageText], body: float, skip: set[int]) -> set[int]:
    """Orders of heading-sized lines that form a paragraph: `PROSE_RUN` or more consecutive non-bold lines of
    one size, each starting within 0.6 em below the previous."""
    out: set[int] = set()
    for p in pages:
        run: list[Line] = []
        for ln in sorted((ln for ln in p.lines if ln.order not in skip), key=lambda ln: ln.order):
            big = ln.size >= body * HEADING_RATIO and not ln.bold
            if big and run:
                prev = run[-1]
                if round(prev.size * 2) == round(ln.size * 2) and 0 <= ln.y0 - prev.y1 <= 0.6 * ln.size:
                    run.append(ln)
                    continue
            if len(run) >= PROSE_RUN:
                out.update(r.order for r in run)
            run = [ln] if big else []
        if len(run) >= PROSE_RUN:
            out.update(r.order for r in run)
    return out


def plan_outline(src: HeadingSources, pages: Sequence[PageText], skip: set[int]) -> None:
    """Switch `src` to outline mode when the outline covers the body, and find the first-page title above it."""
    titles: Counter[str] = Counter()
    for (key, _page), _lvl in src.outline.items():
        titles[key] += 1
    if not titles:
        return
    hidden = skip | src.prose | src.turned
    lines = [ln for p in pages for ln in p.lines if ln.order not in hidden]
    src.numbered_keys = {
        norm_text(rest)
        for ln in lines
        for depth, rest in [section_number(ln.text)]
        if depth is not None and norm_text(rest) in titles
    }
    left = titles.copy()
    matched: list[tuple[Line, int]] = []
    for ln in lines:
        hit = outline_key(ln, src.body, left, src.numbered_keys)
        if hit is not None:
            left[hit] -= 1
            matched.append((ln, src.outline.get((hit, ln.page - 1)) or src.outline_any.get(hit) or 1))
    if len(matched) < min(OUTLINE_MIN_MATCHES, sum(titles.values())):
        return
    src.outline_mode = True
    src.outline_left = titles
    by_size: dict[float, Counter[int]] = {}
    for ln, lvl in matched:
        by_size.setdefault(round(ln.size * 2) / 2, Counter())[lvl] += 1
    src.outline_sizes = {s: c.most_common(1)[0][0] for s, c in by_size.items()}
    biggest = max(ln.size for ln, _ in matched)
    first = min((ln.page for ln in lines), default=1)
    on_first = [ln for ln in lines if ln.page == first and len(ln.text) <= 200]
    if on_first:
        top = max(ln.size for ln in on_first)
        if top > biggest * 1.1:
            src.title_orders = {ln.order for ln in on_first if round(ln.size * 2) == round(top * 2)}
            src.offset = 1


def plan_headings(
    pages: Sequence[PageText], body: float, outline: Sequence[tuple[int, str, int | None]], skip: set[int]
) -> HeadingSources:
    """Heading sources for the document; `skip` holds running header/footer orders."""
    turned = minority_turned(pages)
    prose = prose_runs(pages, body, skip | turned)
    sizes = size_levels(pages, body, skip | prose | turned)
    src = HeadingSources(sizes=sizes, body=body, prose=prose, turned=turned)
    for level, title, page in outline:
        key = norm_text(title)
        src.outline.setdefault((key, page), level)
        src.outline_any.setdefault(key, level)
    plan_outline(src, pages, skip)
    return src


def minority_turned(pages: Sequence[PageText]) -> set[int]:
    """Orders of turned lines on pages where they are under `TURNED_MINORITY` of the lines."""
    out: set[int] = set()
    for p in pages:
        turned = [ln.order for ln in p.lines if ln.turn]
        if turned and len(turned) < TURNED_MINORITY * len(p.lines):
            out.update(turned)
    return out
