"""Figure lettering: text drawn inside a form XObject together with its graphics (an included plot) is one
paragraph where the figure sits, never a table, a heading or part of the prose."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import pikepdf
from conftest import TextOp, content, convert_path, new_pdf, save
from pikepdf import Array, Dictionary, Name

from ezmd.core.textclean import CleanStats
from ezmd.ir import Paragraph, Table, spans_text
from ezmd_converters.pdf.assemble import FIGURE_TEXT_ATTR
from ezmd_converters.pdf.layout import detect_tables, figure_texts
from ezmd_converters.pdf.textlayer import Line, read_page

LETTERING: list[TextOp] = [
    (10, 20, "0.0", 6, False),
    (60, 20, "0.5", 6, False),
    (110, 20, "1.0", 6, False),
    (10, 32, "a", 6, False),
    (60, 32, "b", 6, False),
    (110, 32, "c", 6, False),
    (40, 5, "Training Steps", 6, False),
]
"""Two adjacent rows of three short cells (a table to the row grouper) and an axis title, in the form's own
space."""

BODY: list[TextOp] = [
    (72, 700, "Figure text stays out of the prose.", 10, False),
    (72, 686, "A second body line follows the first.", 10, False),
    (72, 380, "Figure 1: Ticks and labels.", 10, False),
]


def _pdf_with_form(
    path: Path,
    *,
    graphics: int,
    lettering: Sequence[TextOp] = LETTERING,
    body: Sequence[TextOp] = BODY,
    matrix: Sequence[float] = (1, 0, 0, 1, 100, 400),
    bbox: Sequence[float] = (0, 0, 300, 200),
    rules: int = 0,
    pages: int = 1,
) -> Path:
    """A PDF whose pages draw `body` and place a form XObject holding `graphics` filled rectangles, `rules`
    thin horizontal lines and `lettering`, through `matrix`."""
    pdf = new_pdf([body] * pages)
    ops: list[tuple[list[object], str]] = []
    for k in range(graphics):
        ops += [([10 + 30 * k, 30, 20, 60 + 10 * k], "re"), ([], "f")]
    for k in range(rules):
        ops += [([5, 15 + 12 * k], "m"), ([140, 15 + 12 * k], "l"), ([], "S")]
    form = pikepdf.Stream(pdf, pikepdf.unparse_content_stream(ops) + b"\n" + content(lettering))
    form.Type = Name.XObject
    form.Subtype = Name.Form
    form.BBox = Array(list(bbox))
    form.Resources = Dictionary(Font=pdf.pages[0].Resources.Font)
    form_ref = pdf.make_indirect(form)
    placed = pikepdf.unparse_content_stream([(list(matrix), "cm"), ([Name("/Fx")], "Do")])
    for page in pdf.pages:
        page.Resources.XObject = Dictionary(Fx=form_ref)
        page.Contents = pdf.make_indirect(
            pikepdf.Stream(pdf, page.Contents.read_bytes() + b"\nq\n" + placed + b"\nQ\n")
        )
    return save(pdf, path)


def test_lettering_in_a_graphics_form_is_one_paragraph_not_a_table(tmp_path: Path) -> None:
    doc = convert_path(_pdf_with_form(tmp_path / "plot.pdf", graphics=5))
    assert not [b for b in doc.blocks if isinstance(b, Table)]
    figs = [b for b in doc.blocks if isinstance(b, Paragraph) and FIGURE_TEXT_ATTR in b.attrs]
    assert len(figs) == 1
    fig = figs[0]
    assert fig.attrs[FIGURE_TEXT_ATTR] == "7"
    assert spans_text(fig.spans) == "a b c 0.0 0.5 1.0 Training Steps"  # row by row, top to bottom
    box = fig.provenance.bbox
    assert box is not None
    # The form's drawn extent through its matrix (the rectangles and the lettering), inside the BBox it was
    # placed with: x 100..400, PDF y 400..600, so displayed y 192..392.
    assert 100 <= box.x0 < box.x1 <= 400 and 192 <= box.y0 < box.y1 <= 392
    assert box.x1 - box.x0 > 100 and box.y1 - box.y0 > 100
    prose = [spans_text(b.spans) for b in doc.blocks if isinstance(b, Paragraph) and FIGURE_TEXT_ATTR not in b.attrs]
    assert prose == [
        "Figure text stays out of the prose. A second body line follows the first.",
        "Figure 1: Ticks and labels.",
    ]
    assert doc.metadata.extra["pdf_figure_text_blocks"] == 1
    # The lettering sits in reading order between the body text above it and the caption below it.
    kinds = [FIGURE_TEXT_ATTR in b.attrs for b in doc.blocks if isinstance(b, Paragraph)]
    assert kinds == [False, True, False]


def test_a_form_with_little_graphics_keeps_its_text_on_the_page(tmp_path: Path) -> None:
    """A logo or a framed box is not a figure: its text is read like the rest of the page."""
    doc = convert_path(_pdf_with_form(tmp_path / "logo.pdf", graphics=2))
    assert not [b for b in doc.blocks if isinstance(b, Paragraph) and FIGURE_TEXT_ATTR in b.attrs]
    assert "pdf_figure_text_blocks" not in doc.metadata.extra
    tables = [b for b in doc.blocks if isinstance(b, Table)]
    assert len(tables) == 1 and tables[0].n_rows == 2 and tables[0].n_cols == 3  # the two rows of cells, as before


def test_a_ruled_table_placed_as_a_form_is_still_a_table(tmp_path: Path) -> None:
    """Rules are thin paths and do not count as graphics, so a table included as its own PDF keeps its rows."""
    doc = convert_path(_pdf_with_form(tmp_path / "ruled.pdf", graphics=0, rules=5))
    assert not [b for b in doc.blocks if isinstance(b, Paragraph) and FIGURE_TEXT_ATTR in b.attrs]
    tables = [b for b in doc.blocks if isinstance(b, Table)]
    assert len(tables) == 1 and tables[0].n_rows == 2 and tables[0].n_cols == 3


def test_lettering_at_the_foot_of_every_page_is_not_a_running_footer(tmp_path: Path) -> None:
    """The same axis title at the bottom of a figure on several pages stays with its figure."""
    path = _pdf_with_form(tmp_path / "foot.pdf", graphics=4, matrix=(1, 0, 0, 1, 100, 0), pages=3)
    doc = convert_path(path)
    figs = [b for b in doc.blocks if isinstance(b, Paragraph) and FIGURE_TEXT_ATTR in b.attrs]
    assert len(figs) == 3
    assert all(spans_text(b.spans).endswith("Training Steps") for b in figs)


def test_page_text_on_a_lettering_baseline_stays_page_text(tmp_path: Path) -> None:
    """A word of body text right after a figure's edge label on the same baseline is split from it."""
    lettering = [*LETTERING, (288, 20, "1.5", 6, False)]  # ends near the form's right edge, page x about 398
    body = [*BODY, (402, 420, "beside", 6, False)]  # 4 pt further on the same baseline: one line without the split
    doc = convert_path(_pdf_with_form(tmp_path / "edge.pdf", graphics=5, lettering=lettering, body=body))
    figs = [b for b in doc.blocks if isinstance(b, Paragraph) and FIGURE_TEXT_ATTR in b.attrs]
    assert len(figs) == 1 and "beside" not in spans_text(figs[0].spans) and "1.5" in spans_text(figs[0].spans)
    prose = " ".join(spans_text(b.spans) for b in doc.blocks if isinstance(b, Paragraph) and b not in figs)
    assert "beside" in prose and "1.5" not in prose


def test_an_included_page_is_not_a_figure(tmp_path: Path) -> None:
    """A whole page placed as a form (pdfpages) with its rules drawn as paths holds most of the text and covers the
    page: that is a page, and its text is prose."""
    lines: list[TextOp] = [
        (72, 700 - 14 * k, f"Line {k} of an included page with enough words to read as prose.", 10, False)
        for k in range(12)
    ]
    path = _pdf_with_form(
        tmp_path / "included.pdf",
        graphics=4,
        lettering=lines,
        body=[],
        matrix=(1, 0, 0, 1, 0, 0),
        bbox=(0, 0, 612, 792),
    )
    doc = convert_path(path)
    assert not [b for b in doc.blocks if isinstance(b, Paragraph) and FIGURE_TEXT_ATTR in b.attrs]
    assert any("Line 0 of an included page" in spans_text(b.spans) for b in doc.blocks if isinstance(b, Paragraph))


def test_read_page_tags_lines_with_their_figure(tmp_path: Path) -> None:
    pdf = pikepdf.open(_pdf_with_form(tmp_path / "plot.pdf", graphics=3))
    pdf.close()
    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument(str(tmp_path / "plot.pdf"))
    page = read_page(doc, 0, [], CleanStats(), 0)
    doc.close()
    assert len(page.figures) == 1
    x0, y0, x1, y1 = page.figures[0]
    assert 100 <= x0 < x1 <= 400 and 192 <= y0 < y1 <= 392  # inside the placed BBox, displayed coordinates
    tagged = {ln.text: ln.figure for ln in page.lines}
    assert {t for t, f in tagged.items() if f == 0} == {"0.0", "0.5", "1.0", "a", "b", "c", "Training Steps"}
    assert {t for t, f in tagged.items() if f == -1} == {
        "Figure text stays out of the prose.",
        "A second body line follows the first.",
        "Figure 1: Ticks and labels.",
    }
    # Lettering is kept out of table detection by the engine; on its own it still looks like a table.
    inside = [ln for ln in page.lines if ln.figure == 0]
    assert detect_tables(inside)[0]


def _line(x0: float, y: float, text: str, order: int, figure: int = -1) -> Line:
    return Line(1, x0, y, x0 + 5.0 * len(text), y + 6.0, 6.0, False, [(text, None, None)], order, figure=figure)


def test_figure_texts_groups_by_figure_in_row_major_order() -> None:
    lines = [
        _line(72, 100, "Body line", 0),
        _line(160, 300, "0.5", 1, figure=0),
        _line(110, 300, "0.0", 2, figure=0),
        _line(110, 250, "a", 3, figure=0),
        _line(450, 250, "legend", 4, figure=1),
        _line(110, 500, "stray", 5, figure=7),  # no such figure box: stays on the page
    ]
    figures, rest = figure_texts(lines, [(100.0, 240.0, 300.0, 320.0), (440.0, 240.0, 520.0, 260.0)])
    assert [ln.text for ln in rest] == ["Body line", "stray"]
    assert [[ln.text for ln in f.lines] for f in figures] == [["a", "0.0", "0.5"], ["legend"]]
    assert (figures[0].x0, figures[0].y0, figures[0].x1, figures[0].y1) == (100.0, 240.0, 300.0, 320.0)
    assert figures[0].order == 1 and figures[0].page == 1
