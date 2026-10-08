"""DOCX body walker: turns `w:body` into IR blocks (Part 2 2c steps 3 to 14).

Placement rules for annotations:
- Tracked insertions and deletions are inline spans (`InlineSpan.change`, `change_author`, `change_id`) at
  their exact position, in paragraphs, headings, list items, table cells, and notes. Moves keep their
  direction in `change_id` (`moveFrom:<id>` / `moveTo:<id>`).
- A paragraph whose whole text is one insertion, deletion, or move becomes an empty Paragraph plus an
  anchored `TrackedChange` block (a structural change). Formatting-only changes (`w:rPrChange`) are
  anchored `TrackedChange(change="format")` blocks.
- Comments are `Comment` blocks anchored to the block where their range starts, with the covered text.
"""

from __future__ import annotations

import posixpath
import re
from dataclasses import dataclass, field
from pathlib import Path

from lxml import etree  # type: ignore[import-untyped]

from intomd.core.textclean import CleanStats, clean_text
from intomd.ir import (
    Block,
    CodeBlock,
    Comment,
    Equation,
    Footnote,
    Heading,
    Image,
    InlineSpan,
    ListBlock,
    ListItem,
    Paragraph,
    Provenance,
    Quote,
    Table,
    TableCell,
    TrackedChange,
)
from intomd.registry import ConvertOptions
from intomd_converters.office._common import BlockList, OfficeOptions, SpanBuilder
from intomd_converters.office._ooxml_ns import W14, W, local, ns_of, q
from intomd_converters.office._package import OfficePackage, Rel
from intomd_converters.office.docx_inline import Counters, InlineCollector, ParaState, Seg
from intomd_converters.office.docx_parts import CommentInfo, Numbering, Styles, on_off, w_val

_MAX_DEPTH = 8
_IMAGE_MIMES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif",
                ".bmp": "image/bmp", ".tif": "image/tiff", ".tiff": "image/tiff", ".emf": "image/emf",
                ".wmf": "image/wmf", ".svg": "image/svg+xml", ".webp": "image/webp"}  # fmt: skip
_ROMAN = ((10, "x"), (9, "ix"), (5, "v"), (4, "iv"), (1, "i"))


def _roman(n: int) -> str:
    out = ""
    for v, s in _ROMAN:
        while n >= v:
            out += s
            n -= v
    return out


@dataclass(slots=True)
class _ListAcc:
    id: str
    num_id: str
    ordered: bool
    path: str
    source_id: str | None
    start: int = 1
    items: list[ListItem] = field(default_factory=list)
    last: list[ListItem] = field(default_factory=list)
    pending: list[Block] = field(default_factory=list)
    textboxes: list[tuple[etree._Element, str]] = field(default_factory=list)


@dataclass(slots=True)
class _CodeAcc:
    lines: list[str]
    path: str


@dataclass(slots=True)
class WalkStats:
    textboxes: int = 0
    ole: int = 0
    inferred_headings: int = 0
    images: int = 0


class DocxWalker:
    def __init__(
        self,
        pkg: OfficePackage,
        doc_part: str,
        source: str,
        opts: OfficeOptions,
        options: ConvertOptions,
        parts: dict[str, str],
        comments: dict[str, CommentInfo],
    ) -> None:
        self.pkg = pkg
        self.source = source
        self.opts = opts
        self.options = options
        self.rels: dict[str, Rel] = pkg.rels(doc_part)
        self.styles = Styles.load(pkg, parts.get("styles"))
        self.numbering = Numbering.load(pkg, parts.get("numbering"))
        self.comments = comments
        self.counters = Counters()
        self.clean = CleanStats()
        self.stats = WalkStats()
        self.inline = InlineCollector(pkg, self.rels, self.styles, self.counters)
        self.out = BlockList()
        self.notes = {"fn": self._load_notes(parts.get("footnotes"), "footnote"),
                      "en": self._load_notes(parts.get("endnotes"), "endnote")}  # fmt: skip
        self.note_order: list[str] = []
        self.comment_anchor: dict[str, str] = {}
        self.comment_ids: dict[str, str] = {}
        self._list: _ListAcc | None = None
        self._code: _CodeAcc | None = None
        self._depth = 0
        self._normal = self.styles.normal_size()
        self._inferred: dict[float, int] = {}

    # -- entry ----------------------------------------------------------------------------------------------

    def walk(self, body: etree._Element) -> list[Block]:
        if self.opts.infer_headings:
            self._prescan(body)
        self._container(list(body), "body", top=True)
        self._flush()
        self._footnotes()
        self._orphan_comments()
        self._link_replies()
        self._attach_captions()
        return self.out.blocks

    def _attach_captions(self) -> None:
        """A Caption-style paragraph right after a Table or Image becomes its caption (Part 2 2c step 9)."""
        blocks = self.out.blocks
        keep: list[Block] = []
        for b in blocks:
            prev = next((k for k in reversed(keep) if not isinstance(k, Comment | TrackedChange)), None)
            if (
                isinstance(b, Paragraph)
                and b.role == "caption"
                and isinstance(prev, Table | Image)
                and prev.caption is None
                and not any(isinstance(o, Comment | TrackedChange) and o.anchor_block_id == b.id for o in blocks)
            ):
                prev.caption = _strip_label(b.spans)
                continue
            keep.append(b)
        self.out.blocks[:] = keep

    def _container(self, elements: list[etree._Element], prefix: str, *, top: bool = False) -> None:
        for i, el in enumerate(elements):
            if top:
                self.options.ctx.check_deadline()
            path = f"{prefix}[{i}]"
            tag = local(el.tag) if ns_of(el.tag) == W else ""
            if tag == "p":
                self._paragraph(el, path)
            elif tag == "tbl":
                self._flush()
                self._table(el, path)
            elif tag == "sdt":
                if _is_toc_sdt(el):
                    continue
                content = el.find(q(W, "sdtContent"))
                if content is not None:
                    self._container(list(content), path)
            elif tag == "customXml":
                self._container(list(el), path)

    # -- paragraphs -----------------------------------------------------------------------------------------

    def _paragraph(self, p: etree._Element, path: str, textbox: bool = False) -> None:
        ppr = p.find(q(W, "pPr"))
        sid = w_val(ppr.find(q(W, "pStyle"))) if ppr is not None else None
        role = self.styles.role(sid)
        level = self.styles.heading_level(sid) if role != "title" else 1
        num_id, ilvl = self._num(ppr, sid)
        is_list = num_id is not None and level is None and role not in ("title", "subtitle", "toc")
        para_id = p.get(q(W14, "paraId"))
        prov = Provenance(source=self.source, path=path, source_id=para_id)
        if is_list:
            assert num_id is not None
            if role != "code":
                self._flush_code()
            acc = self._ensure_list(num_id, ilvl, path, para_id)
            anchor = acc.id
        else:
            self._flush_list()
            anchor = self.out.next_id()
        st = self.inline.collect(p)
        for wid in self.inline.comment_starts:
            self.comment_anchor[wid] = anchor
        self.stats.ole += st.ole
        if role == "toc" or not st.has_content():
            return
        if is_list:
            self._list_item(st, ilvl or 0, prov)
            return
        inferred = None if level is not None or role else self._inferred_level(p, st)
        if inferred is not None:
            level = inferred
            self.stats.inferred_headings += 1
        if role == "code" and level is None:
            self._code_line(st, path)
            self._after(st, anchor, prov, textbox)
            return
        self._flush_code()
        block: Block | None = self._main_block(st, level, role, prov, anchor, textbox)
        if block is not None:
            self.out.add(block)
        whole = self._whole_change(st) if level is None and block is not None else None
        self._after(st, anchor, prov, textbox, whole)

    def _main_block(
        self, st: ParaState, level: int | None, role: str | None, prov: Provenance, anchor: str, textbox: bool
    ) -> Block | None:
        attrs = {"role": "textbox"} if textbox else {}
        if level is not None:
            spans = self._spans(st.segs)
            if not spans:
                return None
            if role == "title":
                attrs["style"] = "title"
            return Heading(id=anchor, level=level, spans=spans, provenance=prov, attrs=attrs)
        if not any(s.text.strip() or s.fn_ref or s.math for s in st.segs):
            return None
        spans = [] if self._whole_change(st) is not None else self._spans(st.segs)
        if role == "quote":
            return Quote(id=anchor, spans=spans, provenance=prov, attrs=attrs)
        para_role = {"subtitle": "subtitle", "caption": "caption"}.get(role or "", "body")
        return Paragraph(
            id=anchor,
            spans=spans,
            role=para_role,
            provenance=prov,
            attrs=attrs,
        )

    def _after(self, st: ParaState, anchor: str, prov: Provenance, textbox: bool, whole: Seg | None = None) -> None:
        """Blocks that follow a paragraph: equations, images, tracked changes, comments, relocated text boxes."""
        follow: list[Block] = []
        for m in st.display_math:
            follow.append(Equation(latex=m.latex or None, text=m.text or None, provenance=prov))
        for img in st.images:
            follow.append(self._image(img.target, img.alt, prov))
        follow.extend(self._changes(st, anchor, prov, whole))
        follow.extend(self._comment_blocks(st.comment_refs, anchor))
        if self._list is not None and self._list.id == anchor:
            self._list.pending.extend(follow)
            self._list.textboxes.extend((tb, prov.path or "") for tb in st.textboxes)
            return
        for b in follow:
            self.out.add(b)
        self._textboxes(st.textboxes, prov.path or "")

    def _textboxes(self, boxes: list[etree._Element], path: str) -> None:
        if not boxes or self._depth >= _MAX_DEPTH:
            return
        self._flush()
        self._depth += 1
        try:
            for k, tb in enumerate(boxes):
                self.stats.textboxes += 1
                for j, el in enumerate(tb):
                    sub = f"{path}/textbox[{k}][{j}]"
                    if local(el.tag) == "p" and ns_of(el.tag) == W:
                        self._paragraph(el, sub, textbox=True)
                    elif local(el.tag) == "tbl":
                        self._flush()
                        self._table(el, sub)
                self._flush()
        finally:
            self._depth -= 1

    def _spans(self, segs: list[Seg]) -> list[InlineSpan]:
        """Inline spans with tracked changes in place; with tracked changes off, the accepted text."""
        sb = SpanBuilder(self.clean)
        keep = self.opts.tracked_changes
        for s in segs:
            if s.change == "delete" and not keep:
                continue
            change = s.change if keep else None
            sb.add(s.text, s.styles, s.href, s.fn_ref, s.math, change=change, change_author=s.author,
                   change_id=s.change_id)  # fmt: skip
            if s.fn_ref and s.fn_ref not in self.note_order:
                self.note_order.append(s.fn_ref)
        return sb.stripped()

    def _whole_change(self, st: ParaState) -> Seg | None:
        """The first segment when every visible segment is the same insertion, deletion, or move."""
        if not self.opts.tracked_changes:
            return None
        text = [x for x in st.segs if x.text.strip() or x.math]
        if not text or any(x.change is None for x in text):
            return None
        first = text[0]
        if any((x.change, x.author, x.move) != (first.change, first.author, first.move) for x in text):
            return None
        return first

    def _changes(self, st: ParaState, anchor: str, prov: Provenance, whole: Seg | None = None) -> list[Block]:
        if not self.opts.tracked_changes:
            return []
        out: list[Block] = []
        if whole is not None:
            sb = SpanBuilder(self.clean)
            for x in st.segs:
                if x.change is not None:
                    sb.add(x.text, x.styles, x.href, None, x.math)
            out.append(
                TrackedChange(
                    change="insert" if whole.change == "insert" else "delete",
                    author=whole.author,
                    created=whole.date,
                    spans=sb.stripped(),
                    anchor_block_id=anchor,
                    provenance=prov,
                    attrs={"move": whole.move, "scope": "paragraph"} if whole.move else {"scope": "paragraph"},
                )
            )
        for fc in st.format_changes:
            out.append(
                TrackedChange(
                    change="format",
                    author=fc.author,
                    created=fc.date,
                    spans=[InlineSpan(text=clean_text(fc.text, self.clean))],
                    anchor_block_id=anchor,
                    provenance=prov,
                )
            )
        return out

    # -- lists and code -------------------------------------------------------------------------------------

    def _num(self, ppr: etree._Element | None, sid: str | None) -> tuple[str | None, int | None]:
        num_id: str | None = None
        ilvl: int | None = None
        num_pr = ppr.find(q(W, "numPr")) if ppr is not None else None
        if num_pr is not None:
            num_id = w_val(num_pr.find(q(W, "numId")))
            lv = w_val(num_pr.find(q(W, "ilvl")))
            ilvl = int(lv) if lv and lv.isdigit() else None
        if num_id is None:
            num_id, style_ilvl = self.styles.numbering(sid)
            ilvl = ilvl if ilvl is not None else style_ilvl
        if not self.numbering.known(num_id):
            return None, None
        return num_id, min(ilvl or 0, 8)

    def _ensure_list(self, num_id: str, ilvl: int | None, path: str, para_id: str | None) -> _ListAcc:
        acc = self._list
        if acc is not None and (acc.num_id == num_id or (ilvl or 0) > 0):
            return acc
        self._flush_list()
        acc = _ListAcc(
            id=self.out.next_id(),
            num_id=num_id,
            ordered=self.numbering.ordered(num_id, 0),
            path=path,
            source_id=para_id,
            start=self.numbering.start(num_id, 0),
        )
        self._list = acc
        return acc

    def _list_item(self, st: ParaState, ilvl: int, prov: Provenance) -> None:
        acc = self._list
        assert acc is not None
        item = ListItem(spans=self._spans(st.segs), provenance=prov)
        depth = min(ilvl, len(acc.last))
        if depth == 0 or not acc.last:
            acc.items.append(item)
            depth = 0
        else:
            parent = acc.last[depth - 1]
            if not parent.children:
                parent.children_ordered = self.numbering.ordered(acc.num_id, ilvl)
            parent.children.append(item)
        del acc.last[depth:]
        acc.last.append(item)
        self._after(st, acc.id, prov, False)

    def _flush_list(self) -> None:
        acc, self._list = self._list, None
        if acc is None:
            return
        if acc.items:
            self.out.add(
                ListBlock(
                    id=acc.id,
                    ordered=acc.ordered,
                    start=acc.start if acc.ordered else 1,
                    items=acc.items,
                    provenance=Provenance(source=self.source, path=acc.path, source_id=acc.source_id),
                )
            )
        for b in acc.pending:
            self.out.add(b)
        for tb, path in acc.textboxes:
            self._textboxes([tb], path)

    def _code_line(self, st: ParaState, path: str) -> None:
        line = clean_text("".join(s.text for s in st.segs if s.change != "delete"), self.clean)
        if self._code is None:
            self._code = _CodeAcc(lines=[], path=path)
        self._code.lines.append(line)

    def _flush_code(self) -> None:
        acc, self._code = self._code, None
        if acc is not None and any(line.strip() for line in acc.lines):
            self.out.add(CodeBlock(code="\n".join(acc.lines), provenance=Provenance(source=self.source, path=acc.path)))

    def _flush(self) -> None:
        self._flush_code()
        self._flush_list()

    # -- inferred headings ----------------------------------------------------------------------------------

    def _candidate_size(self, p: etree._Element, st: ParaState | None = None) -> float | None:
        """Font size of a short, all-bold paragraph at least 1.3x the Normal size; None otherwise."""
        ppr = p.find(q(W, "pPr"))
        sid = w_val(ppr.find(q(W, "pStyle"))) if ppr is not None else None
        if self.styles.heading_level(sid) is not None or self.styles.role(sid) or self._num(ppr, sid)[0]:
            return None
        sizes: list[float] = []
        text = ""
        for r in p.iter(q(W, "r")):
            t = "".join(x.text or "" for x in r.iter(q(W, "t")))
            if not t.strip():
                continue
            rpr = r.find(q(W, "rPr"))
            char_sid = w_val(rpr.find(q(W, "rStyle"))) if rpr is not None else None
            from intomd_converters.office.docx_parts import RunProps

            eff = RunProps.parse(rpr).over(self.styles.run_props(sid, char_sid))
            if not eff.bold:
                return None
            sizes.append(eff.size or self._normal)
            text += t
        if not sizes or len(text.strip()) > 150 or text.strip().endswith((".", ":", ";", ",")):
            return None
        size = max(sizes)
        return size if size >= 1.3 * self._normal else None

    def _prescan(self, body: etree._Element) -> None:
        sizes = {s for p in body.iter(q(W, "p")) if (s := self._candidate_size(p)) is not None}
        self._inferred = {s: min(6, i + 1) for i, s in enumerate(sorted(sizes, reverse=True))}

    def _inferred_level(self, p: etree._Element, st: ParaState) -> int | None:
        if not self._inferred:
            return None
        size = self._candidate_size(p, st)
        return self._inferred.get(size) if size is not None else None

    # -- tables ---------------------------------------------------------------------------------------------

    def _table(self, tbl: etree._Element, path: str) -> None:
        if self._depth >= _MAX_DEPTH:
            return
        anchor = self.out.next_id()
        cells: list[TableCell] = []
        follow: list[Block] = []
        nested: list[tuple[etree._Element, str]] = []
        rows = [c for c in _children(tbl) if local(c.tag) == "tr"]
        grid_cols = len(tbl.findall(f"{q(W, 'tblGrid')}/{q(W, 'gridCol')}"))
        active: dict[int, TableCell] = {}
        n_cols = grid_cols
        header_rows = 0
        header_run = True
        for ri, tr in enumerate(rows):
            self.options.ctx.check_deadline()
            trpr = tr.find(q(W, "trPr"))
            is_header = trpr is not None and on_off(trpr.find(q(W, "tblHeader"))) is True
            if header_run and is_header:
                header_rows += 1
            else:
                header_run = False
            col = _int(w_val(trpr.find(q(W, "gridBefore"))) if trpr is not None else None, 0)
            for ci, tc in enumerate(c for c in _children(tr) if local(c.tag) == "tc"):
                tcpr = tc.find(q(W, "tcPr"))
                span = max(1, _int(w_val(tcpr.find(q(W, "gridSpan"))) if tcpr is not None else None, 1))
                vm_el = tcpr.find(q(W, "vMerge")) if tcpr is not None else None
                vm = None if vm_el is None else (w_val(vm_el) or "continue")
                if vm == "continue" and col in active:
                    active[col].row_span += 1
                    col += span
                    continue
                spans = self._cell(tc, f"{path}/r{ri}c{ci}", anchor, follow, nested)
                cell = TableCell(spans=spans, row=ri, col=col, col_span=span, is_header=is_header)
                cells.append(cell)
                for k in range(col, col + span):
                    active.pop(k, None)
                if vm == "restart":
                    active[col] = cell
                col += span
            n_cols = max(n_cols, col)
        if not header_rows and len(rows) > 1 and (_first_row_flag(tbl) or _first_row_bold(cells)):
            header_rows = 1
        for c in cells:
            c.is_header = c.row < header_rows
        n_rows = len(rows)
        if not cells:
            return
        self.out.add(
            Table(
                id=anchor,
                cells=cells,
                n_rows=n_rows,
                n_cols=max(n_cols, 1),
                header_rows=header_rows,
                provenance=Provenance(source=self.source, path=path),
            )
        )
        for b in follow:
            self.out.add(b)
        self._depth += 1
        try:
            for el, npath in nested:
                self._table(el, npath)
        finally:
            self._depth -= 1

    def _cell(
        self,
        tc: etree._Element,
        path: str,
        anchor: str,
        follow: list[Block],
        nested: list[tuple[etree._Element, str]],
    ) -> list[InlineSpan]:
        out: list[InlineSpan] = []
        prov = Provenance(source=self.source, path=path)
        for el in _children(tc):
            tag = local(el.tag)
            if tag == "tbl":
                nested.append((el, path))
                continue
            if tag != "p":
                continue
            st = self.inline.collect(el)
            for wid in self.inline.comment_starts:
                self.comment_anchor[wid] = anchor
            spans = self._spans(st.segs)
            if spans:
                if out:
                    out.append(InlineSpan(text="\n"))
                out.extend(spans)
            for img in st.images:
                follow.append(self._image(img.target, img.alt, prov))
            follow.extend(self._changes(st, anchor, prov))
            follow.extend(self._comment_blocks(st.comment_refs, anchor))
            self.stats.ole += st.ole
        return out

    # -- images, notes, comments ----------------------------------------------------------------------------

    def _image(self, target: str, alt: str | None, prov: Provenance) -> Image:
        self.stats.images += 1
        ext = posixpath.splitext(target)[1].lower()
        ref = target
        if self.options.extract_images and self.options.image_dir and self.pkg.has(target):
            name = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in posixpath.basename(target))[:100]
            dest = Path(self.options.image_dir) / name
            try:
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(self.pkg.read(target))
                ref = str(dest)
            except OSError:
                ref = target
        return Image(
            ref=ref, alt=clean_text(alt, self.clean) if alt else None, mime=_IMAGE_MIMES.get(ext), provenance=prov
        )

    def _load_notes(self, part: str | None, tag: str) -> dict[str, etree._Element]:
        root = self.pkg.xml(part) if part else None
        if root is None:
            return {}
        out: dict[str, etree._Element] = {}
        for n in root.iter(q(W, tag)):
            kind = n.get(q(W, "type")) or "normal"
            if kind in ("separator", "continuationSeparator", "continuationNotice"):
                continue
            out[n.get(q(W, "id")) or ""] = n
        return out

    def _footnotes(self) -> None:
        counters = {"fn": 0, "en": 0}
        for ref in list(self.note_order):
            kind, _, wid = ref.partition("-")
            note = self.notes.get(kind, {}).get(wid)
            counters[kind] = counters.get(kind, 0) + 1
            n = counters[kind]
            marker = str(n) if kind == "fn" else _roman(n)
            spans: list[InlineSpan] = []
            if note is not None:
                for p in note.iter(q(W, "p")):
                    st = self.inline.isolated(p)
                    ps = self._spans(st.segs)
                    if ps:
                        if spans:
                            spans.append(InlineSpan(text="\n"))
                        spans.extend(ps)
            self.out.add(
                Footnote(
                    id=ref,
                    marker=marker,
                    spans=spans,
                    provenance=Provenance(
                        source=self.source, path=f"{'footnotes' if kind == 'fn' else 'endnotes'}/{wid}", source_id=wid
                    ),
                    attrs={"kind": "footnote" if kind == "fn" else "endnote"},
                )
            )

    def _comment_blocks(self, wids: list[str], anchor: str) -> list[Block]:
        if not self.opts.comments:
            return []
        out: list[Block] = []
        for wid in wids:
            info = self.comments.get(wid)
            if info is None or wid in self.comment_ids:
                continue
            out.append(self._comment(info, self.comment_anchor.get(wid, anchor)))
        return out

    def _comment(self, info: CommentInfo, anchor: str | None) -> Comment:
        sb = SpanBuilder(self.clean)
        for i, p in enumerate(info.paragraphs):
            if i:
                sb.add("\n")
            sb.add("".join(t.text or "" for t in p.iter(q(W, "t"))))
        covered = self.inline.closed_comments.get(info.wid) or "".join(self.inline.active_comments.get(info.wid, []))
        cid = f"c-{info.wid}"
        self.comment_ids[info.wid] = cid
        return Comment(
            id=cid,
            author=info.author,
            created=info.date,
            spans=sb.stripped(),
            anchor_block_id=anchor,
            anchor_text=clean_text(covered, self.clean).strip() or None,
            resolved=info.resolved,
            provenance=Provenance(source=self.source, path=f"comments/{info.wid}", source_id=info.wid),
        )

    def _orphan_comments(self) -> None:
        if not self.opts.comments:
            return
        for wid, info in self.comments.items():
            if wid not in self.comment_ids:
                self.out.add(self._comment(info, self.comment_anchor.get(wid)))

    def _link_replies(self) -> None:
        ids = {b.id for b in self.out.blocks}
        for b in self.out.blocks:
            if isinstance(b, Comment | TrackedChange) and b.anchor_block_id and b.anchor_block_id not in ids:
                b.anchor_block_id = None
            if isinstance(b, Comment):
                info = self.comments.get(b.provenance.source_id or "")
                if info is not None and info.parent_wid in self.comment_ids:
                    b.reply_to = self.comment_ids[info.parent_wid]


_LABEL = re.compile(r"^\s*(table|figure|fig\.|chart)\s+\d+\s*[:.\-]?\s*", re.I)


def _strip_label(spans: list[InlineSpan]) -> list[InlineSpan]:
    """Drop a leading "Table 3:" label (the renderer numbers captions itself); keep the spans otherwise."""
    if not spans or spans[0].footnote_ref is not None:
        return spans
    rest = _LABEL.sub("", spans[0].text, count=1)
    if rest == spans[0].text or (not rest.strip() and len(spans) == 1):
        return spans
    return [spans[0].model_copy(update={"text": rest}), *spans[1:]]


def _children(el: etree._Element) -> list[etree._Element]:
    """Children with content-control and customXml wrappers unwrapped."""
    out: list[etree._Element] = []
    for c in el:
        tag = local(c.tag)
        if tag == "sdt":
            content = c.find(q(W, "sdtContent"))
            if content is not None:
                out.extend(_children(content))
        elif tag == "customXml":
            out.extend(_children(c))
        else:
            out.append(c)
    return out


def _int(v: str | None, default: int) -> int:
    return int(v) if v and v.isdigit() else default


def _is_toc_sdt(el: etree._Element) -> bool:
    gallery = el.find(f"{q(W, 'sdtPr')}/{q(W, 'docPartObj')}/{q(W, 'docPartGallery')}")
    return gallery is not None and "table of contents" in (w_val(gallery) or "").lower()


def _first_row_flag(tbl: etree._Element) -> bool:
    look = tbl.find(f"{q(W, 'tblPr')}/{q(W, 'tblLook')}")
    if look is None:
        return False
    if look.get(q(W, "firstRow")) is not None:
        return look.get(q(W, "firstRow")) in ("1", "true", "on")
    try:
        return bool(int(look.get(q(W, "val")) or "0", 16) & 0x0020)
    except ValueError:
        return False


def _first_row_bold(cells: list[TableCell]) -> bool:
    first = [c for c in cells if c.row == 0]
    spans = [s for c in first for s in c.spans if s.text.strip()]
    return bool(spans) and all("bold" in s.styles for s in spans)
