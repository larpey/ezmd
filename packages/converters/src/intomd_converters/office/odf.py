"""documents.odf: native OpenDocument converter (ODT, ODS, ODP) over content.xml with the hardened parser.

Part 2 2b names a native `content.xml` parser as the no-LibreOffice path for ODT; it is the default here
because it keeps structure and needs no external process: headings (`text:h` outline level), paragraphs with
spans and links, lists (ordered from the list style), tables with spans, footnotes and endnotes, comments
(`office:annotation`), tracked changes (`text:tracked-changes`), images and text boxes. ODS sheets reuse the
XLSX table builder; ODP pages become Slide blocks with notes. Macros (`Basic/`, `Scripts/`) are removed by
the package sanitizer before parsing.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from lxml import etree  # type: ignore[import-untyped]

from intomd.context import Limits
from intomd.core.textclean import CleanStats, clean_text
from intomd.inputs import InputRef
from intomd.ir import (
    Block,
    Comment,
    Document,
    Footnote,
    Heading,
    Image,
    InlineSpan,
    InlineStyle,
    ListBlock,
    ListItem,
    Metadata,
    Paragraph,
    Provenance,
    Quote,
    Slide,
    SourceType,
    Table,
    TableCell,
    TrackedChange,
    Warning,
    WarningKind,
    spans_text,
)
from intomd.registry import ConversionError, ConvertOptions
from intomd_converters.office._common import (
    FAMILY,
    MB,
    ODF_EXTS,
    ODF_MIMES,
    BlockList,
    OfficeOptions,
    SpanBuilder,
    check_size,
    clean_warning,
    confidence,
    parse_datetime,
    safe_href,
)
from intomd_converters.office._ooxml_ns import local, ns_of
from intomd_converters.office._package import OfficePackage
from intomd_converters.office.xlsx import SheetStats, sheet_table, sheet_warnings
from intomd_converters.office.xlsx_cells import XCell, regions

OFFICE = "urn:oasis:names:tc:opendocument:xmlns:office:1.0"
TEXT = "urn:oasis:names:tc:opendocument:xmlns:text:1.0"
TABLE = "urn:oasis:names:tc:opendocument:xmlns:table:1.0"
DRAW = "urn:oasis:names:tc:opendocument:xmlns:drawing:1.0"
STYLE = "urn:oasis:names:tc:opendocument:xmlns:style:1.0"
FO = "urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0"
XLINK = "http://www.w3.org/1999/xlink"
DC = "http://purl.org/dc/elements/1.1/"
META = "urn:oasis:names:tc:opendocument:xmlns:meta:1.0"
PRES = "urn:oasis:names:tc:opendocument:xmlns:presentation:1.0"
SVG = "urn:oasis:names:tc:opendocument:xmlns:svg-compatible:1.0"

_MAX_DEPTH = 16
_MAX_REPEAT = 1024


def t(ns: str, name: str) -> str:
    return f"{{{ns}}}{name}"


@dataclass(slots=True)
class _TextStyle:
    bold: bool = False
    italic: bool = False
    strike: bool = False
    sup: bool = False
    sub: bool = False
    hidden: bool = False
    mono: bool = False


@dataclass(slots=True)
class _Styles:
    text: dict[str, _TextStyle] = field(default_factory=dict)
    parent: dict[str, str] = field(default_factory=dict)
    display: dict[str, str] = field(default_factory=dict)
    lists: dict[str, dict[int, bool]] = field(default_factory=dict)
    hidden_tables: set[str] = field(default_factory=set)

    def load(self, root: etree._Element | None) -> None:
        if root is None:
            return
        for st in root.iter(t(STYLE, "style")):
            name = st.get(t(STYLE, "name")) or ""
            parent = st.get(t(STYLE, "parent-style-name"))
            if parent:
                self.parent[name] = parent
            self.display[name] = st.get(t(STYLE, "display-name")) or name.replace("_20_", " ")
            tp = st.find(t(STYLE, "text-properties"))
            if tp is not None:
                pos = (tp.get(t(STYLE, "text-position")) or "").split()
                font = (tp.get(t(STYLE, "font-name")) or tp.get(t(FO, "font-family")) or "").lower()
                self.text[name] = _TextStyle(
                    bold=(tp.get(t(FO, "font-weight")) or "") in ("bold", "600", "700", "800", "900"),
                    italic=(tp.get(t(FO, "font-style")) or "") == "italic",
                    strike=(tp.get(t(STYLE, "text-line-through-style")) or "none") != "none",
                    sup=bool(pos)
                    and (pos[0] == "super" or (pos[0].endswith("%") and pos[0][:1].isdigit() and pos[0] != "0%")),
                    sub=bool(pos) and (pos[0] == "sub" or pos[0].startswith("-")),
                    hidden=(tp.get(t(TEXT, "display")) or "") == "none",
                    mono=any(m in font for m in ("courier", "mono", "consolas")),
                )
            tbp = st.find(t(STYLE, "table-properties"))
            if tbp is not None and (tbp.get(t(TABLE, "display")) or "") == "false":
                self.hidden_tables.add(name)
        for ls in root.iter(t(TEXT, "list-style")):
            name = ls.get(t(STYLE, "name")) or ""
            levels: dict[int, bool] = {}
            for lvl in ls:
                n = lvl.get(t(TEXT, "level")) or "1"
                if n.isdigit():
                    levels[int(n)] = local(lvl.tag) == "list-level-style-number"
            self.lists[name] = levels

    def role(self, name: str | None) -> str | None:
        seen = 0
        while name and seen < 16:
            d = self.display.get(name, name).lower()
            if d in ("title", "subtitle", "caption", "quotations", "preformatted text", "source text"):
                return {"quotations": "quote", "preformatted text": "code", "source text": "code"}.get(d, d)
            if d.startswith("heading"):
                return None
            name = self.parent.get(name)
            seen += 1
        return None

    def text_style(self, name: str | None) -> _TextStyle:
        out = _TextStyle()
        seen = 0
        chain: list[_TextStyle] = []
        while name and seen < 16:
            if name in self.text:
                chain.append(self.text[name])
            name = self.parent.get(name)
            seen += 1
        for s in reversed(chain):
            out = _TextStyle(
                bold=out.bold or s.bold, italic=out.italic or s.italic, strike=out.strike or s.strike,
                sup=out.sup or s.sup, sub=out.sub or s.sub, hidden=out.hidden or s.hidden, mono=out.mono or s.mono,
            )  # fmt: skip
        return out


@dataclass(slots=True)
class _Change:
    kind: str
    author: str | None
    date: dt.datetime | None
    deleted: str = ""


@dataclass(slots=True)
class _Para:
    sb: SpanBuilder
    accepted: SpanBuilder
    changes: list[TrackedChange] = field(default_factory=list)
    comments: list[Comment] = field(default_factory=list)
    images: list[tuple[str, str | None]] = field(default_factory=list)
    boxes: list[etree._Element] = field(default_factory=list)


class OdfConverter:
    id = "documents.odf"
    family = FAMILY
    priority = 10
    experimental = False
    requires_extras: tuple[str, ...] = ()
    mimes: tuple[str, ...] = ODF_MIMES
    limits = Limits(max_bytes=200 * MB, timeout_s=120)

    def can_handle(self, ref: InputRef) -> float:
        return confidence(ref, ODF_MIMES, ODF_EXTS)

    def convert(self, ref: InputRef, options: ConvertOptions) -> Document:
        check_size(ref, self.limits.max_bytes or 200 * MB, "OpenDocument")
        pkg = OfficePackage(ref.read(), what="ODF")
        root = pkg.xml("content.xml")
        if root is None:
            raise ConversionError(
                f"{ref.display}: no content.xml", user_message="This is not a valid OpenDocument file."
            )
        styles = _Styles()
        styles.load(pkg.xml("styles.xml"))
        styles.load(root)
        reader = _OdfReader(pkg, ref.display, OfficeOptions.from_options(options), options, styles)
        body = root.find(t(OFFICE, "body"))
        kind = "text"
        if body is not None:
            for child in body:
                kind = local(child.tag)
                reader.read_body(child, kind)
                break
        source_type = {"text": SourceType.ODF, "spreadsheet": SourceType.ODF, "presentation": SourceType.ODF}
        meta = _metadata(
            pkg, ref.display, source_type.get(kind, SourceType.ODF), ref.detected.mime if ref.detected else None
        )
        meta.extra["odf_kind"] = kind
        if kind == "spreadsheet":
            meta.sheets = list(reader.sheet_names)
        elif kind == "presentation":
            meta.slides = reader.n_slides
        doc = Document(metadata=meta, blocks=reader.out.blocks)
        if meta.title is None:
            first = next((b for b in doc.blocks if isinstance(b, Heading)), None)
            meta.title = spans_text(first.spans).strip() or None if first is not None else None
        doc.warnings.extend(pkg.warnings())
        doc.warnings.extend(reader.warnings())
        if not doc.blocks:
            doc.warnings.append(
                Warning(kind=WarningKind.EXTRACTION_EMPTY, severity="error", message="The document contains no text.")
            )
        return doc.finalize()


def _metadata(pkg: OfficePackage, source: str, st: SourceType, mime: str | None) -> Metadata:
    meta = Metadata(source=source, source_type=st, mime=mime)
    root = pkg.xml("meta.xml")
    m = root.find(t(OFFICE, "meta")) if root is not None else None
    if m is None:
        return meta

    def txt(ns: str, name: str) -> str | None:
        el = m.find(t(ns, name))
        return (el.text or "").strip() or None if el is not None else None

    meta.title = txt(DC, "title")
    meta.author = txt(META, "initial-creator") or txt(DC, "creator")
    meta.authors = [meta.author] if meta.author else []
    meta.published = parse_datetime(txt(META, "creation-date"))
    meta.modified = parse_datetime(txt(DC, "date"))
    meta.description = txt(DC, "description")
    return meta


class _OdfReader:
    def __init__(
        self, pkg: OfficePackage, source: str, opts: OfficeOptions, options: ConvertOptions, styles: _Styles
    ) -> None:
        self.pkg, self.source, self.opts, self.options, self.styles = pkg, source, opts, options, styles
        self.out = BlockList()
        self.clean = CleanStats()
        self.notes: list[Footnote] = []
        self.note_counts = {"footnote": 0, "endnote": 0}
        self.changes: dict[str, _Change] = {}
        self.hidden = 0
        self.boxes = 0
        self.sheet_stats = SheetStats()
        self.n_sheets = 0
        self.sheet_names: list[str] = []
        self.n_slides = 0
        self._depth = 0

    # -- dispatch ---------------------------------------------------------------------------------------------

    def read_body(self, el: etree._Element, kind: str) -> None:
        if kind == "spreadsheet":
            self._spreadsheet(el)
        elif kind == "presentation":
            self._presentation(el)
        else:
            self._collect_changes(el)
            self._container(list(el), "body")
            for fn in self.notes:
                self.out.add(fn)

    def _container(self, elements: list[etree._Element], prefix: str) -> None:
        for i, el in enumerate(elements):
            self.options.ctx.check_deadline()
            path = f"{prefix}[{i}]"
            ns, tag = ns_of(el.tag), local(el.tag)
            if ns == TEXT and tag in ("p", "h"):
                self._paragraph(el, path)
            elif ns == TEXT and tag == "list":
                self._list(el, path)
            elif ns == TABLE and tag == "table":
                self._table(el, path)
            elif ns == TEXT and tag in ("section", "index-body") and self._depth < _MAX_DEPTH:
                self._depth += 1
                self._container(list(el), path)
                self._depth -= 1
            elif ns == DRAW and tag == "frame":
                para = self._new_para()
                self._frame(el, para)
                self._emit_after(para, None, path)
            elif ns == TEXT and tag == "hidden-paragraph":
                self.hidden += 1

    # -- paragraphs -------------------------------------------------------------------------------------------

    def _new_para(self) -> _Para:
        return _Para(sb=SpanBuilder(self.clean), accepted=SpanBuilder(self.clean))

    def _paragraph(self, el: etree._Element, path: str) -> None:
        style = el.get(t(TEXT, "style-name"))
        role = self.styles.role(style)
        anchor = self.out.next_id()
        para = self._new_para()
        self._inline(el, para, (), None, anchor, set())
        prov = Provenance(source=self.source, path=path)
        heading = local(el.tag) == "h" or role == "title"
        spans = (para.accepted if role == "code" else para.sb).stripped()
        whole = _whole_change(spans) if not heading and role != "code" else None
        if whole is not None:
            para.changes.append(
                TrackedChange(
                    change=whole.change or "insert",
                    author=whole.change_author,
                    spans=[
                        sp.model_copy(update={"change": None, "change_author": None, "change_id": None}) for sp in spans
                    ],
                    provenance=Provenance(source=self.source),
                    attrs={"scope": "paragraph"},
                )
            )
            spans = []
        block: Block | None = None
        if heading and spans:
            lvl = el.get(t(TEXT, "outline-level")) or "1"
            level = max(1, min(6, int(lvl))) if lvl.isdigit() else 1
            block = Heading(id=anchor, level=level, spans=spans, provenance=prov)
        elif spans or para.changes:
            if role == "quote":
                block = Quote(id=anchor, spans=spans, provenance=prov)
            elif role == "code":
                from intomd.ir import CodeBlock

                block = CodeBlock(id=anchor, code=spans_text(spans), provenance=prov)
            else:
                prole = {"subtitle": "subtitle", "caption": "caption"}.get(role or "", "body")
                block = Paragraph(id=anchor, spans=spans, role=prole, provenance=prov)
        if block is not None:
            self.out.add(block)
        self._emit_after(para, anchor if block is not None else None, path)

    def _emit_after(self, para: _Para, anchor: str | None, path: str) -> None:
        prov = Provenance(source=self.source, path=path)
        for href, alt in para.images:
            self.out.add(Image(ref=href, alt=alt, provenance=prov))
        follow: list[TrackedChange | Comment] = [*para.changes, *para.comments]
        for b in follow:
            b.anchor_block_id = anchor
            b.provenance = prov.model_copy(update={"source_id": b.provenance.source_id})
            self.out.add(b)
        for box in para.boxes:
            if self._depth >= _MAX_DEPTH:
                break
            self.boxes += 1
            self._depth += 1
            self._container(list(box), f"{path}/textbox")
            self._depth -= 1

    def _inline(
        self,
        el: etree._Element,
        para: _Para,
        styles: tuple[InlineStyle, ...],
        href: str | None,
        anchor: str,
        inserting: set[str],
        depth: int = 0,
    ) -> None:
        if depth > _MAX_DEPTH:
            return
        self._text(el.text, para, styles, href, inserting)
        for child in el:
            ns, tag = ns_of(child.tag), local(child.tag)
            if ns == TEXT and tag == "span":
                ts = self.styles.text_style(child.get(t(TEXT, "style-name")))
                if ts.hidden:
                    self.hidden += 1
                else:
                    self._inline(child, para, styles + _styles(ts), href, anchor, inserting, depth + 1)
            elif ns == TEXT and tag == "a":
                link = safe_href(child.get(t(XLINK, "href")))
                self._inline(child, para, styles, link or href, anchor, inserting, depth + 1)
            elif ns == TEXT and tag == "s":
                c = child.get(t(TEXT, "c")) or "1"
                self._text(" " * min(int(c) if c.isdigit() else 1, 64), para, styles, href, inserting)
            elif ns == TEXT and tag == "tab":
                self._text("\t", para, styles, href, inserting)
            elif ns == TEXT and tag == "line-break":
                self._text("\n", para, styles, href, inserting)
            elif ns == TEXT and tag == "note":
                self._note(child, para)
            elif ns == TEXT and tag in ("hidden-text", "hidden-paragraph"):
                self.hidden += 1
            elif ns == TEXT and tag == "change-start":
                inserting.add(child.get(t(TEXT, "change-id")) or "")
            elif ns == TEXT and tag == "change-end":
                inserting.discard(child.get(t(TEXT, "change-id")) or "")
            elif ns == TEXT and tag == "change":
                self._deletion(child.get(t(TEXT, "change-id")) or "", para, anchor)
            elif ns == OFFICE and tag == "annotation":
                self._annotation(child, para, anchor)
            elif ns == DRAW and tag == "frame":
                self._frame(child, para)
            elif (ns == DRAW and tag == "a") or (
                ns == TEXT
                and tag
                not in (
                    "bookmark",
                    "bookmark-start",
                    "bookmark-end",
                    "soft-page-break",
                    "reference-mark",
                    "alphabetical-index-mark",
                    "toc-mark",
                )
            ):
                self._inline(child, para, styles, href, anchor, inserting, depth + 1)
            self._text(child.tail, para, styles, href, inserting)

    def _text(
        self, s: str | None, para: _Para, styles: tuple[InlineStyle, ...], href: str | None, ins: set[str]
    ) -> None:
        if not s:
            return
        s = s.replace("\n", " ")
        para.accepted.add(s, styles, href)
        if ins and self.opts.tracked_changes:
            cid = next(iter(ins))
            ch = self.changes.get(cid)
            para.sb.add(s, styles, href, change="insert", change_author=ch.author if ch else None, change_id=cid)
            return
        para.sb.add(s, styles, href)

    def _note(self, el: etree._Element, para: _Para) -> None:
        kind = el.get(t(TEXT, "note-class")) or "footnote"
        nid = el.get(t(TEXT, "id")) or str(len(self.notes) + 1)
        fid = f"{'fn' if kind == 'footnote' else 'en'}-{nid}"
        self.note_counts[kind] = self.note_counts.get(kind, 0) + 1
        cit = el.find(t(TEXT, "note-citation"))
        marker = (cit.text or "").strip() if cit is not None and cit.text else str(self.note_counts[kind])
        body = el.find(t(TEXT, "note-body"))
        sb = SpanBuilder(self.clean)
        for p in body.iter(t(TEXT, "p")) if body is not None else []:
            if sb.spans:
                sb.add("\n")
            sb.add(" ".join("".join(p.itertext()).split()))
        para.sb.add("", footnote_ref=fid)
        para.accepted.add("", footnote_ref=fid)
        self.notes.append(
            Footnote(
                id=fid,
                marker=marker,
                spans=sb.stripped(),
                provenance=Provenance(source=self.source, path=f"notes/{nid}", source_id=nid),
                attrs={"kind": kind},
            )
        )

    def _annotation(self, el: etree._Element, para: _Para, anchor: str) -> None:
        if not self.opts.comments:
            return
        creator = el.find(t(DC, "creator"))
        date = el.find(t(DC, "date"))
        lines = [" ".join("".join(p.itertext()).split()) for p in el.iter(t(TEXT, "p"))]
        body = clean_text("\n".join(x for x in lines if x), self.clean)
        if not body:
            return
        para.comments.append(
            Comment(
                author=(creator.text or "").strip() or None if creator is not None else None,
                created=parse_datetime(date.text if date is not None else None),
                spans=[InlineSpan(text=body)],
                anchor_block_id=anchor,
                provenance=Provenance(source=self.source, source_id=el.get(t(OFFICE, "name"))),
            )
        )

    def _frame(self, el: etree._Element, para: _Para) -> None:
        title = el.find(t(SVG, "title"))
        desc = el.find(t(SVG, "desc"))
        alt = ((desc.text or "") if desc is not None else "") or ((title.text or "") if title is not None else "")
        for child in el:
            tag = local(child.tag)
            if tag == "image":
                href = child.get(t(XLINK, "href")) or ""
                if href and not href.startswith(("http:", "https:", "file:")):
                    para.images.append((href, clean_text(alt.strip(), self.clean) or None))
            elif tag == "text-box":
                para.boxes.append(child)
            elif tag == "object":
                pass

    # -- tracked changes ------------------------------------------------------------------------------------

    def _collect_changes(self, body: etree._Element) -> None:
        tc = body.find(t(TEXT, "tracked-changes"))
        if tc is None:
            return
        for region in tc.findall(t(TEXT, "changed-region")):
            cid = region.get(t(TEXT, "id")) or region.get("{http://www.w3.org/XML/1998/namespace}id") or ""
            for kind_el in region:
                kind = local(kind_el.tag)
                info = kind_el.find(t(OFFICE, "change-info"))
                author = date = None
                if info is not None:
                    c = info.find(t(DC, "creator"))
                    d = info.find(t(DC, "date"))
                    author = (c.text or "").strip() or None if c is not None else None
                    date = parse_datetime(d.text if d is not None else None)
                deleted = ""
                if kind == "deletion":
                    deleted = " ".join(
                        " ".join("".join(p.itertext()).split()) for p in kind_el if local(p.tag) in ("p", "h")
                    )
                self.changes[cid] = _Change(kind=kind, author=author, date=date, deleted=deleted)

    def _deletion(self, cid: str, para: _Para, anchor: str) -> None:
        ch = self.changes.get(cid)
        if ch is None or ch.kind != "deletion" or not ch.deleted or not self.opts.tracked_changes:
            return
        text = ch.deleted if ch.deleted.endswith(" ") else ch.deleted + " "
        para.sb.add(text, change="delete", change_author=ch.author, change_id=cid)

    # -- lists and tables -------------------------------------------------------------------------------------

    def _list(self, el: etree._Element, path: str) -> None:
        style = el.get(t(TEXT, "style-name"))
        levels = self.styles.lists.get(style or "", {})
        items = self._items(el, levels, 1)
        if items:
            self.out.add(
                ListBlock(
                    ordered=levels.get(1, False), items=items, provenance=Provenance(source=self.source, path=path)
                )
            )

    def _items(self, el: etree._Element, levels: dict[int, bool], level: int) -> list[ListItem]:
        out: list[ListItem] = []
        if level > _MAX_DEPTH:
            return out
        for li in el:
            if local(li.tag) not in ("list-item", "list-header"):
                continue
            item = ListItem(spans=[])
            for child in li:
                tag = local(child.tag)
                if tag in ("p", "h"):
                    para = self._new_para()
                    self._inline(child, para, (), None, "", set())
                    spans = para.sb.stripped()
                    if spans:
                        if item.spans:
                            item.spans.append(InlineSpan(text=" "))
                        item.spans.extend(spans)
                elif tag == "list":
                    sub_style = child.get(t(TEXT, "style-name"))
                    sub_levels = self.styles.lists.get(sub_style, levels) if sub_style else levels
                    item.children.extend(self._items(child, sub_levels, level + 1))
                    item.children_ordered = sub_levels.get(level + 1, False)
            if item.spans or item.children:
                out.append(item)
        return out

    def _rows(self, el: etree._Element) -> list[tuple[etree._Element, bool]]:
        rows: list[tuple[etree._Element, bool]] = []
        for child in el:
            tag = local(child.tag)
            if tag == "table-row":
                rows.append((child, False))
            elif tag == "table-header-rows":
                rows.extend((r, True) for r in child if local(r.tag) == "table-row")
            elif tag in ("table-rows", "table-row-group"):
                rows.extend(self._rows(child))
        return rows

    def _table(self, el: etree._Element, path: str) -> None:
        cells: list[TableCell] = []
        n_cols = 0
        header = 0
        rows = self._rows(el)
        ri = 0
        for row, is_header in rows:
            rep = row.get(t(TABLE, "number-rows-repeated")) or "1"
            for _ in range(min(int(rep) if rep.isdigit() else 1, _MAX_REPEAT)):
                if not any("".join(c.itertext()).strip() for c in row) and ri > 0:
                    break
                col = 0
                for c in row:
                    tag = local(c.tag)
                    crep = c.get(t(TABLE, "number-columns-repeated")) or "1"
                    count = min(int(crep) if crep.isdigit() else 1, _MAX_REPEAT)
                    if tag == "covered-table-cell":
                        col += count
                        continue
                    if tag != "table-cell":
                        continue
                    text = "\n".join(" ".join("".join(p.itertext()).split()) for p in c if local(p.tag) in ("p", "h"))
                    cs = c.get(t(TABLE, "number-columns-spanned")) or "1"
                    rs = c.get(t(TABLE, "number-rows-spanned")) or "1"
                    for _ in range(count if text else 1):
                        if text:
                            cells.append(
                                TableCell(
                                    spans=[InlineSpan(text=clean_text(text, self.clean))],
                                    row=ri,
                                    col=col,
                                    row_span=max(1, int(rs) if rs.isdigit() else 1),
                                    col_span=max(1, int(cs) if cs.isdigit() else 1),
                                    is_header=is_header,
                                )
                            )
                        col += 1 if text else count
                n_cols = max(n_cols, col)
                header += int(is_header and header == ri)
                ri += 1
        if not cells:
            return
        n_rows = ri
        for c in cells:
            c.row_span = min(c.row_span, n_rows - c.row)
            n_cols = max(n_cols, c.col + c.col_span)
        if not header and n_rows > 1:
            header = 1
            for c in cells:
                c.is_header = c.row == 0
        self.out.add(
            Table(
                cells=cells,
                n_rows=n_rows,
                n_cols=n_cols,
                header_rows=header,
                provenance=Provenance(source=self.source, path=path),
            )
        )

    # -- spreadsheets ---------------------------------------------------------------------------------------

    def _spreadsheet(self, el: etree._Element) -> None:
        sheets = [s for s in el if local(s.tag) == "table" and ns_of(s.tag) == TABLE]
        self.n_sheets = len(sheets)
        self.sheet_names = [s.get(t(TABLE, "name")) or f"Sheet{i}" for i, s in enumerate(sheets, start=1)]
        for idx, sheet in enumerate(sheets[: self.opts.max_sheets], start=1):
            self.options.ctx.check_deadline()
            name = sheet.get(t(TABLE, "name")) or f"Sheet{idx}"
            hidden = (sheet.get(t(TABLE, "style-name")) or "") in self.styles.hidden_tables
            if hidden:
                if not self.opts.include_hidden_sheets:
                    continue
                self.sheet_stats.hidden.append(name)
            attrs = {"sheet_state": "hidden" if hidden else "visible"}
            if hidden:
                attrs["hidden"] = "true"
            self.out.add(
                Heading(
                    level=2,
                    spans=[InlineSpan(text=clean_text(name, self.clean))],
                    provenance=Provenance(source=self.source, source_page=idx, source_label=name, path=f"{name}!A1"),
                    attrs=attrs,
                )
            )
            grid, merges = self._sheet_grid(sheet)
            regs = regions(grid)
            for n, reg in enumerate(regs, start=1):
                table = sheet_table(
                    grid, reg, merges, name, idx, self.source, self.clean, self.sheet_stats, False, len(regs) > 1, n
                )
                if table is not None:
                    self.out.add(table)

    def _sheet_grid(self, sheet: etree._Element) -> tuple[list[list[XCell | None]], list[tuple[int, int, int, int]]]:
        grid: list[list[XCell | None]] = []
        merges: list[tuple[int, int, int, int]] = []
        for row, _hdr in self._rows(sheet):
            rep = row.get(t(TABLE, "number-rows-repeated")) or "1"
            cells: list[XCell | None] = []
            col = 0
            for c in row:
                tag = local(c.tag)
                crep = c.get(t(TABLE, "number-columns-repeated")) or "1"
                count = min(int(crep) if crep.isdigit() else 1, self.opts.max_cols)
                xc = _ods_cell(c) if tag == "table-cell" else None
                if xc is None:
                    cells.extend([None] * count)
                    col += count
                    continue
                cs = c.get(t(TABLE, "number-columns-spanned")) or "1"
                rs = c.get(t(TABLE, "number-rows-spanned")) or "1"
                if cs != "1" or rs != "1":
                    merges.append((len(grid), col, len(grid) + int(rs) - 1 if rs.isdigit() else len(grid),
                                   col + int(cs) - 1 if cs.isdigit() else col))  # fmt: skip
                for _ in range(count):
                    cells.append(xc)
                    col += 1
                if col >= self.opts.max_cols:
                    break
            while cells and cells[-1] is None:
                cells.pop()
            times = min(int(rep) if rep.isdigit() else 1, _MAX_REPEAT) if cells else 1
            for _ in range(times):
                if len(grid) >= self.opts.max_rows:
                    self.sheet_stats.row_capped.append(sheet.get(t(TABLE, "name")) or "")
                    return grid, merges
                grid.append(list(cells))
        while grid and not grid[-1]:
            grid.pop()
        return grid, merges

    # -- presentations --------------------------------------------------------------------------------------

    def _presentation(self, el: etree._Element) -> None:
        pages = [p for p in el if local(p.tag) == "page" and ns_of(p.tag) == DRAW]
        self.n_slides = len(pages)
        for n, page in enumerate(pages[: self.opts.max_slides], start=1):
            self.options.ctx.check_deadline()
            frames = [f for f in page if local(f.tag) in ("frame", "custom-shape")]
            frames.sort(key=lambda f: (_length(f.get(t(SVG, "y"))), _length(f.get(t(SVG, "x")))))
            title = None
            for f in frames:
                if f.get(t(PRES, "class")) == "title":
                    title = " ".join("".join(f.itertext()).split()) or None
            slide_id = self.out.add(
                Slide(
                    index=n,
                    title=clean_text(title, self.clean) if title else None,
                    provenance=Provenance(source=self.source, source_page=n, path=f"page{n}"),
                    attrs={"name": page.get(t(DRAW, "name")) or ""},
                )
            )
            start = len(self.out.blocks)
            for i, f in enumerate(frames):
                if f.get(t(PRES, "class")) in ("title", "page-number", "footer", "date-time"):
                    continue
                for box in (
                    [f]
                    if local(f.tag) == "custom-shape"
                    else [c for c in f if local(c.tag) in ("text-box", "image", "table")]
                ):
                    path = f"page{n}/frame{i}"
                    if local(box.tag) == "image":
                        desc = f.find(t(SVG, "desc"))
                        alt = (desc.text or None) if desc is not None else None
                        prov = Provenance(source=self.source, source_page=n, path=path)
                        self.out.add(Image(ref=box.get(t(XLINK, "href")) or "", alt=alt, provenance=prov))
                    elif local(box.tag) == "table":
                        self._table(box, path)
                    else:
                        self._container(list(box), path)
            notes = page.find(t(PRES, "notes"))
            if notes is not None and self.opts.include_notes:
                text = "\n".join(
                    " ".join("".join(p.itertext()).split())
                    for fr in notes
                    if fr.get(t(PRES, "class")) == "notes"
                    for p in fr.iter(t(TEXT, "p"))
                )
                if text.strip():
                    self.out.add(
                        Paragraph(
                            spans=[InlineSpan(text=clean_text(text.strip(), self.clean))],
                            provenance=Provenance(source=self.source, source_page=n, path=f"page{n}/notes"),
                            attrs={"slide_part": "notes"},
                        )
                    )
            for b in self.out.blocks[start:]:
                b.parent_id = slide_id
                if b.provenance.source_page is None:
                    b.provenance.source_page = n

    def warnings(self) -> list[Warning]:
        out: list[Warning] = []
        if self.hidden:
            out.append(
                Warning(
                    kind=WarningKind.REMOVED_HIDDEN_ELEMENTS,
                    message=f"Excluded {self.hidden} hidden text elements from the body.",
                    count=self.hidden,
                )
            )
        if self.boxes:
            out.append(
                Warning(
                    kind=WarningKind.TEXTBOX_CONTENT_RELOCATED,
                    message=f"Moved the content of {self.boxes} text frames after their anchoring paragraphs.",
                    count=self.boxes,
                )
            )
        out.extend(sheet_warnings(self.sheet_stats, self.n_sheets, self.opts))
        cw = clean_warning(self.clean)
        if cw is not None:
            out.append(cw)
        return out


def _whole_change(spans: list[InlineSpan]) -> InlineSpan | None:
    """The first span when every visible span is the same insertion or deletion (a structural change)."""
    vis = [sp for sp in spans if sp.text.strip()]
    if not vis or any(sp.change is None for sp in vis):
        return None
    if any((sp.change, sp.change_author) != (vis[0].change, vis[0].change_author) for sp in vis):
        return None
    return vis[0]


def _styles(ts: _TextStyle) -> tuple[InlineStyle, ...]:
    out: list[InlineStyle] = []
    if ts.bold:
        out.append(InlineStyle.BOLD)
    if ts.italic:
        out.append(InlineStyle.ITALIC)
    if ts.strike:
        out.append(InlineStyle.STRIKE)
    if ts.sup:
        out.append(InlineStyle.SUPERSCRIPT)
    elif ts.sub:
        out.append(InlineStyle.SUBSCRIPT)
    if ts.mono:
        out.append(InlineStyle.CODE)
    return tuple(out)


def _ods_cell(c: etree._Element) -> XCell | None:
    vtype = c.get(t(OFFICE, "value-type")) or ""
    formula = c.get(t(TABLE, "formula"))
    if formula and formula.startswith("of:"):
        formula = formula[3:]
    text = "\n".join("".join(p.itertext()) for p in c if local(p.tag) == "p")
    value: object = text or None
    fmt = "General"
    if vtype in ("float", "percentage", "currency"):
        try:
            value = float(c.get(t(OFFICE, "value")) or "")
        except ValueError:
            value = text or None
        fmt = {"percentage": "0%", "currency": "$0"}.get(vtype, "General")
        if vtype == "percentage" and isinstance(value, float):
            decimals = text.split(".")[-1].rstrip("%") if "." in text else ""
            fmt = "0." + "0" * len(decimals) + "%" if decimals.isdigit() else "0%"
    elif vtype == "date":
        raw = c.get(t(OFFICE, "date-value")) or ""
        try:
            value = dt.datetime.fromisoformat(raw) if "T" in raw else dt.date.fromisoformat(raw)
        except ValueError:
            value = text or None
    elif vtype == "boolean":
        value = (c.get(t(OFFICE, "boolean-value")) or "").lower() == "true"
    if value is None and not formula:
        return None
    return XCell(
        value=value,
        number_format=fmt,
        data_type="s" if isinstance(value, str) else "n",
        bold=False,
        formula=("=" + formula.lstrip("=")) if formula else None,
        display=text or None if isinstance(value, float) else None,
    )


def _length(v: str | None) -> float:
    if not v:
        return 0.0
    num = "".join(ch for ch in v if ch.isdigit() or ch in ".-")
    try:
        return float(num)
    except ValueError:
        return 0.0
