"""HTML-to-IR block conversion (part2 5c step 10): headings, paragraphs, nested lists, code with language,
quotes, tables with spans and header rows, figures with captions, images, definition lists, details, math,
footnotes, and embedded-video links. Layout tables are unwrapped (5e item 11)."""

from __future__ import annotations

from intomd.ir import (
    CodeBlock,
    Equation,
    Figure,
    Footnote,
    Heading,
    InlineSpan,
    Link,
    ListBlock,
    ListItem,
    Paragraph,
    Quote,
    Table,
    TableCell,
)
from intomd_converters.web.build import MAX_DEPTH, Builder, code_language
from intomd_converters.web.dom import BLOCK_TAGS, HtmlElement, collapse, is_element, tag_of
from intomd_converters.web.inline import Inline, inline_spans, is_math, tex_of

_SKIP = frozenset({"head", "title", "meta", "base", "br", "hr", "wbr", "area", "map", "param"})
_HEADINGS = {"h1": 1, "h2": 2, "h3": 3, "h4": 4, "h5": 5, "h6": 6}
_FOOTNOTE_CLASSES = frozenset({"footnotes", "footnote-list", "references", "endnotes", "footnotes-list"})
MAX_SPAN = 1000
_LINENO = frozenset({"lineno", "linenos", "ln", "line-number", "linenumber"})


def is_footnote_section(el: HtmlElement) -> bool:
    role = (el.get("role") or "").lower()
    classes = set((el.get("class") or "").lower().split())
    return role == "doc-endnotes" or (bool(classes & _FOOTNOTE_CLASSES) and el.find(".//li[@id]") is not None)


def register_footnotes(root: HtmlElement, b: Builder) -> None:
    """Map footnote target ids to Footnote block ids before conversion so references can point at them."""
    for sec in root.iter():
        if is_element(sec) and is_footnote_section(sec):
            for n, li in enumerate(sec.iter("li"), start=1):
                if li.get("id"):
                    b.footnote_ids[li.get("id")] = f"fn-{n}"


def convert_children(el: HtmlElement, b: Builder, depth: int = 0) -> None:
    """Convert a container: runs of inline content become paragraphs; block children convert recursively."""
    acc = Inline(b)
    acc.add_text(el.text or "", (), None)
    for child in el:
        if is_element(child) and _is_block(child):
            _flush(acc, el, b)
            acc = Inline(b)
            convert_block(child, b, depth + 1)
        elif is_element(child):
            acc.child(child, (), None, 0)
        acc.add_text(child.tail or "", (), None)
    _flush(acc, el, b)


def _is_block(el: HtmlElement) -> bool:
    tag = tag_of(el)
    if tag in BLOCK_TAGS or (tag in ("img", "amp-img") and el.getparent() is not None and _is_alone(el)):
        return True
    return tag in _SKIP


def _is_alone(img: HtmlElement) -> bool:
    """An image that is the only content of its container is a block image, not an inline one."""
    parent = img.getparent()
    return tag_of(parent) not in ("p", "a", "span", "li", "td", "th") and not collapse(parent.text_content() or "")


def _flush(acc: Inline, el: HtmlElement, b: Builder) -> None:
    spans = acc.finish()
    if spans and "".join(s.text for s in spans).strip():
        b.blocks.append(Paragraph(spans=spans, provenance=b.prov(el)))
    b.blocks.extend(acc.images)


def convert_block(el: HtmlElement, b: Builder, depth: int = 0) -> None:
    tag = tag_of(el)
    if tag in _SKIP:
        return
    if depth > MAX_DEPTH:
        text = collapse(el.text_content() or "")
        if text:
            b.blocks.append(Paragraph(spans=[InlineSpan(text=text)], provenance=b.prov(el)))
        return
    if tag in _HEADINGS:
        spans, images = inline_spans(el, b)
        if spans:
            b.blocks.append(Heading(level=_HEADINGS[tag], spans=spans, provenance=b.prov(el)))
        b.blocks.extend(images)
    elif tag == "p":
        _flush_el(el, b)
    elif tag in ("ul", "ol", "menu"):
        _list(el, b)
    elif tag == "pre":
        _code(el, b)
    elif tag == "blockquote":
        _quote(el, b)
    elif tag == "table":
        _table(el, b, depth)
    elif tag == "figure":
        _figure(el, b, depth)
    elif tag in ("img", "amp-img"):
        img = b.image(el)
        if img is not None:
            b.blocks.append(img)
    elif tag == "picture":
        inner = el.find(".//img")
        img = b.image(inner) if inner is not None else None
        if img is not None:
            b.blocks.append(img)
    elif tag == "dl":
        _definition_list(el, b)
    elif tag == "details":
        _details(el, b, depth)
    elif tag == "intomd-link":
        href = el.get("href") or ""
        b.blocks.append(Link(href=b.url(href), text=el.get("title") or None, rel="embed", provenance=b.prov(el)))
    elif is_math(el) and tag != "span":
        _equation(el, b)
    elif is_footnote_section(el):
        _footnotes(el, b)
    else:
        convert_children(el, b, depth)


def _flush_el(el: HtmlElement, b: Builder) -> None:
    spans, images = inline_spans(el, b)
    if spans and "".join(s.text for s in spans).strip():
        b.blocks.append(Paragraph(spans=spans, provenance=b.prov(el)))
    b.blocks.extend(images)


def _item(li: HtmlElement, b: Builder, depth: int) -> ListItem:
    acc = Inline(b)
    acc.add_text(li.text or "", (), None)
    children: list[ListItem] = []
    ordered: bool | None = None
    start = 1
    for child in li:
        if is_element(child) and tag_of(child) in ("ul", "ol") and depth < MAX_DEPTH:
            if ordered is None:
                ordered = tag_of(child) == "ol"
                start = _start(child)
            children.extend(_item(c, b, depth + 1) for c in child if is_element(c) and tag_of(c) == "li")
        elif is_element(child):
            acc.child(child, (), None, 0)
        acc.add_text(child.tail or "", (), None)
    b.blocks.extend(acc.images)
    return ListItem(
        spans=acc.finish(),
        children=children,
        children_ordered=bool(ordered),
        children_start=start,
        provenance=b.prov(li),
    )


def _start(el: HtmlElement) -> int:
    raw = (el.get("start") or "1").strip()
    return int(raw) if raw.lstrip("-").isdigit() and abs(int(raw)) < 1_000_000 else 1


def _list(el: HtmlElement, b: Builder) -> None:
    pos = len(b.blocks)
    items = [_item(li, b, 1) for li in el if is_element(li) and tag_of(li) == "li"]
    items = [it for it in items if it.spans or it.children]
    if not items:
        return
    block = ListBlock(ordered=tag_of(el) == "ol", start=_start(el), items=items, provenance=b.prov(el))
    b.blocks.insert(pos, block)


def _code(el: HtmlElement, b: Builder) -> None:
    for junk in list(el.iter()):
        if is_element(junk) and set((junk.get("class") or "").split()) & _LINENO and junk.getparent() is not None:
            junk.drop_tree()
    code = (el.text_content() or "").replace("\r\n", "\n").strip("\n")
    if code.strip():
        b.blocks.append(CodeBlock(code=code, language=code_language(el), provenance=b.prov(el)))


def _quote(el: HtmlElement, b: Builder) -> None:
    attribution: str | None = None
    parts: list[list[InlineSpan]] = []
    acc = Inline(b)
    acc.add_text(el.text or "", (), None)
    for child in el:
        tag = tag_of(child) if is_element(child) else ""
        if tag in ("footer", "cite") and child.getnext() is None:
            attribution = collapse(child.text_content() or "").lstrip("-— ") or None
        elif tag in ("p", "div", "blockquote", "ul", "ol", "pre"):
            parts.append(acc.finish())
            acc = Inline(b)
            acc.walk(child)
            parts.append(acc.finish())
            acc = Inline(b)
        elif tag:
            acc.child(child, (), None, 0)
        acc.add_text(child.tail or "", (), None)
    parts.append(acc.finish())
    b.blocks.extend(acc.images)
    spans: list[InlineSpan] = []
    for p in (p for p in parts if p):
        if spans:
            spans.append(InlineSpan(text="\n\n"))
        spans.extend(p)
    if spans:
        b.blocks.append(Quote(spans=spans, attribution=attribution, provenance=b.prov(el)))


def _rows(table: HtmlElement) -> list[tuple[HtmlElement, bool]]:
    rows: list[tuple[HtmlElement, bool]] = []
    for child in table:
        tag = tag_of(child) if is_element(child) else ""
        if tag == "tr":
            rows.append((child, False))
        elif tag in ("thead", "tbody", "tfoot"):
            rows.extend((tr, tag == "thead") for tr in child if is_element(tr) and tag_of(tr) == "tr")
    return rows


def _cells(tr: HtmlElement) -> list[HtmlElement]:
    return [c for c in tr if is_element(c) and tag_of(c) in ("td", "th")]


def _span(el: HtmlElement, attr: str) -> int:
    raw = (el.get(attr) or "1").strip()
    return max(1, min(MAX_SPAN, int(raw))) if raw.isdigit() else 1


def is_layout_table(table: HtmlElement) -> bool:
    """Tables used for page layout: role=presentation, or no header cells and either one column or block
    content (paragraphs, lists, nested tables) in every non-empty cell (5e item 11)."""
    if (table.get("role") or "").lower() in ("presentation", "none"):
        return True
    rows = _rows(table)
    if not rows:
        return True
    if any(tag_of(c) == "th" for tr, _ in rows for c in _cells(tr)):
        return False
    widths = [sum(_span(c, "colspan") for c in _cells(tr)) for tr, _ in rows]
    if max(widths, default=0) <= 1:
        return True
    filled = [c for tr, _ in rows for c in _cells(tr) if collapse(c.text_content() or "")]
    blocky = ("p", "div", "table", "ul", "ol", "h1", "h2", "h3", "h4", "pre", "blockquote")
    return bool(filled) and all(any(d.tag in blocky for d in c.iterdescendants()) for c in filled)


def _table(el: HtmlElement, b: Builder, depth: int) -> None:
    if is_layout_table(el):
        for tr, _ in _rows(el):
            for cell in _cells(tr):
                convert_children(cell, b, depth + 1)
        return
    rows = _rows(el)
    occupied: set[tuple[int, int]] = set()
    cells: list[TableCell] = []
    n_cols = 0
    header_rows = 0
    counting_header = True
    for r, (tr, in_thead) in enumerate(rows):
        c = 0
        row_cells = _cells(tr)
        all_th = bool(row_cells) and all(tag_of(x) == "th" for x in row_cells)
        if counting_header and (in_thead or all_th):
            header_rows += 1
        else:
            counting_header = False
        for cell in row_cells:
            while (r, c) in occupied:
                c += 1
            rs = min(_span(cell, "rowspan"), len(rows) - r)
            cs = _span(cell, "colspan")
            for dr in range(rs):
                for dc in range(cs):
                    occupied.add((r + dr, c + dc))
            spans, _imgs = inline_spans(cell, b)
            cells.append(
                TableCell(
                    spans=spans,
                    row=r,
                    col=c,
                    row_span=rs,
                    col_span=cs,
                    is_header=tag_of(cell) == "th" or in_thead,
                )
            )
            c += cs
        n_cols = max(n_cols, c, *(cc + 1 for rr, cc in occupied if rr == r))
    if not cells:
        return
    caption_el = el.find("caption")
    caption = inline_spans(caption_el, b)[0] if caption_el is not None else None
    b.blocks.append(
        Table(
            cells=cells,
            n_rows=len(rows),
            n_cols=n_cols,
            caption=caption or None,
            header_rows=header_rows,
            provenance=b.prov(el),
        )
    )


def _figure(el: HtmlElement, b: Builder, depth: int) -> None:
    cap_el = el.find("figcaption")
    caption = inline_spans(cap_el, b)[0] if cap_el is not None else []
    imgs = list(el.iter("img", "amp-img"))
    others = [c for c in el if is_element(c) and tag_of(c) in ("table", "pre", "blockquote")]
    if not imgs and not others:
        convert_children(el, b, depth)
        return
    b.figures += 1
    fid = f"fig-{b.figures}"
    b.blocks.append(Figure(id=fid, provenance=b.prov(el)))
    for img_el in imgs:
        img = b.image(img_el, parent=fid, captioned=bool(caption))
        if img is not None:
            b.blocks.append(img)
    for other in others:
        start = len(b.blocks)
        convert_block(other, b, depth + 1)
        for blk in b.blocks[start:]:
            blk.parent_id = fid
    if caption:
        b.blocks.append(Paragraph(spans=caption, role="caption", parent_id=fid, provenance=b.prov(cap_el)))


def _definition_list(el: HtmlElement, b: Builder) -> None:
    """`<dl>` as a ListBlock with attrs kind=definition: one item per term, one child per definition."""
    items: list[ListItem] = []
    for child in el.iter("dt", "dd"):
        spans = inline_spans(child, b)[0]
        if tag_of(child) == "dt":
            items.append(ListItem(spans=spans, provenance=b.prov(child)))
        elif items and spans:
            items[-1].children.append(ListItem(spans=spans, provenance=b.prov(child)))
        elif spans:
            items.append(ListItem(spans=[], children=[ListItem(spans=spans, provenance=b.prov(child))]))
    if items:
        b.blocks.append(ListBlock(items=items, attrs={"kind": "definition"}, provenance=b.prov(el)))


def _details(el: HtmlElement, b: Builder, depth: int) -> None:
    summary = el.find("summary")
    if summary is not None:
        level = next((blk.level for blk in reversed(b.blocks) if isinstance(blk, Heading)), 1)
        spans = inline_spans(summary, b)[0]
        if spans:
            b.blocks.append(Heading(level=min(6, level + 1), spans=spans, provenance=b.prov(summary)))
    for child in el:
        if child is summary:
            continue
        if is_element(child):
            convert_block(child, b, depth + 1)
        tail = collapse(child.tail or "")
        if tail:
            b.blocks.append(Paragraph(spans=[InlineSpan(text=tail)], provenance=b.prov(el)))


def _equation(el: HtmlElement, b: Builder) -> None:
    tex = el.get("data-latex") if tag_of(el) == "intomd-math" else tex_of(el)
    text = collapse(el.text_content() or "") or None
    if tex or text:
        b.blocks.append(Equation(latex=tex, text=None if tex else text, provenance=b.prov(el)))


def _footnotes(el: HtmlElement, b: Builder) -> None:
    for n, li in enumerate(el.iter("li"), start=1):
        for back in list(li.iter("a")):
            role = (back.get("role") or "").lower()
            classes = (back.get("class") or "").lower()
            if role == "doc-backlink" or "footnote-back" in classes or "backref" in classes or back.text in ("↩",):
                back.drop_tree()
        spans = inline_spans(li, b)[0]
        if spans:
            fid = b.footnote_ids.get(li.get("id") or "", f"fn-{n}")
            b.blocks.append(Footnote(id=fid, marker=str(n), spans=spans, provenance=b.prov(li)))
