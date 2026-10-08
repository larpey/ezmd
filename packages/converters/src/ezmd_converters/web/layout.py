"""Layout-table pages on the Trafilatura path (docs/spec/part2.md 5e item 11).

Trafilatura flattens 2005-era pages built from nested presentation tables into a run of `<table>` elements in
whatever order its own tree walk produces (footers first is common) and keeps the chrome cells: the header
tagline, the navigation column, the copyright footer. This module

- splits an unmatched XML layout table into its pieces (paragraph runs and block children of each cell);
- anchors a piece back into the cleaned DOM (the deepest element whose text contains the piece's text), so the
  caller can sort every block back into source order;
- picks the content cell (the table cell holding most of the anchored text) and reports the pieces that sit in
  other layout cells and look like chrome (short, or mostly links) so the caller can drop them.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from lxml import etree  # type: ignore[import-untyped]

from ezmd_converters.web.boilerplate import link_density
from ezmd_converters.web.dom import HtmlElement, collapse, is_element, match_key, tag_of, text_of

XML_BLOCKS = frozenset({"p", "list", "head", "table", "code", "quote", "graphic"})
CHROME_MAX_CHARS = 200
"""A layout cell outside the content cell with less text than this is chrome (tagline, nav, footer)."""
CHROME_LINK_DENSITY = 0.5
_MAX_DEPTH = 32


def layout_pieces(node: Any, is_layout: Any, depth: int = 0) -> list[Any]:
    """The pieces of an XML layout table in reading order: each cell's inline runs become `<p>` elements, block
    children are kept, nested layout tables are split the same way (`is_layout` decides)."""
    out: list[Any] = []
    for row in node.findall("row"):
        for cell in row.findall("cell"):
            run = etree.Element("p")
            run.text = cell.text
            for child in cell:
                if child.tag not in XML_BLOCKS:
                    run.append(deepcopy(child))
                    continue
                _keep_run(run, out)
                if child.tag == "table" and depth < _MAX_DEPTH and is_layout(child):
                    out.extend(layout_pieces(child, is_layout, depth + 1))
                else:
                    out.append(child)
                run = etree.Element("p")
                run.text = child.tail
            _keep_run(run, out)
    return out


def _keep_run(run: Any, out: list[Any]) -> None:
    if (run.text or "").strip() or len(run):
        out.append(run)


class Anchors:
    """Locate XML pieces in the DOM by text: the deepest (shortest-text) element containing the piece's key."""

    def __init__(self, body: HtmlElement, order: dict[HtmlElement, int]) -> None:
        self._body = body
        self._order = order
        self._keys: list[tuple[HtmlElement, str]] | None = None

    def locate(self, key: str, after: int = 0) -> HtmlElement | None:
        if len(key) < 2:
            return None
        if self._keys is None:
            self._keys = [(el, match_key(text_of(el))) for el in self._body.iter() if is_element(el)]
        best: tuple[tuple[int, int, int], HtmlElement] | None = None
        for el, k in self._keys:
            if key not in k:
                continue
            pos = self._order.get(el, 0)
            # Shortest text first; then at or after `after`; then the deepest (latest in document order) of
            # equal-text ancestors, e.g. the <font> inside a <td> inside a <tr>.
            rank = (len(k), 0 if pos >= after else 1, -pos)
            if best is None or rank < best[0]:
                best = (rank, el)
        return best[1] if best is not None else None


def cell_of(el: HtmlElement | None) -> HtmlElement | None:
    node = el
    while node is not None and is_element(node):
        if tag_of(node) in ("td", "th"):
            return node
        node = node.getparent()
    return None


def _ancestors(el: HtmlElement) -> set[HtmlElement]:
    out: set[HtmlElement] = set()
    node = el.getparent()
    while node is not None and is_element(node):
        out.add(node)
        node = node.getparent()
    return out


def content_cell(weighted: list[tuple[HtmlElement, int]]) -> HtmlElement | None:
    """The table cell (td/th) with the most anchored text, from (anchor, chars) pairs."""
    totals: dict[HtmlElement, int] = {}
    for el, chars in weighted:
        cell = cell_of(el)
        if cell is not None:
            totals[cell] = totals.get(cell, 0) + chars
    return max(totals, key=lambda c: totals[c]) if totals else None


def is_chrome(anchor: HtmlElement | None, main: HtmlElement | None) -> bool:
    """A layout piece anchored in a cell that is not the content cell (nor nested in or around it) whose text is
    short or mostly links."""
    if anchor is None or main is None:
        return False
    cell = cell_of(anchor)
    if cell is None or cell is main or main in _ancestors(cell) or cell in _ancestors(main):
        return False
    chars = len(collapse(text_of(cell)))
    return chars < CHROME_MAX_CHARS or link_density(cell) >= CHROME_LINK_DENSITY
