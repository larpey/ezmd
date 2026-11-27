"""Paragraph assembly from text-layer lines: the page's own line spacing decides what continues a paragraph,
and a first-line indent after a short line starts one (ezmd_converters.pdf.assemble)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from conftest import TextOp, convert_path

from ezmd.ir import Document, Paragraph, spans_text
from ezmd_converters.pdf.assemble import PAGES_ATTR, Assembler, PageGeom, column_right_edges, line_spacing
from ezmd_converters.pdf.headings import HeadingSources
from ezmd_converters.pdf.layout import Item
from ezmd_converters.pdf.textlayer import Line

SIZE = 10.0
LEFT = 72.0
RIGHT = 540.0


def _line(text: str, y0: float, *, x0: float = LEFT, x1: float = RIGHT, order: int, size: float = SIZE) -> Line:
    return Line(1, x0, y0, x1, y0 + size, size, False, [(text, None, None)], order)


def _lines(
    texts: list[str], gap_em: float, *, indents: dict[int, float] | None = None, short: set[int] = frozenset()
) -> list[Line]:
    """Lines stacked down the page `gap_em` ems apart; `indents` moves a line's left edge, `short` ends one early."""
    out = []
    y = 100.0
    for i, text in enumerate(texts):
        x0 = LEFT + (indents or {}).get(i, 0.0)
        x1 = LEFT + 180.0 if i in short else RIGHT
        out.append(_line(text, y, x0=x0, x1=x1, order=i))
        y += SIZE * (1 + gap_em)
    return out


def _paragraphs(lines: list[Line]) -> list[str]:
    asm = Assembler("t.pdf", "pdfium", HeadingSources(), set(), True)
    items = [Item(ln.x0, ln.y0, ln.x1, ln.y1, ln.order, line=ln) for ln in lines]
    asm.page(PageGeom(1, 612.0, 792.0), items, False)
    return [spans_text(b.spans) for b in asm.blocks if isinstance(b, Paragraph)]


def test_single_spaced_lines_join_and_a_wide_gap_breaks() -> None:
    lines = _lines(["one two", "three four", "five six"], 0.3)
    assert _paragraphs(lines) == ["one two three four five six"]
    lines = _lines(["one two", "three four"], 0.3) + _lines(["new paragraph"], 0.3)
    lines[2] = _line("new paragraph", lines[1].y1 + 1.5 * SIZE, order=2)
    assert _paragraphs(lines) == ["one two three four", "new paragraph"]


def test_double_spaced_manuscript_lines_join_into_one_paragraph() -> None:
    texts = [f"line {i} of a double spaced manuscript" for i in range(8)]
    lines = _lines(texts, 1.0)
    assert line_spacing(lines) == 1.0
    assert _paragraphs(lines) == [" ".join(texts)]


def test_double_spaced_page_still_breaks_on_extra_space() -> None:
    lines = _lines([f"l{i}" for i in range(6)], 1.0)
    lines[3] = _line("l3", lines[2].y1 + 1.6 * SIZE, order=3)
    for i in (4, 5):
        lines[i] = _line(f"l{i}", lines[i - 1].y1 + 1.0 * SIZE, order=i)
    assert _paragraphs(lines) == ["l0 l1 l2", "l3 l4 l5"]


def test_first_line_indent_after_a_short_line_starts_a_paragraph() -> None:
    # Paragraph A: an indented first line, two lines at the margin, the last one short.
    # Paragraph B: starts indented again. Same spacing throughout, as in a double-spaced manuscript.
    texts = ["A first", "A second", "A last short", "B first", "B second"]
    lines = _lines(texts, 1.0, indents={0: 1.5 * SIZE, 3: 1.5 * SIZE}, short={2})
    assert _paragraphs(lines) == ["A first A second A last short", "B first B second"]


def test_hanging_indent_after_a_full_line_continues() -> None:
    # A reference entry: a full-width first line, continuation lines indented. Not a new paragraph.
    texts = ["Author, A. (2020). A long title that fills the line", "continued on the next line, indented."]
    lines = _lines(texts, 0.3, indents={1: 1.5 * SIZE})
    assert _paragraphs(lines) == [" ".join(texts)]


def test_line_spacing_needs_enough_pairs_and_column_right_edges_follow_the_column() -> None:
    assert line_spacing(_lines(["a", "b", "c"], 1.0)) == 0.0
    left = _lines([f"l{i}" for i in range(5)], 0.3)
    right = [_line(f"r{i}", 100.0 + i * 13.0, x0=320.0, x1=560.0, order=10 + i) for i in range(5)]
    right[2] = _line("short", right[2].y0, x0=320.0, x1=400.0, order=12)
    edges = column_right_edges(left + right)
    assert edges[0] == RIGHT and edges[12] == 560.0


# -- across a column or a page --------------------------------------------------------

HARBOR = [
    "The harbor pilots met each arriving vessel beyond the breakwater and stayed on the bridge",
    "until the lines were made fast, a duty they kept in every weather and at every hour of the",
    "night, so that no master ever brought a ship past the shoals without one of them beside the",
]
QUAY = [
    "helm and the tide tables open on the chart table, which the harbor board required by its rules.",
    "Smaller craft followed the marked channel on their own and kept clear of the deep water lane.",
]


def _stack(texts: list[str], x: float, top: float, step: float = 13.0) -> list[TextOp]:
    """Lines of 10 pt text downwards from `top` (PDF user space, so y decreases)."""
    return [(x, top - step * i, t, 10.0, False) for i, t in enumerate(texts)]


def _next_page(texts: list[str]) -> list[TextOp]:
    """The top of a page: the first line, then a new paragraph a blank line below."""
    return _stack(texts[:1], 72, 740) + _stack(texts[1:], 72, 714)


def _paras(doc: Document) -> list[Paragraph]:
    return [b for b in doc.blocks if isinstance(b, Paragraph)]


def test_a_sentence_running_over_a_page_break_stays_one_paragraph(make_pdf: Callable[..., Path]) -> None:
    doc = convert_path(make_pdf([_stack(HARBOR, 72, 160), _next_page(QUAY)]))
    kinds = [type(b).__name__ for b in doc.blocks]
    assert kinds == ["PageBreak", "Paragraph", "PageBreak", "Paragraph"]
    joined, rest = _paras(doc)
    assert spans_text(joined.spans) == " ".join([*HARBOR, QUAY[0]])
    assert spans_text(rest.spans) == QUAY[1]
    assert joined.attrs[PAGES_ATTR] == "1,2"
    assert joined.provenance.source_page == 1 and joined.provenance.bbox is not None
    assert joined.provenance.bbox.y1 > 600  # the part on page 1, at its foot

    # A page that ends a sentence, or a next page that opens with a capital, keeps the break.
    ended = [*HARBOR[:2], "night, as the harbor board required of them in its rules for the pilots of the port."]
    doc = convert_path(make_pdf([_stack(ended, 72, 160), _next_page(QUAY)]))
    assert len(_paras(doc)) == 3 and all(PAGES_ATTR not in p.attrs for p in _paras(doc))
    doc = convert_path(make_pdf([_stack(HARBOR, 72, 160), _next_page(QUAY[1:])]))
    assert len(_paras(doc)) == 2


KEEPER = [
    "The keeper climbed the iron stairs of",
    "the tower each evening, trimmed the",
    "wick, wound the clockwork and set it",
    "turning the great lens at the top of",
]
LAMP = [
    "the lighthouse until dawn, and then",
    "logged the weather and the passing",
    "ships in the book kept by the door.",
    "In winter the relief boat came only",
]


def test_a_sentence_running_from_one_column_into_the_next_stays_one_paragraph(make_pdf: Callable[..., Path]) -> None:
    right = _stack(LAMP[:3], 330, 700) + _stack(LAMP[3:], 330, 648)  # the last line opens a new paragraph
    doc = convert_path(make_pdf([_stack(KEEPER, 72, 700) + right]))
    texts = [spans_text(p.spans) for p in _paras(doc)]
    assert texts[0] == " ".join([*KEEPER, *LAMP[:3]])
    assert texts[1:] == [LAMP[3]]
