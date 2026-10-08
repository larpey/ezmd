"""documents.pptx: native PPTX converter (lxml over the sanitized package; Part 2 2c steps 16 to 23).

One `Slide` block per slide in presentation order, its content as children (parent_id): body text as
Paragraph or List by bullet level, tables with merged cells, charts as data tables, SmartArt as lists,
pictures with alt text, speaker notes as a Paragraph with attrs slide_part=notes (D-0017), and slide
comments. Shapes are read in top-then-left order, with placeholder positions inherited from the layout.
python-pptx is not used at runtime: it pulls in Pillow and XlsxWriter only to read text and XML that lxml
reads directly (docs/decisions/P1-T01-office.md).
"""

from __future__ import annotations

import posixpath

from intomd.context import Limits
from intomd.core.textclean import CleanStats, clean_text
from intomd.inputs import InputRef
from intomd.ir import (
    BBox,
    Block,
    Comment,
    Document,
    Heading,
    Image,
    InlineSpan,
    ListBlock,
    ListItem,
    Metadata,
    Paragraph,
    Provenance,
    Slide,
    SourceType,
    Table,
    TableCell,
    Warning,
    WarningKind,
    spans_text,
)
from intomd.registry import ConversionError, ConvertOptions
from intomd_converters.office._common import (
    FAMILY,
    MB,
    PPTX_EXTS,
    PPTX_MIMES,
    BlockList,
    OfficeOptions,
    check_size,
    clean_warning,
    confidence,
    parse_datetime,
)
from intomd_converters.office._ooxml_ns import P14, P188, A, P, R, q
from intomd_converters.office._package import OfficePackage, Rel
from intomd_converters.office.docx import main_part
from intomd_converters.office.docx_parts import load_core
from intomd_converters.office.pptx_shapes import (
    BULLET_TYPES,
    FURNITURE_TYPES,
    TITLE_TYPES,
    DgmNode,
    LayoutBoxes,
    Shape,
    TextPara,
    cell_spans,
    read_chart,
    read_shapes,
    read_smartart,
    text_paras,
)

_IMAGE_MIMES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif",
                ".emf": "image/emf", ".wmf": "image/wmf", ".svg": "image/svg+xml", ".tiff": "image/tiff"}  # fmt: skip


class _Counts:
    def __init__(self) -> None:
        self.hidden: list[int] = []
        self.hidden_skipped = 0
        self.smartart = 0
        self.ole = 0
        self.comments = 0


class PptxConverter:
    id = "documents.pptx"
    family = FAMILY
    priority = 10
    experimental = False
    requires_extras: tuple[str, ...] = ()
    mimes: tuple[str, ...] = PPTX_MIMES
    limits = Limits(max_bytes=200 * MB, max_entries=500, timeout_s=120)

    def can_handle(self, ref: InputRef) -> float:
        return confidence(ref, PPTX_MIMES, PPTX_EXTS)

    def convert(self, ref: InputRef, options: ConvertOptions) -> Document:
        check_size(ref, self.limits.max_bytes or 200 * MB, "PowerPoint")
        pkg = OfficePackage(ref.read(), what="PPTX")
        return convert_package(pkg, ref.display, options, mime=ref.detected.mime if ref.detected else None)


def convert_package(pkg: OfficePackage, source: str, options: ConvertOptions, *, mime: str | None = None) -> Document:
    pres_part = main_part(pkg, "ppt/presentation.xml")
    pres = pkg.xml(pres_part)
    if pres is None:
        raise ConversionError(f"{source}: missing {pres_part}", user_message="This is not a valid PowerPoint file.")
    opts = OfficeOptions.from_options(options)
    rels = pkg.rels(pres_part)
    size = pres.find(q(P, "sldSz"))
    width = float(size.get("cx", 9144000)) if size is not None else 9144000.0
    height = float(size.get("cy", 6858000)) if size is not None else 6858000.0
    slides: list[tuple[str, str]] = []
    lst = pres.find(q(P, "sldIdLst"))
    for sid in lst if lst is not None else []:
        rel = rels.get(sid.get(q(R, "id")) or "")
        if rel is not None and not rel.external and pkg.has(rel.target):
            slides.append((sid.get("id") or "", rel.target))
    sections = _sections(pres)
    authors = _authors(pkg, rels)
    core = load_core(pkg)
    meta = Metadata(
        source=source,
        source_type=SourceType.PPTX,
        mime=mime,
        title=core.title,
        author=core.author,
        authors=[core.author] if core.author else [],
        published=core.created,
        modified=core.modified,
        slides=len(slides),
    )
    doc = Document(metadata=meta)
    out = BlockList()
    counts = _Counts()
    stats = CleanStats()
    capped = slides[: opts.max_slides]
    for n, (sid, part) in enumerate(capped, start=1):
        options.ctx.check_deadline()
        options.ctx.progress("slides", n / max(len(capped), 1), f"Slide {n}")
        if sid in sections:
            out.add(
                Heading(
                    level=1,
                    spans=[InlineSpan(text=clean_text(sections[sid], stats))],
                    provenance=Provenance(source=source, source_page=n, path=f"slide{n}"),
                    attrs={"role": "section"},
                )
            )
        _SlideReader(pkg, part, n, source, opts, stats, counts, authors, (width, height)).read(out)
        doc.blocks = list(out.blocks)
        options.ctx.publish_partial(doc)
    doc.blocks = list(out.blocks)
    if meta.title is None:
        first = next((b for b in doc.blocks if isinstance(b, Slide) and b.title), None)
        meta.title = first.title if isinstance(first, Slide) else None
    doc.warnings.extend(pkg.warnings())
    doc.warnings.extend(_warnings(counts, len(slides), opts.max_slides))
    cw = clean_warning(stats)
    if cw is not None:
        doc.warnings.append(cw)
    if len(slides) > opts.max_slides:
        doc.truncated = True
    if not doc.blocks:
        doc.warnings.append(
            Warning(kind=WarningKind.EXTRACTION_EMPTY, severity="error", message="The presentation has no slides.")
        )
    return doc.finalize()


def _sections(pres: object) -> dict[str, str]:
    """First slide id of each p14:section -> section name."""
    out: dict[str, str] = {}
    for sec in pres.iter(q(P14, "section")):  # type: ignore[attr-defined]
        ids = sec.find(q(P14, "sldIdLst"))
        first = ids[0] if ids is not None and len(ids) else None
        name = (sec.get("name") or "").strip()
        if first is not None and name:
            out.setdefault(first.get("id") or "", name)
    return out


def _authors(pkg: OfficePackage, rels: dict[str, Rel]) -> dict[str, str]:
    out: dict[str, str] = {}
    for rel in rels.values():
        if rel.external:
            continue
        if rel.kind == "commentauthors":
            root = pkg.xml(rel.target)
            for a in root.iter(q(P, "cmAuthor")) if root is not None else []:
                out[a.get("id") or ""] = a.get("name") or ""
        elif rel.kind == "authors":
            root = pkg.xml(rel.target)
            for a in root.iter(q(P188, "author")) if root is not None else []:
                out[a.get("id") or ""] = a.get("name") or ""
    return out


def _warnings(c: _Counts, total: int, cap: int) -> list[Warning]:
    out: list[Warning] = []
    if c.hidden:
        out.append(
            Warning(
                kind=WarningKind.HIDDEN_SLIDES_INCLUDED,
                message=f"Included {len(c.hidden)} hidden slides (marked hidden).",
                count=len(c.hidden),
                detail={"slides": ",".join(str(n) for n in c.hidden)},
            )
        )
    if c.smartart:
        out.append(
            Warning(
                kind=WarningKind.SMARTART_FLATTENED,
                message=f"Flattened {c.smartart} SmartArt graphics into lists.",
                count=c.smartart,
            )
        )
    if c.ole:
        out.append(
            Warning(kind=WarningKind.OLE_OBJECT_SKIPPED, message=f"Skipped {c.ole} embedded OLE objects.", count=c.ole)
        )
    if total > cap:
        out.append(
            Warning(
                kind=WarningKind.SLIDE_CAP_REACHED,
                message=f"Converted the first {cap} of {total} slides; raise office.max_slides to convert more.",
                count=total - cap,
                detail={"cap": cap, "slides": total},
            )
        )
    return out


class _SlideReader:
    def __init__(
        self,
        pkg: OfficePackage,
        part: str,
        n: int,
        source: str,
        opts: OfficeOptions,
        stats: CleanStats,
        counts: _Counts,
        authors: dict[str, str],
        size: tuple[float, float],
    ) -> None:
        self.pkg, self.part, self.n, self.source = pkg, part, n, source
        self.opts, self.stats, self.counts, self.authors = opts, stats, counts, authors
        self.width, self.height = size
        self.rels = pkg.rels(part)

    def prov(self, sh: Shape | None, box: tuple[float, float, float, float] | None = None) -> Provenance:
        bbox = None
        if box is not None and box[2] >= 0 and box[3] >= 0:
            x, y, w, h = box
            bbox = BBox(x0=x, y0=y, x1=x + w, y1=y + h, page_width=self.width, page_height=self.height)
        path = f"slide{self.n}" + (f"/shape{sh.shape_id}" if sh is not None else "")
        return Provenance(source=self.source, source_page=self.n, path=path, bbox=bbox)

    def read(self, out: BlockList) -> None:
        root = self.pkg.xml(self.part)
        if root is None:
            return
        hidden = (root.get("show") or "1") in ("0", "false")
        if hidden and not self.opts.include_hidden_slides:
            self.counts.hidden_skipped += 1
            return
        layout = LayoutBoxes(self.pkg, self.rels)
        csld = root.find(q(P, "cSld"))
        shapes = read_shapes(csld.find(q(P, "spTree")) if csld is not None else None)
        boxes = {id(s): layout.resolve(s) for s in shapes}
        shapes.sort(key=lambda s: _order(s, boxes[id(s)]))
        title_shape = self._title_shape(shapes, boxes)
        title = None
        if title_shape is not None:
            paras = text_paras(title_shape.el.find(q(P, "txBody")), self.rels, self.stats, False)
            title = " ".join(" ".join(spans_text(tp.spans).split()) for tp in paras).strip() or None
        slide = Slide(
            index=self.n,
            title=title,
            layout=layout.layout_name,
            provenance=Provenance(source=self.source, source_page=self.n, source_label=title, path=f"slide{self.n}"),
            attrs={"hidden": "true"} if hidden else {},
        )
        if hidden:
            self.counts.hidden.append(self.n)
        sid = out.add(slide)
        for sh in shapes:
            if sh is title_shape:
                continue
            for b in self._shape_blocks(sh, boxes[id(sh)]):
                b.parent_id = sid
                out.add(b)
        notes = self._notes()
        if notes is not None:
            notes.parent_id = sid
            out.add(notes)
        for c in self._comments(sid):
            c.parent_id = sid
            out.add(c)

    def _title_shape(
        self, shapes: list[Shape], boxes: dict[int, tuple[float, float, float, float] | None]
    ) -> Shape | None:
        for sh in shapes:
            if sh.kind == "text" and sh.ph_type in TITLE_TYPES and self._has_text(sh):
                return sh
        best: tuple[float, float, Shape] | None = None
        for sh in shapes:
            if sh.kind != "text" or sh.is_placeholder:
                continue
            box = boxes[id(sh)]
            if box is None or box[1] > self.height / 3:
                continue
            paras = text_paras(sh.el.find(q(P, "txBody")), self.rels, CleanStats(), False)
            if len(paras) != 1 or len(spans_text(paras[0].spans)) > 100:
                continue
            key = (-(paras[0].max_size or 0.0), box[1])
            if best is None or key < (best[0], best[1]):
                best = (key[0], key[1], sh)
        return best[2] if best is not None else None

    def _has_text(self, sh: Shape) -> bool:
        return any("".join(t.itertext()).strip() for t in sh.el.iter(q(A, "t")))

    def _shape_blocks(self, sh: Shape, box: tuple[float, float, float, float] | None) -> list[Block]:
        prov = self.prov(sh, box)
        if sh.kind == "text":
            if sh.ph_type in FURNITURE_TYPES:
                return []
            bullets = sh.is_placeholder and sh.ph_type in BULLET_TYPES
            paras = text_paras(sh.el.find(q(P, "txBody")), self.rels, self.stats, bullets)
            if sh.ph_type == "subTitle":
                return [Paragraph(spans=_join(paras), role="subtitle", provenance=prov)] if paras else []
            return _text_blocks(paras, prov)
        if sh.kind == "table":
            t = self._table(sh, prov)
            return [t] if t is not None else []
        if sh.kind == "chart":
            t = self._chart(sh, prov)
            return [t] if t is not None else []
        if sh.kind == "smartart":
            nodes = self._smartart(sh)
            if not nodes:
                return []
            self.counts.smartart += 1
            return [
                ListBlock(items=[_dgm_item(n, self.stats) for n in nodes], provenance=prov, attrs={"smartart": "true"})
            ]
        if sh.kind == "pic":
            rel = self.rels.get(sh.rid or "")
            if rel is None or rel.external:
                return []
            ext = posixpath.splitext(rel.target)[1].lower()
            alt = clean_text(sh.descr, self.stats) if sh.descr else None
            return [Image(ref=rel.target, alt=alt, mime=_IMAGE_MIMES.get(ext), provenance=prov)]
        if sh.kind == "ole":
            self.counts.ole += 1
        return []

    def _table(self, sh: Shape, prov: Provenance) -> Table | None:
        tbl = sh.el.find(f".//{q(A, 'tbl')}")
        if tbl is None:
            return None
        n_cols = len(tbl.findall(f"{q(A, 'tblGrid')}/{q(A, 'gridCol')}"))
        cells: list[TableCell] = []
        rows = tbl.findall(q(A, "tr"))
        for ri, tr in enumerate(rows):
            for ci, tc in enumerate(tr.findall(q(A, "tc"))):
                if tc.get("hMerge") in ("1", "true") or tc.get("vMerge") in ("1", "true"):
                    continue
                rs = int(tc.get("rowSpan", "1")) if (tc.get("rowSpan") or "1").isdigit() else 1
                cs = int(tc.get("gridSpan", "1")) if (tc.get("gridSpan") or "1").isdigit() else 1
                rs = max(1, min(rs, len(rows) - ri))
                cs = max(1, cs)
                n_cols = max(n_cols, ci + cs)
                cells.append(
                    TableCell(spans=cell_spans(tc, self.rels, self.stats), row=ri, col=ci, row_span=rs, col_span=cs)
                )
        if not cells:
            return None
        tbl_pr = tbl.find(q(A, "tblPr"))
        header = 1 if tbl_pr is not None and tbl_pr.get("firstRow") in ("1", "true") and len(rows) > 1 else 0
        for c in cells:
            c.is_header = c.row < header
        return Table(cells=cells, n_rows=len(rows), n_cols=max(n_cols, 1), header_rows=header, provenance=prov)

    def _chart(self, sh: Shape, prov: Provenance) -> Table | None:
        rel = self.rels.get(sh.rid or "")
        if rel is None or rel.external:
            return None
        data = read_chart(self.pkg.xml(rel.target))
        if data is None or not data.series:
            return None
        n_rows = max(len(data.categories), max(len(v) for _, v in data.series))
        header = ["Category", *[name for name, _ in data.series]]
        cells = [
            TableCell(spans=[InlineSpan(text=clean_text(h, self.stats))], row=0, col=i, is_header=True)
            for i, h in enumerate(header)
        ]
        for r in range(n_rows):
            cat = data.categories[r] if r < len(data.categories) else str(r + 1)
            row = [cat, *[(v[r] if r < len(v) else "") for _, v in data.series]]
            cells.extend(
                TableCell(spans=[InlineSpan(text=clean_text(v, self.stats))] if v else [], row=r + 1, col=i)
                for i, v in enumerate(row)
            )
        caption = f"Chart: {data.title}" if data.title else "Chart"
        return Table(
            cells=cells,
            n_rows=n_rows + 1,
            n_cols=len(header),
            header_rows=1,
            caption=[InlineSpan(text=clean_text(caption, self.stats))],
            provenance=prov,
            attrs={"chart_type": data.chart_type},
        )

    def _smartart(self, sh: Shape) -> list[DgmNode]:
        rel = self.rels.get(sh.rid or "")
        if rel is None or rel.external:
            return []
        return read_smartart(self.pkg.xml(rel.target))

    def _notes(self) -> Paragraph | None:
        if not self.opts.include_notes:
            return None
        rel = next((r for r in self.rels.values() if r.kind == "notesslide" and not r.external), None)
        root = self.pkg.xml(rel.target) if rel is not None else None
        if root is None:
            return None
        csld = root.find(q(P, "cSld"))
        lines: list[InlineSpan] = []
        for sh in read_shapes(csld.find(q(P, "spTree")) if csld is not None else None):
            if sh.kind != "text" or sh.ph_type != "body":
                continue
            for tp in text_paras(sh.el.find(q(P, "txBody")), self.pkg.rels(rel.target), self.stats, False):  # type: ignore[union-attr]
                if lines:
                    lines.append(InlineSpan(text="\n"))
                lines.extend(tp.spans)
        if not lines:
            return None
        return Paragraph(
            spans=lines,
            provenance=Provenance(source=self.source, source_page=self.n, path=f"slide{self.n}/notes"),
            attrs={"slide_part": "notes"},
        )

    def _comments(self, slide_id: str) -> list[Comment]:
        if not self.opts.comments:
            return []
        out: list[Comment] = []
        for rel in self.rels.values():
            if rel.external or rel.kind != "comments":
                continue
            root = self.pkg.xml(rel.target)
            if root is None:
                continue
            for i, cm in enumerate([*root.iter(q(P, "cm")), *root.iter(q(P188, "cm"))]):
                text_el = cm.find(q(P, "text"))
                body = text_el.text if text_el is not None and text_el.text else ""
                if not body:
                    body = "\n".join("".join(t.text or "" for t in p.iter(q(A, "t"))) for p in cm.iter(q(A, "p")))
                body = clean_text(body, self.stats).strip()
                if not body:
                    continue
                self.counts.comments += 1
                out.append(
                    Comment(
                        author=self.authors.get(cm.get("authorId") or "") or None,
                        created=parse_datetime(cm.get("dt") or cm.get("created")),
                        spans=[InlineSpan(text=body)],
                        anchor_block_id=slide_id,
                        provenance=Provenance(
                            source=self.source,
                            source_page=self.n,
                            path=f"slide{self.n}/comment{i + 1}",
                            source_id=cm.get("id") or cm.get("idx"),
                        ),
                    )
                )
        return out


def _order(sh: Shape, box: tuple[float, float, float, float] | None) -> tuple[float, float]:
    if box is not None:
        return box[1], box[0]
    if sh.ph_type in TITLE_TYPES:
        return -1.0, -1.0
    return float("inf"), float("inf")


def _join(paras: list[TextPara]) -> list[InlineSpan]:
    out: list[InlineSpan] = []
    for tp in paras:
        if out:
            out.append(InlineSpan(text="\n"))
        out.extend(tp.spans)
    return out


def _text_blocks(paras: list[TextPara], prov: Provenance) -> list[Block]:
    """Consecutive bulleted paragraphs become one List (nesting by level); the rest become Paragraphs."""
    out: list[Block] = []
    run: list[TextPara] = []

    def flush() -> None:
        if run:
            out.append(_list(run, prov))
            run.clear()

    for tp in paras:
        if tp.bullet:
            run.append(tp)
        else:
            flush()
            out.append(Paragraph(spans=tp.spans, provenance=prov))
    flush()
    return out


def _list(paras: list[TextPara], prov: Provenance) -> ListBlock:
    items: list[ListItem] = []
    last: list[ListItem] = []
    base = min(tp.level for tp in paras)
    for tp in paras:
        item = ListItem(spans=tp.spans)
        depth = min(tp.level - base, len(last))
        if depth == 0:
            items.append(item)
        else:
            parent = last[depth - 1]
            if not parent.children:
                parent.children_ordered = tp.bullet == "number"
            parent.children.append(item)
        del last[depth:]
        last.append(item)
    return ListBlock(ordered=paras[0].bullet == "number", items=items, provenance=prov)


def _dgm_item(node: DgmNode, stats: CleanStats) -> ListItem:
    return ListItem(
        spans=[InlineSpan(text=clean_text(node.text, stats))], children=[_dgm_item(c, stats) for c in node.children]
    )
