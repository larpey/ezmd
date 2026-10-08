"""Trafilatura extraction (part2 5b step 2) and its TEI-like XML to IR.

Trafilatura decides *what* the article is; each block it keeps is matched back into the cleaned DOM by text
(5c step 15) and, when found, converted from the DOM element, which restores what the XML loses: code
languages, ordered-list starts, table spans, figure captions (5e item 2), footnotes, math, and a CSS-ish
`path`. Blocks that cannot be matched are converted from the XML with `path = article#<index>`.
"""

from __future__ import annotations

import logging
import re
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from lxml import etree  # type: ignore[import-untyped]

from ezmd.ir import CodeBlock, Heading, Image, InlineSpan, InlineStyle, ListBlock, ListItem, Paragraph, Quote, Table
from ezmd.ir import TableCell as Cell
from ezmd_converters.web.build import LAZY_ATTRS, LAZY_SRCSET, Builder
from ezmd_converters.web.dom import HtmlElement, is_element, match_key, tag_of
from ezmd_converters.web.html_blocks import convert_block, is_footnote_section, is_layout_table
from ezmd_converters.web.inline import footnote_target, is_math, normalize_spans, tex_of
from ezmd_converters.web.layout import Anchors, content_cell, is_chrome, layout_pieces

log = logging.getLogger(__name__)
_WS = re.compile(r"\s+")

_DOM_FOR: dict[str, tuple[str, ...]] = {
    "head": ("h1", "h2", "h3", "h4", "h5", "h6", "summary"),
    "p": ("p", "dd", "dt", "figcaption"),
    "list": ("ul", "ol", "dl"),
    "code": ("pre",),
    "quote": ("blockquote",),
    "table": ("table", "dl"),
}
_REND_STYLE = {
    "#b": InlineStyle.BOLD,
    "#i": InlineStyle.ITALIC,
    "#u": InlineStyle.UNDERLINE,
    "#t": InlineStyle.CODE,
    "#sup": InlineStyle.SUPERSCRIPT,
    "#sub": InlineStyle.SUBSCRIPT,
    "#s": InlineStyle.STRIKE,
}


def run_trafilatura(root: HtmlElement, url: str | None) -> Any | None:
    """Run Trafilatura on a copy of the cleaned tree and parse its XML safely. None when it finds nothing."""
    import trafilatura
    from trafilatura.deduplication import LRUCache

    try:
        xml = trafilatura.extract(
            deepcopy(root),
            url=url,
            output_format="xml",
            include_tables=True,
            include_images=True,
            include_links=True,
            include_formatting=True,
            include_comments=False,
            favor_precision=False,
            deduplicate=LRUCache(maxsize=4096),
            with_metadata=False,
        )
    except Exception as e:  # engine bugs fall through to the rules extractor
        log.info("trafilatura failed: %s", e)
        return None
    if not xml:
        return None
    parser = etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=False, load_dtd=False)
    try:
        doc = etree.fromstring(xml.encode("utf-8"), parser=parser)
    except etree.XMLSyntaxError as e:
        log.info("trafilatura produced invalid XML: %s", e)
        return None
    return doc.find("main")


class DomIndex:
    """Cleaned-DOM block elements by text key, in document order."""

    def __init__(self, body: HtmlElement) -> None:
        self.order: dict[HtmlElement, int] = {}
        self.by_key: dict[tuple[str, str], list[HtmlElement]] = {}
        self.imgs: dict[str, HtmlElement] = {}
        self.used: set[HtmlElement] = set()
        wanted = {t for tags in _DOM_FOR.values() for t in tags}
        for i, el in enumerate(body.iter()):
            if not is_element(el):
                continue
            self.order[el] = i
            tag = tag_of(el)
            if tag in wanted:
                key = match_key(_dom_text(el))
                if key:
                    self.by_key.setdefault((tag, key), []).append(el)

    def find(self, xml_tag: str, key: str, after: int) -> HtmlElement | None:
        """The first unused DOM element at or after `after` whose text equals `key`; failing that, one whose
        text contains or is contained in `key` with at least 80 percent overlap (extractors drop markers such
        as footnote numbers or inline math)."""
        tags = _DOM_FOR.get(xml_tag, ())
        exact = self._best(((t, key) for t in tags), after)
        if exact is not None:
            return exact
        fuzzy: HtmlElement | None = None
        for tag, k in self.by_key:
            if tag not in tags or not _overlaps(key, k):
                continue
            cand = self._best([(tag, k)], after)
            if cand is not None and (fuzzy is None or self.order[cand] < self.order[fuzzy]):
                fuzzy = cand
        return fuzzy

    def _best(self, keys: Any, after: int) -> HtmlElement | None:
        best: HtmlElement | None = None
        for k in keys:
            for el in self.by_key.get(k, []):
                pos = self.order.get(el, 0)
                if el not in self.used and pos >= after and (best is None or pos < self.order.get(best, 0)):
                    best = el
        return best

    def seen(self, xml_tag: str, key: str) -> bool:
        """True when an element with this text was already converted (as part of a container)."""
        return any(el in self.used for t in _DOM_FOR.get(xml_tag, ()) for el in self.by_key.get((t, key), []))

    def mark(self, el: HtmlElement) -> None:
        for d in el.iter():
            self.used.add(d)


def _dom_text(el: HtmlElement, depth: int = 0) -> str:
    """Text of `el` with math replaced by its TeX source, as extractors print it."""
    if depth > 100:
        return str(el.text_content() or "")
    parts = [el.text or ""]
    for child in el:
        if is_element(child):
            parts.append((tex_of(child) or "") if is_math(child) else _dom_text(child, depth + 1))
        parts.append(child.tail or "")
    return "".join(parts)


def _xml_key(node: Any) -> str:
    text = "".join(node.itertext())
    for token in (chr(92) + "(", chr(92) + ")", chr(92) + "[", chr(92) + "]"):
        text = text.replace(token, "")
    return match_key(text)


def _overlaps(a: str, b: str) -> bool:
    if len(a) < 12 or len(b) < 12:
        return False
    short, long_ = (a, b) if len(a) <= len(b) else (b, a)
    return short in long_ and len(short) >= 0.8 * len(long_)


def _image_urls(body: HtmlElement, b: Builder) -> dict[str, HtmlElement]:
    """Every URL an extractor may report for a DOM image (src, lazy-load attributes, srcset candidates)."""
    out: dict[str, HtmlElement] = {}
    for el in body.iter("img", "amp-img"):
        for attr in ("src", *LAZY_ATTRS):
            v = (el.get(attr) or "").strip()
            if v:
                out.setdefault(b.url(v), el)
        for attr in ("srcset", *LAZY_SRCSET):
            for part in (el.get(attr) or "").split(","):
                bits = part.split()
                if bits:
                    out.setdefault(b.url(bits[0]), el)
    return out


def _container(el: HtmlElement) -> HtmlElement | None:
    """The figure, details block, or footnote section around `el`, converted whole so captions, summaries,
    and footnote ids survive."""
    node = el if tag_of(el) in ("figure", "details") else el.getparent()
    while node is not None and is_element(node):
        if tag_of(node) in ("figure", "details") or is_footnote_section(node):
            return node
        if tag_of(node) in ("article", "main", "body"):
            return None
        node = node.getparent()
    return None


def tei_to_blocks(main: Any, body: HtmlElement, b: Builder) -> None:
    """Convert Trafilatura's <main> into blocks on `b`, preferring the matching DOM element for each block.

    Trafilatura drops images whose `src` is a lazy-load placeholder. Unused images inside the matched article
    region (the common ancestor of the matched elements, outside nav/aside/header/footer) are put back in
    document order. Unmatched layout tables are split into their pieces (layout.py); every block is anchored in
    the DOM and emitted in source order, and layout chrome outside the content cell is dropped."""
    index = DomIndex(body)
    anchors = Anchors(body, index.order)
    imgs = _image_urls(body, b)
    after = 0
    plan: list[_Step] = []
    for node, n, from_layout in _expand(main, index):
        tag = node.tag
        key = "" if tag == "graphic" else _xml_key(node)
        if tag == "graphic":
            dom = imgs.get(node.get("src") or "")
        else:
            if not key:
                continue
            dom = index.find(tag, key, after)
            if dom is None:
                dom = index.find(tag, key, 0)
            if dom is None and index.seen(tag, key):
                continue
        if dom is None or from_layout:
            anchor = dom if dom is not None else anchors.locate(key, after)
            pos = index.order.get(anchor, -1) if anchor is not None else -1
            plan.append(_Step(None, node, n, pos, anchor, from_layout, len(key)))
            continue
        if dom in index.used:
            continue
        target = _container(dom)
        if target is None or target in index.used:
            target = dom
        index.mark(target)
        after = max(after, index.order.get(target, after))
        if tag_of(target) not in ("dd", "dt", "figcaption", "summary"):
            layout = tag_of(target) == "table" and is_layout_table(target)
            plan.append(_Step(target, node, n, index.order.get(target, -1), target, layout, len(key)))
    plan = _source_order(_drop_chrome(plan))
    targets = [s.target for s in plan if s.target is not None]
    extra = _dropped_images(targets, index)
    for step in plan:
        while extra and index.order.get(extra[0], 0) < step.pos:
            _restore_image(extra.pop(0), index, b)
        if step.target is None:
            _xml_block(step.node, b, step.n)
        else:
            convert_block(step.target, b)
    for img in extra:
        _restore_image(img, index, b)
    for sec in _referenced_footnotes(body, targets, index):
        index.mark(sec)
        convert_block(sec, b)


@dataclass(slots=True)
class _Step:
    target: HtmlElement | None
    """DOM element converted for this block, or None to convert the XML node."""
    node: Any
    n: int
    pos: int
    """Source position (DomIndex order) of the anchor; -1 when the block could not be anchored."""
    anchor: HtmlElement | None
    from_layout: bool
    chars: int


def _expand(main: Any, index: DomIndex) -> list[tuple[Any, int, bool]]:
    """Top-level XML blocks; unmatched layout tables are replaced by their pieces (flagged True)."""
    out: list[tuple[Any, int, bool]] = []
    for n, node in enumerate(main):
        if not isinstance(node.tag, str):
            continue
        if node.tag == "table" and _is_xml_layout_table(node):
            key = _xml_key(node)
            if key and index.find("table", key, 0) is None:
                out.extend((piece, n, True) for piece in layout_pieces(node, _is_xml_layout_table))
                continue
        out.append((node, n, False))
    return out


def _drop_chrome(plan: list[_Step]) -> list[_Step]:
    if not any(s.from_layout for s in plan):
        return plan
    main = content_cell([(s.anchor, s.chars) for s in plan if s.anchor is not None])
    return [s for s in plan if not (s.from_layout and is_chrome(s.anchor, main))]


def _source_order(plan: list[_Step]) -> list[_Step]:
    """Stable sort by source position; an unanchored block keeps the position of the block before it."""
    last = -1
    keyed = []
    for i, step in enumerate(plan):
        if step.pos < 0:
            step.pos = last
        last = step.pos
        keyed.append((step.pos, i, step))
    return [s for _, _, s in sorted(keyed, key=lambda t: (t[0], t[1]))]


def _ancestors(el: HtmlElement) -> list[HtmlElement]:
    out = []
    node = el
    while node is not None and is_element(node):
        out.append(node)
        node = node.getparent()
    return out


def _dropped_images(targets: list[HtmlElement], index: DomIndex) -> list[HtmlElement]:
    if not targets:
        return []
    common = _ancestors(targets[0])
    for t in targets[1:]:
        chain = set(_ancestors(t))
        common = [a for a in common if a in chain]
    if not common:
        return []
    region = common[0]
    out = []
    for img in region.iter("img", "amp-img", *_DISPLAY_MATH_TAGS):
        if img in index.used:
            continue
        if tag_of(img) not in ("img", "amp-img") and not _display_math(img):
            continue
        if any(tag_of(a) in ("nav", "aside", "header", "footer") or is_math(a) for a in _ancestors(img)[1:]):
            continue
        out.append(img)
    return sorted(out, key=lambda e: index.order.get(e, 0))


_DISPLAY_MATH_TAGS = ("ezmd-math", "mjx-container", "math")


def _display_math(el: HtmlElement) -> bool:
    """Block-level math Trafilatura drops because it has no paragraph around it: MathJax v2 display scripts
    (captured as `<ezmd-math data-display="block">`), MathJax v3 `<mjx-container display="true">`, and
    `<math display="block">`."""
    tag = tag_of(el)
    if tag == "ezmd-math":
        return bool(el.get("data-display") == "block")
    return str(el.get("display") or "").lower() in (("true",) if tag == "mjx-container" else ("block",))


def _referenced_footnotes(body: HtmlElement, targets: list[HtmlElement], index: DomIndex) -> list[HtmlElement]:
    """Footnote sections outside the extracted article (often a sibling of `<article>`) whose notes are
    referenced from converted blocks; without them the references would dangle."""
    refs = {footnote_target(a) for t in targets for a in t.iter("a")} - {None}
    if not refs:
        return []
    out = []
    for sec in body.iter():
        if not is_element(sec) or sec in index.used or not is_footnote_section(sec):
            continue
        if any(li.get("id") in refs for li in sec.iter("li")):
            out.append(sec)
    return out


def _restore_image(img: HtmlElement, index: DomIndex, b: Builder) -> None:
    if img in index.used:
        return
    if tag_of(img) not in ("img", "amp-img"):
        index.mark(img)
        convert_block(img, b)
        return
    fig = _container(img)
    target = fig if fig is not None and fig not in index.used and tag_of(fig) == "figure" else img
    index.mark(target)
    convert_block(target, b)


def _spans(node: Any, b: Builder, styles: tuple[InlineStyle, ...] = (), href: str | None = None) -> list[InlineSpan]:
    out: list[InlineSpan] = []

    def walk(el: Any, st: tuple[InlineStyle, ...], hr: str | None) -> None:
        if el.text:
            out.append(InlineSpan(text=_WS.sub(" ", el.text), styles=list(st), href=hr))
        for child in el:
            if isinstance(child.tag, str):
                ctag = child.tag
                new_st, new_hr = st, hr
                if ctag == "hi":
                    style = _REND_STYLE.get(child.get("rend") or "")
                    if style is not None and style not in st:
                        new_st = (*st, style)
                elif ctag == "code" and InlineStyle.CODE not in st:
                    new_st = (*st, InlineStyle.CODE)
                elif ctag == "ref" and child.get("target"):
                    new_hr = b.url(str(child.get("target")))
                if ctag == "lb":
                    out.append(InlineSpan(text="\n", styles=list(st), href=hr))
                elif ctag not in ("list", "graphic"):
                    walk(child, new_st, new_hr)
            if child.tail:
                out.append(InlineSpan(text=_WS.sub(" ", child.tail), styles=list(st), href=hr))

    walk(node, styles, href)
    return normalize_spans(out)


def _items(lst: Any, b: Builder) -> list[ListItem]:
    items: list[ListItem] = []
    for it in lst.findall("item"):
        nested = it.find("list")
        children = _items(nested, b) if nested is not None else []
        items.append(
            ListItem(
                spans=_spans(it, b),
                children=children,
                children_ordered=nested is not None and nested.get("rend") == "ol",
            )
        )
    return items


def _xml_block(node: Any, b: Builder, n: int) -> None:
    prov = b.prov(None, fallback=f"article#{n}")
    tag = node.tag
    if tag == "head":
        rend = node.get("rend") or "h2"
        level = int(rend[1]) if len(rend) == 2 and rend[1].isdigit() else 2
        spans = _spans(node, b)
        if spans:
            b.blocks.append(Heading(level=max(1, min(6, level)), spans=spans, provenance=prov))
    elif tag == "p":
        spans = _spans(node, b)
        if spans:
            b.blocks.append(Paragraph(spans=spans, provenance=prov))
    elif tag == "list":
        items = _items(node, b)
        if items:
            b.blocks.append(ListBlock(ordered=node.get("rend") == "ol", items=items, provenance=prov))
    elif tag == "code":
        code = "".join(node.itertext()).strip("\n")
        if code.strip():
            b.blocks.append(CodeBlock(code=code, provenance=prov))
    elif tag == "quote":
        spans = _spans(node, b)
        if spans:
            b.blocks.append(Quote(spans=spans, provenance=prov))
    elif tag == "table":
        _xml_table(node, b, prov, n)
    elif tag == "graphic":
        src = node.get("src") or ""
        if src:
            alt = (node.get("alt") or "").strip()
            if not alt:
                alt = "image"
                b.images_without_alt += 1
            b.blocks.append(Image(ref=b.url(src), alt=alt, provenance=prov))


def _is_xml_layout_table(node: Any) -> bool:
    """The XML side of 5e item 11 for tables Trafilatura keeps but that match no DOM table. With no header cells,
    a table is layout when it has one column; or when its filled cells carry layout signals (block content,
    images, nested tables) and it is a single row, or has at most one filled cell per row; or when every filled
    cell holds block content. A one-row or sparse table of plain values stays a data table."""
    rows = node.findall("row")
    cells = [c for row in rows for c in row.findall("cell")]
    if not cells or any(c.get("role") == "head" for c in cells):
        return False

    def filled(c: Any) -> bool:
        return bool("".join(c.itertext()).strip()) or c.find(".//graphic") is not None

    def signal(c: Any) -> bool:
        return any(ch.tag in ("p", "list", "table", "head", "graphic") for ch in c.iterdescendants())

    if max(len(row.findall("cell")) for row in rows) <= 1:
        return True
    full = [c for c in cells if filled(c)]
    if not full:
        return True
    sparse = all(sum(1 for c in row.findall("cell") if filled(c)) <= 1 for row in rows)
    if len(rows) == 1 or sparse:
        return len(full) <= 1 or any(signal(c) for c in full)
    return all(any(ch.tag in ("p", "list", "table", "head") for ch in c) for c in full)


def _unwrap_xml_table(node: Any, b: Builder, n: int) -> None:
    """Emit a layout table's cells in reading order: inline runs become paragraphs, block children convert."""
    for piece in layout_pieces(node, _is_xml_layout_table):
        _xml_block(piece, b, n)


def _xml_table(node: Any, b: Builder, prov: Any, n: int = 0) -> None:
    if _is_xml_layout_table(node):
        _unwrap_xml_table(node, b, n)
        return
    cells: list[Cell] = []
    rows = node.findall("row")
    n_cols = 0
    header_rows = 0
    for r, row in enumerate(rows):
        row_cells = row.findall("cell")
        if r == header_rows and row_cells and all(c.get("role") == "head" for c in row_cells):
            header_rows += 1
        for c, cell in enumerate(row_cells):
            cells.append(Cell(spans=_spans(cell, b), row=r, col=c, is_header=cell.get("role") == "head"))
        n_cols = max(n_cols, len(row_cells))
    if cells:
        b.blocks.append(Table(cells=cells, n_rows=len(rows), n_cols=n_cols, header_rows=header_rows, provenance=prov))
