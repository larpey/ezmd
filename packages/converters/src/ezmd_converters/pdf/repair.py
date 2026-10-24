"""What a qpdf repair left behind, located per page where the object graph allows (sanitize.py).

Truncation and a broken cross-reference table cost a PDF its tail objects; qpdf opens the file anyway, resolving
every reference to a lost object as null and recovering what it can of a cut stream. Two losses are definite and
locatable from the object graph: a page whose content stream is gone or cut, and a figure or form XObject a page
draws that is gone or cut. Font losses are not: whether a lost ToUnicode map, width table or glyph procedure costs
any text depends on the font type and the reader's fallbacks (measured on 51 repaired arXiv papers: the pages with
a damaged font and the pages that lost words barely overlap), so fonts are counted, not placed.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass

import pikepdf
from pikepdf import Array, Dictionary, Stream

_WARNED_OBJECT = re.compile(r"\(object (\d+) \d+,|\bobject (\d+) \d+\b")
_FORM_DEPTH = 3
"""How deep to follow form XObjects that draw other forms."""
_MAX_RESOURCES = 20_000
"""Upper bound on resource entries inspected per file (hostile files can declare millions)."""


@dataclass(frozen=True, slots=True)
class RepairAssessment:
    pages_content_damaged: tuple[int, ...] = ()
    """1-based pages whose content stream is gone or cut; their text is partly or wholly lost."""
    pages_figures_missing: tuple[int, ...] = ()
    """1-based pages that draw an image or form XObject which is gone or cut."""
    fonts_damaged: int = 0
    """Fonts (distinct objects, plus font entries that resolve to nothing) whose text mapping lost a part."""

    @property
    def located(self) -> bool:
        return bool(self.pages_content_damaged or self.pages_figures_missing or self.fonts_damaged)

    def detail(self) -> dict[str, str | int]:
        out: dict[str, str | int] = {}
        if self.pages_content_damaged:
            out["pages_content_damaged"] = ",".join(map(str, self.pages_content_damaged))
        if self.pages_figures_missing:
            out["pages_figures_missing"] = ",".join(map(str, self.pages_figures_missing))
        if self.fonts_damaged:
            out["fonts_damaged"] = self.fonts_damaged
        return out

    def clauses(self) -> list[str]:
        """Message fragments, one per located loss, in the order they matter to a reader."""
        out: list[str] = []
        if self.pages_content_damaged:
            out.append(f"{_pages(self.pages_content_damaged)} lost {_its(self.pages_content_damaged)} content stream")
        if self.pages_figures_missing:
            out.append(f"{_pages(self.pages_figures_missing)} lost a figure or form")
        if self.fonts_damaged:
            n = self.fonts_damaged
            out.append(
                f"{n} font{'s' if n != 1 else ''} lost part of {'their' if n != 1 else 'its'} definition, so text "
                "set in them may be incomplete on pages that cannot be pinpointed"
            )
        return out


def _pages(pages: tuple[int, ...]) -> str:
    return ("page " if len(pages) == 1 else "pages ") + ", ".join(map(str, pages))


def _its(pages: tuple[int, ...]) -> str:
    return "its" if len(pages) == 1 else "their"


def warned_objects(messages: list[str]) -> frozenset[int]:
    """Object numbers qpdf's warnings name (`(object 12 0, offset 345): ...`, `object 12 0 not found ...`)."""
    found: set[int] = set()
    for m in messages:
        for a, b in _WARNED_OBJECT.findall(m):
            found.add(int(a or b))
    return frozenset(found)


def assess(pdf: pikepdf.Pdf, warned: frozenset[int] = frozenset()) -> RepairAssessment:
    """Locate the definite losses in a repaired PDF. `warned` is the set of object numbers qpdf complained
    about (a cut stream keeps its object but loses data; its number appears in the warning)."""
    content_pages: list[int] = []
    figure_pages: list[int] = []
    damaged_fonts: set[object] = set()
    missing_fonts: set[object] = set()
    budget = _MAX_RESOURCES
    for number, page in enumerate(pdf.pages, start=1):
        try:
            entries = dict(page.obj.items())
        except _READ_ERRORS:
            content_pages.append(number)
            continue
        if "/Contents" in entries and _content_gone(entries["/Contents"], warned):
            content_pages.append(number)
        figures = False
        resources = entries.get("/Resources")
        for kind, owner, name, obj in _resources(resources, depth=0, seen=set()):
            budget -= 1
            if budget <= 0:
                break
            # A resource dictionary shared by several pages is one dictionary: count its entries once.
            key = (owner if owner is not None else ("page", number), name)
            if kind == "/XObject":
                figures = figures or _gone(obj, warned)
            elif kind == "/Font":
                if _gone(obj, warned):
                    missing_fonts.add(key)
                elif isinstance(obj, Dictionary) and _font_damaged(obj, warned):
                    damaged_fonts.add(obj.objgen if obj.is_indirect else key)
        if figures:
            figure_pages.append(number)
    return RepairAssessment(
        pages_content_damaged=tuple(content_pages),
        pages_figures_missing=tuple(figure_pages),
        fonts_damaged=len(damaged_fonts) + len(missing_fonts),
    )


_READ_ERRORS = (pikepdf.PdfError, RuntimeError, ValueError, TypeError)
"""What qpdf raises through pikepdf when an object or stream cannot be read back; treated as lost."""


def _gone(obj: object, warned: frozenset[int]) -> bool:
    """The object a reference points at is null (pikepdf hands back None for a reference to a lost object),
    named in a qpdf warning (cut), or an unreadable or emptied stream."""
    if obj is None:
        return True
    if not isinstance(obj, pikepdf.Object):
        return False
    try:
        if obj.is_indirect and obj.objgen[0] in warned:
            return True
        if isinstance(obj, Stream):
            raw = obj.read_raw_bytes()
            return len(raw) == 0 and int(obj.get("/Length", 0)) > 0
    except _READ_ERRORS:
        return True
    return False


def _content_gone(contents: object, warned: frozenset[int]) -> bool:
    if isinstance(contents, Array):
        try:
            items = list(contents)
        except _READ_ERRORS:
            return True
        return any(_gone(item, warned) for item in items)
    return _gone(contents, warned)


def _resources(
    res: object, *, depth: int, seen: set[tuple[int, int]], holder: tuple[int, int] | None = None
) -> Iterator[tuple[str, tuple[int, int] | None, str, object]]:
    """(category, owner, name, object) for every font and XObject a resource dictionary declares, following form
    XObjects' own resources a few levels down. `owner` identifies the dictionary holding the entry so that one
    shared between pages counts once and two forms' direct dictionaries stay distinct: the /Font or /XObject
    dictionary's object number when indirect, else the resource dictionary's, else `holder`, the form XObject
    the direct dictionary sits in (None for the page's own direct dictionary)."""
    if not isinstance(res, Dictionary):
        return
    groups = _entries(res)
    for category in ("/Font", "/XObject"):
        group = groups.get(category)
        if not isinstance(group, Dictionary):
            continue
        owner = group.objgen if group.is_indirect else (res.objgen if res.is_indirect else holder)
        for name, obj in _entries(group).items():
            yield category, owner, name, obj
            if category == "/XObject" and depth < _FORM_DEPTH and isinstance(obj, Stream):
                og = obj.objgen if obj.is_indirect else None
                if og is not None and og in seen:
                    continue
                if og is not None:
                    seen.add(og)
                yield from _resources(_entries(obj).get("/Resources"), depth=depth + 1, seen=seen, holder=og)


def _entries(obj: Dictionary | Stream) -> dict[str, object]:
    """A dictionary's entries including those whose value is null (`keys()` hides them, `items()` keeps them);
    empty when the object cannot be read back."""
    try:
        return {str(k): v for k, v in obj.items()}
    except _READ_ERRORS:
        return {}


_FONT_PARTS = ("/Encoding", "/ToUnicode", "/Widths", "/CharProcs", "/DescendantFonts", "/W", "/CIDToGIDMap")
"""Font dictionary entries whose loss can change what text is extracted."""
_FONT_PROGRAMS = ("/FontFile", "/FontFile2", "/FontFile3")
"""The embedded font program. Its glyph names are what maps codes to characters wherever the /ToUnicode map is
absent or incomplete (LaTeX ligatures and math symbols), so losing it can cost text even with a map present."""


_FONT_DEPTH = 2
"""A Type0 font's /DescendantFonts hold CIDFonts, which have no descendants of their own; anything deeper is a
cycle in a hostile or broken file and is not followed."""


def _font_damaged(font: Dictionary, warned: frozenset[int], depth: int = 0) -> bool:
    if depth >= _FONT_DEPTH:
        return False
    try:
        entries = dict(font.items())
    except _READ_ERRORS:
        return True
    for key in _FONT_PARTS:
        if key in entries and _gone(entries[key], warned):
            return True
    if "/FontDescriptor" in entries:
        descriptor = entries["/FontDescriptor"]
        if _gone(descriptor, warned):
            return True
        if isinstance(descriptor, Dictionary):
            try:
                parts = dict(descriptor.items())
            except _READ_ERRORS:
                return True
            if any(key in parts and _gone(parts[key], warned) for key in _FONT_PROGRAMS):
                return True
    procs = entries.get("/CharProcs")
    if isinstance(procs, Dictionary):
        try:
            if any(_gone(p, warned) for _, p in procs.items()):
                return True
        except _READ_ERRORS:
            return True
    descendants = entries.get("/DescendantFonts")
    if isinstance(descendants, Array):
        try:
            return any(
                _gone(d, warned) or (isinstance(d, Dictionary) and _font_damaged(d, warned, depth + 1))
                for d in descendants
            )
        except _READ_ERRORS:
            return True
    return False
