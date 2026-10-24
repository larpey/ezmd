"""ezmd_converters.pdf.repair: locating what a qpdf repair left behind."""

from __future__ import annotations

from pathlib import Path

import pikepdf

from ezmd_converters.pdf.repair import RepairAssessment, assess, warned_objects

# A hand-written PDF with no cross-reference table (qpdf reconstructs one) in which objects 95 to 99 do not exist:
# page 2's content stream, page 3's image and the ToUnicode map, font program and whole font of three fonts are
# references to nothing, which qpdf resolves as null. Page 4 has no /Contents at all, a legitimate blank page.
_DAMAGED = b"""%PDF-1.4
1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj
2 0 obj << /Type /Pages /Kids [3 0 R 4 0 R 5 0 R 11 0 R] /Count 4 >> endobj
3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] /Contents 6 0 R
  /Resources << /Font << /F1 7 0 R >> >> >> endobj
4 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] /Contents 99 0 R >> endobj
5 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] /Contents [6 0 R]
  /Resources << /XObject << /Im1 98 0 R >> /Font << /F1 7 0 R /F2 8 0 R /F3 9 0 R /F4 97 0 R >> >> >> endobj
6 0 obj << /Length 44 >>
stream
BT /F1 12 Tf 20 100 Td (Hello) Tj ET
endstream
endobj
7 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj
8 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Foo /ToUnicode 96 0 R >> endobj
9 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Bar /FontDescriptor 10 0 R >> endobj
10 0 obj << /Type /FontDescriptor /FontName /Bar /Flags 4 /FontFile 95 0 R >> endobj
11 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] >> endobj
trailer << /Root 1 0 R >>
"""


# Two pages share one indirect resource dictionary whose only font is gone, and page 1 also uses a Type0 font whose
# /DescendantFonts array points back at the font itself (a cycle qpdf preserves).
_SHARED = b"""%PDF-1.4
1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj
2 0 obj << /Type /Pages /Kids [3 0 R 4 0 R] /Count 2 >> endobj
3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] /Contents 6 0 R /Resources 12 0 R >> endobj
4 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] /Contents 6 0 R /Resources 12 0 R >> endobj
6 0 obj << /Length 44 >>
stream
BT /F1 12 Tf 20 100 Td (Hello) Tj ET
endstream
endobj
12 0 obj << /Font << /F1 97 0 R /F2 20 0 R >> >> endobj
20 0 obj << /Type /Font /Subtype /Type0 /BaseFont /Loop /Encoding /Identity-H /DescendantFonts [20 0 R] >> endobj
trailer << /Root 1 0 R >>
"""


def _open(tmp_path: Path, data: bytes) -> pikepdf.Pdf:
    path = tmp_path / "damaged.pdf"
    path.write_bytes(data)
    return pikepdf.open(path)


def test_locates_lost_content_figures_and_counts_fonts(tmp_path: Path) -> None:
    with _open(tmp_path, _DAMAGED) as pdf:
        found = assess(pdf)
    assert found.pages_content_damaged == (2,)
    assert found.pages_figures_missing == (3,)
    assert found.fonts_damaged == 3  # F2 lost its ToUnicode map, F3 its font program, F4 is gone entirely
    assert found.located
    assert found.detail() == {"pages_content_damaged": "2", "pages_figures_missing": "3", "fonts_damaged": 3}


def test_blank_page_and_intact_font_are_not_losses(tmp_path: Path) -> None:
    with _open(tmp_path, _DAMAGED) as pdf:
        found = assess(pdf)
    assert 4 not in found.pages_content_damaged  # no /Contents is a blank page, not a lost stream
    assert 1 not in found.pages_content_damaged
    assert 1 not in found.pages_figures_missing


def test_shared_resources_count_a_missing_font_once_and_a_font_cycle_ends(tmp_path: Path) -> None:
    with _open(tmp_path, _SHARED) as pdf:
        found = assess(pdf)
    assert found.fonts_damaged == 1  # /F1 is gone once, not once per page; the self-referencing /F2 is intact
    assert found.pages_content_damaged == ()


def test_cut_stream_named_by_qpdf_counts_as_damaged(tmp_path: Path) -> None:
    """A stream qpdf recovered as empty keeps its object number; the warning names it, and every page drawing it
    is content-damaged."""
    with _open(tmp_path, _DAMAGED) as pdf:
        found = assess(pdf, frozenset({6}))
    assert found.pages_content_damaged == (1, 2, 3)


def test_intact_file_locates_nothing(tmp_path: Path) -> None:
    pdf = pikepdf.new()
    pdf.add_blank_page()
    pdf.add_blank_page()
    found = assess(pdf)
    assert found == RepairAssessment()
    assert not found.located
    assert found.detail() == {}
    assert found.clauses() == []


def test_warned_objects_reads_both_qpdf_spellings() -> None:
    messages = [
        "C:\\x\\cut.pdf: file is damaged",
        "C:\\x\\cut.pdf (object 14 0, offset 3352): expected endstream",
        "C:\\x\\cut.pdf (object 14 0, offset 3047): unable to recover stream data; treating stream as empty",
        "C:\\x\\cut.pdf: object 7 0 not found in file after regenerating cross reference table",
    ]
    assert warned_objects(messages) == frozenset({14, 7})
    assert warned_objects([]) == frozenset()


def test_clauses_read_as_one_sentence() -> None:
    one = RepairAssessment(pages_content_damaged=(3,), pages_figures_missing=(5, 6), fonts_damaged=1)
    assert one.clauses() == [
        "page 3 lost its content stream",
        "pages 5, 6 lost a figure or form",
        "1 font lost part of its definition, so text set in them may be incomplete on pages that cannot be pinpointed",
    ]
    many = RepairAssessment(pages_content_damaged=(3, 4), fonts_damaged=8)
    assert many.clauses()[0] == "pages 3, 4 lost their content stream"
    assert many.clauses()[1].startswith("8 fonts lost part of their definition")
