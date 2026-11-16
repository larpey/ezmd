"""Geometry heuristics for the text-layer engine: running headers and footers, best-effort tables, column
reading order, and font-size heading levels. Pure functions over `textlayer.Line`, so they are unit-tested
without PDFs."""

from __future__ import annotations

import itertools
import math
import re
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field

from ezmd_converters.pdf.textlayer import Line, PageText, Rect, Run

MARGIN_ZONE = 0.08
"""Top and bottom share of the page height where running headers and footers live."""
WIDE_ZONE = 0.25
"""Share of the page height a running header may sit in when the margin is large; there it must also repeat
at the same position to count (see `running_lines`)."""
HEADING_RATIO = 1.15
"""A line whose font size is at least this multiple of the body size is a heading candidate."""
TABLE_CELL_CHARS = 30
"""Rows whose cells average more characters than this read as prose columns, not table cells."""
_DIGITS = re.compile(r"\d+")
_SPACES = re.compile(r"\s+")


def norm_key(text: str) -> str:
    """Normalization for matching repeats and headings: case-folded, digits collapsed, spaces collapsed."""
    return _SPACES.sub(" ", _DIGITS.sub("#", text.casefold())).strip()


def norm_text(text: str) -> str:
    return _SPACES.sub(" ", text.casefold()).strip(" .:")


# ---------------------------------------------------------------------------
# Running headers and footers
# ---------------------------------------------------------------------------


def running_lines(pages: Sequence[PageText]) -> set[int]:
    """`Line.order` values of running headers/footers.

    Two rules. In the top or bottom margin zone (`MARGIN_ZONE`), a line whose normalized text (digits
    collapsed, so page numbers match) repeats on at least half the pages (min 2) is furniture. In the wider
    band (`WIDE_ZONE`), where a large margin can put a header, the text must also repeat at the same place
    (y and x within a line height) on at least half the pages (min 3): a court opinion's case name 17% below
    the top edge on every page is a header; the same name quoted once mid-page is not. Any further copy of a
    known running text inside a margin zone is furniture too, however rarely it appears there."""
    if len(pages) < 2:
        return set()
    seen: dict[str, set[int]] = {}
    where: dict[str, list[int]] = {}
    placed_seen: dict[tuple[str, str, int, int], set[int]] = {}
    placed_where: dict[tuple[str, str, int, int], list[int]] = {}
    for p in pages:
        for ln in p.lines:
            zone = "T:" if ln.y1 <= p.height / 2 else "B:"
            if ln.y1 <= p.height * MARGIN_ZONE or ln.y0 >= p.height * (1 - MARGIN_ZONE):
                key = zone + norm_key(ln.text)
                seen.setdefault(key, set()).add(p.number)
                where.setdefault(key, []).append(ln.order)
            elif ln.y1 <= p.height * WIDE_ZONE or ln.y0 >= p.height * (1 - WIDE_ZONE):
                step = max(ln.size, 1.0)
                placed = (zone, norm_key(ln.text), round(ln.y0 / step), round(ln.x0 / step))
                placed_seen.setdefault(placed, set()).add(p.number)
                placed_where.setdefault(placed, []).append(ln.order)
    need = max(2, math.ceil(len(pages) * 0.5))
    out: set[int] = set()
    texts: set[str] = set()
    for key, pgs in seen.items():
        if len(pgs) >= need:
            out.update(where[key])
            texts.add(key[2:])
    for placed, pgs in placed_seen.items():
        if len(pgs) >= max(3, need):
            out.update(placed_where[placed])
            texts.add(placed[1])
    if texts:
        for p in pages:
            for ln in p.lines:
                in_margin = ln.y1 <= p.height * MARGIN_ZONE or ln.y0 >= p.height * (1 - MARGIN_ZONE)
                if in_margin and norm_key(ln.text) in texts:
                    out.add(ln.order)
    return out


def body_font_size(pages: Sequence[PageText]) -> float:
    """The most common font size, weighted by characters (rounded to 0.5 pt)."""
    counts: Counter[float] = Counter()
    for p in pages:
        for ln in p.lines:
            counts[round(ln.size * 2) / 2] += len(ln.text)
    return counts.most_common(1)[0][0] if counts else 10.0


# ---------------------------------------------------------------------------
# Tables (best effort)
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class TableGrid:
    page: int
    x0: float
    y0: float
    x1: float
    y1: float
    rows: list[list[str]]
    header: bool
    order: int
    runs: list[list[list[Run]]] = field(default_factory=list)
    """Per row and column, the cell's runs (scripts and links kept); empty for grids built from text only."""


def _rows(lines: list[Line]) -> list[list[Line]]:
    """Group lines that share a baseline into rows, top to bottom, each row left to right."""
    rows: list[list[Line]] = []
    for ln in sorted(lines, key=lambda ln: (ln.y1, ln.x0)):
        if rows and abs(rows[-1][0].y1 - ln.y1) <= 0.35 * max(ln.size, rows[-1][0].size):
            rows[-1].append(ln)
        else:
            rows.append([ln])
    for r in rows:
        r.sort(key=lambda ln: ln.x0)
    return _attach_centered_header_cells(rows)


def _has_digit(row: list[Line]) -> bool:
    return any(ch.isdigit() for ln in row for ch in ln.text)


def _attach_centered_header_cells(rows: list[list[Line]]) -> list[list[Line]]:
    """A header cell set vertically centred over a two-line header ("Model" beside "BLEU" over "EN-DE EN-FR")
    has a baseline of its own; move it into the header row above so it does not break the table. Only in the
    header zone: both neighbours are multi-cell rows without digits, and the cell sits within half an em of
    each and beside, not under, the cells above."""
    out: list[list[Line]] = []
    for k, row in enumerate(rows):
        nxt = rows[k + 1] if k + 1 < len(rows) else None
        prev = out[-1] if out else None
        if len(row) == 1 and prev is not None and nxt is not None and len(prev) >= 2 and len(nxt) >= 2:
            cell = row[0]
            em = 0.5 * cell.size
            near = cell.y0 - max(ln.y1 for ln in prev) <= em and min(ln.y0 for ln in nxt) - cell.y1 <= em
            beside = all(cell.x1 < ln.x0 or cell.x0 > ln.x1 for ln in prev)
            if near and beside and not _has_digit(prev) and not _has_digit(row):
                out[-1] = sorted([*prev, cell], key=lambda ln: ln.x0)
                continue
        out.append(row)
    return out


def _is_cell_row(row: list[Line]) -> bool:
    if len(row) < 2:
        return False
    avg = sum(len(ln.text) for ln in row) / len(row)
    return avg <= TABLE_CELL_CHARS or len(row) >= 4


def _columns(rows: list[list[Line]]) -> list[tuple[float, float]]:
    """Column x-ranges: merge overlapping cell extents across rows."""
    spans = sorted((ln.x0, ln.x1) for r in rows for ln in r)
    cols: list[list[float]] = []
    for x0, x1 in spans:
        if cols and x0 <= cols[-1][1] + 1.0:
            cols[-1][1] = max(cols[-1][1], x1)
        else:
            cols.append([x0, x1])
    return [(c[0], c[1]) for c in cols]


def _column_of(ln: Line, cols: list[tuple[float, float]]) -> int:
    """The column holding `ln`: the first one its left edge falls in, else the one nearest its centre (a
    header cell spanning two columns lands in the first it covers)."""
    for k, (a, b) in enumerate(cols):
        if a - 1.0 <= ln.x0 <= b + 1.0:
            return k
    mid = (ln.x0 + ln.x1) / 2
    return min(range(len(cols)), key=lambda k: max(cols[k][0] - mid, mid - cols[k][1], 0.0))


EQUATION_NUMBER = re.compile(r"^\(\d{1,3}[a-z]?\)$")
"""A display equation's number, "(4)" or "(3a)", set flush right like a last column."""
MATH_CHARS = frozenset("=+×·∑∏∫√∂∇∞≤≥≈≠∈∝±∓→↦⟨⟩|^′") | {chr(c) for c in range(0x391, 0x3CA)}
"""Operators, relations and Greek letters (a minus sign is left out: negative numbers fill real tables)."""
MATH_DENSITY = 0.2
"""A grid whose visible characters are at least this share math symbols is typeset math, not a table."""


def _display_math(group: list[list[Line]]) -> bool:
    """A display equation (or a block of them) that row and column grouping mistook for a table: fractions
    put the numerator, the main line and the denominator on separate rows and the equation number sits at
    the right like a last column. Half or more of the rows carry an equation number or an "=", or the grid
    is dense with math symbols."""
    mathy = sum(1 for r in group if EQUATION_NUMBER.match(r[-1].text.strip()) or any("=" in ln.text for ln in r))
    if 2 * mathy >= len(group):
        return True
    ink = [ch for r in group for ln in r for ch in ln.text if not ch.isspace()]
    return bool(ink) and sum(ch in MATH_CHARS for ch in ink) >= MATH_DENSITY * len(ink)


def _sparse_pair(group: list[list[Line]], n_cols: int) -> bool:
    """Two rows that leave a third or more of their cells empty and hold at most one number are a typeset
    formula, not a table (`Attention(Q, K, V) = softmax(` over `√dk`, numbered `(1)`)."""
    if len(group) != 2:
        return False
    filled = sum(len(r) for r in group)
    numeric = sum(1 for r in group for ln in r if any(ch.isdigit() for ch in ln.text))
    return filled <= (2 * n_cols) * 2 / 3 and numeric < 2


def detect_tables(lines: list[Line]) -> tuple[list[TableGrid], list[Line]]:
    """Find runs of at least two consecutive multi-cell rows whose cells fall into consistent columns."""
    rows = _rows(lines)
    tables: list[TableGrid] = []
    used: set[int] = set()
    i = 0
    while i < len(rows):
        if not _is_cell_row(rows[i]):
            i += 1
            continue
        j = i + 1
        while j < len(rows) and _is_cell_row(rows[j]):
            gap = rows[j][0].y0 - max(ln.y1 for ln in rows[j - 1])
            if gap > 2.0 * rows[j][0].size:
                break
            j += 1
        group = rows[i:j]
        width = max(len(r) for r in group)
        cols = _columns([r for r in group if len(r) == width] if width >= 3 else group)
        tabular = len(group) >= 2 and 2 <= len(cols) <= max(width, 2) + 1
        if tabular and not _sparse_pair(group, len(cols)) and not _display_math(group):
            grid = [["" for _ in cols] for _ in group]
            cell_runs: list[list[list[Run]]] = [[[] for _ in cols] for _ in group]
            for r_i, row in enumerate(group):
                for ln in row:
                    c_i = _column_of(ln, cols)
                    grid[r_i][c_i] = (grid[r_i][c_i] + " " + ln.text).strip()
                    if cell_runs[r_i][c_i] and ln.runs:
                        t, h, sc = cell_runs[r_i][c_i][-1]
                        cell_runs[r_i][c_i][-1] = (t + " ", h, sc)
                    cell_runs[r_i][c_i].extend(ln.runs)
                    used.add(ln.order)
            flat = [ln for r in group for ln in r]
            tables.append(
                TableGrid(
                    page=flat[0].page,
                    x0=min(ln.x0 for ln in flat),
                    y0=min(ln.y0 for ln in flat),
                    x1=max(ln.x1 for ln in flat),
                    y1=max(ln.y1 for ln in flat),
                    rows=grid,
                    header=all(ln.bold for ln in group[0]) and not all(ln.bold for ln in group[-1]),
                    order=min(ln.order for ln in flat),
                    runs=cell_runs,
                )
            )
            i = j
        else:
            i += 1
    return tables, [ln for ln in lines if ln.order not in used]


# ---------------------------------------------------------------------------
# Reading order
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class FigureText:
    """The lettering of one figure form (axis ticks, legend entries, panel labels): its lines read row by row,
    left to right, with the form's displayed box."""

    page: int
    x0: float
    y0: float
    x1: float
    y1: float
    lines: list[Line]
    order: int


def figure_texts(lines: list[Line], boxes: Sequence[Rect]) -> tuple[list[FigureText], list[Line]]:
    """Split off the lines drawn inside figure forms (`Line.figure` indexes `boxes`), one group per figure in
    row-major order, so they are neither read as tables nor joined into the page's paragraphs. Returns
    (figures, the lines on the page itself)."""
    groups: dict[int, list[Line]] = {}
    rest: list[Line] = []
    for ln in lines:
        if 0 <= ln.figure < len(boxes):
            groups.setdefault(ln.figure, []).append(ln)
        else:
            rest.append(ln)
    figures: list[FigureText] = []
    for k, group in sorted(groups.items()):
        ordered = [ln for row in _rows(group) for ln in row]
        x0, y0, x1, y1 = boxes[k]
        figures.append(FigureText(ordered[0].page, x0, y0, x1, y1, ordered, min(ln.order for ln in ordered)))
    return figures, rest


@dataclass(slots=True)
class Item:
    """A positioned unit to order: a text line, a table, a figure's lettering, or an image."""

    x0: float
    y0: float
    x1: float
    y1: float
    order: int
    line: Line | None = None
    table: TableGrid | None = None
    figure: FigureText | None = None
    image: tuple[float, float, float, float] | None = None
    column: int = 0
    extra: dict[str, str] = field(default_factory=dict)


def _gutter(items: list[Item], lo: float, hi: float) -> tuple[float, float] | None:
    """A vertical gutter in the middle half of [lo, hi]: the x position crossed by the fewest items (at most
    a fifth of them), with at least three items entirely on each side. Returns (left edge, right edge) of the
    gap between the two sides."""
    if len(items) < 6:
        return None
    width = hi - lo
    lo_mid, hi_mid = lo + 0.25 * width, lo + 0.75 * width
    candidates = sorted({it.x1 + 0.5 for it in items} | {it.x0 - 0.5 for it in items})
    candidates = [x for x in candidates if lo_mid <= x <= hi_mid][:400]
    best: tuple[int, float, tuple[float, float]] | None = None
    for x in candidates:
        left = [it for it in items if it.x1 <= x]
        right = [it for it in items if it.x0 >= x]
        if len(left) < 3 or len(right) < 3:
            continue
        crossing = len(items) - len(left) - len(right)
        if crossing > 0.2 * len(items):
            continue
        gap = (max(it.x1 for it in left), min(it.x0 for it in right))
        if gap[1] - gap[0] < 6.0:
            continue
        key = (crossing, -(gap[1] - gap[0]), gap)
        if best is None or key[:2] < best[:2]:
            best = key
    return None if best is None else best[2]


BAND_MIN_ITEMS = 3
"""A region of a page reads as two columns when at least this many items sit on each side of its gutter."""
BAND_DENSE_EM = 0.8
"""...and each side is running text: the median gap between its consecutive items is at most this many ems. A
two-column table whose labels sit one per row, a value of several lines beside each, is sparse on the label side
and keeps reading row by row."""


def _bands(items: list[Item], x: float) -> list[tuple[list[Item], list[Item], list[Item]]]:
    """`items` (sorted top to bottom) cut into bands at every item that crosses the vertical line `x`. Each band is
    (its items in order, those wholly left of `x`, those wholly right); a crossing item is a band of its own."""
    out: list[tuple[list[Item], list[Item], list[Item]]] = []
    cur: tuple[list[Item], list[Item], list[Item]] = ([], [], [])
    for it in items:
        if it.x1 <= x or it.x0 >= x:
            cur[0].append(it)
            (cur[1] if it.x1 <= x else cur[2]).append(it)
            continue
        if cur[0]:
            out.append(cur)
        out.append(([it], [], []))
        cur = ([], [], [])
    if cur[0]:
        out.append(cur)
    return out


def _dense(side: list[Item]) -> bool:
    """Consecutive items of `side` (top to bottom) follow each other at about line spacing."""
    gaps = sorted(
        (b.y0 - a.y1) / max(b.y1 - b.y0, 1.0) for a, b in itertools.pairwise(sorted(side, key=lambda it: it.y0))
    )
    return bool(gaps) and gaps[len(gaps) // 2] <= BAND_DENSE_EM


def _block_tops(side: list[Item]) -> list[tuple[float, float]]:
    """(top, line height) of each block of `side`: items that follow each other within an em of space."""
    out: list[tuple[float, float]] = []
    prev: Item | None = None
    for it in sorted(side, key=lambda it: it.y0):
        height = max(it.y1 - it.y0, 1.0)
        if prev is None or it.y0 - prev.y1 > height:
            out.append((it.y0, height))
        prev = it
    return out


def _paired_rows(left: list[Item], right: list[Item]) -> bool:
    """The two sides are the cells of a table: at least two blocks on each side and half or more of the blocks on
    the side with fewer start level (within a line) with a block on the other side, as a question beside its answer
    does. The paragraphs of two text columns start wherever their text takes them."""
    a, b = _block_tops(left), _block_tops(right)
    if len(a) > len(b):
        a, b = b, a
    if len(a) < 2:
        return False
    level = sum(1 for top, h in a if any(abs(top - other) <= 1.2 * max(h, oh) for other, oh in b))
    return level >= 2 and 2 * level >= len(a)


def _two_columns(left: list[Item], right: list[Item]) -> bool:
    """A band whose two sides are both columns of running text set beside each other: enough items on each side,
    each side dense, the sides overlapping vertically for at least half of the shorter one, and their blocks not
    paired off row by row like table cells (`_paired_rows`)."""
    if len(left) < BAND_MIN_ITEMS or len(right) < BAND_MIN_ITEMS or not _dense(left) or not _dense(right):
        return False
    if _paired_rows(left, right):
        return False
    l0, l1 = min(it.y0 for it in left), max(it.y1 for it in left)
    r0, r1 = min(it.y0 for it in right), max(it.y1 for it in right)
    return min(l1, r1) - max(l0, r0) >= 0.5 * min(l1 - l0, r1 - r0)


def _column_bands(items: list[Item], x: float) -> list[tuple[list[Item], list[Item], list[Item], bool]]:
    """`_bands` at `x`, each flagged when it reads as two columns: `_two_columns`, and the crossing items around
    it span the whole gap between its sides (full-width text; a line of the right column that starts a little left
    of `x` does not frame a band)."""
    bands = _bands(items, x)
    out: list[tuple[list[Item], list[Item], list[Item], bool]] = []
    for k, (band, left, right) in enumerate(bands):
        ok = _two_columns(left, right)
        if ok:
            inner, outer = max(it.x1 for it in left), min(it.x0 for it in right)
            frame = [bands[j][0][0] for j in (k - 1, k + 1) if 0 <= j < len(bands)]
            ok = all(it.x0 <= inner and it.x1 >= outer for it in frame)
        out.append((band, left, right, ok))
    return out


def _band_gutter(items: list[Item], lo: float, hi: float) -> float | None:
    """A gutter that holds in part of the page only: a sidebar or a two-column section between full-width text.
    The x position in the middle half of [lo, hi] that puts the most items into two-column bands (`_two_columns`),
    with at least 6 points clear on each side in those bands; None when no band qualifies."""
    if len(items) < 2 * BAND_MIN_ITEMS:
        return None
    width = hi - lo
    lo_mid, hi_mid = lo + 0.25 * width, lo + 0.75 * width
    candidates = sorted({it.x1 + 0.5 for it in items} | {it.x0 - 0.5 for it in items})
    candidates = [x for x in candidates if lo_mid <= x <= hi_mid][:400]
    best: tuple[int, float, float] | None = None
    for x in candidates:
        paired = [(left, right) for _, left, right, ok in _column_bands(items, x) if ok]
        if not paired:
            continue
        clear = min(min(it.x0 for it in r) - max(it.x1 for it in lf) for lf, r in paired)
        if clear < 6.0:
            continue
        key = (sum(len(lf) + len(r) for lf, r in paired), clear, x)
        if best is None or key[:2] > best[:2]:
            best = key
    return None if best is None else best[2]


def order_items(items: list[Item], lo: float, hi: float, depth: int = 0) -> tuple[list[Item], bool]:
    """Top-to-bottom order; when a column gutter is found, full-width items split the page into bands and
    each band reads left column then right column (recursively, up to three levels). A gutter that holds only in
    part of the page (`_band_gutter`) splits only the bands where two columns of running text stand side by side;
    the rest of the page reads top to bottom. Returns (ordered, columns_found)."""
    items = sorted(items, key=lambda it: (it.y0, it.x0))
    gutter = _gutter(items, lo, hi) if depth < 3 else None
    if gutter is None:
        x = _band_gutter(items, lo, hi) if depth < 3 else None
        if x is None:
            return items, False
        banded: list[Item] = []
        for band, west, east, ok in _column_bands(items, x):
            if not ok:
                banded.extend(band)
                continue
            for side, a, b, col in ((west, lo, x, 1), (east, x, hi, 2)):
                for it in side:
                    it.column = 2 * depth + col
                banded.extend(order_items(side, a, b, depth + 1)[0])
        return banded, True
    out: list[Item] = []
    left: list[Item] = []
    right: list[Item] = []

    def flush() -> None:
        if left:
            sub, _ = order_items(left, lo, gutter[0], depth + 1)
            out.extend(sub)
        if right:
            sub, _ = order_items(right, gutter[1], hi, depth + 1)
            out.extend(sub)
        left.clear()
        right.clear()

    for it in items:
        if it.x1 <= gutter[0]:
            it.column = 2 * depth + 1
            left.append(it)
        elif it.x0 >= gutter[1]:
            it.column = 2 * depth + 2
            right.append(it)
        else:
            flush()
            out.append(it)
    flush()
    return out, True


def interleaved(ordered: list[Item]) -> bool:
    """True when the content-stream order disagrees with the geometric order (the source interleaved lines)."""
    seq = [it.order for it in ordered if it.line is not None]
    return any(b < a for a, b in itertools.pairwise(seq))


# ---------------------------------------------------------------------------
# Headings from font size
# ---------------------------------------------------------------------------


def size_levels(pages: Sequence[PageText], body: float, skip: set[int]) -> dict[float, int]:
    """Map heading font sizes (rounded to 0.5 pt) to levels 1..6, largest first."""
    sizes = sorted(
        {
            round(ln.size * 2) / 2
            for p in pages
            for ln in p.lines
            if ln.order not in skip and ln.size >= body * HEADING_RATIO and 0 < len(ln.text) <= 200
        },
        reverse=True,
    )
    return {s: min(i + 1, 6) for i, s in enumerate(sizes)}
