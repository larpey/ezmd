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

from ezmd.ir import Heading, InlineStyle, Paragraph, Table, WarningKind, spans_text
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


# -- harder papers: Mamba, KAN, LLaMA -----------------------------------------------


def test_math_italic_folds_to_plain_letters_and_other_styles_stay() -> None:
    """Italic is how every TeX variable is set (no meaning); bold, double-struck and script carry meaning."""
    from ezmd_converters.pdf.textlayer import _fold

    italic = [_fold(c) for c in ("𝑥", "𝐷", "𝜆", "ℎ")]
    assert italic == ["x", "D", "λ", "h"]
    kept = ("𝐃", "𝔼", "𝒜", "∆")  # bold D, double-struck E, script A, increment
    assert [_fold(c) for c in kept] == list(kept)
    assert _fold("ﬁ") == "fi"


def test_acl_bold_section_headings_just_above_body_size() -> None:
    """ACL papers set 12 pt bold section headings over an 11 pt body: under 1.15x, still headings; a non-bold
    line at that size (an affiliation) is not."""
    title = _line(1, 117, 75, "LLaMA: Open and Efficient Foundation Language Models", 0, size=14.35, bold=True)
    authors = _line(1, 130, 116, "Hugo Touvron, Thibaut Lavril, Gautier Izacard", 1, size=11.96, bold=True)
    venue = _line(1, 277, 182, "Meta AI", 2, size=11.96)
    abstract = _line(1, 157, 215, "Abstract", 3, size=11.96, bold=True)
    intro = _line(1, 71, 391, "1 Introduction", 4, size=11.96, bold=True)
    sub = _line(1, 71, 450, "2.1 Pre-training Data", 5, size=10.91, bold=True)
    body = [_line(1, 71, 480 + 12 * k, "Body text " * 6, k, size=10.91) for k in range(6, 30)]
    src = plan_headings([_page([title, authors, venue, abstract, intro, sub, *body])], 10.91, [], set())
    levels = [src.level(ln) for ln in (title, authors, venue, abstract, intro, sub)]
    assert levels == [1, None, None, 2, 2, 3]


def test_lone_math_symbol_in_a_figure_is_not_a_heading() -> None:
    sym = _line(1, 300, 200, "∆", 0, size=16)
    letter = _line(1, 330, 200, "A", 1, size=16)
    head = _line(1, 72, 100, "State Space Models", 2, size=16, bold=True)
    lines = [head, sym, letter, *(_body(k, 240 + 12 * k) for k in range(3, 13))]
    src = plan_headings([_page(lines)], 10.0, [], set())
    assert [src.level(head), src.level(sym), src.level(letter)] == [1, None, None]


def test_appendix_numbered_headings_match_their_bookmarks() -> None:
    """Mamba's appendix: "B Related Work", "B.1 S4 Variants..." for bookmarks without the letters, while a
    title that starts with "A" ("A Simplified SSM Architecture") still matches whole."""
    heads = [
        _line(1, 72, 60, "1 Introduction", 0, size=12, bold=True),
        _line(1, 72, 120, "A Simplified SSM Architecture", 1, bold=True),
        _line(1, 72, 180, "B Related Work", 2, size=12, bold=True),
        _line(1, 72, 240, "B.1 S4 Variants and Derivatives", 3, bold=True),
    ]
    lines = [*heads, *(_body(k, 300 + 12 * k) for k in range(4, 14))]
    outline = [
        (1, "Introduction", 0),
        (2, "A Simplified SSM Architecture", 0),
        (1, "Related Work", 0),
        (2, "S4 Variants and Derivatives", 0),
    ]
    src = plan_headings([_page(lines)], 10.0, outline, set())
    assert [src.level(ln) for ln in heads] == [1, 2, 1, 2]


# -- bug hunt over 100+ CC BY arXiv papers ---------------------------------------------


def test_junk_metadata_titles_are_rejected() -> None:
    from ezmd_converters.pdf.pdfinfo import plausible_title

    assert plausible_title("") is None  # Word stored a lone private-use glyph
    assert plausible_title("Microsoft Word - draft3.docx") is None
    assert plausible_title("main.tex") is None
    assert plausible_title("untitled") is None
    assert plausible_title("Mamba: Linear-Time Sequence Modeling") == "Mamba: Linear-Time Sequence Modeling"


def test_page_title_prefers_first_page_largest_text_over_first_heading() -> None:
    from ezmd_converters.pdf.headings import page_title

    lines = [
        _line(1, 100, 80, "Straintronics using the monolayer-Xene platform", 0, size=17, bold=True),
        _line(1, 100, 102, "a comparative study", 1, size=17, bold=True),
        _line(1, 100, 140, "Ada Lovelace, Charles Babbage", 2, size=11),
        *(_body(k, 180 + 12 * k) for k in range(3, 13)),
    ]
    assert (
        page_title([_page(lines)], 10.0, set()) == "Straintronics using the monolayer-Xene platform a comparative study"
    )


def test_page_title_takes_a_centred_capitals_title_at_body_size() -> None:
    from ezmd_converters.pdf.headings import page_title

    title = Line(1, 184, 120, 428, 131, 10.9, False, [("COMPACT T(1) THEOREM À LA STEIN", None, None)], 0)
    lines = [title, *(_line(1, 72, 180 + 12 * k, "Body text " * 7, k, size=10.9) for k in range(1, 12))]
    assert page_title([_page(lines)], 10.9, set()) == "COMPACT T(1) THEOREM À LA STEIN"


def test_free_standing_accents_compose_with_their_letters(tmp_path: Path) -> None:
    """TeX's \'A draws "´" as its own glyph over "A", after the rest of the word."""
    path = _pdf_with(tmp_path, [(72, 700, 10, "ARPAD wrote"), (74.5, 702.0, 10, "\xb4")])
    lines = _page_lines_of(path)
    assert lines[0].text == "ÁRPAD wrote"


def _page_lines_of(path: Path) -> list[Line]:
    import pypdfium2 as pdfium

    from ezmd.core.textclean import CleanStats
    from ezmd_converters.pdf.textlayer import read_page

    doc = pdfium.PdfDocument(str(path))
    try:
        return read_page(doc, 0, [], CleanStats(), 0).lines
    finally:
        doc.close()


def test_ieee_and_revtex_headings_match_bookmarks() -> None:
    heads = [
        _line(1, 72, 60, "I. INTRODUCTION", 0, size=8),  # small capitals, smaller than the body
        _line(1, 72, 120, "A. Proposed Courses", 1),  # IEEE letter subsection, body size
        _line(1, 72, 180, "MODEL", 2, size=8),  # REVTeX: numeral drawn apart
    ]
    lines = [*heads, *(_body(k, 220 + 12 * k) for k in range(3, 13))]
    outline = [(1, "Introduction", 0), (2, "Proposed Courses", 0), (1, "Model", 0)]
    src = plan_headings([_page(lines)], 10.0, outline, set())
    assert [src.level(ln) for ln in heads] == [1, 2, 1]


def test_contents_list_without_page_numbers_does_not_take_bookmarks() -> None:
    names = ["1. Introduction", "2. Methods", "2.1. Data", "2.2. Model", "3. Results", "4. Discussion"]
    listing = [_line(1, 83, 300 + 12 * k, n, k) for k, n in enumerate(names)]
    real = [_line(2, 72, 60 + 100 * k, n, 100 + k, size=12, bold=True) for k, n in enumerate(names)]
    body = [_body(200 + k, 700 + k, page=2) for k in range(10)]
    outline = [(1 if "." not in n[2:] else 2, n, None) for n in names]
    src = plan_headings([_page(listing), _page([*real, *body], 2)], 10.0, outline, set())
    assert [src.level(ln) for ln in listing] == [None] * 6
    assert all(src.level(ln) is not None for ln in real)


def test_run_in_heading_is_split_from_its_paragraph() -> None:
    from ezmd_converters.pdf.assemble import Assembler
    from ezmd_converters.pdf.layout import Item

    run_in = _line(1, 83, 370, "2.1. Metric graph theory. For a graph G, a walk of length k is", 1)
    heads = [_line(1, 83, 300, "2. Recollections", 0, size=12, bold=True), run_in]
    tail = _line(1, 83, 600, "3. Results", 12, size=12, bold=True)
    lines = [*heads, *(_body(k, 400 + 12 * k) for k in range(2, 12)), tail]
    outline = [(1, "2. Recollections", 0), (2, "2.1. Metric graph theory", 0), (1, "3. Results", 0)]
    src = plan_headings([_page(lines)], 10.0, outline, set())
    assert src.outline_mode
    asm = Assembler("t.pdf", "pdfium", src, set(), True)
    from ezmd_converters.pdf.assemble import PageGeom

    asm.page(PageGeom(1, 612, 792), [Item(ln.x0, ln.y0, ln.x1, ln.y1, ln.order, line=ln) for ln in lines], False)
    kinds = [(type(b).__name__, spans_text(b.spans)[:30]) for b in asm.blocks[:3]]
    assert kinds == [
        ("Heading", "2. Recollections"),
        ("Heading", "2.1. Metric graph theory"),
        ("Paragraph", "For a graph G, a walk of lengt"),
    ]


# -- second hunt pass: glyph mapping, equation grids, title zone -----------------------


def _pdf_with_cmap(tmp_path: Path, text: str, bfchars: str) -> Path:
    """One line of `text` in Helvetica whose ToUnicode CMap carries `bfchars` ("<41> <00410041>")."""
    pdf = new_pdf([[]])
    cmap = (
        "/CIDInit /ProcSet findresource begin 12 dict begin begincmap /CMapName /Custom def\n"
        "1 begincodespacerange <00> <FF> endcodespacerange\n"
        f"{bfchars.count('<') // 2} beginbfchar {bfchars} endbfchar\n"
        "endcmap CMapName currentdict /CMap defineresource pop end end"
    )
    font = pdf.pages[0].obj.Resources.Font.F1
    font.ToUnicode = pdf.make_indirect(pikepdf.Stream(pdf, cmap.encode("ascii")))
    ops: list[tuple[list[object], str]] = [
        ([], "BT"),
        ([Name("/F1"), 10], "Tf"),
        ([72, 700], "Td"),
        ([pikepdf.String(text)], "Tj"),
        ([], "ET"),
    ]
    pdf.pages[0].obj.Contents = pdf.make_indirect(pikepdf.Stream(pdf, pikepdf.unparse_content_stream(ops)))
    return save(pdf, tmp_path / "cmap.pdf")


def test_glyph_mapped_to_its_text_twice_is_one_character(tmp_path: Path) -> None:
    """Some fonts' ToUnicode gives a glyph its text twice (ψψ for one ψ); the repeat shares the glyph's box."""
    path = _pdf_with_cmap(tmp_path, "A plan", "<41> <00410041>")
    assert [ln.text for ln in _page_lines_of(path)] == ["A plan"]


def test_ligature_spelled_by_tounicode_keeps_both_letters(tmp_path: Path) -> None:
    """TeX fonts map the ff glyph to "ff" (two characters, one box): a ligature, not a doubling font."""
    path = _pdf_with_cmap(tmp_path, "coeAicients", "<41> <00660066>")
    assert [ln.text for ln in _page_lines_of(path)] == ["coefficients"]


def test_unmapped_glyphs_are_kept_and_warned(tmp_path: Path) -> None:
    path = _pdf_with_cmap(tmp_path, "see A here", "<41> <FFFD>")
    doc = convert_path(path)
    assert "�" in doc.plain_text()
    warn = next(w for w in doc.warnings if w.kind == WarningKind.UNMAPPED_GLYPHS)
    assert warn.count == 1 and warn.page == 1 and warn.detail["pages"] == "1"


def test_display_equation_with_fraction_is_not_a_table() -> None:
    lines = [
        _line(1, 200, 100, "8πG", 0),
        _line(1, 300, 100, "1", 1),
        _line(1, 72, 112, "H² =", 2),
        _line(1, 200, 112, "ϕ′² + a²V", 3),
        _line(1, 330, 112, ",", 4),
        _line(1, 480, 112, "(4)", 5),
        _line(1, 200, 124, "3", 6),
        _line(1, 300, 124, "2", 7),
    ]
    tables, rest = detect_tables(lines)
    assert tables == [] and len(rest) == 8


def test_numeric_table_without_equals_is_still_a_table() -> None:
    rows = [("Layer", "Params", "FLOPs"), ("Small", "12M", "1.1"), ("Base", "110M", "4.2"), ("Large", "340M", "13.5")]
    lines = [
        _line(1, x, 100 + 14 * r, text, r * 3 + c)
        for r, row in enumerate(rows)
        for c, (x, text) in enumerate(zip((72, 200, 300), row, strict=True))
    ]
    tables, _rest = detect_tables(lines)
    assert len(tables) == 1 and tables[0].rows[0] == ["Layer", "Params", "FLOPs"]


def test_page_title_in_the_top_zone_under_draft_notes() -> None:
    """AASTeX: "Draft version" notes top left in small type, then the title at body size, centred."""
    from ezmd_converters.pdf.headings import page_title

    title = "Hyperfine Structure Investigation of Singly Ionized Thulium in FT Spectra"
    lines = [
        _line(1, 60, 53, "Draft version May 10, 2024", 0, size=8),
        _line(1, 60, 63, "Typeset using LaTeX twocolumn style in AASTeX631", 1, size=8),
        _line(1, 131, 109, title, 2, size=9.96),
        _line(1, 72, 130, "Taha Yusuf Kebapci, Seyma Parlatan", 3, size=9),
        *(_line(1, 60, 180 + 12 * k, "Body text " * 8, k, size=9.96) for k in range(4, 20)),
    ]
    assert page_title([_page(lines)], 10.0, set()) == title


def test_page_title_joins_a_colon_set_as_a_separate_object() -> None:
    from ezmd_converters.pdf.headings import page_title

    a = Line(1, 129, 84, 163, 97, 14.35, True, [("Eagle", None, None)], 0)
    b = Line(1, 182, 84, 466, 95, 14.35, True, [(": Ethical Dataset Given from Real Interactions", None, None)], 1)
    lines = [a, b, *(_body(k, 140 + 12 * k) for k in range(2, 12))]
    assert page_title([_page(lines)], 10.0, set()) == "Eagle: Ethical Dataset Given from Real Interactions"


def test_contents_entries_and_overlong_lines_are_not_headings() -> None:
    entry = _line(1, 72, 100, "4.1 Motivation . . . . . . . . . . . . . . . . . . . . 12", 0, size=14)
    long = _line(1, 72, 130, "4 School of Fundamental Physics and Mathematical Sciences, " * 3, 1, size=14)
    head = _line(1, 72, 160, "Results", 2, size=14, bold=True)
    lines = [entry, long, head, *(_body(k, 200 + 12 * k) for k in range(3, 13))]
    src = plan_headings([_page(lines)], 10.0, [], set())
    assert [src.level(entry), src.level(long), src.level(head)] == [None, None, 1]
