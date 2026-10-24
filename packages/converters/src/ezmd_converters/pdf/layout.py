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

from ezmd_converters.pdf.textlayer import Line, PageText, Run

MARGIN_ZONE = 0.08
"""Top and bottom share of the page height where running headers and footers live."""
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
    """`Line.order` values of running headers/footers: lines in the top or bottom margin zone whose
    normalized text (digits collapsed, so page numbers match) repeats on at least half the pages (min 2)."""
    if len(pages) < 2:
        return set()
    seen: dict[str, set[int]] = {}
    where: dict[str, list[int]] = {}
    for p in pages:
        for ln in p.lines:
            if ln.y1 <= p.height * MARGIN_ZONE or ln.y0 >= p.height * (1 - MARGIN_ZONE):
                key = ("T:" if ln.y1 <= p.height / 2 else "B:") + norm_key(ln.text)
                seen.setdefault(key, set()).add(p.number)
                where.setdefault(key, []).append(ln.order)
    need = max(2, math.ceil(len(pages) * 0.5))
    out: set[int] = set()
    for key, pgs in seen.items():
        if len(pgs) >= need:
            out.update(where[key])
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
        if len(group) >= 2 and 2 <= len(cols) <= max(width, 2) + 1 and not _sparse_pair(group, len(cols)):
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
class Item:
    """A positioned unit to order: a text line, a table, or an image."""

    x0: float
    y0: float
    x1: float
    y1: float
    order: int
    line: Line | None = None
    table: TableGrid | None = None
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


def order_items(items: list[Item], lo: float, hi: float, depth: int = 0) -> tuple[list[Item], bool]:
    """Top-to-bottom order; when a column gutter is found, full-width items split the page into bands and
    each band reads left column then right column (recursively, up to three levels). Returns (ordered,
    columns_found)."""
    items = sorted(items, key=lambda it: (it.y0, it.x0))
    gutter = _gutter(items, lo, hi) if depth < 3 else None
    if gutter is None:
        return items, False
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
