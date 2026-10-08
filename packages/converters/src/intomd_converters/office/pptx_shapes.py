"""PPTX shape tree reading: positions (with group transforms and placeholder inheritance), text bodies,
tables, charts, and SmartArt data models. Pure lxml over the sanitized package."""

from __future__ import annotations

import posixpath
from dataclasses import dataclass, field

from lxml import etree  # type: ignore[import-untyped]

from intomd.core.textclean import CleanStats
from intomd.ir import InlineSpan, InlineStyle
from intomd_converters.office._common import SpanBuilder, safe_href
from intomd_converters.office._ooxml_ns import DGM, MC, A, C, P, R, local, ns_of, q
from intomd_converters.office._package import OfficePackage, Rel

TITLE_TYPES = ("title", "ctrTitle")
FURNITURE_TYPES = ("dt", "ftr", "sldNum", "hdr")
BULLET_TYPES = ("body", "obj", None)
_MAX_GROUP_DEPTH = 16


@dataclass(slots=True)
class Shape:
    kind: str
    """'text', 'pic', 'table', 'chart', 'smartart', 'ole'."""
    el: etree._Element
    shape_id: str
    name: str
    descr: str | None
    ph_type: str | None
    ph_idx: str | None
    is_placeholder: bool
    box: tuple[float, float, float, float] | None
    """x, y, width, height in EMU."""
    rid: str | None = None


@dataclass(slots=True)
class TextPara:
    level: int
    bullet: str | None
    """None, 'bullet', or 'number'."""
    spans: list[InlineSpan]
    max_size: float | None


@dataclass(slots=True)
class _Xform:
    off_x: float = 0.0
    off_y: float = 0.0
    sx: float = 1.0
    sy: float = 1.0

    def apply(self, x: float, y: float, w: float, h: float) -> tuple[float, float, float, float]:
        return self.off_x + x * self.sx, self.off_y + y * self.sy, w * self.sx, h * self.sy


def _xfrm_box(xfrm: etree._Element | None) -> tuple[float, float, float, float] | None:
    if xfrm is None:
        return None
    off, ext = xfrm.find(q(A, "off")), xfrm.find(q(A, "ext"))
    if off is None or ext is None:
        return None
    try:
        return float(off.get("x", 0)), float(off.get("y", 0)), float(ext.get("cx", 0)), float(ext.get("cy", 0))
    except ValueError:
        return None


def read_shapes(tree: etree._Element | None) -> list[Shape]:
    out: list[Shape] = []
    if tree is not None:
        _walk(tree, _Xform(), out, 0)
    return out


def _walk(tree: etree._Element, xf: _Xform, out: list[Shape], depth: int) -> None:
    for child in tree:
        ns, tag = ns_of(child.tag), local(child.tag)
        if ns == MC and tag == "AlternateContent":
            branch = child.find(q(MC, "Choice"))
            if branch is None:
                branch = child.find(q(MC, "Fallback"))
            if branch is not None:
                _walk(branch, xf, out, depth)
            continue
        if ns != P:
            continue
        if tag == "grpSp" and depth < _MAX_GROUP_DEPTH:
            gx = child.find(f"{q(P, 'grpSpPr')}/{q(A, 'xfrm')}")
            _walk(child, _group_xform(gx, xf), out, depth + 1)
            continue
        if tag not in ("sp", "pic", "graphicFrame"):
            continue
        nv = child.find(f"{q(P, 'nvSpPr' if tag == 'sp' else 'nvPicPr' if tag == 'pic' else 'nvGraphicFramePr')}")
        cnv = nv.find(q(P, "cNvPr")) if nv is not None else None
        ph = nv.find(f"{q(P, 'nvPr')}/{q(P, 'ph')}") if nv is not None else None
        if tag == "graphicFrame":
            box = _xfrm_box(child.find(q(P, "xfrm")))
        else:
            box = _xfrm_box(child.find(f"{q(P, 'spPr')}/{q(A, 'xfrm')}"))
        if box is not None:
            box = xf.apply(*box)
        kind, rid = _kind(child, tag)
        if kind is None:
            continue
        out.append(
            Shape(
                kind=kind,
                el=child,
                shape_id=(cnv.get("id") if cnv is not None else None) or str(len(out) + 1),
                name=(cnv.get("name") if cnv is not None else None) or "",
                descr=((cnv.get("descr") or "").strip() or None) if cnv is not None else None,
                ph_type=(ph.get("type") or "body") if ph is not None else None,
                ph_idx=ph.get("idx") if ph is not None else None,
                is_placeholder=ph is not None,
                box=box,
                rid=rid,
            )
        )


def _group_xform(gx: etree._Element | None, parent: _Xform) -> _Xform:
    if gx is None:
        return parent
    box = _xfrm_box(gx)
    ch_off, ch_ext = gx.find(q(A, "chOff")), gx.find(q(A, "chExt"))
    if box is None or ch_off is None or ch_ext is None:
        return parent
    try:
        cx, cy = float(ch_off.get("x", 0)), float(ch_off.get("y", 0))
        cw, chh = float(ch_ext.get("cx", 0)) or 1.0, float(ch_ext.get("cy", 0)) or 1.0
    except ValueError:
        return parent
    x, y, w, h = parent.apply(*box)
    sx, sy = w / cw, h / chh
    return _Xform(off_x=x - cx * sx, off_y=y - cy * sy, sx=sx, sy=sy)


def _kind(el: etree._Element, tag: str) -> tuple[str | None, str | None]:
    if tag == "sp":
        return ("text", None) if el.find(q(P, "txBody")) is not None else (None, None)
    if tag == "pic":
        blip = next(iter(el.iter(q(A, "blip"))), None)
        return "pic", (blip.get(q(R, "embed")) if blip is not None else None)
    data = el.find(f"{q(A, 'graphic')}/{q(A, 'graphicData')}")
    uri = (data.get("uri") or "") if data is not None else ""
    if data is None:
        return None, None
    if uri.endswith("/table"):
        return "table", None
    if uri.endswith("/chart"):
        ch = data.find(q(C, "chart"))
        return "chart", (ch.get(q(R, "id")) if ch is not None else None)
    if uri.endswith("/diagram"):
        ids = data.find(q(DGM, "relIds"))
        return "smartart", (ids.get(q(R, "dm")) if ids is not None else None)
    if uri.endswith("/ole"):
        return "ole", None
    return None, None


# -- placeholder inheritance -------------------------------------------------------------------------------


class LayoutBoxes:
    """Positions of placeholders on a slide's layout and master, for placeholders without their own xfrm."""

    def __init__(self, pkg: OfficePackage, slide_rels: dict[str, Rel]) -> None:
        self.by_idx: dict[str, tuple[float, float, float, float]] = {}
        self.by_type: dict[str, tuple[float, float, float, float]] = {}
        self.layout_name: str | None = None
        layout = next((r.target for r in slide_rels.values() if r.kind == "slidelayout" and not r.external), None)
        chain: list[str] = []
        if layout:
            chain.append(layout)
            master = next(
                (r.target for r in pkg.rels(layout).values() if r.kind == "slidemaster" and not r.external), None
            )
            if master:
                chain.append(master)
        for i, part in enumerate(chain):
            root = pkg.xml(part)
            if root is None:
                continue
            csld = root.find(q(P, "cSld"))
            if i == 0 and csld is not None:
                self.layout_name = csld.get("name") or None
            tree = csld.find(q(P, "spTree")) if csld is not None else None
            for sh in read_shapes(tree):
                if not sh.is_placeholder or sh.box is None:
                    continue
                if sh.ph_idx is not None:
                    self.by_idx.setdefault(sh.ph_idx, sh.box)
                self.by_type.setdefault(_norm_type(sh.ph_type), sh.box)

    def resolve(self, sh: Shape) -> tuple[float, float, float, float] | None:
        if sh.box is not None or not sh.is_placeholder:
            return sh.box
        if sh.ph_idx is not None and sh.ph_idx in self.by_idx:
            return self.by_idx[sh.ph_idx]
        return self.by_type.get(_norm_type(sh.ph_type))


def _norm_type(t: str | None) -> str:
    return "title" if t in TITLE_TYPES else (t or "body")


# -- text bodies ------------------------------------------------------------------------------------------


def text_paras(tx: etree._Element | None, rels: dict[str, Rel], stats: CleanStats, bullets: bool) -> list[TextPara]:
    out: list[TextPara] = []
    if tx is None:
        return out
    for p in tx.findall(q(A, "p")):
        ppr = p.find(q(A, "pPr"))
        level = int(ppr.get("lvl", "0")) if ppr is not None and (ppr.get("lvl") or "0").isdigit() else 0
        bullet: str | None = "bullet" if bullets else None
        if ppr is not None:
            if ppr.find(q(A, "buNone")) is not None:
                bullet = None
            elif ppr.find(q(A, "buAutoNum")) is not None:
                bullet = "number"
            elif ppr.find(q(A, "buChar")) is not None or ppr.find(q(A, "buBlip")) is not None:
                bullet = "bullet"
        sb = SpanBuilder(stats)
        sizes: list[float] = []
        for r in p:
            tag = local(r.tag)
            if tag in ("r", "fld"):
                rpr = r.find(q(A, "rPr"))
                styles, href, size = _run_style(rpr, rels)
                if size:
                    sizes.append(size)
                sb.add("".join(t.text or "" for t in r.findall(q(A, "t"))), styles, href)
            elif tag == "br":
                sb.add("\n")
        spans = sb.stripped()
        if spans:
            out.append(
                TextPara(level=min(level, 8), bullet=bullet, spans=spans, max_size=max(sizes) if sizes else None)
            )
    return out


def _run_style(rpr: etree._Element | None, rels: dict[str, Rel]) -> tuple[tuple[InlineStyle, ...], str | None, float]:
    if rpr is None:
        return (), None, 0.0
    styles: list[InlineStyle] = []
    if rpr.get("b") in ("1", "true"):
        styles.append(InlineStyle.BOLD)
    if rpr.get("i") in ("1", "true"):
        styles.append(InlineStyle.ITALIC)
    if (rpr.get("strike") or "noStrike") != "noStrike":
        styles.append(InlineStyle.STRIKE)
    base = rpr.get("baseline") or "0"
    if base.lstrip("-").isdigit() and int(base) > 0:
        styles.append(InlineStyle.SUPERSCRIPT)
    elif base.lstrip("-").isdigit() and int(base) < 0:
        styles.append(InlineStyle.SUBSCRIPT)
    href = None
    link = rpr.find(q(A, "hlinkClick"))
    if link is not None:
        rel = rels.get(link.get(q(R, "id")) or "")
        href = safe_href(rel.target) if rel is not None and rel.external else None
    sz = rpr.get("sz") or ""
    size = int(sz) / 100.0 if sz.isdigit() else 0.0
    return tuple(styles), href, size


def cell_spans(tc: etree._Element, rels: dict[str, Rel], stats: CleanStats) -> list[InlineSpan]:
    out: list[InlineSpan] = []
    for tp in text_paras(tc.find(q(A, "txBody")), rels, stats, False):
        if out:
            out.append(InlineSpan(text="\n"))
        out.extend(tp.spans)
    return out


# -- charts -----------------------------------------------------------------------------------------------


@dataclass(slots=True)
class ChartData:
    title: str | None
    chart_type: str
    categories: list[str]
    series: list[tuple[str, list[str]]] = field(default_factory=list)


def read_chart(root: etree._Element | None) -> ChartData | None:
    if root is None:
        return None
    title_el = root.find(f"{q(C, 'chart')}/{q(C, 'title')}")
    title = " ".join("".join(t.text or "" for t in title_el.iter(q(A, "t"))).split()) if title_el is not None else ""
    plot = root.find(f"{q(C, 'chart')}/{q(C, 'plotArea')}")
    if plot is None:
        return None
    charts = [c for c in plot if local(c.tag).endswith("Chart")]
    if not charts:
        return None
    ctype = local(charts[0].tag)
    bar_dir = charts[0].find(q(C, "barDir"))
    if bar_dir is not None and bar_dir.get("val") == "col":
        ctype = "columnChart"
    data = ChartData(title=title or None, chart_type=ctype, categories=[])
    for ch in charts:
        for ser in ch.findall(q(C, "ser")):
            name = " ".join("".join(v.text or "" for v in ser.iter(q(C, "v")) if _within(v, ser, "tx")).split())
            cats = _points(ser.find(q(C, "cat")))
            vals = _points(ser.find(q(C, "val")))
            if len(cats) > len(data.categories):
                data.categories = cats
            data.series.append((name or f"Series {len(data.series) + 1}", vals))
    return data


def _within(el: etree._Element, stop: etree._Element, name: str) -> bool:
    parent = el.getparent()
    while parent is not None and parent is not stop:
        if local(parent.tag) == name:
            return True
        parent = parent.getparent()
    return False


def _points(el: etree._Element | None) -> list[str]:
    if el is None:
        return []
    pts: dict[int, str] = {}
    for pt in el.iter(q(C, "pt")):
        idx = pt.get("idx") or ""
        v = pt.find(q(C, "v"))
        if idx.isdigit() and v is not None:
            pts[int(idx)] = (v.text or "").strip()
    if not pts:
        return []
    n = min(max(pts) + 1, 10_000)
    return [pts.get(i, "") for i in range(n)]


# -- SmartArt -----------------------------------------------------------------------------------------------


@dataclass(slots=True)
class DgmNode:
    text: str
    children: list[DgmNode] = field(default_factory=list)


def read_smartart(root: etree._Element | None) -> list[DgmNode]:
    if root is None:
        return []
    pts: dict[str, tuple[str, str]] = {}
    doc_id = None
    for pt in root.iter(q(DGM, "pt")):
        mid = pt.get("modelId") or ""
        kind = pt.get("type") or "node"
        text = " ".join("".join(t.text or "" for t in pt.iter(q(A, "t"))).split())
        pts[mid] = (kind, text)
        if kind == "doc":
            doc_id = mid
    edges: dict[str, list[tuple[int, str]]] = {}
    for cxn in root.iter(q(DGM, "cxn")):
        if (cxn.get("type") or "parOf") != "parOf":
            continue
        src, dst = cxn.get("srcId") or "", cxn.get("destId") or ""
        order = cxn.get("srcOrd") or "0"
        edges.setdefault(src, []).append((int(order) if order.isdigit() else 0, dst))

    def build(mid: str, depth: int) -> list[DgmNode]:
        out: list[DgmNode] = []
        if depth > 16:
            return out
        for _, dst in sorted(edges.get(mid, [])):
            kind, text = pts.get(dst, ("", ""))
            if kind != "node":
                continue
            out.append(DgmNode(text=text, children=build(dst, depth + 1)))
        return out

    if doc_id is not None:
        return build(doc_id, 0)
    return [DgmNode(text=t) for k, t in pts.values() if k == "node" and t]


def part_dir(part: str) -> str:
    return posixpath.dirname(part)
