"""Slide-deck PDFs: bullets drawn small on their own baseline (#28), and slides whose body text is larger than
the document's (#33)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from conftest import TextOp, convert_path

from ezmd.ir import Document, Heading, ListBlock, Paragraph, spans_text

BULLET = "•"


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
    doc = convert_path(make_pdf([_body_page(), _slide(24.0)]))
    assert [h for h in _headings(doc) if h[0] >= 3] == []
    assert not any(BULLET in text for _, text in _headings(doc))
    assert _lists(doc)[-1] == _ITEMS
    assert "Harbor inspection questions" in [t for _, t in _headings(doc)]


def test_bulleted_lines_are_never_headings_even_with_a_subtitle_on_the_slide(make_pdf: Callable[..., Path]) -> None:
    """Three sizes above the body: the slide rule does not apply, the bullet glyph (and the lines wrapped under
    it) decide."""
    doc = convert_path(make_pdf([_body_page(), _slide(24.0, subtitle=True)]))
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
