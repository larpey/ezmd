"""How much of a page an extractor left behind (part2 5c step 16).

`Page.clean_chars` cannot answer this: it is measured after the same class and id rules that remove sections, so
a section those rules take is missing from both sides of the ratio. Here the page is the body with only the
structural boilerplate gone (what `web.html_raw` keeps), and each block of it is looked up in the extracted text
by its word shingles. The cost is linear in the page. Blocks that are mostly links and blocks too short to
shingle are not counted: they are the related-story lists and button labels extraction is there to remove.
Browser-upgrade and exit-popup banners are not counted either. Heading text is page text: it counts as lost
only when a heading of five or more words is missing and the text under it was kept, and as kept otherwise.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from copy import deepcopy

from ezmd.ir import Warning, WarningKind
from ezmd_converters.web.boilerplate import (
    MAX_ANCHOR_LINK_DENSITY,
    link_density,
    mostly_content,
    protected,
    section_anchors,
    strip_boilerplate,
    words,
)
from ezmd_converters.web.dom import HtmlElement, collapse, is_element, tag_of, text_of
from ezmd_converters.web.hygiene import _remove

_HEADINGS = ("h1", "h2", "h3", "h4", "h5", "h6")
_BLOCKS = ("p", "li", "dd", "dt", "td", "th", "blockquote", "pre")
SHINGLE_WORDS = 5
KEPT_SHINGLES = 0.5
"""A block counts as kept when this share of its shingles appears in the extracted text."""
KEPT_SECTION = 0.5
"""The text under a heading counts as kept when this share of its characters was kept."""
MIN_SECTION_CHARS = 200
"""A headed section is reported once this much of its text is gone (and most of the section with it)."""
MIN_PAGE_RATIO = 0.05
"""Share of the page's text that must be gone for a loss with no headed section to be reported. The same 5 percent
the benchmark calls silent loss (tools/bench)."""
MAX_NAMED_SECTIONS = 12
MAX_BANNER_BLOCK_CHARS = 300
"""A block longer than this is prose that mentions browsers or leaving a site, not a banner saying so."""
_BANNER_ATTR = re.compile(
    r"(^|[-_ ])((outdated|unsupported|old)[-_]?browser|browser[-_]?(upgrade|update|warning|notice|alert|banner)|"
    r"upgrade[-_]?browser|browsehappy|buorg|exit[-_]?(intent|popup|pop-up|modal|overlay|disclaimer))([-_ ]|$)",
    re.I,
)
_BANNER_TEXT = re.compile(
    r"\b(you(['’]re| are) (currently )?using an? (outdated|unsupported|old(er)?)( version of)?( web)? ?browser|"
    r"your (web )?browser is (out of date|outdated|unsupported|(not|no longer) supported)|"
    r"(please )?(upgrade|update) your (web )?browser (to|for)\b|"
    r"you(['’]re| are) (now )?(leaving|about to leave) (this|our|the) (web ?)?site)",
    re.I,
)


def _shingles(tokens: list[str]) -> Iterator[int]:
    return (hash(tuple(tokens[i : i + SHINGLE_WORDS])) for i in range(len(tokens) - SHINGLE_WORDS + 1))


_CONTAINERS = ("div", "section", "span", "font", "center", "summary", "figcaption", "caption", "label")
"""Elements that hold text on pages built without paragraph tags: a table drawn with divs (`divTableCell`), a
component that puts its sentence in a span. They count when no counted block or other container sits inside."""
_NESTED = (*_BLOCKS, *_HEADINGS, "div", "section", "table", "ul", "ol", "dl")


def _is_leaf(el: HtmlElement) -> bool:
    return next(el.iterdescendants(*_BLOCKS), None) is None


def _is_text_container(el: HtmlElement) -> bool:
    """A div-like leaf: no block, heading, div, section, table or list sits inside it."""
    return next(el.iterdescendants(*_NESTED), None) is None


def _is_kept(tokens: list[str], kept: set[int]) -> bool:
    shingles = list(_shingles(tokens))
    return sum(s in kept for s in shingles) >= KEPT_SHINGLES * len(shingles)


class _Tally:
    """Characters of counted text per heading, in page order; index 0 is the text before the first heading."""

    def __init__(self) -> None:
        self.titles: list[str] = [""]
        self.total: list[int] = [0]
        self.lost: list[int] = [0]
        self.levels: list[int] = [0]
        self.missing: list[bool] = [False]
        """Per section: its heading is long enough to match and is not in the extracted text."""

    def open(self, title: str, *, level: int, missing: bool) -> None:
        self.titles.append(title)
        self.total.append(0)
        self.lost.append(0)
        self.levels.append(level)
        self.missing.append(missing)

    def add(self, chars: int, *, kept: bool) -> None:
        self.total[-1] += chars
        if not kept:
            self.lost[-1] += chars

    def settle_headings(self) -> None:
        """Count each heading's characters, once all body text is in. A missing heading is lost only when the text
        under it was kept; where that text is gone too, the text's own characters report the loss (D-0089)."""
        lost = {i for i, missing in enumerate(self.missing) if missing and self._body_kept(i)}
        for i, title in enumerate(self.titles):
            self.total[i] += len(title)
            if i in lost:
                self.lost[i] += len(title)

    def _body_kept(self, i: int) -> bool:
        """Whether at least half of the body text under heading `i`, subsections included, was kept. Only right
        before any heading characters are added."""
        end = i + 1
        while end < len(self.levels) and self.levels[end] > self.levels[i]:
            end += 1
        total, lost = sum(self.total[i:end]), sum(self.lost[i:end])
        return total > 0 and total - lost >= KEPT_SECTION * total

    def dropped_sections(self) -> list[str]:
        return [
            title
            for title, total, lost in zip(self.titles, self.total, self.lost, strict=True)
            if title and lost >= MIN_SECTION_CHARS and lost > total / 2
        ]


def _tally(body: HtmlElement, kept: set[int]) -> _Tally:
    tally = _Tally()
    taken: set[HtmlElement] = set()
    """Headings and counted elements. Their text is spoken for, so nothing inside them is counted again; the walk is
    in document order, so an ancestor is always decided before its descendants."""
    for el in body.iter(*_HEADINGS, *_BLOCKS, *_CONTAINERS):
        if not is_element(el):
            continue
        if tag_of(el) in _HEADINGS:
            if el not in taken:  # one inside a counted element was opened with that element
                taken.add(el)
                _open_heading(tally, el, kept)
            continue
        if any(a in taken for a in el.iterancestors()) or not _holds_text(el):
            continue
        taken.add(el)
        # A heading inside a list item or cell titles the rest of that element: open its section first, and count the
        # heading's characters there only, not in the element too.
        nested = list(el.iterdescendants(*_HEADINGS))
        for heading in nested:
            taken.add(heading)
            _open_heading(tally, heading, kept)
        text = collapse(text_of(el))
        tokens = words(text)
        if len(tokens) < SHINGLE_WORDS or link_density(el) >= MAX_ANCHOR_LINK_DENSITY or _is_banner(text):
            continue
        own = _text_outside_headings(el) if nested else text
        own_tokens = words(own)
        tally.add(len(own), kept=_is_kept(own_tokens if len(own_tokens) >= SHINGLE_WORDS else tokens, kept))
    tally.settle_headings()
    return tally


def _holds_text(el: HtmlElement) -> bool:
    """A leaf block, or a div-like leaf."""
    tag = tag_of(el)
    return (tag in _BLOCKS and _is_leaf(el)) or (tag in _CONTAINERS and _is_text_container(el))


def _is_banner(text: str) -> bool:
    return len(text) <= MAX_BANNER_BLOCK_CHARS and _BANNER_TEXT.search(text) is not None


def _open_heading(tally: _Tally, el: HtmlElement, kept: set[int]) -> None:
    title = collapse(text_of(el))
    tokens = words(title)
    missing = (
        len(tokens) >= SHINGLE_WORDS
        and link_density(el) < MAX_ANCHOR_LINK_DENSITY
        and not _is_banner(title)
        and not _is_kept(tokens, kept)
    )
    tally.open(title, level=int(tag_of(el)[1]), missing=missing)


def _text_outside_headings(el: HtmlElement) -> str:
    rest = deepcopy(el)
    for heading in list(rest.iterdescendants(*_HEADINGS)):
        _remove(heading)
    return collapse(text_of(rest))


def shingles_of(text: str) -> set[int]:
    return set(_shingles(words(text)))


def holds(kept: set[int], text: str) -> bool:
    """True when `kept` (shingles of extracted text) holds `text`. Text too short to shingle counts as held: it is
    too short to tell, and too short to matter to the loss checks."""
    tokens = words(text)
    if len(tokens) < SHINGLE_WORDS:
        return True
    return _is_kept(tokens, kept)


def _remove_banners(body: HtmlElement) -> None:
    """Drop browser-upgrade and exit-popup containers, named so by class or id."""
    anchors = section_anchors(body)
    for el in list(body.iterdescendants()):
        if not is_element(el) or el.getparent() is None or el in anchors:
            continue
        attrs = f"{el.get('class') or ''} {el.get('id') or ''}"
        if _BANNER_ATTR.search(attrs) and not protected(el) and not mostly_content(el, body):
            _remove(el)


def dropped_text(body: HtmlElement, extracted: str) -> Warning | None:
    """An `extraction_dropped_text` warning when `extracted` lacks a headed section or a material share of `body`."""
    page = deepcopy(body)
    strip_boilerplate(page, aggressive=False)
    _remove_banners(page)
    tally = _tally(page, set(_shingles(words(extracted))))
    page_chars, dropped = sum(tally.total), sum(tally.lost)
    sections = tally.dropped_sections()
    if not sections and (dropped < MIN_SECTION_CHARS or dropped < MIN_PAGE_RATIO * page_chars):
        return None
    named = "; ".join(sections[:MAX_NAMED_SECTIONS])
    listing = f" Sections left out: {named}." if named else ""
    return Warning(
        kind=WarningKind.EXTRACTION_DROPPED_TEXT,
        message=f"Extraction left out {dropped} of {page_chars} characters of page text.{listing}",
        detail={"page_chars": page_chars, "dropped_chars": dropped, "sections": named},
    )
