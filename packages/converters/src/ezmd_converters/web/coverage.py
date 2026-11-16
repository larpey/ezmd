"""How much of a page an extractor left behind (part2 5c step 16).

`Page.clean_chars` cannot answer this: it is measured after the same class and id rules that remove sections, so
a section those rules take is missing from both sides of the ratio. Here the page is the body with only the
structural boilerplate gone (what `web.html_raw` keeps), and each block of it is looked up in the extracted text
by its word shingles. The cost is linear in the page. Blocks that are mostly links and blocks too short to
shingle are not counted: they are the related-story lists and button labels extraction is there to remove.
"""

from __future__ import annotations

from collections.abc import Iterator
from copy import deepcopy

from ezmd.ir import Warning, WarningKind
from ezmd_converters.web.boilerplate import MAX_ANCHOR_LINK_DENSITY, link_density, strip_boilerplate, words
from ezmd_converters.web.dom import HtmlElement, collapse, is_element, tag_of, text_of

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


def _shingles(tokens: list[str]) -> Iterator[int]:
    return (hash(tuple(tokens[i : i + SHINGLE_WORDS])) for i in range(len(tokens) - SHINGLE_WORDS + 1))


_CONTAINERS = ("div", "section", "span", "font", "center", "summary", "figcaption", "caption", "label")
"""Elements that hold text on pages built without paragraph tags: a table drawn with divs (`divTableCell`), a
component that puts its sentence in a span. They count when no counted block or other container sits inside."""
_NESTED = (*_BLOCKS, *_HEADINGS, "div", "section", "table", "ul", "ol", "dl")


def _is_leaf(el: HtmlElement) -> bool:
    return next(el.iterdescendants(*_BLOCKS), None) is None


def _is_text_container(el: HtmlElement) -> bool:
    """A div-like leaf: none of its descendants is a block, a heading or another container, and no counted block
    is its ancestor (so a span inside a counted `<p>` is not counted twice)."""
    if next(el.iterdescendants(*_NESTED), None) is not None:
        return False
    return next(el.iterancestors(*_BLOCKS, *_HEADINGS, *_CONTAINERS[2:]), None) is None


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
    for el in body.iter(*_HEADINGS, *_BLOCKS, *_CONTAINERS):
        if not is_element(el):
            continue
        tag = tag_of(el)
        if tag in _HEADINGS:
            text = collapse(text_of(el))
            tally.open(text)
        elif (tag in _BLOCKS and _is_leaf(el)) or (tag in _CONTAINERS and _is_text_container(el)):
            text = collapse(text_of(el))
        else:
            continue
        tokens = words(text)
        if len(tokens) >= SHINGLE_WORDS and link_density(el) < MAX_ANCHOR_LINK_DENSITY:
            tally.add(len(text), kept=_is_kept(tokens, kept))
    return tally


def shingles_of(text: str) -> set[int]:
    return set(_shingles(words(text)))


def holds(kept: set[int], text: str) -> bool:
    """True when `kept` (shingles of extracted text) holds `text`. Text too short to shingle counts as held: it is
    too short to tell, and too short to matter to the loss checks."""
    tokens = words(text)
    if len(tokens) < SHINGLE_WORDS:
        return True
    return _is_kept(tokens, kept)


def dropped_text(body: HtmlElement, extracted: str) -> Warning | None:
    """An `extraction_dropped_text` warning when `extracted` lacks a headed section or a material share of `body`."""
    page = deepcopy(body)
    strip_boilerplate(page, aggressive=False)
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
