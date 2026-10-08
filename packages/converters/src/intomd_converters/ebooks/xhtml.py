"""ebooks.xhtml: a small, safe XHTML/HTML-to-IR walker for EPUB chapters and notebook HTML outputs.

The spec routes EPUB chapters through section 5's shared HTML-to-IR module; that module is built in parallel
(P1-T02), so this walker covers what ebooks need (headings, paragraphs, lists, tables with spans, code,
quotes, images, figures, EPUB footnotes and page breaks) and can be swapped for the shared module later.

Parsing never touches the network or resolves entities (docs/spec/part1.md 8.2): lxml's XML parser runs
with `resolve_entities=False, no_network=True, load_dtd=False, huge_tree=False`; documents that are not
well-formed XML (HTML entities such as `&nbsp;`, unclosed tags) fall back to lxml's HTML parser with
`no_network=True`. Scripts, styles, `<nav>`, and hidden elements are dropped; hidden ones are counted.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from lxml import etree, html  # type: ignore[import-untyped]

from intomd.core.textclean import CleanStats, clean_text
from intomd.ir import (
    Block,
    CodeBlock,
    Equation,
    Footnote,
    Heading,
    Image,
    InlineSpan,
    InlineStyle,
    ListBlock,
    ListItem,
    PageBreak,
    Paragraph,
    Provenance,
    Quote,
    Table,
    TableCell,
)

EPUB_NS = "http://www.idpf.org/2007/ops"
_WS = re.compile(r"[ \t\n\r\f\v]+")
_HIDDEN_STYLE = re.compile(r"display\s*:\s*none|visibility\s*:\s*hidden", re.IGNORECASE)
_MAX_SPAN = 1000

SKIP_TAGS = frozenset(
    {"script", "style", "noscript", "template", "head", "title", "meta", "link", "nav", "iframe", "object",
     "embed", "button", "input", "select", "textarea", "form", "svg", "canvas", "audio", "video", "source"}
)  # fmt: skip
BLOCK_TAGS = frozenset(
    {"p", "div", "section", "article", "aside", "header", "footer", "main", "h1", "h2", "h3", "h4", "h5", "h6",
     "ul", "ol", "li", "pre", "blockquote", "table", "figure", "figcaption", "hr", "dl", "dt", "dd", "address",
     "hgroup", "details", "summary", "body", "html", "center", "math", "nav", "caption"}
)  # fmt: skip
STYLE_TAGS: dict[str, InlineStyle] = {
    "em": InlineStyle.ITALIC,
    "i": InlineStyle.ITALIC,
    "cite": InlineStyle.ITALIC,
    "dfn": InlineStyle.ITALIC,
    "var": InlineStyle.ITALIC,
    "strong": InlineStyle.BOLD,
    "b": InlineStyle.BOLD,
    "code": InlineStyle.CODE,
    "kbd": InlineStyle.CODE,
    "samp": InlineStyle.CODE,
    "tt": InlineStyle.CODE,
    "s": InlineStyle.STRIKE,
    "strike": InlineStyle.STRIKE,
    "del": InlineStyle.STRIKE,
    "u": InlineStyle.UNDERLINE,
    "ins": InlineStyle.UNDERLINE,
    "sup": InlineStyle.SUPERSCRIPT,
    "sub": InlineStyle.SUBSCRIPT,
}
FOOTNOTE_TYPES = frozenset({"footnote", "endnote", "rearnote", "note"})
FOOTNOTE_ROLES = frozenset({"doc-footnote", "doc-endnote"})

ImageResolver = Callable[[str, str | None], Image | None]
"""(src attribute, alt) -> Image block (without provenance), or None to drop the image."""
LinkResolver = Callable[[str], str | None]
"""href attribute -> footnote block id when the link is a note reference, else None."""


def parse_document(data: bytes, *, html_mode: bool = False) -> Any:
    """Parse XHTML (or HTML when `html_mode`) safely. Returns the root element, or None when unparseable."""
    if not html_mode:
        parser = etree.XMLParser(
            resolve_entities=False,
            no_network=True,
            load_dtd=False,
            huge_tree=False,
            recover=True,
            remove_comments=True,
            remove_pis=True,
        )
        try:
            root = etree.fromstring(data, parser)
        except etree.XMLSyntaxError:
            root = None
        if root is not None and not len(parser.error_log):
            return root
    hparser = html.HTMLParser(no_network=True, remove_comments=True, remove_pis=True, huge_tree=False)
    try:
        return html.document_fromstring(data, parser=hparser)
    except (etree.ParserError, etree.XMLSyntaxError, ValueError):
        return None


def local(el: Any) -> str:
    tag = el.tag
    if not isinstance(tag, str):
        return ""
    return tag.rsplit("}", 1)[-1].lower()


def epub_types(el: Any) -> set[str]:
    """Values of `epub:type` (namespaced in XHTML, a literal `epub:type` attribute after an HTML parse)."""
    raw = el.get(f"{{{EPUB_NS}}}type") or el.get("epub:type") or ""
    return set(raw.split())


def is_footnote_el(el: Any) -> bool:
    return bool(epub_types(el) & FOOTNOTE_TYPES) or (el.get("role") or "") in FOOTNOTE_ROLES


def is_noteref_el(el: Any) -> bool:
    return "noteref" in epub_types(el) or (el.get("role") or "") == "doc-noteref"


def find_body(root: Any) -> Any:
    for el in root.iter():
        if local(el) == "body":
            return el
    return root


@dataclass(slots=True)
class WalkContext:
    source: str
    path: str | None = None
    """Container-relative path (EPUB `OEBPS/ch1.xhtml`, notebook `cells[3].outputs[0]`)."""
    stats: CleanStats = field(default_factory=CleanStats)
    resolve_image: ImageResolver | None = None
    resolve_noteref: LinkResolver | None = None
    footnote_id: Callable[[str], str | None] | None = None
    """Element id -> footnote block id when this element is a known footnote body."""
    footnote_marker: Callable[[str], str] | None = None
    page_ids: dict[str, str] = field(default_factory=dict)
    """Element id -> print page label (EPUB page-list)."""
    page: str | None = None
    hidden_removed: int = 0
    _pending: list[Block] = field(default_factory=list)

    def prov(self, anchor: str | None) -> Provenance:
        path = self.path
        if path is not None and anchor:
            path = f"{path}#{anchor}"
        page_no = int(self.page) if self.page is not None and self.page.isdigit() else None
        label = self.page if self.page is not None and page_no is None else None
        return Provenance(source=self.source, path=path, source_page=page_no, page_label=label)


class Walker:
    """Converts a parsed (X)HTML body into IR blocks."""

    def __init__(self, ctx: WalkContext) -> None:
        self.ctx = ctx

    # ---------------------------------------------------------------- blocks

    def blocks(self, el: Any, anchor: str | None = None) -> list[Block]:
        out: list[Block] = []
        self._container(el, anchor, out)
        self._flush_pending(out)
        return out

    def _hidden(self, el: Any) -> bool:
        if el.get("hidden") is not None or (el.get("aria-hidden") or "").lower() == "true":
            return True
        return bool(_HIDDEN_STYLE.search(el.get("style") or ""))

    def _container(self, el: Any, anchor: str | None, out: list[Block]) -> None:
        """Walk mixed content: inline runs become paragraphs, block children are walked recursively."""
        buf: list[InlineSpan] = []
        anchor = el.get("id") or anchor
        self._text(el.text, [], None, buf)
        for child in el:
            tag = local(child)
            if not tag:
                self._text(child.tail, [], None, buf)
                continue
            if tag in BLOCK_TAGS or (tag == "img" and not buf_has_text(buf)):
                self._para(buf, anchor, out)
                buf = []
                self._block(child, anchor, out)
            else:
                self._inline(child, [], None, buf)
            self._text(child.tail, [], None, buf)
        self._para(buf, anchor, out)

    def _block(self, el: Any, anchor: str | None, out: list[Block]) -> None:
        tag = local(el)
        if tag in SKIP_TAGS:
            return
        if self._hidden(el):
            self.ctx.hidden_removed += 1
            return
        self._page_marker(el, out)
        own = el.get("id")
        here = own or anchor
        if own and is_footnote_el(el) and self.ctx.footnote_id is not None:
            fid = self.ctx.footnote_id(own)
            if fid is not None:
                self._footnote(el, fid, here, out)
                return
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            spans = self._spans(el)
            if spans:
                out.append(Heading(level=int(tag[1]), spans=spans, provenance=self.ctx.prov(here)))
            self._flush_pending(out)
        elif tag == "p" or tag in ("dt", "dd", "address", "summary", "figcaption", "caption"):
            spans = self._spans(el, styles=[InlineStyle.BOLD] if tag == "dt" else [])
            role = "caption" if tag in ("figcaption", "caption") else "body"
            if spans:
                out.append(Paragraph(spans=spans, role=role, provenance=self.ctx.prov(here)))
            self._flush_pending(out)
        elif tag in ("ul", "ol"):
            items = self._list_items(el)
            if items:
                out.append(
                    ListBlock(
                        ordered=tag == "ol", start=_int(el.get("start"), 1), items=items, provenance=self.ctx.prov(here)
                    )
                )
            self._flush_pending(out)
        elif tag == "pre":
            code = clean_text("".join(el.itertext()), self.ctx.stats).strip("\n")
            if code.strip():
                out.append(CodeBlock(code=code, language=_language(el), provenance=self.ctx.prov(here)))
        elif tag == "blockquote":
            parts = [self._spans(p) for p in el if local(p) in BLOCK_TAGS]
            spans = _join_paragraphs([p for p in parts if p]) if parts else self._spans(el)
            if spans:
                out.append(Quote(spans=spans, provenance=self.ctx.prov(here)))
            self._flush_pending(out)
        elif tag == "table":
            table = self._table(el, here)
            if table is not None:
                out.append(table)
            self._flush_pending(out)
        elif tag == "img":
            self._image(el)
            self._flush_pending(out, here)
        elif tag == "figure":
            self._figure(el, here, out)
        elif tag == "math":
            text = el.get("alttext") or clean_text(" ".join("".join(el.itertext()).split()), self.ctx.stats)
            if text:
                out.append(Equation(text=text, provenance=self.ctx.prov(here)))
        elif tag == "hr":
            return
        else:
            self._container(el, here, out)

    def _page_marker(self, el: Any, out: list[Block]) -> None:
        own = el.get("id")
        if own and own in self.ctx.page_ids:
            label = self.ctx.page_ids[own]
            self.ctx.page = label
            if label.isdigit():
                out.append(PageBreak(page_number=int(label), provenance=self.ctx.prov(own)))

    def _flush_pending(self, out: list[Block], anchor: str | None = None) -> None:
        for b in self.ctx._pending:
            if isinstance(b, Image):
                here = self.ctx.prov(anchor)
                if b.provenance.path is None and self.ctx.path is not None:
                    b.provenance = here
                elif b.provenance.source_page is None and b.provenance.page_label is None:
                    b.provenance = b.provenance.model_copy(
                        update={"source_page": here.source_page, "page_label": here.page_label}
                    )
            out.append(b)
        self.ctx._pending.clear()

    def _para(self, buf: list[InlineSpan], anchor: str | None, out: list[Block]) -> None:
        spans = _strip(buf)
        if spans:
            out.append(Paragraph(spans=spans, provenance=self.ctx.prov(anchor)))
        self._flush_pending(out, anchor)

    def _footnote(self, el: Any, fid: str, anchor: str | None, out: list[Block]) -> None:
        parts: list[list[InlineSpan]] = []
        for child in el:
            if local(child) in BLOCK_TAGS:
                parts.append(self._spans(child, skip_backlinks=True))
        spans = _join_paragraphs([p for p in parts if p]) if parts else self._spans(el, skip_backlinks=True)
        marker = self.ctx.footnote_marker(fid) if self.ctx.footnote_marker else fid
        out.append(Footnote(id=fid, marker=marker, spans=spans, provenance=self.ctx.prov(anchor)))
        self.ctx._pending.clear()

    def _figure(self, el: Any, anchor: str | None, out: list[Block]) -> None:
        caption: list[InlineSpan] = []
        for child in el:
            tag = local(child)
            if tag == "figcaption":
                caption = self._spans(child)
            elif tag == "img":
                self._image(child)
            elif tag:
                self._block(child, anchor, out)
        images = [b for b in self.ctx._pending if isinstance(b, Image)]
        if images and caption:
            images[-1].caption = caption
            caption = []
        self._flush_pending(out, anchor)
        if caption:
            out.append(Paragraph(spans=caption, role="caption", provenance=self.ctx.prov(anchor)))

    def _image(self, el: Any) -> None:
        if self.ctx.resolve_image is None:
            return
        src = el.get("src") or el.get("{http://www.w3.org/1999/xlink}href") or ""
        alt = el.get("alt")
        alt = clean_text(" ".join(alt.split()), self.ctx.stats) if alt else None
        img = self.ctx.resolve_image(src, alt or None)
        if img is not None:
            self.ctx._pending.append(img)

    # ---------------------------------------------------------------- lists and tables

    def _list_items(self, el: Any) -> list[ListItem]:
        items: list[ListItem] = []
        for li in el:
            if local(li) != "li":
                continue
            if self._hidden(li):
                self.ctx.hidden_removed += 1
                continue
            spans = self._spans(li, skip_tags=frozenset({"ul", "ol"}))
            sub = next((c for c in li if local(c) in ("ul", "ol")), None)
            children = self._list_items(sub) if sub is not None else []
            item = ListItem(spans=spans, children=children)
            if sub is not None:
                item.children_ordered = local(sub) == "ol"
                item.children_start = _int(sub.get("start"), 1)
            items.append(item)
        return items

    def _table(self, el: Any, anchor: str | None) -> Table | None:
        rows: list[tuple[Any, bool]] = []
        caption: list[InlineSpan] | None = None
        for child in el:
            tag = local(child)
            if tag == "tr":
                rows.append((child, False))
            elif tag in ("thead", "tbody", "tfoot"):
                rows.extend((tr, tag == "thead") for tr in child if local(tr) == "tr")
            elif tag == "caption":
                caption = self._spans(child) or None
        if not rows:
            return None
        cells: list[TableCell] = []
        occupied: set[tuple[int, int]] = set()
        n_cols = 0
        header_rows = 0
        header_run = True
        for r, (tr, in_head) in enumerate(rows):
            col = 0
            tds = [c for c in tr if local(c) in ("td", "th")]
            all_th = bool(tds) and all(local(c) == "th" for c in tds)
            if header_run and (in_head or all_th):
                header_rows += 1
            else:
                header_run = False
            for td in tds:
                while (r, col) in occupied:
                    col += 1
                rs = min(_int(td.get("rowspan"), 1), len(rows) - r, _MAX_SPAN)
                cs = min(_int(td.get("colspan"), 1), _MAX_SPAN)
                for dr in range(rs):
                    for dc in range(cs):
                        occupied.add((r + dr, col + dc))
                cells.append(
                    TableCell(
                        spans=self._spans(td),
                        row=r,
                        col=col,
                        row_span=rs,
                        col_span=cs,
                        is_header=local(td) == "th" or in_head,
                    )
                )
                col += cs
            n_cols = max(n_cols, col)
        n_cols = max([n_cols, *(c + 1 for _r, c in occupied)]) if occupied else n_cols
        if n_cols == 0:
            return None
        table = Table(
            cells=cells,
            n_rows=len(rows),
            n_cols=n_cols,
            caption=caption,
            header_rows=header_rows,
            provenance=self.ctx.prov(anchor),
        )
        return table

    # ---------------------------------------------------------------- inline

    def _spans(
        self,
        el: Any,
        *,
        styles: list[InlineStyle] | None = None,
        skip_tags: frozenset[str] = frozenset(),
        skip_backlinks: bool = False,
    ) -> list[InlineSpan]:
        buf: list[InlineSpan] = []
        st = list(styles or [])
        self._text(el.text, st, None, buf)
        for child in el:
            tag = local(child)
            if tag and tag not in skip_tags:
                if tag in BLOCK_TAGS and buf_has_text(buf):
                    _push(buf, " ", st, None)
                self._inline(child, st, None, buf, skip_tags=skip_tags, skip_backlinks=skip_backlinks)
            self._text(child.tail, st, None, buf)
        return _strip(buf)

    def _inline(
        self,
        el: Any,
        styles: list[InlineStyle],
        href: str | None,
        buf: list[InlineSpan],
        *,
        skip_tags: frozenset[str] = frozenset(),
        skip_backlinks: bool = False,
    ) -> None:
        tag = local(el)
        if not tag or tag in SKIP_TAGS or tag in skip_tags:
            return
        if self._hidden(el):
            self.ctx.hidden_removed += 1
            return
        own = el.get("id")
        if own and own in self.ctx.page_ids:
            label = self.ctx.page_ids[own]
            self.ctx.page = label
            if label.isdigit():
                self.ctx._pending.append(PageBreak(page_number=int(label), provenance=self.ctx.prov(own)))
        if tag == "br":
            _push(buf, "\n", styles, href)
            return
        if tag == "img":
            self._image(el)
            return
        st = [*styles, STYLE_TAGS[tag]] if tag in STYLE_TAGS else styles
        link = href
        if tag == "a":
            target = el.get("href") or ""
            if is_noteref_el(el):
                fid = self.ctx.resolve_noteref(target) if self.ctx.resolve_noteref else None
                if fid is not None:
                    marker = self.ctx.footnote_marker(fid) if self.ctx.footnote_marker else fid
                    buf.append(InlineSpan(text=f"[^{marker}]", footnote_ref=fid))
                    return
            if skip_backlinks and ("backlink" in epub_types(el) or (el.get("role") or "") == "doc-backlink"):
                return
            if target and not target.startswith("#"):
                link = target
        self._text(el.text, st, link, buf)
        for child in el:
            self._inline(child, st, link, buf, skip_tags=skip_tags, skip_backlinks=skip_backlinks)
            self._text(child.tail, st, link, buf)

    def _text(self, text: str | None, styles: list[InlineStyle], href: str | None, buf: list[InlineSpan]) -> None:
        if not text:
            return
        cleaned = clean_text(text, self.ctx.stats)
        _push(buf, _WS.sub(" ", cleaned), styles, href)


def buf_has_text(buf: list[InlineSpan]) -> bool:
    return any(s.text.strip() for s in buf)


def _push(buf: list[InlineSpan], text: str, styles: list[InlineStyle], href: str | None) -> None:
    if not text:
        return
    st = sorted(set(styles), key=list(InlineStyle).index)
    if buf and buf[-1].styles == st and buf[-1].href == href and buf[-1].footnote_ref is None:
        prev = buf[-1].text
        if prev.endswith((" ", "\n")) and text.startswith(" "):
            text = text.lstrip(" ")
        buf[-1] = InlineSpan(text=prev + text, styles=st, href=href)
        return
    if buf and text.startswith(" ") and buf[-1].text.endswith((" ", "\n")):
        text = text.lstrip(" ")
        if not text:
            return
    buf.append(InlineSpan(text=text, styles=st, href=href))


def _strip(buf: list[InlineSpan]) -> list[InlineSpan]:
    out = [s for s in buf if s.text]
    while out and not out[0].text.strip() and out[0].footnote_ref is None:
        out.pop(0)
    while out and not out[-1].text.strip() and out[-1].footnote_ref is None:
        out.pop()
    if not out:
        return []
    out[0] = out[0].model_copy(update={"text": out[0].text.lstrip()})
    out[-1] = out[-1].model_copy(update={"text": out[-1].text.rstrip()})
    out = [s.model_copy(update={"text": s.text.replace(" \n", "\n").replace("\n ", "\n")}) for s in out]
    return [s for s in out if s.text]


def _join_paragraphs(parts: list[list[InlineSpan]]) -> list[InlineSpan]:
    out: list[InlineSpan] = []
    for i, p in enumerate(parts):
        if i:
            out.append(InlineSpan(text="\n\n"))
        out.extend(p)
    return out


def _int(value: str | None, default: int) -> int:
    try:
        n = int(value) if value is not None else default
    except ValueError:
        return default
    return n if n >= 1 else default


def _language(el: Any) -> str | None:
    classes = (el.get("class") or "").split()
    code = next((c for c in el if local(c) == "code"), None)
    if code is not None:
        classes += (code.get("class") or "").split()
    for c in classes:
        if c.startswith(("language-", "lang-")):
            return c.split("-", 1)[1] or None
    return None
