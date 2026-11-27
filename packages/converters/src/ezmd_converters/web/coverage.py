"""How much of a page an extractor left behind (part2 5c step 16).

`Page.clean_chars` cannot answer this: it is measured after the same class and id rules that remove sections, so
a section those rules take is missing from both sides of the ratio. Here the page is the body with only the
structural boilerplate gone (what `web.html_raw` keeps), and each block of it is looked up in the extracted text
by its word shingles. The cost is linear in the page. Blocks that are mostly links and blocks too short to
shingle are not counted: they are the related-story lists and button labels extraction is there to remove.
Browser-upgrade and exit-popup banners are not counted either, and heading text always counts as kept.
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


def _is_leaf(el: HtmlElement) -> bool:
    return next(el.iterdescendants(*_BLOCKS), None) is None


def _is_kept(tokens: list[str], kept: set[int]) -> bool:
    shingles = list(_shingles(tokens))
    return sum(s in kept for s in shingles) >= KEPT_SHINGLES * len(shingles)


class _Tally:
    """Characters of counted text per heading, in page order; index 0 is the text before the first heading."""

    def __init__(self) -> None:
        self.titles: list[str] = [""]
        self.total: list[int] = [0]
        self.lost: list[int] = [0]

    def open(self, title: str) -> None:
        self.titles.append(title)
        self.total.append(0)
        self.lost.append(0)

    def add(self, chars: int, *, kept: bool) -> None:
        self.total[-1] += chars
        if not kept:
            self.lost[-1] += chars

    def dropped_sections(self) -> list[str]:
        return [
            title
            for title, total, lost in zip(self.titles, self.total, self.lost, strict=True)
            if title and lost >= MIN_SECTION_CHARS and lost > total / 2
        ]


def _tally(body: HtmlElement, kept: set[int]) -> _Tally:
    tally = _Tally()
    for el in body.iter(*_HEADINGS, *_BLOCKS):
        if not is_element(el):
            continue
        if tag_of(el) in _HEADINGS:
            title = collapse(text_of(el))
            tally.open(title)
            tally.add(len(title), kept=True)
        elif _is_leaf(el):
            text = collapse(text_of(el))
            tokens = words(text)
            if len(tokens) < SHINGLE_WORDS or link_density(el) >= MAX_ANCHOR_LINK_DENSITY:
                continue
            if len(text) <= MAX_BANNER_BLOCK_CHARS and _BANNER_TEXT.search(text):
                continue
            # Headings inside the block are counted, as kept, when the walk reaches them.
            own = len(text) - sum(len(collapse(text_of(h))) for h in el.iterdescendants(*_HEADINGS))
            tally.add(max(0, own), kept=_is_kept(tokens, kept))
    return tally


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
