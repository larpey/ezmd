from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pikepdf
import pytest
from conftest import FIXTURES, convert_path, new_pdf, save
from pikepdf import Array, Dictionary, Name

import intomd_converters.pdf as pdf_family
from intomd.detect import detect
from intomd.inputs import InputRef
from intomd.ir import Heading, ListBlock, PageBreak, Paragraph, Table, WarningKind, spans_text
from intomd.registry import ConverterRegistry, ConvertOptions, Unavailable
from intomd_converters.pdf import converter as converter_mod
from intomd_converters.pdf.layout import Item, detect_tables, order_items, running_lines, size_levels
from intomd_converters.pdf.textlayer import Line, PageText


def _headings(doc: object) -> list[tuple[int, str]]:
    return [(b.level, spans_text(b.spans)) for b in doc.blocks if isinstance(b, Heading)]  # type: ignore[attr-defined]


def _line(page: int, x0: float, y: float, text: str, order: int, size: float = 10.0, bold: bool = False) -> Line:
    return Line(page, x0, y, x0 + 5.0 * len(text), y + size, size, bold, [(text, None)], order)


# -- geometry heuristics -------------------------------------------------------


def test_running_lines_need_repeats_in_margins() -> None:
    pages = [
        PageText(
            n,
            612,
            792,
            [
                _line(n, 72, 20, "Annual report", n * 10),
                _line(n, 72, 400, f"Body {n}", n * 10 + 1),
                _line(n, 280, 770, f"Page {n}", n * 10 + 2),
            ],
            300,
            0.0,
        )
        for n in (1, 2, 3)
    ]
    assert running_lines(pages) == {10, 12, 20, 22, 30, 32}
    assert running_lines(pages[:1]) == set()


def test_detect_tables_and_prose_rows() -> None:
    rows = [("Name", "Qty"), ("Bolts", "12"), ("Nuts", "40")]
    lines = [
        _line(1, x, 100 + 14 * r, text, r * 2 + c)
        for r, row in enumerate(rows)
        for c, (x, text) in enumerate(zip((72, 300), row, strict=True))
    ]
    lines.append(_line(1, 72, 200, "A closing paragraph that is long enough to be prose.", 99))
    tables, rest = detect_tables(lines)
    assert len(tables) == 1 and tables[0].rows == [["Name", "Qty"], ["Bolts", "12"], ["Nuts", "40"]]
    assert [ln.order for ln in rest] == [99]
    prose = [_line(1, 72, 100 + 14 * r, "a long line of left column prose text here", r * 2) for r in range(4)]
    prose += [_line(1, 330, 100 + 14 * r, "a long line of right column prose text here", r * 2 + 1) for r in range(4)]
    assert detect_tables(prose)[0] == []


def test_order_items_columns() -> None:
    lines = [_line(1, 72, 50, "Title spanning both columns of the page here ok", 0)]
    lines += [_line(1, 72, 100 + 14 * r, f"left {r} words words", 1 + 2 * r) for r in range(4)]
    lines += [_line(1, 330, 100 + 14 * r, f"right {r} words words", 2 + 2 * r) for r in range(4)]
    items = [Item(ln.x0, ln.y0, ln.x1, ln.y1, ln.order, line=ln) for ln in lines]
    ordered, columns = order_items(items, 0, 612)
    assert columns
    assert [it.line.text.split()[0] for it in ordered if it.line] == ["Title"] + ["left"] * 4 + ["right"] * 4


def test_size_levels() -> None:
    page = PageText(
        1,
        612,
        792,
        [
            _line(1, 72, y, t, i, size=s)
            for i, (y, t, s) in enumerate(
                [
                    (50, "Big", 24),
                    (90, "Mid", 16),
                    (120, "body text " * 5, 10),
                    (140, "Small head", 13),
                    (160, "x" * 300, 18),
                ]
            )
        ],
        400,
        0.0,
    )
    assert size_levels([page], 10.0, set()) == {24.0: 1, 16.0: 2, 13.0: 3}


# -- end-to-end on fixtures ------------------------------------------------------


def test_born_digital_headings_lists_links_hyphenation() -> None:
    doc = convert_path(FIXTURES / "born-digital-report" / "input.pdf")
    assert _headings(doc) == [
        (1, "Harbor Lane Annual Report"),
        (2, "1. Overview"),
        (3, "1.1 Scope"),
        (2, "2. Berth condition"),
        (3, "2.1 Repairs scheduled"),
        (2, "3. Cargo volumes"),
        (3, "3.1 Staffing"),
        (2, "4. Capital plan"),
    ]
    text = doc.plain_text()
    assert "recorded information about" in text
    assert "Confidential" not in text and "Page 1 of 4" not in text
    removed = next(w for w in doc.warnings if w.kind == WarningKind.REMOVED_RUNNING_HEADER_FOOTER)
    assert removed.count == 12
    lists = [b for b in doc.blocks if isinstance(b, ListBlock)]
    assert [(lb.ordered, len(lb.items)) for lb in lists] == [(False, 3), (True, 3)]
    assert spans_text(lists[1].items[1].spans) == "Re-anchor bollard 14"
    link = next(s for b in doc.blocks if isinstance(b, Paragraph) for s in b.spans if s.href)
    assert link.href == "https://example.org/harbor-lane/volumes" and link.text.startswith("Further detail")
    assert [b.page_number for b in doc.blocks if isinstance(b, PageBreak)] == [1, 2, 3, 4]
    for b in doc.blocks:
        assert b.provenance.source_page is not None
        if not isinstance(b, PageBreak):
            assert b.provenance.bbox is not None
    assert doc.metadata.title == "Harbor Lane Annual Report" and doc.metadata.author == "intomd fixtures"


def test_keep_running_headers_option() -> None:
    doc = convert_path(FIXTURES / "born-digital-report" / "input.pdf", {"pdf.keep_running_headers": True})
    assert "Confidential" in doc.plain_text()


def test_dehyphenate_off_keeps_hyphen() -> None:
    doc = convert_path(FIXTURES / "born-digital-report" / "input.pdf", {"pdf.dehyphenate": False})
    assert "infor-mation" in doc.plain_text()


def test_two_column_order_and_warning() -> None:
    doc = convert_path(FIXTURES / "two-column-page" / "input.pdf")
    paras = [spans_text(b.spans) for b in doc.blocks if isinstance(b, Paragraph)]
    assert paras[0].startswith("Tides in the inner harbor") and paras[0].endswith("for a full year.")
    assert paras[1].startswith("Wind set-up") and paras[1].endswith("deep-draft arrivals.")
    assert paras[2] == "Both columns together describe one year of observations."
    assert "reading_order_uncertain" in [str(w.kind) for w in doc.warnings]


def test_simple_table() -> None:
    doc = convert_path(FIXTURES / "simple-table" / "input.pdf")
    table = next(b for b in doc.blocks if isinstance(b, Table))
    assert (table.n_rows, table.n_cols, table.header_rows) == (5, 4, 1)
    grid = [[spans_text(c.spans) for c in table.cells if c.row == r] for r in range(5)]
    assert grid[0] == ["Terminal", "Q1", "Q2", "Q3"] and grid[3] == ["Container yard", "301", "322", "290"]


def test_image_only_page_warnings_and_stub() -> None:
    doc = convert_path(FIXTURES / "image-only-page" / "input.pdf")
    w = {str(x.kind): x for x in doc.warnings}
    assert w["pages_without_text"].detail == {"pages": "2"}
    assert "ocr_unavailable" in w
    stub = [b for b in doc.blocks if isinstance(b, Paragraph) and b.attrs.get("pdf_stub")]
    assert len(stub) == 1 and stub[0].provenance.source_page == 2
    assert doc.metadata.extra["pdf_page_modes"] == "hybrid=1,scanned=1"


def test_image_only_page_with_ocr_off() -> None:
    doc = convert_path(FIXTURES / "image-only-page" / "input.pdf", {"pdf.ocr": "off"})
    kinds = [str(x.kind) for x in doc.warnings]
    assert "pages_without_text" in kinds and "ocr_unavailable" not in kinds
    assert not any(isinstance(b, Paragraph) and b.attrs.get("pdf_stub") for b in doc.blocks)


def test_structure_tree_precedence_and_ignore() -> None:
    path = FIXTURES / "tagged-structure-tree" / "input.pdf"
    doc = convert_path(path)
    assert _headings(doc) == [(1, "Port safety handbook"), (2, "Personal protective equipment"), (2, "Night work")]
    assert "heading_source_structure_tree" in [str(w.kind) for w in doc.warnings]
    assert doc.metadata.language == "en-US"
    ignored = convert_path(path, {"pdf.structure_tree": "ignore"})
    assert _headings(ignored) == [(2, "Port safety handbook"), (1, "Personal protective equipment"), (1, "Night work")]


def test_unusable_structure_tree(tmp_path: Path) -> None:
    pdf = new_pdf([[(72, 700, "Heading drawn large", 18, True), (72, 670, "Body text below the heading.", 10, False)]])
    pdf.Root.MarkInfo = Dictionary(Marked=True)
    pdf.Root.StructTreeRoot = pdf.make_indirect(Dictionary(Type=Name.StructTreeRoot, K=Array()))
    doc = convert_path(save(pdf, tmp_path / "t.pdf"))
    assert "structure_tree_unusable" in [str(w.kind) for w in doc.warnings]
    assert _headings(doc) == [(1, "Heading drawn large")]


def test_outline_levels(tmp_path: Path) -> None:
    pdf = new_pdf(
        [
            [
                (72, 700, "Introduction", 10, True),
                (72, 680, "Opening text of the report body.", 10, False),
                (72, 650, "Background", 10, True),
                (72, 630, "More body text in the second part.", 10, False),
            ]
        ]
    )
    with pdf.open_outline() as ol:
        intro = pikepdf.OutlineItem("Introduction", 0)
        intro.children.append(pikepdf.OutlineItem("Background", 0))
        ol.root.append(intro)
    doc = convert_path(save(pdf, tmp_path / "o.pdf"))
    assert _headings(doc) == [(1, "Introduction"), (2, "Background")]
    assert doc.metadata.extra["pdf_heading_source"] == "outline"


def test_rotated_page(tmp_path: Path) -> None:
    """A landscape page stored portrait: text runs up the user space and /Rotate 90 displays it upright."""
    pdf = new_pdf([[]], rotate=90)
    ops: list[tuple[list[object], str]] = []
    for x, text in ((100, "First line on a rotated page."), (114, "Second line follows.")):
        ops += [
            ([], "BT"),
            ([Name("/F1"), 10], "Tf"),
            ([0, 1, -1, 0, x, 72], "Tm"),
            ([pikepdf.String(text)], "Tj"),
            ([], "ET"),
        ]
    pdf.pages[0].obj.Contents = pdf.make_indirect(pikepdf.Stream(pdf, pikepdf.unparse_content_stream(ops)))
    doc = convert_path(save(pdf, tmp_path / "r.pdf"))
    assert doc.plain_text() == "First line on a rotated page. Second line follows."
    para = next(b for b in doc.blocks if isinstance(b, Paragraph))
    assert para.provenance.bbox is not None and para.provenance.bbox.page_width == 792


def test_empty_page_document_is_not_silent(make_pdf: Callable[..., Path]) -> None:
    doc = convert_path(make_pdf([[]]))
    kinds = [str(w.kind) for w in doc.warnings]
    assert "pages_without_text" in kinds


# -- registration and fallback -------------------------------------------------


def test_engine_fallback_warning_when_docling_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(converter_mod, "docling_installed", lambda: False)
    doc = convert_path(FIXTURES / "simple-table" / "input.pdf")
    fb = next(w for w in doc.warnings if w.kind == WarningKind.ENGINE_FALLBACK)
    assert "tables are best-effort" in fb.message and fb.severity == "warning"
    doc2 = convert_path(FIXTURES / "simple-table" / "input.pdf", {"pdf.engine": "pypdf"})
    assert WarningKind.ENGINE_FALLBACK not in [w.kind for w in doc2.warnings]


def test_family_registers_unavailable_docling(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(converter_mod, "docling_installed", lambda: False)
    convs = pdf_family.converters()
    ids = {c.id: c for c in convs}
    assert isinstance(ids["documents.docling_pdf"], Unavailable)
    assert ids["documents.docling_pdf"].requires_extras == ("docs",)
    assert pdf_family.CHAINS["application/pdf"] == ["documents.docling_pdf", "documents.pdfium_text"]
    reg = ConverterRegistry()
    for c in convs:
        reg.register(c)
    for mime, chain in pdf_family.CHAINS.items():
        reg.set_chain(mime, chain)
    ref = InputRef.from_path(FIXTURES / "simple-table" / "input.pdf")
    detect(ref)
    assert ref.detected is not None and ref.detected.mime == "application/pdf"
    result = reg.convert(ref, ConvertOptions())
    assert result.converter_id == "documents.pdfium_text"
    assert WarningKind.ENGINE_FALLBACK in [w.kind for w in result.all_warnings]
