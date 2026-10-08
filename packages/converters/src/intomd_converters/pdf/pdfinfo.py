"""Read document-level facts from an open pikepdf.Pdf: Info/XMP metadata, outline, structure-tree headings,
URI links, and AcroForm fields (docs/spec/part2.md 1c steps 2, 5, 9). Every walk is bounded."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta, timezone

import pikepdf
from pikepdf import Array, Dictionary

from intomd.core.textclean import clean_text

_MAX_OUTLINE = 5000
_MAX_STRUCT = 200_000
_MAX_FIELDS = 2000
_HEADING_TAGS = {f"/H{i}": i for i in range(1, 7)} | {"/H": 1, "/Title": 1}
_SAFE_SCHEMES = ("http://", "https://", "mailto:")
_PDF_DATE = re.compile(r"^D?:?(\d{4})(\d{2})?(\d{2})?(\d{2})?(\d{2})?(\d{2})?([Zz]|[+-]\d{2}'?\d{2}'?)?")

Rect = tuple[float, float, float, float]


@dataclass(slots=True)
class FormField:
    name: str
    kind: str
    value: str
    page: int | None


@dataclass(slots=True)
class PdfInfo:
    title: str | None = None
    author: str | None = None
    subject: str | None = None
    keywords: list[str] = field(default_factory=list)
    created: datetime | None = None
    modified: datetime | None = None
    language: str | None = None
    tagged: bool = False
    outline: list[tuple[int, str, int | None]] = field(default_factory=list)
    """(level 1..6, title, 0-based page index or None)."""
    struct_state: str = "absent"
    """absent | usable | unusable."""
    struct_headings: dict[tuple[int, int], int] = field(default_factory=dict)
    """(0-based page index, MCID) -> heading level from the structure tree."""
    links: dict[int, list[tuple[Rect, str]]] = field(default_factory=dict)
    """0-based page index -> [(rect in PDF user space, absolute URI)]."""
    fields: list[FormField] = field(default_factory=list)
    has_acroform: bool = False


def _text(obj: object) -> str | None:
    if obj is None:
        return None
    try:
        s = str(obj)
    except Exception:
        return None
    s = clean_text(s).strip()
    return s or None


def parse_pdf_date(raw: str | None) -> datetime | None:
    if not raw:
        return None
    m = _PDF_DATE.match(raw.strip())
    if not m:
        return None
    y, mo, d, h, mi, s, tz = m.groups()
    try:
        dt = datetime(int(y), int(mo or 1), int(d or 1), int(h or 0), int(mi or 0), int(s or 0))
    except ValueError:
        return None
    if tz and tz not in ("Z", "z"):
        digits = tz.replace("'", "")
        sign = 1 if digits[0] == "+" else -1
        offset = timedelta(hours=int(digits[1:3]), minutes=int(digits[3:5] or 0))
        return dt.replace(tzinfo=timezone(sign * offset))
    return dt.replace(tzinfo=UTC)


def read_info(pdf: pikepdf.Pdf, *, source: str) -> PdfInfo:
    info = PdfInfo()
    page_index = {p.obj.objgen: i for i, p in enumerate(pdf.pages)}
    try:
        docinfo = pdf.docinfo
        info.title = _text(docinfo.get("/Title"))
        info.author = _text(docinfo.get("/Author"))
        info.subject = _text(docinfo.get("/Subject"))
        kw = _text(docinfo.get("/Keywords"))
        info.keywords = [k.strip() for k in re.split(r"[;,]", kw) if k.strip()] if kw else []
        info.created = parse_pdf_date(_text(docinfo.get("/CreationDate")))
        info.modified = parse_pdf_date(_text(docinfo.get("/ModDate")))
    except Exception:
        pass
    if info.title is None:
        try:
            with pdf.open_metadata() as meta:
                info.title = _text(meta.get("dc:title"))
        except Exception:
            pass
    info.language = _text(pdf.Root.get("/Lang"))
    mark = pdf.Root.get("/MarkInfo")
    info.tagged = isinstance(mark, Dictionary) and bool(mark.get("/Marked", False))
    info.outline = _outline(pdf, page_index)
    _struct_tree(pdf, page_index, info)
    info.links = _links(pdf)
    form = pdf.Root.get("/AcroForm")
    if isinstance(form, Dictionary):
        info.has_acroform = True
        info.fields = _fields(form, page_index)
    return info


def _dest_page(pdf: pikepdf.Pdf, dest: object, page_index: dict[tuple[int, int], int]) -> int | None:
    if isinstance(dest, pikepdf.String | pikepdf.Name):
        try:
            names = pdf.Root.Names.Dests
            tree = pikepdf.NameTree(names)
            dest = tree.get(str(dest))
        except Exception:
            dests = pdf.Root.get("/Dests")
            dest = dests.get("/" + str(dest).lstrip("/")) if isinstance(dests, Dictionary) else None
        if isinstance(dest, Dictionary):
            dest = dest.get("/D")
    if isinstance(dest, Array) and len(dest) > 0:
        target = dest[0]
        if isinstance(target, pikepdf.Object) and target.is_indirect:
            return page_index.get(target.objgen)
        if isinstance(target, int):
            return target
    return None


def _outline(pdf: pikepdf.Pdf, page_index: dict[tuple[int, int], int]) -> list[tuple[int, str, int | None]]:
    out: list[tuple[int, str, int | None]] = []
    try:
        with pdf.open_outline() as ol:
            stack = [(item, 1) for item in reversed(ol.root)]
            while stack and len(out) < _MAX_OUTLINE:
                item, depth = stack.pop()
                title = _text(item.title)
                dest: object = item.destination
                if dest is None and item.action is not None and str(item.action.get("/S", "")) == "/GoTo":
                    dest = item.action.get("/D")
                if title:
                    out.append((min(depth, 6), title, _dest_page(pdf, dest, page_index)))
                if depth < 16:
                    stack.extend((child, depth + 1) for child in reversed(item.children))
    except Exception:
        return out
    return out


def _struct_tree(pdf: pikepdf.Pdf, page_index: dict[tuple[int, int], int], info: PdfInfo) -> None:
    root = pdf.Root.get("/StructTreeRoot")
    if not isinstance(root, Dictionary):
        return
    role_map = root.get("/RoleMap")
    roles: dict[str, str] = {}
    if isinstance(role_map, Dictionary):
        for k, v in role_map.items():
            roles[str(k)] = str(v)

    def std(tag: str) -> str:
        for _ in range(5):
            if tag in _HEADING_TAGS or tag not in roles:
                break
            tag = roles[tag]
        return tag

    elements = 0
    mapped = 0
    seen: set[tuple[int, int]] = set()
    # (node, inherited page index, heading level of the nearest heading ancestor or 0)
    stack: list[tuple[object, int | None, int]] = [(root.get("/K"), None, 0)]
    while stack and elements < _MAX_STRUCT:
        node, page, level = stack.pop()
        if isinstance(node, Array):
            stack.extend((k, page, level) for k in reversed(list(node)))
            continue
        if isinstance(node, int):
            if level and page is not None:
                info.struct_headings[(page, node)] = level
                mapped += 1
            continue
        if not isinstance(node, Dictionary):
            continue
        if node.is_indirect:
            if node.objgen in seen:
                continue
            seen.add(node.objgen)
        pg = node.get("/Pg")
        if isinstance(pg, pikepdf.Object) and pg.is_indirect and pg.objgen in page_index:
            page = page_index[pg.objgen]
        if str(node.get("/Type", "")) == "/MCR" or "/MCID" in node:
            mcid = node.get("/MCID")
            if level and page is not None and isinstance(mcid, int):
                info.struct_headings[(page, int(mcid))] = level
                mapped += 1
            continue
        if str(node.get("/Type", "")) == "/OBJR":
            continue
        elements += 1
        tag = std(str(node.get("/S", "")))
        child_level = level or _HEADING_TAGS.get(tag, 0)
        stack.append((node.get("/K"), page, child_level))
    if elements == 0:
        info.struct_state = "unusable"
    else:
        info.struct_state = "usable" if mapped else "unusable"


def _links(pdf: pikepdf.Pdf) -> dict[int, list[tuple[Rect, str]]]:
    out: dict[int, list[tuple[Rect, str]]] = {}
    for i, page in enumerate(pdf.pages):
        annots = page.obj.get("/Annots")
        if not isinstance(annots, Array):
            continue
        for a in annots:
            if not isinstance(a, Dictionary) or str(a.get("/Subtype", "")) != "/Link":
                continue
            action = a.get("/A")
            if not isinstance(action, Dictionary) or str(action.get("/S", "")) != "/URI":
                continue
            uri = _text(action.get("/URI"))
            rect = a.get("/Rect")
            if not uri or not uri.lower().startswith(_SAFE_SCHEMES) or not isinstance(rect, Array) or len(rect) != 4:
                continue
            try:
                x0, y0, x1, y1 = (float(v) for v in rect)
            except (TypeError, ValueError):  # noqa: S112 - a malformed /Rect just drops that link
                continue
            out.setdefault(i, []).append(((min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1)), uri))
    return out


def _field_kind(ft: str, flags: int) -> str:
    if ft == "/Btn":
        if flags & (1 << 16):
            return "pushbutton"
        return "radio" if flags & (1 << 15) else "checkbox"
    return {"/Tx": "text", "/Ch": "choice", "/Sig": "signature"}.get(ft, "unknown")


def _field_value(kind: str, v: object) -> str:
    if kind == "signature":
        return "(signed)" if v is not None else "(unsigned)"
    if kind == "checkbox":
        return "[x]" if v is not None and str(v) not in ("/Off", "") else "[ ]"
    if v is None:
        return ""
    if isinstance(v, Array):
        return ", ".join(_text(x) or "" for x in v)
    s = _text(v) or ""
    return s[1:] if s.startswith("/") and kind in ("radio", "choice") else s


def _fields(form: Dictionary, page_index: dict[tuple[int, int], int]) -> list[FormField]:
    out: list[FormField] = []
    roots = form.get("/Fields")
    if not isinstance(roots, Array):
        return out
    seen: set[tuple[int, int]] = set()
    stack: list[tuple[Dictionary, str, str, int]] = [
        (f, "", "", 0) for f in reversed(list(roots)) if isinstance(f, Dictionary)
    ]
    while stack and len(out) < _MAX_FIELDS:
        node, prefix, ft, flags = stack.pop()
        if node.is_indirect:
            if node.objgen in seen:
                continue
            seen.add(node.objgen)
        part = _text(node.get("/T"))
        name = ".".join(p for p in (prefix, part) if p)
        ft = str(node.get("/FT", ft) or ft)
        ff = node.get("/Ff")
        flags = int(ff) if isinstance(ff, int) else flags
        kids = [k for k in node.get("/Kids", Array()) if isinstance(k, Dictionary)]
        named_kids = [k for k in kids if "/T" in k]
        if named_kids:
            stack.extend((k, name, ft, flags) for k in reversed(named_kids))
            continue
        widget = kids[0] if kids else node
        pg = widget.get("/P")
        page = page_index.get(pg.objgen) if isinstance(pg, pikepdf.Object) and pg.is_indirect else None
        kind = _field_kind(ft, flags)
        if kind == "pushbutton":
            continue
        out.append(FormField(name=name or "(unnamed)", kind=kind, value=_field_value(kind, node.get("/V")), page=page))
    return out
