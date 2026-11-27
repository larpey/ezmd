"""Slide-deck PDFs: bullets drawn small on their own baseline (#28), and slides whose body text is larger than
the document's (#33)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from conftest import TextOp, convert_path

from ezmd.ir import Document, Heading, ListBlock, Paragraph, spans_text
from ezmd_converters.pdf.headings import plan_headings
from ezmd_converters.pdf.textlayer import Line, PageText, attach_bullets

BULLET = "•"
SLIDE_PAGE = (960, 720)


def _body_page(n: int = 12) -> list[TextOp]:
    """A page of 17 pt text that sets the document's body size."""
    return [
        (
            72.0,
            700.0 - 24 * k,
            f"Mooring line {k} runs from the quay to the bollard beside the old lighthouse.",
            17.0,
            False,
        )
        for k in range(n)
    ]


def _lists(doc: Document) -> list[list[str]]:
    return [[spans_text(i.spans) for i in b.items] for b in doc.blocks if isinstance(b, ListBlock)]


def _paragraphs(doc: Document) -> list[str]:
    return [spans_text(b.spans) for b in doc.blocks if isinstance(b, Paragraph)]


def _headings(doc: Document) -> list[tuple[int, str]]:
    return [(b.level, spans_text(b.spans)) for b in doc.blocks if isinstance(b, Heading)]


def test_a_small_bullet_on_its_own_baseline_is_the_prefix_of_the_text_beside_it(
    make_pdf: Callable[..., Path],
) -> None:
    ops: list[TextOp] = [
        (45.0, 396.0, BULLET, 7.0, False),
        (71.0, 400.0, "Where does the harbor master keep the tide tables?", 17.0, False),
        (45.0, 366.0, BULLET, 7.0, False),
        (71.0, 370.0, "Which lighthouse marks the northern channel?", 17.0, False),
        (45.0, 340.0, f"{BULLET} Who inspects the breakwater each spring?", 17.0, False),
    ]
    doc = convert_path(make_pdf([_body_page() + ops]))
    assert _lists(doc) == [
        [
            "Where does the harbor master keep the tide tables?",
            "Which lighthouse marks the northern channel?",
            "Who inspects the breakwater each spring?",
        ]
    ]
    assert not [p for p in _paragraphs(doc) if p.strip() in {BULLET, ""}]
    assert not [w for w in doc.warnings if str(w.kind) == "reading_order_uncertain"]


def test_a_small_bullet_does_not_split_a_wrapped_item(make_pdf: Callable[..., Path]) -> None:
    ops: list[TextOp] = [
        (45.0, 396.0, BULLET, 7.0, False),
        (71.0, 400.0, "Which of the three lighthouses on the northern shore", 17.0, False),
        (71.0, 380.0, "still burns a lamp through the winter?", 17.0, False),
        (45.0, 356.0, BULLET, 7.0, False),
        (71.0, 360.0, "Who keeps the logbook?", 17.0, False),
    ]
    doc = convert_path(make_pdf([_body_page() + ops]))
    assert _lists(doc) == [
        [
            "Which of the three lighthouses on the northern shore still burns a lamp through the winter?",
            "Who keeps the logbook?",
        ]
    ]


def test_a_bullet_far_from_the_text_is_left_alone(make_pdf: Callable[..., Path]) -> None:
    ops: list[TextOp] = [
        (45.0, 396.0, BULLET, 7.0, False),
        (300.0, 400.0, "Where does the harbor master keep the tide tables?", 17.0, False),
    ]
    doc = convert_path(make_pdf([_body_page() + ops]))
    assert not _lists(doc)


def _slide(size: float, subtitle: bool = False) -> list[TextOp]:
    ops: list[TextOp] = [(72.0, 700.0, "Harbor inspection questions", 44.0, False)]
    if subtitle:
        ops.append((72.0, 660.0, "Spring survey", 30.0, False))
    return [
        *ops,
        (72.0, 620.0, f"{BULLET} What does the lighthouse keeper log each night?", size, False),
        (97.0, 620.0 - 1.2 * size, "Is the lamp checked before dusk?", size, False),
        (72.0, 545.0, f"{BULLET} Where are the mooring lines stored?", size, False),
        (72.0, 505.0, f"{BULLET} Who signs off the breakwater survey each spring", size, False),
        (97.0, 505.0 - 1.2 * size, "and files it with the harbor office?", size, False),
    ]


_ITEMS = [
    "What does the lighthouse keeper log each night? Is the lamp checked before dusk?",
    "Where are the mooring lines stored?",
    "Who signs off the breakwater survey each spring and files it with the harbor office?",
]


def test_a_slide_whose_body_is_larger_than_the_documents_reads_like_one_at_body_size(
    make_pdf: Callable[..., Path],
) -> None:
    """The slide's only larger text is its title: the 24 pt questions are the slide's body, not H3s."""
    doc = convert_path(make_pdf([_body_page(), _slide(24.0)], size=SLIDE_PAGE))
    assert [h for h in _headings(doc) if h[0] >= 3] == []
    assert not any(BULLET in text for _, text in _headings(doc))
    assert _lists(doc)[-1] == _ITEMS
    assert "Harbor inspection questions" in [t for _, t in _headings(doc)]


def test_bulleted_lines_are_never_headings_even_with_a_subtitle_on_the_slide(make_pdf: Callable[..., Path]) -> None:
    """Three sizes above the body: the slide rule does not apply, the bullet glyph (and the lines wrapped under
    it) decide."""
    doc = convert_path(make_pdf([_body_page(), _slide(24.0, subtitle=True)], size=SLIDE_PAGE))
    assert not any(BULLET in text for _, text in _headings(doc))
    assert "Spring survey" in [t for _, t in _headings(doc)]
    assert _lists(doc)[-1] == _ITEMS


def test_a_long_run_of_same_size_lines_is_prose_not_one_truncated_heading(make_pdf: Callable[..., Path]) -> None:
    words = "Which of the harbor lights along the northern shore still burns through the long winter nights"
    lines = [words[i : i + 28].strip() for i in range(0, len(words), 28)]
    ops: list[TextOp] = [(72.0, 700.0 - 40 * k, text, 32.0, True) for k, text in enumerate(lines * 2)]
    doc = convert_path(make_pdf([_body_page(), ops]))
    heads = [t for _, t in _headings(doc)]
    assert not any(t.endswith("...") for t in heads)
    assert all(len(t) < 150 for t in heads)
    assert " ".join(lines * 2) in " ".join(_paragraphs(doc))


def _line(order: int, x0: float, y: float, text: str, size: float = 10.0, bold: bool = False) -> Line:
    return Line(1, x0, y, x0 + 0.5 * size * len(text), y + size, size, bold, [(text, None, None)], order)


def _planned(
    lines: list[Line], size: tuple[int, int], outline: list[tuple[int, str, int | None]] | None = None
) -> list[int | None]:
    """Heading levels of `lines` on one page of a document whose body size is 10 pt."""
    page = PageText(1, size[0], size[1], lines, sum(len(ln.text) for ln in lines), 0.0)
    src = plan_headings([page], 10.0, outline or [], set())
    return [src.level(ln) for ln in lines]


_SUBHEADS = ["Tides and soundings", "Moorings and bollards", "Lamps and logbooks"]


def _titled(bold: bool) -> list[Line]:
    """A 24 pt title over three spaced 14 pt subheads and nothing else."""
    subheads = [_line(k + 1, 72, 160 + 60 * k, text, 14.0, bold) for k, text in enumerate(_SUBHEADS)]
    return [_line(0, 72, 80, "The harbor", 24.0), *subheads]


@pytest.mark.parametrize("bold", [True, False])
def test_a_sparse_chapter_page_keeps_its_subheadings(bold: bool) -> None:
    assert _planned(_titled(bold), (612, 792)) == [1, 2, 2, 2]


def test_a_contents_page_keeps_its_headings() -> None:
    names = [*_SUBHEADS, "Breakwater survey", "Northern channel", "Harbor office"]
    entries = [_line(k + 1, 72, 160 + 40 * k, text, 14.0) for k, text in enumerate(names)]
    lines = [_line(0, 72, 80, "Contents", 24.0), *entries]
    assert _planned(lines, (612, 792)) == [1, 2, 2, 2, 2, 2, 2]


def test_a_landscape_page_demotes_plain_text_but_not_bold_subheads() -> None:
    assert _planned(_titled(False), SLIDE_PAGE) == [1, None, None, None]
    assert _planned(_titled(True), SLIDE_PAGE) == [1, 2, 2, 2]


def test_a_landscape_page_with_body_size_text_is_not_a_slide() -> None:
    lines = [*_titled(False), _line(4, 72, 400, "See the annex.", 10.0)]
    assert _planned(lines, SLIDE_PAGE) == [1, 2, 2, 2, None]


def test_a_small_footer_does_not_stop_a_page_being_a_slide() -> None:
    lines = [*_titled(False), _line(4, 72, 680, "7", 8.0)]
    assert _planned(lines, SLIDE_PAGE) == [1, None, None, None, None]


def test_an_outline_bookmarked_subhead_is_never_demoted() -> None:
    outline: list[tuple[int, str, int | None]] = [(2, "2.1 Moorings and bollards", 0)]
    levels = _planned(_titled(False), SLIDE_PAGE, outline)
    assert levels[2] == 3  # outline level 2, under the page's title
    assert levels[1] is None and levels[3] is None


@pytest.mark.parametrize("glyph", ["\u2013", "\u00b7"])
@pytest.mark.parametrize("gap_em", [1.5, 3.5])
def test_a_lone_dash_or_middle_dot_cell_is_not_attached(glyph: str, gap_em: float) -> None:
    dash = _line(0, 100, 200, glyph)
    number = _line(1, dash.x1 + 10.0 * gap_em, 200, "12")
    assert [ln.text for ln in attach_bullets([dash, number], 0)] == [glyph, "12"]


@pytest.mark.parametrize("glyph", ["\u2022", "\u25e6", "\u25aa", "\u25cf", "\u25a0"])
def test_a_real_bullet_is_attached(glyph: str) -> None:
    mark = _line(0, 100, 200, glyph)
    text = _line(1, mark.x1 + 15.0, 200, "Tide tables")
    assert [ln.text for ln in attach_bullets([mark, text], 0)] == [f"{glyph} Tide tables"]


def test_an_empty_line_is_neither_a_bullet_nor_its_text() -> None:
    mark = _line(0, 100, 200, BULLET)
    empty = _line(1, mark.x1 + 5.0, 200, "")
    text = _line(2, mark.x1 + 15.0, 200, "Tide tables")
    assert [ln.text for ln in attach_bullets([mark, empty, text], 0)] == ["", f"{BULLET} Tide tables"]
    # An empty line is not a list item, so the indented line under it can still be a heading.
    blank = _line(0, 72, 200, "", 20.0)
    heading = _line(1, 90, 225, "Harbor", 20.0)
    assert _planned([blank, heading], (612, 792))[1] == 1
