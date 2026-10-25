"""Turn ordered text-layer items into IR blocks: headings (structure tree, outline, or font size), paragraphs
with dehyphenation and inline links, lists, best-effort tables, and page markers."""

from __future__ import annotations

import dataclasses
import itertools
import re
from dataclasses import dataclass, field

from ezmd.ir import (
    BBox,
    Block,
    Heading,
    InlineSpan,
    InlineStyle,
    ListBlock,
    ListItem,
    PageBreak,
    Paragraph,
    Provenance,
    Table,
    TableCell,
)
from ezmd_converters.pdf.headings import HeadingSources
from ezmd_converters.pdf.layout import FigureText, Item, TableGrid
from ezmd_converters.pdf.textlayer import Line, Run

_BULLETS = "".join(chr(c) for c in (0x2022, 0x25E6, 0x25AA, 0x2023, 0x2219, 0x00B7, 0x25CF, 0x25A0, 0x2013, 0x2043))
_BULLET = re.compile("^[" + re.escape(_BULLETS + "-*") + r"]\s+")
_NUMBERED = re.compile(r"^(\d{1,3}|[a-z])[.)]\s+")
_HYPHEN_END = re.compile(r"([A-Za-z]+)-$")
_WORD_START = re.compile(r"^([a-z]+)")
_WORDS = re.compile(r"[A-Za-z]+")

FIGURE_TEXT_ATTR = "pdf_figure_text"
"""`Paragraph.attrs` key on a paragraph that holds one figure's lettering; the value is the number of lines."""


@dataclass(slots=True)
class PageGeom:
    number: int
    width: float
    height: float


def _bbox(x0: float, y0: float, x1: float, y1: float, g: PageGeom) -> BBox:
    x0, x1 = max(0.0, min(x0, g.width)), max(0.0, min(x1, g.width))
    y0, y1 = max(0.0, min(y0, g.height)), max(0.0, min(y1, g.height))
    return BBox(
        x0=round(x0, 2),
        y0=round(y0, 2),
        x1=round(max(x0, x1), 2),
        y1=round(max(y0, y1), 2),
        page_width=round(g.width, 2),
        page_height=round(g.height, 2),
    )


def _prov(source: str, g: PageGeom, x0: float, y0: float, x1: float, y1: float, engine: str) -> Provenance:
    return Provenance(source=source, source_page=g.number, bbox=_bbox(x0, y0, x1, y1, g), engine=engine)


_SCRIPT_STYLES = {"sup": [InlineStyle.SUPERSCRIPT], "sub": [InlineStyle.SUBSCRIPT]}


def _spans(runs: list[Run]) -> list[InlineSpan]:
    out: list[InlineSpan] = []
    for text, href, script in runs:
        styles = _SCRIPT_STYLES.get(script or "", [])
        if out and out[-1].href == href and out[-1].styles == styles:
            out[-1] = out[-1].model_copy(update={"text": out[-1].text + text})
        elif text:
            out.append(InlineSpan(text=text, href=href, styles=list(styles)))
    if out:
        out[0] = out[0].model_copy(update={"text": out[0].text.lstrip()})
        out[-1] = out[-1].model_copy(update={"text": out[-1].text.rstrip()})
    return [s for s in out if s.text]


def vocabulary(lines: list[Line]) -> set[str]:
    return {w.casefold() for ln in lines for w in _WORDS.findall(ln.text)}


def _join(acc: list[Run], nxt: list[Run], vocab: set[str], dehyphenate: bool) -> None:
    """Append line runs to paragraph runs, joining hyphenated breaks when the joined word is known."""
    if not acc:
        acc.extend(nxt)
        return
    last_text, last_href, last_script = acc[-1]
    first = nxt[0][0] if nxt else ""
    m_end = _HYPHEN_END.search(last_text)
    m_start = _WORD_START.match(first)
    if m_end and m_start:
        joined = (m_end.group(1) + m_start.group(1)).casefold()
        if dehyphenate and joined in vocab:
            acc[-1] = (last_text[:-1], last_href, last_script)
        acc.extend(nxt)
        return
    acc[-1] = (last_text + " ", last_href, last_script)
    acc.extend(nxt)


def _marker(text: str) -> tuple[bool, str, int] | None:
    """(ordered, text without marker, start number) when the line starts a list item."""
    m = _BULLET.match(text)
    if m:
        return False, text[m.end() :], 1
    m = _NUMBERED.match(text)
    if m:
        tok = m.group(1)
        return True, text[m.end() :], int(tok) if tok.isdigit() else 1
    return None


CONTINUE_EM = 0.7
"""A line this close below the previous one (in ems) continues its paragraph whatever the page's spacing."""
SPACING_SLACK_EM = 0.35
"""How much more than the page's typical line gap a continuation may leave: a paragraph break in a
double-spaced manuscript adds at least half a line, the indent rule catches the ones that add nothing."""
INDENT_EM = 0.8
"""A line starting this far right of the paragraph's left edge is indented."""
MAX_INDENT_EM = 4.0
"""A first-line indent is at most this wide; a bigger step left is a new block, not a return to the margin."""
SHORT_LINE_EM = 1.0
"""A line ending this far before the column's right edge stopped short: the end of a paragraph."""


def line_spacing(lines: list[Line]) -> float:
    """The page's typical vertical gap between consecutive lines of the same size in the same column, in ems:
    the median over pairs, 0.0 when the page has too few lines to say."""
    gaps: list[float] = []
    by_pos = sorted(lines, key=lambda ln: (round(ln.x0 / (2.0 * max(ln.size, 1.0))), ln.y0))
    for a, b in itertools.pairwise(by_pos):
        if abs(a.size - b.size) > 0.15 * max(a.size, b.size) or b.x0 > a.x1 or a.x0 > b.x1:
            continue
        gap = (b.y0 - a.y1) / max(b.size, 1.0)
        if -0.2 <= gap <= 2.0:
            gaps.append(gap)
    if len(gaps) < 4:
        return 0.0
    gaps.sort()
    return gaps[len(gaps) // 2]


def column_right_edges(lines: list[Line]) -> dict[int, float]:
    """For each line, the right edge of its column: the 90th percentile of x1 over lines that start within two
    ems of its left edge (so an indented first line still sees its column's edge)."""
    out: dict[int, float] = {}
    for ln in lines:
        peers = sorted(o.x1 for o in lines if abs(o.x0 - ln.x0) <= 2.0 * max(ln.size, 1.0))
        out[ln.order] = peers[min(len(peers) - 1, int(0.9 * len(peers)))] if peers else ln.x1
    return out


@dataclass(slots=True)
class _ListState:
    ordered: bool
    start: int
    x0: float
    first: Line
    last: Line
    items: list[tuple[float, list[Run]]] = field(default_factory=list)


class Assembler:
    def __init__(self, source: str, engine: str, headings: HeadingSources, vocab: set[str], dehyphenate: bool) -> None:
        self.source = source
        self.engine = engine
        self.headings = headings
        self.vocab = vocab
        self.dehyphenate = dehyphenate
        self.blocks: list[Block] = []
        self._para: list[Line] = []
        self._runs: list[Run] = []
        self._list: _ListState | None = None
        self._geom = PageGeom(1, 612.0, 792.0)
        self._table_tail: tuple[int, Table] | None = None
        self._spacing = 0.0
        """The page's typical gap between consecutive body lines, in ems (0.2 to 0.4 single-spaced, about 1.0
        double-spaced)."""
        self._right: dict[int, float] = {}
        """Line order -> right edge of the column that line sits in."""

    # -- page level ---------------------------------------------------------
    def page(self, geom: PageGeom, ordered: list[Item], marker: bool) -> None:
        self.flush()
        self._geom = geom
        lines = [it.line for it in ordered if it.line is not None]
        self._spacing = line_spacing(lines)
        self._right = column_right_edges(lines)
        if marker:
            self.blocks.append(
                PageBreak(page_number=geom.number, provenance=Provenance(source=self.source, source_page=geom.number))
            )
        for it in ordered:
            if it.table is not None:
                self.flush()
                self._append_table(self._table(it.table))
            elif it.figure is not None:
                self.flush()
                self.blocks.append(self._figure(it.figure))
            elif it.line is not None:
                self._line(it.line)
        self.flush()

    # -- lines --------------------------------------------------------------
    def _line(self, ln: Line) -> None:
        level = self.headings.level(ln)
        cut = self.headings.run_in.pop(ln.order, None)
        if level is not None and cut is not None:
            head, tail = _split_runs(ln.runs, cut)
            if head:
                text, href, script = head[-1]
                head[-1] = (text.rstrip().rstrip(".:"), href, script)  # "2.1. Metric graph theory." loses its "."
            self.flush()
            self.blocks.append(Heading(level=level, spans=_spans(head), provenance=self._lprov([ln])))
            if tail:
                self._para.append(dataclasses.replace(ln, runs=tail))
                _join(self._runs, tail, self.vocab, self.dehyphenate)
            return
        if level is not None:
            self.flush()
            prev = self.blocks[-1] if self.blocks else None
            if (
                isinstance(prev, Heading)
                and prev.level == level
                and prev.provenance.source_page == ln.page
                and prev.provenance.bbox is not None
                and 0 <= ln.y0 - prev.provenance.bbox.y1 <= 0.6 * ln.size
            ):
                b = prev.provenance.bbox
                prev.spans = [InlineSpan(text=" ".join(s.text for s in prev.spans) + " " + ln.text)]
                prev.provenance = _prov(
                    self.source, self._geom, min(b.x0, ln.x0), b.y0, max(b.x1, ln.x1), ln.y1, self.engine
                )
                return
            self.blocks.append(Heading(level=level, spans=_spans(ln.runs), provenance=self._lprov([ln])))
            return
        mk = _marker(ln.text)
        if mk is not None:
            self._flush_para()
            ordered, rest, start = mk
            runs: list[Run] = (
                [(rest, ln.runs[-1][1] if ln.runs else None, None)]
                if len(ln.runs) <= 1
                else _strip_marker(ln.runs, len(ln.text) - len(rest))
            )
            if self._list is None or self._list.ordered != ordered or ln.y0 - self._list.last.y1 > 1.2 * ln.size:
                self._flush_list()
                self._list = _ListState(ordered=ordered, start=start, x0=ln.x0, first=ln, last=ln)
            self._list.items.append((ln.x0, runs))
            self._list.last = ln
            return
        if self._list is not None:
            lst = self._list
            if ln.x0 > lst.x0 + 2.0 and 0 <= ln.y0 - lst.last.y1 <= 0.8 * ln.size:
                _join(lst.items[-1][1], ln.runs, self.vocab, self.dehyphenate)
                lst.last = ln
                return
            self._flush_list()
        if self._para and not self._continues(self._para[-1], ln):
            self._flush_para()
        self._para.append(ln)
        _join(self._runs, ln.runs, self.vocab, self.dehyphenate)

    def _continues(self, prev: Line, ln: Line) -> bool:
        """Does `ln` continue the open paragraph? Same size and weight; a vertical gap no larger than the page's
        own line spacing allows (single-spaced text continues within 0.7 em, a double-spaced manuscript within
        its measured spacing plus a little); and a left edge that fits the paragraph: at its left edge, or
        returning to the margin after an indented first line. A line indented past the paragraph's left edge
        after a short line is a new paragraph (the first-line indent of body text)."""
        if abs(prev.size - ln.size) > 0.15 * max(prev.size, ln.size) or prev.bold != ln.bold:
            return False
        limit = max(CONTINUE_EM, self._spacing + SPACING_SLACK_EM)
        if not -0.2 * ln.size <= ln.y0 - prev.y1 <= limit * ln.size:
            return False
        left = min(line.x0 for line in self._para)
        if ln.x0 < left - 2.0:
            # The first line was indented and this one returns to the margin.
            return len(self._para) == 1 and left - ln.x0 <= MAX_INDENT_EM * ln.size
        if ln.x0 > left + INDENT_EM * ln.size:
            # Indented relative to the paragraph: a new paragraph when the previous line stopped short of the
            # column's right edge, a continuation (a hanging indent, a centred line) otherwise.
            right = self._right.get(prev.order, prev.x1)
            if prev.x1 < right - SHORT_LINE_EM * ln.size:
                return False
        return ln.x0 <= left + 3.0 * ln.size

    def _lprov(self, lines: list[Line]) -> Provenance:
        return _prov(
            self.source,
            self._geom,
            min(ln.x0 for ln in lines),
            min(ln.y0 for ln in lines),
            max(ln.x1 for ln in lines),
            max(ln.y1 for ln in lines),
            self.engine,
        )

    # -- flushing -----------------------------------------------------------
    def flush(self) -> None:
        self._flush_para()
        self._flush_list()

    def _flush_para(self) -> None:
        if self._para:
            spans = _spans(self._runs)
            if spans:
                self.blocks.append(Paragraph(spans=spans, provenance=self._lprov(self._para)))
        self._para, self._runs = [], []

    def _flush_list(self) -> None:
        lst = self._list
        if lst is None:
            return
        self._list = None
        indents = sorted({round(x / 4.0) for x, _ in lst.items})
        root: list[ListItem] = []
        stack: list[tuple[int, list[ListItem]]] = [(0, root)]
        for x, runs in lst.items:
            depth = min(indents.index(round(x / 4.0)), 5)
            item = ListItem(spans=_spans(runs))
            while len(stack) > 1 and stack[-1][0] > depth:
                stack.pop()
            if depth > stack[-1][0] and stack[-1][1]:
                parent = stack[-1][1][-1]
                parent.children.append(item)
                stack.append((depth, parent.children))
            else:
                stack[-1][1].append(item)
        lines = [lst.first, lst.last]
        self.blocks.append(ListBlock(ordered=lst.ordered, start=lst.start, items=root, provenance=self._lprov(lines)))

    def _append_table(self, table: Table) -> None:
        """Append a table, or continue the previous page's table (spec part2.md 1f.9). A continuation needs
        all of: the previous content block is that table (only page markers between), it is on the previous page
        and ends in the bottom part of it, this table starts in the top part of its page, both have one header
        row, the column counts match, and the header cells are identical. The repeated header is dropped;
        `attrs.pdf_table_pages` lists the pages and `attrs.pdf_table_row_pages` maps row ranges to pages."""
        k = len(self.blocks) - 1
        while k >= 0 and isinstance(self.blocks[k], PageBreak):
            k -= 1
        prev = self.blocks[k] if k >= 0 else None
        # The last fragment of a merged table decides whether the next page continues it (its page and bbox).
        tail = self._table_tail[1] if self._table_tail is not None and self._table_tail[0] == k else prev
        if isinstance(prev, Table) and isinstance(tail, Table) and _continues_table(prev, tail, table):
            rows = [c.model_copy(update={"row": c.row - 1 + prev.n_rows}) for c in table.cells if c.row >= 1]
            pages = str(prev.attrs.get("pdf_table_pages", prev.provenance.source_page))
            first_page = prev.provenance.source_page
            row_pages = str(prev.attrs.get("pdf_table_row_pages", f"{first_page}:0-{prev.n_rows - 1}"))
            n_rows = prev.n_rows + table.n_rows - 1
            span = f"{table.provenance.source_page}:{prev.n_rows}-{n_rows - 1}"
            merged = prev.model_copy(
                update={
                    "cells": [*prev.cells, *rows],
                    "n_rows": n_rows,
                    "attrs": {
                        **prev.attrs,
                        "pdf_table_pages": f"{pages},{table.provenance.source_page}",
                        "pdf_table_row_pages": f"{row_pages},{span}",
                    },
                }
            )
            self.blocks[k] = merged
            self._table_tail = (k, table)
            return
        self.blocks.append(table)
        self._table_tail = (len(self.blocks) - 1, table)

    def _table(self, t: TableGrid) -> Table:
        n_cols = max(len(r) for r in t.rows)
        cells = [
            TableCell(spans=self._cell_spans(t, r, c, text), row=r, col=c, is_header=(r == 0 and t.header))
            for r, row in enumerate(t.rows)
            for c, text in enumerate(row)
        ]
        return Table(
            cells=cells,
            n_rows=len(t.rows),
            n_cols=n_cols,
            header_rows=1 if t.header else 0,
            provenance=_prov(self.source, self._geom, t.x0, t.y0, t.x1, t.y1, self.engine),
            attrs={"pdf_table": "heuristic"},
        )

    def _figure(self, f: FigureText) -> Paragraph:
        """One figure's lettering as a single paragraph, in reading order, where the figure sits: the text of a
        chart that cannot be read as data (docs/internal/spec/part3.md, chart fallback). Never a table, a heading
        or part of the surrounding prose."""
        runs: list[Run] = []
        for ln in f.lines:
            if runs:
                text, href, script = runs[-1]
                runs[-1] = (text + " ", href, script)
            runs.extend(ln.runs)
        return Paragraph(
            spans=_spans(runs),
            provenance=_prov(self.source, self._geom, f.x0, f.y0, f.x1, f.y1, self.engine),
            attrs={FIGURE_TEXT_ATTR: str(len(f.lines))},
        )

    @staticmethod
    def _cell_spans(t: TableGrid, r: int, c: int, text: str) -> list[InlineSpan]:
        if r < len(t.runs) and c < len(t.runs[r]) and t.runs[r][c]:
            return _spans(t.runs[r][c])
        return [InlineSpan(text=text)] if text else []


CONTINUATION_EDGE = 0.3
"""A table continues across a page break only when the first part ends in the bottom CONTINUATION_EDGE of
its page and the next part starts in the top CONTINUATION_EDGE of the following page."""


def _continues_table(prev: Table, tail: Table, table: Table) -> bool:
    """`prev` is the (possibly already merged) table, `tail` its last page fragment, `table` the candidate."""
    prev_page, page = tail.provenance.source_page or 0, table.provenance.source_page or 0
    a, b = tail.provenance.bbox, table.provenance.bbox
    if page != prev_page + 1 or a is None or b is None or not a.page_height or not b.page_height:
        return False
    at_bottom = a.y1 >= (1 - CONTINUATION_EDGE) * a.page_height
    at_top = b.y0 <= CONTINUATION_EDGE * b.page_height
    return (
        at_bottom
        and at_top
        and prev.header_rows == 1
        and table.header_rows == 1
        and prev.n_cols == table.n_cols
        and _header_texts(prev) == _header_texts(table)
    )


def _header_texts(t: Table) -> list[str]:
    return [" ".join(s.text for s in c.spans) for c in sorted(t.cells, key=lambda c: c.col) if c.row == 0]


def _split_runs(runs: list[Run], n: int) -> tuple[list[Run], list[Run]]:
    """Runs split after `n` characters of text (a run-in heading and the paragraph it opens)."""
    head: list[Run] = []
    rest: list[Run] = []
    for text, href, script in runs:
        if n >= len(text):
            head.append((text, href, script))
            n -= len(text)
        elif n > 0:
            head.append((text[:n], href, script))
            rest.append((text[n:].lstrip(), href, script))
            n = 0
        else:
            rest.append((text, href, script))
    return head, [r for r in rest if r[0]]


def _strip_marker(runs: list[Run], n: int) -> list[Run]:
    out: list[Run] = []
    for text, href, script in runs:
        if n >= len(text):
            n -= len(text)
            continue
        out.append((text[n:], href, script))
        n = 0
    return out
