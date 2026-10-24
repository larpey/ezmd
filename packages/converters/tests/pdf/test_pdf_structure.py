"""Regressions from the "Attention Is All You Need" conversion: the rotated arXiv margin stamp became the
title, a three-line licence notice in the section-heading size became headings, outline bookmarks without
section numbers missed the numbered headings ("3.1 Encoder" for "Encoder") and matched figure labels
instead, superscripts were split onto their own line or flattened (`10^20` as `1020`), a header cell centred
over a two-line header broke Table 2, and a typeset formula came out as a table."""

from __future__ import annotations

from pathlib import Path

import pikepdf
from conftest import convert_path, new_pdf, save
from pikepdf import Name

from ezmd.ir import Heading, InlineStyle, Paragraph, Table, spans_text
from ezmd_converters.pdf.headings import plan_headings, section_number
from ezmd_converters.pdf.layout import detect_tables
from ezmd_converters.pdf.textlayer import Line, PageText


def _line(
    page: int, x0: float, y: float, text: str, order: int, size: float = 10.0, bold: bool = False, turn: int = 0
) -> Line:
    return Line(page, x0, y, x0 + 5.0 * len(text), y + size, size, bold, [(text, None, None)], order, turn=turn)


def _headings(doc: object) -> list[tuple[int, str]]:
    return [(b.level, spans_text(b.spans)) for b in doc.blocks if isinstance(b, Heading)]  # type: ignore[attr-defined]


def _page(lines: list[Line], number: int = 1) -> PageText:
    return PageText(number, 612, 792, lines, sum(len(ln.text) for ln in lines), 0.0)


def _body(order: int, y: float, page: int = 1) -> Line:
    return _line(page, 72, y, "Body text that sets the most common font size on the page.", order)


# -- heading planning -----------------------------------------------------------


def test_section_number() -> None:
    assert section_number("3.2.1 Scaled Dot-Product Attention") == (3, "Scaled Dot-Product Attention")
    assert section_number("4. Why Self-Attention") == (1, "Why Self-Attention")
    assert section_number("2023 was a good year")[0] is None
    assert section_number("Abstract") == (None, "Abstract")


def test_turned_margin_stamp_is_not_a_heading() -> None:
    stamp = _line(1, 18, 215, "arXiv:1706.03762v7 [cs.CL] 2 Aug 2023", 0, size=20, turn=1)
    title = _line(1, 211, 150, "Attention Is All You Need", 1, size=17.2, bold=True)
    lines = [stamp, title, *(_body(k, 200 + 12 * k) for k in range(2, 12))]
    src = plan_headings([_page(lines)], 10.0, [], set())
    assert src.level(stamp) is None
    assert src.level(title) == 1


def test_heading_sized_paragraph_is_prose() -> None:
    notice = [
        _line(1, 124, 74 + 14 * k, "Provided proper attribution is provided, permission", k, size=12) for k in range(3)
    ]
    head = _line(1, 108, 300, "Introduction", 3, size=12, bold=True)
    lines = [*notice, head, *(_body(k, 320 + 12 * k) for k in range(4, 14))]
    src = plan_headings([_page(lines)], 10.0, [], set())
    assert [src.level(ln) for ln in notice] == [None, None, None]
    assert src.level(head) == 1


def test_numbered_bold_body_lines_without_outline() -> None:
    top = _line(1, 108, 70, "3 Model Architecture", 0, size=12, bold=True)
    sub = _line(1, 108, 120, "3.1 Encoder and Decoder Stacks", 1, bold=True)
    subsub = _line(1, 108, 170, "3.2.1 Scaled Dot-Product Attention", 2, bold=True)
    plain = _line(1, 108, 220, "3.3 is the value we used throughout", 3)
    lines = [top, sub, subsub, plain, *(_body(k, 260 + 12 * k) for k in range(4, 14))]
    src = plan_headings([_page(lines)], 10.0, [], set())
    assert [src.level(ln) for ln in (top, sub, subsub, plain)] == [1, 2, 3, None]


def test_outline_mode_matches_numbered_headings_once_and_skips_figure_labels() -> None:
    title = _line(1, 200, 150, "Attention Is All You Need", 0, size=17, bold=True)
    page1 = [title, *(_body(k, 200 + 12 * k) for k in range(1, 8))]
    label = _line(2, 150, 72, "Scaled Dot-Product Attention", 100)  # a figure label, body size, not bold
    page2 = [
        label,
        _line(2, 108, 120, "3 Model Architecture", 101, size=12, bold=True),
        _line(2, 108, 160, "3.1 Scaled Dot-Product Attention", 102, bold=True),
        _line(2, 108, 200, "Abstract", 103, size=12, bold=True),
        _line(2, 108, 230, "4 Training", 104, size=12, bold=True),
        *(_body(k, 260 + 12 * (k - 105), page=2) for k in range(105, 113)),
    ]
    outline = [
        (1, "Model Architecture", 1),
        (2, "Scaled Dot-Product Attention", 1),
        (1, "Training", 1),
        (1, "Unused", 1),
    ]
    src = plan_headings([_page(page1), _page(page2, 2)], 10.0, outline, set())
    assert src.outline_mode and src.offset == 1
    levels = [src.level(ln) for ln in page2[:5]]
    assert src.level(title) == 1
    assert levels == [None, 2, 3, 2, 2]  # label skipped; "Abstract" takes the level of its size


# -- tables ------------------------------------------------------------------------


def test_header_cell_centred_over_two_header_lines_joins_the_header() -> None:
    def cell(x: float, y: float, text: str, order: int) -> Line:
        return Line(1, x, y, x + 30, y + 7, 10, False, [(text, None, None)], order)

    lines = [
        cell(311, 99, "BLEU", 0),
        cell(390, 99, "Cost", 1),
        cell(137, 107, "Model", 2),
        cell(289, 115, "EN-DE", 3),
        cell(331, 115, "EN-FR", 4),
        cell(388, 115, "EN-DE", 5),
        cell(440, 115, "EN-FR", 6),
    ]
    for r, vals in enumerate([("ByteNet", "23.75", "39.9", "1.0", "2.0"), ("MoE", "26.03", "40.56", "2.0", "1.2")]):
        lines += [
            cell(x, 126 + 11 * r, v, 10 + 5 * r + k)
            for k, (x, v) in enumerate(zip((137, 292, 334, 384, 436), vals, strict=True))
        ]
    tables, rest = detect_tables(lines)
    assert rest == [] and len(tables) == 1
    rows = tables[0].rows
    assert rows[0] == ["Model", "BLEU", "", "Cost", ""]
    assert rows[1] == ["", "EN-DE", "EN-FR", "EN-DE", "EN-FR"]
    assert rows[2] == ["ByteNet", "23.75", "39.9", "1.0", "2.0"]


def test_two_sparse_rows_are_a_formula_not_a_table() -> None:
    lines = [
        _line(1, 160, 300, "Attention(Q, K, V ) = softmax(", 0),
        _line(1, 330, 300, ")V", 1),
        _line(1, 480, 300, "(1)", 2),
        _line(1, 300, 312, "dk", 3),
    ]
    tables, rest = detect_tables(lines)
    assert tables == [] and len(rest) == 4


# -- end to end: superscripts ------------------------------------------------------


def _pdf_with(tmp_path: Path, runs: list[tuple[float, float, float, str]]) -> Path:
    """Each run is its own text object at (x, y) with size, like a TeX formula with a raised exponent."""
    pdf = new_pdf([[]])
    ops: list[tuple[list[object], str]] = []
    for x, y, size, text in runs:
        ops += [
            ([], "BT"),
            ([Name("/F1"), 1], "Tf"),
            ([size, 0, 0, size, x, y], "Tm"),
            ([pikepdf.String(text)], "Tj"),
            ([], "ET"),
        ]
    pdf.pages[0].obj.Contents = pdf.make_indirect(pikepdf.Stream(pdf, pikepdf.unparse_content_stream(ops)))
    return save(pdf, tmp_path / "scripts.pdf")


def test_raised_exponent_in_its_own_text_object_stays_on_the_line(tmp_path: Path) -> None:
    path = _pdf_with(
        tmp_path,
        [
            (72, 700, 10, "Training cost was 2.3 x 10"),
            (196.5, 703.6, 7, "19"),
            (205, 700, 10, " FLOPs for the base model."),
        ],
    )
    doc = convert_path(path)
    para = next(b for b in doc.blocks if isinstance(b, Paragraph))
    sup = [s.text for s in para.spans if InlineStyle.SUPERSCRIPT in s.styles]
    assert sup == ["19"]
    assert spans_text(para.spans).replace(" ", "").startswith("Trainingcostwas2.3x1019FLOPs")
    assert not [b for b in doc.blocks if isinstance(b, Table)]


# -- review follow-ups ---------------------------------------------------------------


def test_page_typeset_sideways_keeps_its_headings() -> None:
    """Every line turned (a landscape page without /Rotate): turned lines are the content, not a stamp."""
    head = _line(1, 72, 60, "Quarterly Throughput", 0, size=16, bold=True, turn=1)
    lines = [head, *(_line(1, 72, 90 + 12 * k, "Body text set sideways on the page.", k, turn=1) for k in range(1, 10))]
    src = plan_headings([_page(lines)], 10.0, [], set())
    assert src.level(head) == 1


def test_partial_outline_keeps_unbookmarked_headings() -> None:
    names = ["Scope", "Method", "Findings"]
    heads = [_line(1, 72, 60 + 80 * k, name, k, size=14, bold=True) for k, name in enumerate(names)]
    extra = _line(1, 72, 300, "Limitations", 3, size=14)  # same size, not bold, no bookmark
    lines = [*heads, extra, *(_body(k, 340 + 12 * k) for k in range(4, 14))]
    src = plan_headings([_page(lines)], 10.0, [(1, n, 0) for n in names], set())
    assert src.outline_mode
    assert [src.level(ln) for ln in [*heads, extra]] == [1, 1, 1, 1]


def test_numbered_lead_in_sentence_is_not_a_heading() -> None:
    lead = _line(1, 108, 120, "2.5 million units shipped in the third quarter.", 0, bold=True)
    lower = _line(1, 108, 140, "3.1 percent of returns", 1, bold=True)
    lines = [lead, lower, *(_body(k, 160 + 12 * k) for k in range(2, 12))]
    src = plan_headings([_page(lines)], 10.0, [], set())
    assert [src.level(lead), src.level(lower)] == [None, None]


def test_two_row_table_with_numbers_is_kept() -> None:
    lines = [
        _line(1, 72, 100, "Item", 0),
        _line(1, 200, 100, "Qty", 1),
        _line(1, 300, 100, "Price", 2),
        _line(1, 400, 100, "Note", 3),
        _line(1, 72, 114, "Bolts", 4),
        _line(1, 200, 114, "12", 5),
        _line(1, 300, 114, "0.40", 6),
    ]
    tables, _rest = detect_tables(lines)
    assert len(tables) == 1 and tables[0].rows[1][:3] == ["Bolts", "12", "0.40"]


def test_small_unit_on_the_same_baseline_keeps_the_break(tmp_path: Path) -> None:
    """A small "kg" set on the cell's baseline is not a script: the line break between objects stands."""
    path = _pdf_with(tmp_path, [(72, 700, 10, "12.5"), (91, 700, 7, "kg"), (300, 700, 10, "Steel plate")])
    doc = convert_path(path)
    styled = [s for b in doc.blocks for s in getattr(b, "spans", []) if s.styles]
    assert styled == []
