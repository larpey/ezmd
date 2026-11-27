"""Word-processor bullets: the glyph sits at the list indent and a tab carries the text to the hanging indent,
up to half an inch further right, so the bullet and its text are separate runs on one baseline."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from conftest import TextOp, convert_path

from ezmd.ir import ListBlock, Paragraph, spans_text
from ezmd_converters.pdf.textlayer import Line, attach_bullets

BULLET = "•"
ITEMS = [
    "The harbor master keeps the tide tables in the north office.",
    "The lighthouse lamp is checked before dusk every evening.",
    "The breakwater is inspected each spring after the storms.",
]


def _page(size: float, bullet_x: float, text_x: float) -> list[TextOp]:
    """A body paragraph, then three items with the bullet at `bullet_x` and the text at `text_x`."""
    lead = 1.25 * size
    ops: list[TextOp] = [
        (72.0, 700.0 - lead * k, f"Line {k} of the survey notes on the old harbor and its lighthouse.", size, False)
        for k in range(8)
    ]
    y = 700.0 - lead * 10
    for k, text in enumerate(ITEMS):
        ops.append((bullet_x, y - 2 * lead * k, BULLET, size, False))
        ops.append((text_x, y - 2 * lead * k, text, size, False))
    return ops


@pytest.mark.parametrize(
    ("size", "bullet_x", "text_x"),
    [
        (10.0, 90.0, 126.0),  # bullet at 1/4 inch, text at the 1/2 inch hanging indent: about 3.3 em apart
        (9.0, 72.0, 108.0),  # 9 pt text and a half-inch tab: about 3.7 em
        (8.0, 72.0, 108.0),  # 8 pt text and the same tab: about 4.2 em
    ],
)
def test_a_bullet_a_tab_stop_left_of_its_text_opens_the_item(
    make_pdf: Callable[..., Path], size: float, bullet_x: float, text_x: float
) -> None:
    doc = convert_path(make_pdf([_page(size, bullet_x, text_x)]))
    items = [spans_text(i.spans) for b in doc.blocks if isinstance(b, ListBlock) for i in b.items]
    assert items == ITEMS  # a blank line between items may start a new list; each is still an item
    assert not [b for b in doc.blocks if isinstance(b, Paragraph) and spans_text(b.spans).strip() == BULLET]


def test_a_bullet_a_column_away_from_the_text_is_left_alone(make_pdf: Callable[..., Path]) -> None:
    """A dot more than a tab stop from the next text on its baseline (a chart marker, a table cell) is not
    that text's bullet."""
    ops: list[TextOp] = [
        (72.0, 400.0, BULLET, 10.0, False),
        (150.0, 400.0, "The ferry timetable is posted by the pier.", 10.0, False),
    ]
    doc = convert_path(make_pdf([_page(10.0, 90.0, 126.0) + ops]))
    items = [spans_text(i.spans) for b in doc.blocks if isinstance(b, ListBlock) for i in b.items]
    assert items == ITEMS


@pytest.mark.parametrize(("gap_em", "attached"), [(4.4, True), (5.0, False)])
def test_a_bullet_reaches_four_and_a_half_ems_and_no_further(gap_em: float, attached: bool) -> None:
    mark = Line(1, 72.0, 200.0, 77.0, 210.0, 10.0, False, [(BULLET, None, None)], 0)
    x0 = mark.x1 + 10.0 * gap_em
    text = Line(1, x0, 200.0, x0 + 50.0, 210.0, 10.0, False, [("Tide tables", None, None)], 1)
    expected = [f"{BULLET} Tide tables"] if attached else [BULLET, "Tide tables"]
    assert [ln.text for ln in attach_bullets([mark, text], 0)] == expected
