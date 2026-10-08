"""Turn ordered text-layer items into IR blocks: headings (structure tree, outline, or font size), paragraphs
with dehyphenation and inline links, lists, best-effort tables, and page markers."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from intomd.ir import (
    BBox,
    Block,
    Heading,
    InlineSpan,
    ListBlock,
    ListItem,
    PageBreak,
    Paragraph,
    Provenance,
    Table,
    TableCell,
)
from intomd_converters.pdf.layout import Item, TableGrid, norm_text
from intomd_converters.pdf.textlayer import Line

_BULLETS = "".join(chr(c) for c in (0x2022, 0x25E6, 0x25AA, 0x2023, 0x2219, 0x00B7, 0x25CF, 0x25A0, 0x2013, 0x2043))
_BULLET = re.compile("^[" + re.escape(_BULLETS + "-*") + r"]\s+")
_NUMBERED = re.compile(r"^(\d{1,3}|[a-z])[.)]\s+")
_HYPHEN_END = re.compile(r"([A-Za-z]+)-$")
_WORD_START = re.compile(r"^([a-z]+)")
_WORDS = re.compile(r"[A-Za-z]+")


@dataclass(slots=True)
class HeadingSources:
    """Where heading levels come from, in precedence order."""

    struct: dict[tuple[int, int], int] = field(default_factory=dict)
    outline: dict[tuple[str, int | None], int] = field(default_factory=dict)
    outline_any: dict[str, int] = field(default_factory=dict)
    sizes: dict[float, int] = field(default_factory=dict)
    use_struct: bool = False
    struct_only: bool = False
    used: dict[str, int] = field(default_factory=dict)
    disagreements: int = 0

    def level(self, ln: Line) -> int | None:
        size_level = self.sizes.get(round(ln.size * 2) / 2)
        if len(ln.text) > 200:
            size_level = None
        if self.use_struct:
            hits = [self.struct[(ln.page - 1, m)] for m in ln.mcids if (ln.page - 1, m) in self.struct]
            if hits or (ln.mcids and self.struct_only):
                lvl = min(hits) if hits else None
                if lvl != size_level:
                    self.disagreements += 1
                return self._count("structure_tree", lvl)
            if self.struct_only:
                return None
        key = norm_text(ln.text)
        lvl = self.outline.get((key, ln.page - 1)) or self.outline_any.get(key)
        if lvl is not None:
            return self._count("outline", lvl)
        return self._count("font_size", size_level)

    def _count(self, source: str, lvl: int | None) -> int | None:
        if lvl is not None:
            self.used[source] = self.used.get(source, 0) + 1
        return lvl


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


def _spans(runs: list[tuple[str, str | None]]) -> list[InlineSpan]:
    out: list[InlineSpan] = []
    for text, href in runs:
        if out and out[-1].href == href:
            out[-1] = InlineSpan(text=out[-1].text + text, href=href)
        elif text:
            out.append(InlineSpan(text=text, href=href))
    if out:
        out[0] = InlineSpan(text=out[0].text.lstrip(), href=out[0].href)
        out[-1] = InlineSpan(text=out[-1].text.rstrip(), href=out[-1].href)
    return [s for s in out if s.text]


def vocabulary(lines: list[Line]) -> set[str]:
    return {w.casefold() for ln in lines for w in _WORDS.findall(ln.text)}


def _join(
    acc: list[tuple[str, str | None]], nxt: list[tuple[str, str | None]], vocab: set[str], dehyphenate: bool
) -> None:
    """Append line runs to paragraph runs, joining hyphenated breaks when the joined word is known."""
    if not acc:
        acc.extend(nxt)
        return
    last_text, last_href = acc[-1]
    first = nxt[0][0] if nxt else ""
    m_end = _HYPHEN_END.search(last_text)
    m_start = _WORD_START.match(first)
    if m_end and m_start:
        joined = (m_end.group(1) + m_start.group(1)).casefold()
        if dehyphenate and joined in vocab:
            acc[-1] = (last_text[:-1], last_href)
        acc.extend(nxt)
        return
    acc[-1] = (last_text + " ", last_href)
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


@dataclass(slots=True)
class _ListState:
    ordered: bool
    start: int
    x0: float
    first: Line
    last: Line
    items: list[tuple[float, list[tuple[str, str | None]]]] = field(default_factory=list)


class Assembler:
    def __init__(self, source: str, engine: str, headings: HeadingSources, vocab: set[str], dehyphenate: bool) -> None:
        self.source = source
        self.engine = engine
        self.headings = headings
        self.vocab = vocab
        self.dehyphenate = dehyphenate
        self.blocks: list[Block] = []
        self._para: list[Line] = []
        self._runs: list[tuple[str, str | None]] = []
        self._list: _ListState | None = None
        self._geom = PageGeom(1, 612.0, 792.0)

    # -- page level ---------------------------------------------------------
    def page(self, geom: PageGeom, ordered: list[Item], marker: bool) -> None:
        self.flush()
        self._geom = geom
        if marker:
            self.blocks.append(
                PageBreak(page_number=geom.number, provenance=Provenance(source=self.source, source_page=geom.number))
            )
        for it in ordered:
            if it.table is not None:
                self.flush()
                self.blocks.append(self._table(it.table))
            elif it.line is not None:
                self._line(it.line)
        self.flush()

    # -- lines --------------------------------------------------------------
    def _line(self, ln: Line) -> None:
        level = self.headings.level(ln)
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
            runs = (
                [(rest, ln.runs[-1][1] if ln.runs else None)]
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
        first = self._para[0]
        return (
            abs(prev.size - ln.size) <= 0.15 * max(prev.size, ln.size)
            and -0.2 * ln.size <= ln.y0 - prev.y1 <= 0.7 * ln.size
            and first.x0 - 2.0 <= ln.x0 <= first.x0 + 3.0 * ln.size
            and prev.bold == ln.bold
        )

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

    def _table(self, t: TableGrid) -> Table:
        n_cols = max(len(r) for r in t.rows)
        cells = [
            TableCell(spans=[InlineSpan(text=text)] if text else [], row=r, col=c, is_header=(r == 0 and t.header))
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


def _strip_marker(runs: list[tuple[str, str | None]], n: int) -> list[tuple[str, str | None]]:
    out: list[tuple[str, str | None]] = []
    for text, href in runs:
        if n >= len(text):
            n -= len(text)
            continue
        out.append((text[n:], href))
        n = 0
    return out
