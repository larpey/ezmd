"""Read the text layer of a PDF with pypdfium2 (BSD-3-Clause / Apache-2.0): characters with boxes, font
size, weight, marked-content ids, and link targets, grouped into `Line`s (runs of glyphs on one baseline
without a column-sized gap). Also measures per-page image coverage for the scan classifier.

Coordinates are converted to the displayed page (honoring `/Rotate`) with the origin at the top left.
"""

from __future__ import annotations

import ctypes
import math
import unicodedata
from dataclasses import dataclass, field

import pypdfium2 as pdfium  # type: ignore[import-untyped]
import pypdfium2.raw as pdfium_c  # type: ignore[import-untyped]

from ezmd.core.textclean import CleanStats, clean_text

Rect = tuple[float, float, float, float]

GAP_EM = 1.2
"""A horizontal gap wider than this many ems splits a baseline into separate lines (columns, table cells)."""
BASELINE_EM = 0.5
"""Glyphs whose baselines differ by more than this many ems are on different lines; a raised footnote
marker (about 0.35 em) stays on its line."""
OVERLAP_SAME_LINE = 0.6
"""Glyphs whose boxes overlap vertically by at least this fraction of the shorter one share a line even when
their reported origins disagree (some Type 3 and broken fonts)."""
PRIVATE_USE_SCANNED = 0.05
"""docs/internal/spec/part2.md 1e.8: over 5 percent private-use glyphs on a page means the text layer is unusable."""


@dataclass(slots=True)
class Line:
    page: int
    """1-based page number."""
    x0: float
    y0: float
    x1: float
    y1: float
    size: float
    bold: bool
    runs: list[tuple[str, str | None]]
    """(text, href) runs in reading order."""
    order: int
    """Position in the content stream (pdfium character order)."""
    mcids: set[int] = field(default_factory=set)

    @property
    def text(self) -> str:
        return "".join(t for t, _ in self.runs).strip()

    @property
    def width(self) -> float:
        return self.x1 - self.x0


@dataclass(slots=True)
class PageText:
    number: int
    width: float
    height: float
    lines: list[Line]
    chars: int
    image_fraction: float
    private_use: int = 0
    image_boxes: list[Rect] = field(default_factory=list)


_LIGATURE_LO, _LIGATURE_HI = chr(0xFB00), chr(0xFB06)
"""Latin ligatures (ff, fi, fl, ffi, ffl, long st, st) are NFKC-expanded (docs/internal/spec/part2.md 1e.8)."""


@dataclass(slots=True)
class _Glyph:
    ch: str
    x0: float
    y0: float
    x1: float
    y1: float
    size: float
    """Effective em size in page units: the Tf size scaled by the text matrix and CTM."""
    bold: bool
    mcid: int
    href: str | None
    turn: int = 0
    """Reading direction on the displayed page in counter-clockwise quarter turns (1: text runs up the page,
    as in a rotated table on an upright page)."""
    along: tuple[float, float] = (0.0, 0.0)
    """Extent along the reading direction."""
    across: tuple[float, float] = (0.0, 0.0)
    """Extent across it, increasing towards the next line."""
    base: float = 0.0
    """Baseline (the glyph origin) on the `across` axis."""


_HYPHEN_CODES = frozenset({0x02, 0xAD})
_SPACE = _Glyph(" ", 0.0, 0.0, 0.0, 0.0, 0.0, False, -1, None)


class _Transform:
    """Map PDF user space (bottom-left origin) to the displayed page with a top-left origin."""

    def __init__(self, width: float, height: float, rotation: int, dx: float = 0.0, dy: float = 0.0) -> None:
        """`width`/`height` are the unrotated crop box size; (dx, dy) is its lower-left corner."""
        self.w, self.h, self.rot = width, height, rotation % 360
        self.dx, self.dy = dx, dy

    @property
    def size(self) -> tuple[float, float]:
        return (self.h, self.w) if self.rot in (90, 270) else (self.w, self.h)

    def box(self, left: float, bottom: float, right: float, top: float) -> Rect:
        pts = [self.point(left, bottom), self.point(right, top)]
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        return min(xs), min(ys), max(xs), max(ys)

    def point(self, x: float, y: float) -> tuple[float, float]:
        x, y = x - self.dx, y - self.dy
        if self.rot == 90:
            return y, x
        if self.rot == 180:
            return self.w - x, y
        if self.rot == 270:
            return self.h - y, self.w - x
        return x, self.h - y


def _font_flags(textpage: pdfium.PdfTextPage, index: int, cache: dict[int, tuple[bool, int]]) -> tuple[bool, int]:
    """(bold, mcid) for the text object that owns character `index`; cached per object."""
    obj = pdfium_c.FPDFText_GetTextObject(textpage.raw, index)
    key = ctypes.cast(obj, ctypes.c_void_p).value or 0
    hit = cache.get(key)
    if hit is not None:
        return hit
    buf = ctypes.create_string_buffer(128)
    flags = ctypes.c_int(0)
    pdfium_c.FPDFText_GetFontInfo(textpage.raw, index, buf, 128, ctypes.byref(flags))
    name = buf.value.decode("latin-1", errors="replace").lower()
    weight = pdfium_c.FPDFText_GetFontWeight(textpage.raw, index)
    bold = weight >= 600 or any(w in name for w in ("bold", "black", "heavy", "semibold", "demi"))
    mcid = pdfium_c.FPDFPageObj_GetMarkedContentID(obj) if obj else -1
    cache[key] = (bold, int(mcid))
    return cache[key]


def _frame_point(turn: int, x: float, y: float) -> tuple[float, float]:
    """(along, across) of a displayed-page point for text turned `turn` quarter turns counter-clockwise."""
    if turn == 1:
        return -y, x
    if turn == 2:
        return -x, -y
    if turn == 3:
        return y, -x
    return x, y


def _placed(glyph: _Glyph, turn: int, origin: tuple[float, float]) -> _Glyph:
    """Fill the reading-direction frame of `glyph` from its displayed box and origin."""
    a0, c0 = _frame_point(turn, glyph.x0, glyph.y0)
    a1, c1 = _frame_point(turn, glyph.x1, glyph.y1)
    glyph.turn = turn
    glyph.along = (min(a0, a1), max(a0, a1))
    glyph.across = (min(c0, c1), max(c0, c1))
    glyph.base = _frame_point(turn, *origin)[1]
    return glyph


def _size_and_frame(
    textpage: pdfium.PdfTextPage, index: int, tf: _Transform, box: Rect
) -> tuple[float, int, tuple[float, float]]:
    """(em size, reading-direction turn, displayed origin) of character `index`.

    The em size is what a reader sees. `FPDFText_GetFontSize` is the nominal Tf operand, which is 1.0 when
    the producer puts the scale in the text matrix (`/F1 1 Tf 10.5 0 0 10.5 x y Tm`) or the CTM, so it is
    multiplied by the vertical scale of the character's full matrix; it falls back to the box height."""
    x0, y0, _x1, y1 = box
    nominal = abs(float(pdfium_c.FPDFText_GetFontSize(textpage.raw, index)))  # negative with a mirrored Tm
    ox, oy = ctypes.c_double(0.0), ctypes.c_double(0.0)
    has_origin = bool(pdfium_c.FPDFText_GetCharOrigin(textpage.raw, index, ctypes.byref(ox), ctypes.byref(oy)))
    origin = tf.point(ox.value, oy.value) if has_origin else (x0, y1)
    m = pdfium_c.FS_MATRIX()
    turn = 0
    if pdfium_c.FPDFText_GetMatrix(textpage.raw, index, ctypes.byref(m)):
        scale = math.hypot(m.c, m.d)
        if scale > 0:
            nominal *= scale
        if has_origin:
            ex, ey = tf.point(ox.value + m.a, oy.value + m.b)
            dx, dy = ex - origin[0], ey - origin[1]
            if dx or dy:
                turn = round(-math.atan2(dy, dx) / (math.pi / 2)) % 4  # displayed y grows downwards
    return nominal or (y1 - y0) or 10.0, turn, origin


def _href_at(links: list[tuple[Rect, str]], cx: float, cy: float) -> str | None:
    for (x0, y0, x1, y1), uri in links:
        if x0 <= cx <= x1 and y0 <= cy <= y1:
            return uri
    return None


def _image_coverage(page: pdfium.PdfPage, tf: _Transform) -> tuple[float, list[Rect]]:
    boxes: list[Rect] = []
    area = 0.0
    pw, ph = tf.size
    for obj in page.get_objects(filter=(pdfium_c.FPDF_PAGEOBJ_IMAGE,), max_depth=3):
        left, bottom, right, top = obj.get_bounds()
        x0, y0, x1, y1 = tf.box(left, bottom, right, top)
        x0, y0, x1, y1 = max(0.0, x0), max(0.0, y0), min(pw, x1), min(ph, y1)
        if x1 > x0 and y1 > y0:
            boxes.append((x0, y0, x1, y1))
            area += (x1 - x0) * (y1 - y0)
    return (min(1.0, area / (pw * ph)) if pw and ph else 0.0), boxes


def read_page(
    pdf: pdfium.PdfDocument, index: int, links: list[tuple[Rect, str]], stats: CleanStats, order_base: int
) -> PageText:
    """Extract one page (0-based `index`). `order_base` keeps content order unique across pages."""
    page = pdf[index]
    try:
        rotation = page.get_rotation()
        left, bottom, right, top = page.get_cropbox()
        tf = _Transform(right - left, top - bottom, rotation, left, bottom)
        pw, ph = tf.size
        image_fraction, image_boxes = _image_coverage(page, tf)
        textpage = page.get_textpage()
        try:
            glyphs, private = _glyphs(textpage, tf, links)
        finally:
            textpage.close()
    finally:
        page.close()
    lines = _lines(glyphs, index + 1, order_base, stats)
    chars = sum(1 for g in glyphs if g is not None and not g.ch.isspace())
    return PageText(
        number=index + 1,
        width=pw,
        height=ph,
        lines=lines,
        chars=chars,
        image_fraction=image_fraction,
        private_use=private,
        image_boxes=image_boxes,
    )


def _glyphs(
    textpage: pdfium.PdfTextPage, tf: _Transform, links: list[tuple[Rect, str]]
) -> tuple[list[_Glyph | None], int]:
    """Glyphs in content order; None marks a line break pdfium generated."""
    out: list[_Glyph | None] = []
    cache: dict[int, tuple[bool, int]] = {}
    private = 0
    n = textpage.count_chars()
    for i in range(n):
        code = pdfium_c.FPDFText_GetUnicode(textpage.raw, i)
        if code in _HYPHEN_CODES:
            code = 0x2D  # pdfium reports a line-end hyphen as U+0002; soft hyphens are U+00AD
        ch = chr(code) if 0 < code < 0x110000 else ""
        if ch in ("\r", "\n"):
            out.append(None)
            continue
        if not ch or code == 0xFFFE:
            continue
        if 0xE000 <= code <= 0xF8FF:
            private += 1
        if ch.isspace():
            out.append(_SPACE)
            continue
        left, bottom, right, top = textpage.get_charbox(i, loose=False)
        bold, mcid = _font_flags(textpage, i, cache)
        box = tf.box(left, bottom, right, top)
        size, turn, origin = _size_and_frame(textpage, i, tf, box)
        href = _href_at(links, (left + right) / 2, (bottom + top) / 2) if links else None
        for c in unicodedata.normalize("NFKC", ch) if _LIGATURE_LO <= ch <= _LIGATURE_HI else ch:
            out.append(_placed(_Glyph(c, *box, size, bold, mcid, href), turn, origin))
    return out, private


def _lines(glyphs: list[_Glyph | None], page: int, order_base: int, stats: CleanStats) -> list[Line]:
    lines: list[Line] = []
    cur: list[_Glyph] = []

    def flush() -> None:
        ink = [g for g in cur if g.ch != " "]
        if ink:
            sizes = sorted(g.size for g in ink)
            size = sizes[len(sizes) // 2]
            bold = sum(g.bold for g in ink) * 2 > len(ink)
            runs: list[tuple[str, str | None]] = []
            for k, g in enumerate(cur):
                text = clean_text(g.ch, stats)
                if not text:
                    continue
                href = g.href
                if g.ch == " " and 0 < k < len(cur) - 1 and cur[k - 1].href == cur[k + 1].href:
                    href = cur[k - 1].href  # a space inside a link belongs to the link
                if runs and runs[-1][1] == href:
                    runs[-1] = (runs[-1][0] + text, href)
                else:
                    runs.append((text, href))
            runs = _collapse_spaces(runs)
            lines.append(
                Line(
                    page=page,
                    x0=min(g.x0 for g in ink),
                    y0=min(g.y0 for g in ink),
                    x1=max(g.x1 for g in ink),
                    y1=max(g.y1 for g in ink),
                    size=size,
                    bold=bold,
                    runs=runs,
                    order=order_base + len(lines),
                    mcids={g.mcid for g in ink if g.mcid >= 0},
                )
            )
        cur.clear()

    last: _Glyph | None = None
    for g in glyphs:
        if g is None:
            flush()
            last = None
            continue
        if g.ch == " ":
            if cur and cur[-1].ch != " ":
                cur.append(g)
            continue
        if last is not None:
            em = max(last.size, g.size, 1.0)
            gap = g.along[0] - last.along[1]
            backwards = g.along[1] < last.along[0] - 0.5 * em
            if g.turn != last.turn or not _same_line(last, g, em) or gap > GAP_EM * em or backwards:
                flush()
        cur.append(g)
        last = g
    flush()
    return lines


def _same_line(a: _Glyph, b: _Glyph, em: float) -> bool:
    """Same baseline (within `BASELINE_EM`), or boxes that mostly overlap across the reading direction.
    Glyph tops and bottoms alone differ at every ascender and descender, so they are never compared."""
    if abs(a.base - b.base) <= BASELINE_EM * em:
        return True
    overlap = min(a.across[1], b.across[1]) - max(a.across[0], b.across[0])
    shorter = min(a.across[1] - a.across[0], b.across[1] - b.across[0])
    return shorter > 0 and overlap >= OVERLAP_SAME_LINE * shorter


def _collapse_spaces(runs: list[tuple[str, str | None]]) -> list[tuple[str, str | None]]:
    out: list[tuple[str, str | None]] = []
    prev_space = True
    for text, href in runs:
        buf = []
        for c in text:
            if c.isspace():
                if not prev_space:
                    buf.append(" ")
                prev_space = True
            else:
                buf.append(c)
                prev_space = False
        if buf:
            out.append(("".join(buf), href))
    if out:
        t, h = out[-1]
        out[-1] = (t.rstrip(), h)
        if not out[-1][0]:
            out.pop()
    return out
