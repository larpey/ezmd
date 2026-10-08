"""DOCX side parts: styles (heading levels through basedOn), numbering (ordered vs bullet), comments with
replies and resolved state, and core/app properties. All read with the hardened parser from `_package`."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime

from lxml import etree  # type: ignore[import-untyped]

from intomd_converters.office._common import parse_datetime
from intomd_converters.office._ooxml_ns import CP, DC, DCTERMS, EP, W14, W15, W, q
from intomd_converters.office._package import OfficePackage

_HEADING_NAME = re.compile(r"^heading\s*([1-9])$", re.I)
_QUOTE_NAMES = ("quote", "intense quote", "block text")
_CODE_NAME = re.compile(r"(^|\s)(code|source|preformatted|verbatim|listing)(\s|$)", re.I)
_MONO_FONTS = ("courier", "consolas", "menlo", "monaco", "source code", "lucida console", "mono", "fira code")
_FALSE = ("0", "false", "off", "none")


def w_val(el: etree._Element | None, attr: str = "val") -> str | None:
    if el is None:
        return None
    v = el.get(q(W, attr))
    return str(v) if v is not None else None


def on_off(el: etree._Element | None) -> bool | None:
    """OOXML boolean property: present without val means true."""
    if el is None:
        return None
    v = w_val(el)
    return v is None or v.lower() not in _FALSE


def is_mono(font: str | None) -> bool:
    return bool(font) and any(m in str(font).lower() for m in _MONO_FONTS)


@dataclass(slots=True)
class RunProps:
    bold: bool | None = None
    italic: bool | None = None
    strike: bool | None = None
    underline: bool | None = None
    vert: str | None = None
    size: float | None = None
    font: str | None = None
    color: str | None = None
    vanish: bool | None = None
    shaded: bool = False

    @classmethod
    def parse(cls, rpr: etree._Element | None) -> RunProps:
        rp = cls()
        if rpr is None:
            return rp
        rp.bold = on_off(rpr.find(q(W, "b")))
        rp.italic = on_off(rpr.find(q(W, "i")))
        strike = on_off(rpr.find(q(W, "strike")))
        dstrike = on_off(rpr.find(q(W, "dstrike")))
        rp.strike = None if strike is None and dstrike is None else bool(strike or dstrike)
        u = rpr.find(q(W, "u"))
        rp.underline = None if u is None else (w_val(u) or "single").lower() != "none"
        rp.vert = w_val(rpr.find(q(W, "vertAlign")))
        sz = w_val(rpr.find(q(W, "sz")))
        if sz and sz.isdigit():
            rp.size = int(sz) / 2.0
        fonts = rpr.find(q(W, "rFonts"))
        if fonts is not None:
            rp.font = fonts.get(q(W, "ascii")) or fonts.get(q(W, "hAnsi"))
        rp.color = w_val(rpr.find(q(W, "color")))
        rp.vanish = on_off(rpr.find(q(W, "vanish")))
        shd = rpr.find(q(W, "shd"))
        fill = (shd.get(q(W, "fill")) or "").upper() if shd is not None else ""
        rp.shaded = fill not in ("", "AUTO", "FFFFFF") or rpr.find(q(W, "highlight")) is not None
        return rp

    def over(self, base: RunProps) -> RunProps:
        """This run's properties layered over `base` (None falls through)."""
        return RunProps(
            bold=self.bold if self.bold is not None else base.bold,
            italic=self.italic if self.italic is not None else base.italic,
            strike=self.strike if self.strike is not None else base.strike,
            underline=self.underline if self.underline is not None else base.underline,
            vert=self.vert if self.vert is not None else base.vert,
            size=self.size if self.size is not None else base.size,
            font=self.font if self.font is not None else base.font,
            color=self.color if self.color is not None else base.color,
            vanish=self.vanish if self.vanish is not None else base.vanish,
            shaded=self.shaded or base.shaded,
        )


@dataclass(slots=True)
class Style:
    id: str
    name: str
    type: str
    based_on: str | None
    outline_lvl: int | None
    num_id: str | None
    ilvl: int | None
    rpr: RunProps


@dataclass(slots=True)
class Styles:
    by_id: dict[str, Style] = field(default_factory=dict)
    default_para: str | None = None
    defaults: RunProps = field(default_factory=RunProps)

    @classmethod
    def load(cls, pkg: OfficePackage, part: str | None) -> Styles:
        st = cls()
        root = pkg.xml(part) if part else None
        if root is None:
            return st
        dd = root.find(f"{q(W, 'docDefaults')}/{q(W, 'rPrDefault')}/{q(W, 'rPr')}")
        st.defaults = RunProps.parse(dd)
        for el in root.iter(q(W, "style")):
            sid = el.get(q(W, "styleId")) or ""
            if not sid:
                continue
            ppr = el.find(q(W, "pPr"))
            outline = w_val(ppr.find(q(W, "outlineLvl"))) if ppr is not None else None
            num = ppr.find(f"{q(W, 'numPr')}") if ppr is not None else None
            num_id = w_val(num.find(q(W, "numId"))) if num is not None else None
            ilvl = w_val(num.find(q(W, "ilvl"))) if num is not None else None
            style = Style(
                id=sid,
                name=(w_val(el.find(q(W, "name"))) or sid).strip(),
                type=el.get(q(W, "type")) or "paragraph",
                based_on=w_val(el.find(q(W, "basedOn"))),
                outline_lvl=int(outline) if outline and outline.isdigit() else None,
                num_id=num_id,
                ilvl=int(ilvl) if ilvl and ilvl.isdigit() else None,
                rpr=RunProps.parse(el.find(q(W, "rPr"))),
            )
            st.by_id[sid] = style
            if style.type == "paragraph" and on_off_attr(el.get(q(W, "default"))):
                st.default_para = sid
        return st

    def chain(self, sid: str | None) -> list[Style]:
        out: list[Style] = []
        seen: set[str] = set()
        cur = sid if sid in self.by_id else self.default_para
        while cur and cur in self.by_id and cur not in seen and len(out) < 32:
            seen.add(cur)
            s = self.by_id[cur]
            out.append(s)
            cur = s.based_on
        return out

    def name(self, sid: str | None) -> str:
        if sid and sid in self.by_id:
            return self.by_id[sid].name
        if self.default_para and self.default_para in self.by_id:
            return self.by_id[self.default_para].name
        return "Normal"

    def heading_level(self, sid: str | None) -> int | None:
        """`Heading N` names to N, `Title` to 1, otherwise an outline level k (0-based) through basedOn to k+1."""
        for s in self.chain(sid):
            m = _HEADING_NAME.match(s.name)
            if m:
                return int(m.group(1))
            if s.name.lower() == "title":
                return 1
            if s.outline_lvl is not None and s.outline_lvl < 9:
                return min(6, s.outline_lvl + 1)
        return None

    def role(self, sid: str | None) -> str | None:
        """'subtitle', 'quote', 'code', 'caption', 'toc', 'title' from the style chain names."""
        for s in self.chain(sid):
            n = s.name.lower()
            if n == "subtitle":
                return "subtitle"
            if n == "title":
                return "title"
            if n in _QUOTE_NAMES:
                return "quote"
            if n == "caption":
                return "caption"
            if n.startswith("toc ") or n == "toc heading":
                return "toc"
            if _CODE_NAME.search(n) or n == "html preformatted":
                return "code"
        return None

    def numbering(self, sid: str | None) -> tuple[str | None, int | None]:
        for s in self.chain(sid):
            if s.num_id is not None:
                return s.num_id, s.ilvl
        return None, None

    def run_props(self, para_sid: str | None, char_sid: str | None) -> RunProps:
        """Effective style-level run properties: char style over paragraph style chain over docDefaults."""
        base = self.defaults
        for s in reversed(self.chain(para_sid)):
            base = s.rpr.over(base)
        if char_sid and char_sid in self.by_id:
            seen: list[Style] = []
            cur: str | None = char_sid
            while cur and cur in self.by_id and len(seen) < 32 and self.by_id[cur] not in seen:
                seen.append(self.by_id[cur])
                cur = self.by_id[cur].based_on
            for s in reversed(seen):
                base = s.rpr.over(base)
        return base

    def normal_size(self) -> float:
        return self.run_props(self.default_para, None).size or 11.0


def on_off_attr(v: str | None) -> bool:
    return v is not None and v.lower() not in _FALSE


@dataclass(slots=True)
class Numbering:
    """numId -> {ilvl: numFmt}, and numId -> {ilvl: start number} (w:start, overridden by startOverride)."""

    fmts: dict[str, dict[int, str]] = field(default_factory=dict)
    starts: dict[str, dict[int, int]] = field(default_factory=dict)

    @classmethod
    def load(cls, pkg: OfficePackage, part: str | None) -> Numbering:
        nb = cls()
        root = pkg.xml(part) if part else None
        if root is None:
            return nb
        abstract: dict[str, dict[int, str]] = {}
        abstract_starts: dict[str, dict[int, int]] = {}
        for an in root.iter(q(W, "abstractNum")):
            aid = an.get(q(W, "abstractNumId")) or ""
            abstract[aid] = _levels(an)
            abstract_starts[aid] = _starts(an)
        for num in root.iter(q(W, "num")):
            nid = num.get(q(W, "numId")) or ""
            aid = w_val(num.find(q(W, "abstractNumId"))) or ""
            levels = dict(abstract.get(aid, {}))
            starts = dict(abstract_starts.get(aid, {}))
            for ov in num.iter(q(W, "lvlOverride")):
                lvl_el = ov.find(q(W, "lvl"))
                ilvl = ov.get(q(W, "ilvl")) or ""
                fmt = w_val(lvl_el.find(q(W, "numFmt"))) if lvl_el is not None else None
                if fmt and ilvl.isdigit():
                    levels[int(ilvl)] = fmt
                start = _int_val(ov.find(q(W, "startOverride")))
                if start is None and lvl_el is not None:
                    start = _int_val(lvl_el.find(q(W, "start")))
                if start is not None and ilvl.isdigit():
                    starts[int(ilvl)] = start
            nb.fmts[nid] = levels
            nb.starts[nid] = starts
        return nb

    def ordered(self, num_id: str, ilvl: int) -> bool:
        fmt = self.fmts.get(num_id, {}).get(ilvl, "bullet")
        return fmt not in ("bullet", "none", "")

    def start(self, num_id: str, ilvl: int) -> int:
        return self.starts.get(num_id, {}).get(ilvl, 1)

    def known(self, num_id: str | None) -> bool:
        return bool(num_id) and num_id != "0" and num_id in self.fmts


def _levels(an: etree._Element) -> dict[int, str]:
    out: dict[int, str] = {}
    for lvl in an.iter(q(W, "lvl")):
        ilvl = lvl.get(q(W, "ilvl")) or ""
        fmt = w_val(lvl.find(q(W, "numFmt"))) or "bullet"
        if ilvl.isdigit():
            out[int(ilvl)] = fmt
    return out


def _int_val(el: etree._Element | None) -> int | None:
    v = w_val(el)
    try:
        return int(v) if v is not None else None
    except ValueError:
        return None


def _starts(an: etree._Element) -> dict[int, int]:
    out: dict[int, int] = {}
    for lvl in an.iter(q(W, "lvl")):
        ilvl = lvl.get(q(W, "ilvl")) or ""
        start = _int_val(lvl.find(q(W, "start")))
        if ilvl.isdigit() and start is not None:
            out[int(ilvl)] = start
    return out


@dataclass(slots=True)
class CommentInfo:
    wid: str
    author: str | None
    date: datetime | None
    paragraphs: list[etree._Element]
    para_ids: list[str]
    parent_wid: str | None = None
    resolved: bool | None = None


def load_comments(pkg: OfficePackage, part: str | None, ext_part: str | None) -> dict[str, CommentInfo]:
    out: dict[str, CommentInfo] = {}
    root = pkg.xml(part) if part else None
    if root is None:
        return out
    by_para: dict[str, str] = {}
    for c in root.iter(q(W, "comment")):
        wid = c.get(q(W, "id")) or ""
        paras = list(c.iter(q(W, "p")))
        pids = [str(p.get(q(W14, "paraId"))) for p in paras if p.get(q(W14, "paraId"))]
        out[wid] = CommentInfo(
            wid=wid,
            author=c.get(q(W, "author")) or None,
            date=parse_datetime(c.get(q(W, "date"))),
            paragraphs=paras,
            para_ids=pids,
        )
        for pid in pids:
            by_para[pid] = wid
    ext = pkg.xml(ext_part) if ext_part else None
    if ext is not None:
        for ce in ext.iter(q(W15, "commentEx")):
            pid = ce.get(q(W15, "paraId")) or ""
            wid = by_para.get(pid)
            if wid is None:
                continue
            info = out[wid]
            if pid != (info.para_ids[-1] if info.para_ids else pid):
                continue  # extended data is keyed by the comment's last paragraph
            info.resolved = on_off_attr(ce.get(q(W15, "done")))
            parent = ce.get(q(W15, "paraIdParent"))
            if parent and parent in by_para:
                info.parent_wid = by_para[parent]
    return out


@dataclass(slots=True)
class CoreProps:
    title: str | None = None
    author: str | None = None
    created: datetime | None = None
    modified: datetime | None = None
    description: str | None = None
    keywords: list[str] = field(default_factory=list)
    pages: int | None = None
    revision: str | None = None


def load_core(pkg: OfficePackage) -> CoreProps:
    cp = CoreProps()
    root = pkg.xml("docProps/core.xml")
    if root is not None:
        cp.title = _txt(root.find(q(DC, "title")))
        cp.author = _txt(root.find(q(DC, "creator")))
        cp.description = _txt(root.find(q(DC, "description")))
        cp.created = parse_datetime(_txt(root.find(q(DCTERMS, "created"))))
        cp.modified = parse_datetime(_txt(root.find(q(DCTERMS, "modified"))))
        cp.revision = _txt(root.find(q(CP, "revision")))
        kw = _txt(root.find(q(CP, "keywords")))
        if kw:
            cp.keywords = [k.strip() for k in re.split(r"[;,]", kw) if k.strip()]
    app = pkg.xml("docProps/app.xml")
    if app is not None:
        pages = _txt(app.find(q(EP, "Pages")))
        if pages and pages.isdigit():
            cp.pages = int(pages)
    return cp


def _txt(el: etree._Element | None) -> str | None:
    if el is None or el.text is None:
        return None
    t = str(el.text).strip()
    return t or None
