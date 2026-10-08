"""DOCX paragraph-content collection: runs, tracked changes, hyperlinks, fields, comments, notes, drawings.

`InlineCollector.collect(p)` walks one `w:p` and returns a `ParaState` of segments (text with styling and an
optional tracked-change kind), images, text boxes, display equations, and comment references. Field state
(`w:fldChar` begin/separate/end) spans paragraphs, so it lives on the collector.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from datetime import datetime

from lxml import etree  # type: ignore[import-untyped]

from intomd.ir import InlineStyle
from intomd_converters.office._common import parse_datetime, safe_href
from intomd_converters.office._ooxml_ns import MC, WP, A, R, V, W, local, ns_of, q
from intomd_converters.office._package import OfficePackage, Rel
from intomd_converters.office.docx_parts import RunProps, Styles, is_mono, w_val
from intomd_converters.office.omml import MathResult, omml_to_latex

_HYPERLINK_FIELD = re.compile(r'^\s*HYPERLINK\s+"([^"]+)"', re.I)
_MAX_FIELDS = 64
_SYMBOL_FONTS = ("symbol", "wingdings", "webdings")


@dataclass(slots=True)
class Seg:
    text: str
    styles: tuple[InlineStyle, ...] = ()
    href: str | None = None
    fn_ref: str | None = None
    math: str | None = None
    change: str | None = None
    """None, 'insert', or 'delete' (moves map to delete at the origin and insert at the destination)."""
    move: str | None = None
    author: str | None = None
    date: datetime | None = None
    change_id: str | None = None


@dataclass(slots=True)
class ImageRef:
    target: str
    alt: str | None
    anchored: bool


@dataclass(slots=True)
class FormatChange:
    text: str
    author: str | None
    date: datetime | None


@dataclass(slots=True)
class ParaState:
    style_id: str | None
    segs: list[Seg] = field(default_factory=list)
    images: list[ImageRef] = field(default_factory=list)
    textboxes: list[etree._Element] = field(default_factory=list)
    display_math: list[MathResult] = field(default_factory=list)
    comment_refs: list[str] = field(default_factory=list)
    format_changes: list[FormatChange] = field(default_factory=list)
    ole: int = 0

    def has_content(self) -> bool:
        return bool(
            any(s.text.strip() or s.fn_ref or s.math for s in self.segs)
            or self.images
            or self.textboxes
            or self.display_math
            or self.comment_refs
        )


@dataclass(slots=True, frozen=True)
class _Ctx:
    change: str | None = None
    move: str | None = None
    author: str | None = None
    date: datetime | None = None
    href: str | None = None
    change_id: str | None = None


@dataclass(slots=True)
class _Field:
    instr: str = ""
    result: bool = False


@dataclass(slots=True)
class Counters:
    hidden_runs: int = 0
    hidden_text: list[str] = field(default_factory=list)
    math_partial: int = 0


class InlineCollector:
    def __init__(self, pkg: OfficePackage, rels: dict[str, Rel], styles: Styles, counters: Counters) -> None:
        self.pkg = pkg
        self.rels = rels
        self.styles = styles
        self.counters = counters
        self.fields: list[_Field] = []
        self.active_comments: dict[str, list[str]] = {}
        """Comment id -> anchored text collected while its range is open."""
        self.closed_comments: dict[str, str] = {}
        self.comment_starts: list[str] = []
        """Comment ids whose range started in the paragraph being collected."""

    # -- public ---------------------------------------------------------------------------------------------

    def collect(self, p: etree._Element) -> ParaState:
        ppr = p.find(q(W, "pPr"))
        sid = w_val(ppr.find(q(W, "pStyle"))) if ppr is not None else None
        st = ParaState(style_id=sid)
        self.comment_starts = []
        self._inline(p, st, _Ctx())
        return st

    def isolated(self, p: etree._Element) -> ParaState:
        """Collect a paragraph outside the body flow (notes, comments): fresh field and comment state."""
        saved = (self.fields, self.active_comments, self.closed_comments, self.comment_starts)
        self.fields, self.active_comments, self.closed_comments = [], {}, {}
        try:
            return self.collect(p)
        finally:
            self.fields, self.active_comments, self.closed_comments, self.comment_starts = saved

    # -- walking --------------------------------------------------------------------------------------------

    def _inline(self, el: etree._Element, st: ParaState, ctx: _Ctx) -> None:
        for child in el:
            ns, tag = ns_of(child.tag), local(child.tag)
            if ns == W:
                if tag == "r":
                    self._run(child, st, ctx)
                elif tag in ("ins", "del", "moveFrom", "moveTo"):
                    kind = "insert" if tag in ("ins", "moveTo") else "delete"
                    move = {"moveFrom": "from", "moveTo": "to"}.get(tag)
                    wid = child.get(q(W, "id")) or ""
                    sub = replace(
                        ctx,
                        change=kind,
                        move=move,
                        change_id=f"{tag}:{wid}" if move else wid or None,
                        author=child.get(q(W, "author")) or None,
                        date=parse_datetime(child.get(q(W, "date"))),
                    )
                    self._inline(child, st, sub)
                elif tag == "hyperlink":
                    rel = self.rels.get(child.get(q(R, "id")) or "")
                    href = safe_href(rel.target) if rel is not None and rel.external else None
                    self._inline(child, st, replace(ctx, href=href or ctx.href))
                elif tag == "fldSimple":
                    if len(self.fields) < _MAX_FIELDS:
                        self.fields.append(_Field(instr=child.get(q(W, "instr")) or "", result=True))
                        self._inline(child, st, ctx)
                        self.fields.pop()
                elif tag == "sdt":
                    content = child.find(q(W, "sdtContent"))
                    if content is not None:
                        self._inline(content, st, ctx)
                elif tag in ("smartTag", "customXml", "bdo", "dir", "sdtContent"):
                    self._inline(child, st, ctx)
                elif tag == "commentRangeStart":
                    wid = child.get(q(W, "id")) or ""
                    self.active_comments[wid] = []
                    self.comment_starts.append(wid)
                elif tag == "commentRangeEnd":
                    wid = child.get(q(W, "id")) or ""
                    self.closed_comments[wid] = "".join(self.active_comments.pop(wid, []))
            elif ns == "http://schemas.openxmlformats.org/officeDocument/2006/math":
                self._math(child, st, ctx, tag)
            elif ns == MC and tag == "AlternateContent":
                branch = _alt_branch(child)
                if branch is not None:
                    self._inline(branch, st, ctx)

    def _math(self, el: etree._Element, st: ParaState, ctx: _Ctx, tag: str) -> None:
        if tag == "oMathPara":
            res = omml_to_latex(el)
            self.counters.math_partial += int(res.partial)
            st.display_math.append(res)
        elif tag == "oMath":
            res = omml_to_latex(el)
            self.counters.math_partial += int(res.partial)
            st.segs.append(
                Seg(
                    text=res.text,
                    math=res.latex,
                    change=ctx.change,
                    author=ctx.author,
                    date=ctx.date,
                    change_id=ctx.change_id,
                )
            )

    def _run(self, r: etree._Element, st: ParaState, ctx: _Ctx) -> None:
        rpr = r.find(q(W, "rPr"))
        char_sid = w_val(rpr.find(q(W, "rStyle"))) if rpr is not None else None
        eff = RunProps.parse(rpr).over(self.styles.run_props(st.style_id, char_sid))
        hidden = bool(eff.vanish) or ((eff.color or "").upper() == "FFFFFF" and not eff.shaded)
        styles = _styles(eff)
        fmt_change = rpr is not None and rpr.find(q(W, "rPrChange")) is not None
        for child in r:
            ns, tag = ns_of(child.tag), local(child.tag)
            if ns == MC and tag == "AlternateContent":
                branch = _alt_branch(child)
                if branch is not None:
                    fake = etree.Element(q(W, "r"))
                    if rpr is not None:
                        fake.append(_copy(rpr))
                    for c in branch:
                        fake.append(_copy(c))
                    self._run(fake, st, ctx)
                continue
            if ns != W:
                continue
            text: str | None = None
            if tag in ("t", "delText"):
                text = child.text or ""
            elif tag in ("tab", "ptab"):
                text = "\t"
            elif tag == "br":
                text = None if (child.get(q(W, "type")) or "") in ("page", "column") else "\n"
            elif tag == "cr":
                text = "\n"
            elif tag == "noBreakHyphen":
                text = "-"
            elif tag == "sym":
                text = _sym(child)
            elif tag in ("footnoteReference", "endnoteReference"):
                if not self._suppressed():
                    prefix = "fn" if tag == "footnoteReference" else "en"
                    st.segs.append(Seg(text="", fn_ref=f"{prefix}-{child.get(q(W, 'id')) or ''}", change=ctx.change))
            elif tag == "commentReference":
                st.comment_refs.append(child.get(q(W, "id")) or "")
            elif tag == "drawing":
                self._drawing(child, st)
            elif tag == "pict":
                self._pict(child, st)
            elif tag == "object":
                st.ole += 1
                self._pict(child, st)
            elif tag == "fldChar":
                self._fld_char(child)
            elif tag == "instrText" and self.fields and not self.fields[-1].result:
                self.fields[-1].instr += child.text or ""
            if text is None or not text:
                continue
            if self._suppressed():
                continue
            if hidden:
                if text.strip():
                    self.counters.hidden_runs += 1
                    self.counters.hidden_text.append(text)
                continue
            for parts in self.active_comments.values():
                if ctx.change != "delete":
                    parts.append(text)
            href = self._field_href() or ctx.href
            st.segs.append(
                Seg(
                    text=text,
                    styles=styles,
                    href=href,
                    change=ctx.change,
                    move=ctx.move,
                    author=ctx.author,
                    date=ctx.date,
                    change_id=ctx.change_id,
                )
            )
            if fmt_change and ctx.change is None and text.strip():
                chg = rpr.find(q(W, "rPrChange")) if rpr is not None else None
                st.format_changes.append(
                    FormatChange(
                        text=text,
                        author=(chg.get(q(W, "author")) or None) if chg is not None else None,
                        date=parse_datetime(chg.get(q(W, "date"))) if chg is not None else None,
                    )
                )

    # -- fields ---------------------------------------------------------------------------------------------

    def _fld_char(self, el: etree._Element) -> None:
        kind = el.get(q(W, "fldCharType")) or ""
        if kind == "begin":
            if len(self.fields) < _MAX_FIELDS:
                self.fields.append(_Field())
        elif kind == "separate":
            if self.fields:
                self.fields[-1].result = True
        elif kind == "end" and self.fields:
            self.fields.pop()

    def _suppressed(self) -> bool:
        """Inside a field's instruction part, or inside a TOC / index field's result."""
        for f in self.fields:
            if not f.result:
                return True
            head = f.instr.strip().upper()
            if head.startswith(("TOC", "INDEX")):
                return True
        return False

    def _field_href(self) -> str | None:
        for f in reversed(self.fields):
            m = _HYPERLINK_FIELD.match(f.instr)
            if f.result and m:
                return safe_href(m.group(1))
        return None

    # -- drawings -------------------------------------------------------------------------------------------

    def _drawing(self, d: etree._Element, st: ParaState) -> None:
        holder = d[0] if len(d) else None
        anchored = holder is not None and local(holder.tag) == "anchor"
        doc_pr = d.find(f".//{q(WP, 'docPr')}")
        alt = None
        if doc_pr is not None:
            alt = (doc_pr.get("descr") or doc_pr.get("title") or "").strip() or None
        blip = next(iter(d.iter(q(A, "blip"))), None)
        if blip is not None:
            rid = blip.get(q(R, "embed")) or blip.get(q(R, "link")) or ""
            rel = self.rels.get(rid)
            if rel is not None and not rel.external:
                st.images.append(ImageRef(target=rel.target, alt=alt, anchored=anchored))
        st.textboxes.extend(_top_level_textboxes(d))

    def _pict(self, el: etree._Element, st: ParaState) -> None:
        for img in el.iter(q(V, "imagedata")):
            rel = self.rels.get(img.get(q(R, "id")) or "")
            if rel is not None and not rel.external:
                alt = (img.get(q("urn:schemas-microsoft-com:office:office", "title")) or "").strip() or None
                st.images.append(ImageRef(target=rel.target, alt=alt, anchored=True))
        st.textboxes.extend(_top_level_textboxes(el))


def _styles(eff: RunProps) -> tuple[InlineStyle, ...]:
    out: list[InlineStyle] = []
    if eff.bold:
        out.append(InlineStyle.BOLD)
    if eff.italic:
        out.append(InlineStyle.ITALIC)
    if eff.strike:
        out.append(InlineStyle.STRIKE)
    if eff.vert == "superscript":
        out.append(InlineStyle.SUPERSCRIPT)
    elif eff.vert == "subscript":
        out.append(InlineStyle.SUBSCRIPT)
    if is_mono(eff.font):
        out.append(InlineStyle.CODE)
    return tuple(out)


def _sym(el: etree._Element) -> str | None:
    font = (el.get(q(W, "font")) or "").lower()
    code = el.get(q(W, "char")) or ""
    if any(f in font for f in _SYMBOL_FONTS):
        return None
    try:
        n = int(code, 16)
    except ValueError:
        return None
    if 0xF000 <= n <= 0xF0FF:
        n -= 0xF000
    return chr(n) if 0x20 <= n < 0x110000 else None


def _alt_branch(el: etree._Element) -> etree._Element | None:
    """mc:AlternateContent: the first Choice (Word always writes one we understand), else the Fallback."""
    choice = el.find(q(MC, "Choice"))
    return choice if choice is not None else el.find(q(MC, "Fallback"))


def _top_level_textboxes(el: etree._Element) -> list[etree._Element]:
    out: list[etree._Element] = []
    for tb in el.iter(q(W, "txbxContent")):
        parent = tb.getparent()
        nested = False
        while parent is not None and parent is not el:
            if parent.tag == q(W, "txbxContent"):
                nested = True
                break
            parent = parent.getparent()
        if not nested:
            out.append(tb)
    return out


def _copy(el: etree._Element) -> etree._Element:
    import copy

    return copy.deepcopy(el)
