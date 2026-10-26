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

from ezmd_converters.pdf.layout import HEADING_RATIO, norm_text
from ezmd_converters.pdf.textlayer import Line, PageText

SECTION_NUMBER = re.compile(r"^(\d{1,2}(?:\.\d{1,2}){0,4})\.?\s+(?=\S)")
"""A leading section number: "3", "3.2.1", "4." followed by the title."""
NUMBERING = (
    re.compile(r"^(?:appendix|section|chapter|part)\s+(?=\S)", re.IGNORECASE),
    re.compile(r"^\d{1,2}(?:\.\d{1,2}){0,4}[.):]?\s+(?=\S)"),
    re.compile(r"^[IVXLC]{1,6}[.):]\s+(?=\S)"),
    re.compile(r"^[A-Z](?:\.\d{1,2}){1,4}[.):]?\s+(?=\S)"),
    re.compile(r"^[A-Z][.):]\s+(?=\S)"),
    re.compile(r"^[B-HJ-Z]\s+(?=[A-Z])"),
)
"""Leading numbering in any common style, stripped (in order, each at most once) to match a heading to its
bookmark: "3.1", "4." and "2)" (arabic), "II." (IEEE roman), "B.1" and "A." (appendix and IEEE letters),
"B Related Work" (appendix letter; never "A" or "I", which are words: "A Simplified SSM Architecture"), and
"Appendix C"."""
WRAPPED_MIN_CHARS = 20
"""A heading that wraps onto a second line matches its bookmark by its first line when that is at least this
long and at least half the title."""
OUTLINE_MIN_MATCHES = 3
"""The outline drives headings when at least this many of its titles (or all of them, if fewer) are found."""
PROSE_RUN = 3
"""This many consecutive heading-sized, non-bold, tightly spaced lines are a paragraph, not a heading."""
NUMBERED_MAX_WORDS = 12
"""A bold body-size line with a section number is a heading only when its title is at most this many words,
starts with a capital, and does not end like a sentence."""
FRONT_MATTER = frozenset(
    {"abstract", "summary", "keywords", "index terms", "contents", "preface", "foreword", "executive summary"}
)
"""Before the first bookmarked heading, only these unbookmarked lines can be headings: the title page's author
names and affiliations are set in heading sizes too."""
BOLD_HEADING_RATIO = 1.05
"""Bold lines this much larger than the body are heading candidates too: ACL-style papers set 12 pt section
headings over an 11 pt body (1.09x, under `HEADING_RATIO`)."""
HEADING_WORD = re.compile(r"[^\W\d_]{2,}")
"""A heading has a word of two letters or more; a lone 𝐴 or ∆, or `h¯Ω1/λ0`, in a diagram's lettering is not
one."""
HEADING_MAX_CHARS = 150
"""Longer text is never a heading: an abstract set in one line, or an affiliation with a footnote number."""
DOT_LEADERS = re.compile(r"(?:\.\s){4,}")
"""A contents entry's dot leaders (". . . ."); such a line lists a heading, it is not one."""
TURNED_MINORITY = 0.5
"""Turned lines are margin furniture (an arXiv stamp) only when under this share of their page's lines; on a
page typeset sideways they are the content and keep their headings."""


def heading_key(text: str) -> tuple[str, bool]:
    """(match key, whether numbering was stripped): the text without leading numbering, case-folded, spaces
    collapsed and trailing ".:" dropped, so "II. RELATED WORK", "2 Related Work" and the bookmark "Related
    Work" share a key."""
    rest = text.strip()
    numbered = False
    for pattern in NUMBERING:
        m = pattern.match(rest)
        if m is not None:
            rest = rest[m.end() :]
            numbered = True
    return norm_text(rest), numbered


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
    contents: set[int] = field(default_factory=set)
    """`Line.order` of lines on a printed table-of-contents page (never headings: they list them)."""
    run_in: dict[int, int] = field(default_factory=dict)
    """Run-in headings found by `level`: `Line.order` -> length of the heading at the start of the line
    ("2.1. Metric graph theory." before the paragraph's first sentence). The assembler splits the line."""
    sizes: dict[float, int] = field(default_factory=dict)
    bold_sizes: set[float] = field(default_factory=set)
    """Sizes in `sizes` that are headings only when the line is bold (under `HEADING_RATIO` x body)."""
    front: set[int] = field(default_factory=set)
    """`Line.order` of title-page lines between the title and "Abstract": authors and affiliations."""
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
    _outline_started: bool = False

    def level(self, ln: Line) -> int | None:
        """Heading level of `ln`, or None. Call once per line, in reading order: outline bookmarks are consumed
        and the depth of "3.1" headings is measured from the last top-level numbered heading."""
        if ln.order in self.turned or ln.order in self.prose or ln.order in self.front or ln.order in self.contents:
            return None
        if not HEADING_WORD.search(ln.text) or DOT_LEADERS.search(ln.text):
            return None
        if len(ln.text) > HEADING_MAX_CHARS and ln.order not in self.title_orders:
            return None
        size = round(ln.size * 2) / 2
        size_level = self.sizes.get(size)
        if len(ln.text) > 200 or (size in self.bold_sizes and not ln.bold):
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
        key, _ = heading_key(ln.text)
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
            self._outline_started = True
            return self._count("outline", lvl + self.offset)
        if not self._outline_started and norm_text(ln.text) not in FRONT_MATTER:
            return None
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
            hit = run_in_heading(ln.text, self.outline_left)
            if hit is None:
                return None
            key, cut = hit
            self.run_in[ln.order] = cut
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
        """Every level leaves through here: bookmarks and structure tags can nest deeper than Markdown's six."""
        if lvl is not None:
            self.used[source] = self.used.get(source, 0) + 1
            return min(lvl, 6)
        return lvl


def outline_key(ln: Line, body: float, left: Counter[str], numbered: set[str]) -> str | None:
    """The outline title `ln` matches, or None.

    - It must look like a heading: bold, large or numbered, so a figure label repeating a section title does
      not take the bookmark. A line that matches exactly and is set apart from the body some other way also
      counts: REVTeX's small capitals ("INTRODUCTION", numeral drawn apart, often smaller than the body), or
      a size 5% off the body's.
    - An unnumbered line does not take a title that also appears numbered.
    - The first line of a wrapped heading matches its title by prefix."""
    whole = norm_text(ln.text)
    key, has_number = heading_key(ln.text)
    letters = [c for c in ln.text if c.isalpha()]
    caps = len(letters) >= 3 and all(c.isupper() for c in letters)
    set_apart = caps or abs(ln.size - body) >= 0.05 * body
    looks_like_heading = ln.bold or ln.size >= body * HEADING_RATIO or has_number
    if not looks_like_heading and (not set_apart or left[key] <= 0):
        return None
    if not has_number and key in numbered:
        return None
    for candidate in (whole, key):
        if left[candidate] > 0:
            return candidate
    if len(key) >= WRAPPED_MIN_CHARS:
        for title, n in left.items():
            if n > 0 and title.startswith(key) and len(key) >= 0.5 * len(title):
                return title
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


def heading_sizes(pages: Sequence[PageText], body: float, skip: set[int]) -> tuple[dict[float, int], set[float]]:
    """Heading font sizes (rounded to 0.5 pt) mapped to levels 1..6, largest first, and the subset that counts
    only for bold lines."""
    big: set[float] = set()
    bold: set[float] = set()
    for p in pages:
        for ln in p.lines:
            if ln.order in skip or not 0 < len(ln.text) <= 200:
                continue
            size = round(ln.size * 2) / 2
            if ln.size >= body * HEADING_RATIO:
                big.add(size)
            elif ln.bold and ln.size >= body * BOLD_HEADING_RATIO:
                bold.add(size)
    bold -= big
    ordered = sorted(big | bold, reverse=True)
    return {s: min(i + 1, 6) for i, s in enumerate(ordered)}, bold


def page_title(pages: Sequence[PageText], body: float, skip: set[int]) -> str | None:
    """The title set on the first page: its largest upright text (consecutive lines of that size joined), when
    that is heading-sized, has a word, and is not a numbered section or "Abstract". Used when the PDF's
    metadata has no usable title, instead of the first top-level heading ("1. Introduction")."""
    page = next((p for p in pages if any(ln.order not in skip for ln in p.lines)), None)
    if page is None:
        return None
    lines = [ln for ln in page.lines if ln.order not in skip and not ln.turn and HEADING_WORD.search(ln.text)]
    if not lines:
        return None
    top = max(ln.size for ln in lines)
    if top >= body * HEADING_RATIO:
        group = sorted((ln for ln in lines if round(ln.size * 2) == round(top * 2)), key=lambda ln: ln.order)
    else:
        group = _top_title_lines(lines, page.height, page.width)
        if not group:
            return None
    run = [group[0]]
    for ln in group[1:]:
        prev = run[-1]
        same_line = abs(ln.y1 - prev.y1) <= 0.3 * ln.size and ln.x0 >= prev.x1  # "Eagle" then ": Ethical ..."
        if ln.order == prev.order + 1 and (same_line or 0 <= ln.y0 - prev.y1 <= 0.8 * ln.size):
            run.append(ln)
        else:
            break
    text = run[0].text
    for ln in run[1:]:
        text += ln.text if ln.text[:1] in ",.:;)" else " " + ln.text
    text = text.strip()
    if section_number(text)[0] is not None or norm_text(text) in FRONT_MATTER or len(text) > 250:
        return None
    return text


TITLE_ZONE = 0.35
"""When no text on the first page is heading-sized, the title is looked for in this top share of the page."""


def _top_title_lines(lines: list[Line], height: float, width: float) -> list[Line]:
    """Title pages that set the title at body size (AMS capitals, AASTeX under "Draft version" notes): the
    largest centred line of two words or more in the top of the page, with the lines continuing it."""

    def centred(ln: Line) -> bool:
        return abs((ln.x0 + ln.x1) / 2 - width / 2) <= 0.06 * width

    zone = [ln for ln in lines if ln.y0 <= TITLE_ZONE * height and len(ln.text.split()) >= 2 and centred(ln)]
    if not zone:
        return []
    top = max(ln.size for ln in zone)
    first = min((ln for ln in zone if round(ln.size * 2) == round(top * 2)), key=lambda ln: (ln.y0, ln.x0))
    same = sorted(
        (ln for ln in lines if round(ln.size * 2) == round(first.size * 2) and ln.bold == first.bold),
        key=lambda ln: ln.order,
    )
    return same[same.index(first) :]


def front_matter_lines(pages: Sequence[PageText], skip: set[int]) -> set[int]:
    """On the first page, the lines between the largest line (the title) and a front-matter heading such as
    "Abstract": author names and affiliations, set in heading sizes. Empty when the page has no such heading."""
    page = next((p for p in pages if any(ln.order not in skip for ln in p.lines)), None)
    if page is None:
        return set()
    lines = [ln for ln in page.lines if ln.order not in skip and not ln.turn]
    marker = next((ln for ln in lines if norm_text(ln.text) in FRONT_MATTER), None)
    if marker is None:
        return set()
    top = max(ln.size for ln in lines)
    title = [ln for ln in lines if round(ln.size * 2) == round(top * 2)]
    below = max(ln.y1 for ln in title)
    return {ln.order for ln in lines if below <= ln.y0 < marker.y0 and ln not in title}


def plan_outline(src: HeadingSources, pages: Sequence[PageText], skip: set[int]) -> None:
    """Switch `src` to outline mode when the outline covers the body, and find the first-page title above it."""
    titles: Counter[str] = Counter()
    for (key, _page), _lvl in src.outline.items():
        titles[key] += 1
    if not titles:
        return
    src.contents |= listed_titles(pages, titles, skip)
    hidden = skip | src.prose | src.turned | src.contents
    lines = [ln for p in pages for ln in p.lines if ln.order not in hidden]
    src.numbered_keys = {
        key for ln in lines for key, has_number in [heading_key(ln.text)] if has_number and key in titles
    }
    left = titles.copy()
    matched: list[tuple[Line, int]] = []
    for ln in lines:
        hit = outline_key(ln, src.body, left, src.numbered_keys)
        if hit is None:
            run_in = run_in_heading(ln.text, left)
            hit = run_in[0] if run_in is not None else None
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
    sizes, bold_sizes = heading_sizes(pages, body, skip | prose | turned)
    src = HeadingSources(sizes=sizes, bold_sizes=bold_sizes, body=body, prose=prose, turned=turned)
    src.front = front_matter_lines(pages, skip)
    src.contents = contents_lines(pages, skip)
    for level, title, page in outline:
        key, _ = heading_key(title)
        src.outline.setdefault((key, page), level)
        src.outline_any.setdefault(key, level)
    plan_outline(src, pages, skip)
    return src


PAGE_REF = re.compile(r"(?:\.\s*){2,}\s*\d{1,4}$|\S\s+\d{1,4}$")
"""A contents entry: dot leaders or a gap before a closing page number ("2.1. Metric graph theory .... 5")."""
CONTENTS_MIN_LINES = 5
CONTENTS_SHARE = 0.3


RUN_IN_END = re.compile(r"[.:]\s+(?=\S)")


def run_in_heading(text: str, left: Counter[str]) -> tuple[str, int] | None:
    """(title, length) when `text` opens with a numbered bookmarked title closed by "." or ":" and the
    paragraph continues on the line: AMS-style run-in headings ("2.1. Metric graph theory. For a graph G,").
    The length covers the heading and its closing punctuation."""
    if heading_key(text)[1] is False:
        return None
    for m in RUN_IN_END.finditer(text):
        key, numbered = heading_key(text[: m.start()])
        if numbered and left[key] > 0:
            return key, m.start() + 1
        if len(key) > 120:
            break
    return None


def listed_titles(pages: Sequence[PageText], titles: Counter[str], skip: set[int]) -> set[int]:
    """Orders of a contents list printed without page numbers: on one page, `CONTENTS_MIN_LINES` or more
    consecutive, tightly spaced lines that are each an outline title. The headings come later; the list must
    not take their bookmarks."""
    out: set[int] = set()
    for p in pages:
        run: list[Line] = []
        for ln in sorted((ln for ln in p.lines if ln.order not in skip), key=lambda ln: ln.order):
            listed = titles[heading_key(ln.text)[0]] > 0 or titles[norm_text(ln.text)] > 0
            if listed and (not run or 0 <= ln.y0 - run[-1].y1 <= ln.size):
                run.append(ln)
                continue
            if len(run) >= CONTENTS_MIN_LINES:
                out.update(r.order for r in run)
            run = [ln] if listed else []
        if len(run) >= CONTENTS_MIN_LINES:
            out.update(r.order for r in run)
    return out


def contents_lines(pages: Sequence[PageText], skip: set[int]) -> set[int]:
    """Orders of the lines on printed table-of-contents pages: at least `CONTENTS_MIN_LINES` lines, and
    `CONTENTS_SHARE` of the page, end in a page number. They repeat the headings, so matching them would hand
    the headings' bookmarks to the contents page."""
    out: set[int] = set()
    for p in pages:
        lines = [ln for ln in p.lines if ln.order not in skip]
        refs = [ln for ln in lines if PAGE_REF.search(ln.text) and HEADING_WORD.search(ln.text)]
        if len(refs) >= CONTENTS_MIN_LINES and len(refs) >= CONTENTS_SHARE * len(lines):
            out.update(ln.order for ln in refs)
    return out


def minority_turned(pages: Sequence[PageText]) -> set[int]:
    """Orders of turned lines on pages where they are under `TURNED_MINORITY` of the lines."""
    out: set[int] = set()
    for p in pages:
        turned = [ln.order for ln in p.lines if ln.turn]
        if turned and len(turned) < TURNED_MINORITY * len(p.lines):
            out.update(turned)
    return out
