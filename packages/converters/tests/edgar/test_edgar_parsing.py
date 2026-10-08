"""EDGAR URL recognition, item sectioning, and financial-table cleanup."""

from __future__ import annotations

import pytest

from intomd.ir import Heading, InlineSpan, InlineStyle, Paragraph, Provenance, Table, TableCell, spans_text
from intomd_converters.edgar.html import parse_filing
from intomd_converters.edgar.items import section
from intomd_converters.edgar.tables import tidy_table
from intomd_converters.edgar.urls import company_target, dashed, parse_target

P = Provenance(source="t")
A = "https://www.sec.gov/Archives/edgar/data/320193/000032019326000018"


@pytest.mark.parametrize(
    ("url", "kind", "cik", "acc", "filename"),
    [
        (f"{A}/aapl-20260730.htm", "document", "320193", "0000320193-26-000018", "aapl-20260730.htm"),
        (f"{A}/", "index", "320193", "0000320193-26-000018", None),
        (f"{A}/index.json", "index", "320193", "0000320193-26-000018", None),
        (f"{A}/0000320193-26-000018-index.htm", "index", "320193", "0000320193-26-000018", None),
        (
            "https://www.sec.gov/ix?doc=/Archives/edgar/data/320193/000032019326000018/aapl-20260730.htm",
            "document",
            "320193",
            "0000320193-26-000018",
            "aapl-20260730.htm",
        ),
        (
            "https://www.sec.gov/Archives/edgar/data/0000320193/0000320193-26-000018.txt",
            "document",
            "320193",
            "0000320193-26-000018",
            "0000320193-26-000018.txt",
        ),
        ("0001376986-26-000026", "accession", "1376986", "0001376986-26-000026", None),
    ],
)
def test_parse_target(url: str, kind: str, cik: str, acc: str, filename: str | None) -> None:
    t = parse_target(url)
    assert t is not None
    assert (t.kind, t.cik, t.accession, t.filename) == (kind, cik, acc, filename)


def test_parse_target_company_and_search() -> None:
    t = parse_target("https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=AAPL&type=10-K")
    assert t is not None and (t.kind, t.company, t.form) == ("company", "AAPL", "10-K")
    s = parse_target("https://efts.sec.gov/LATEST/search-index?q=%22going%20concern%22&forms=10-K")
    assert s is not None and s.kind == "search" and s.query == '"going concern"'
    assert company_target("320193", "10-Q") is not None
    assert company_target("not a ticker!", "10-K") is None


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/Archives/edgar/data/1/000000000126000001/a.htm",
        "https://www.sec.gov/about.html",
        "https://www.sec.gov/Archives/edgar/data/1/000000000126000001/sub/dir/a.htm",
        "ftp://www.sec.gov/Archives/edgar/data/1/000000000126000001/a.htm",
        "0001376986-26-00002",
        "",
    ],
)
def test_parse_target_rejects(url: str) -> None:
    assert parse_target(url) is None


def test_dashed_accession() -> None:
    assert dashed("000137698626000026") == "0001376986-26-000026"
    assert dashed("0001376986-26-000026") == "0001376986-26-000026"


def _para(text: str, *, bold: bool = False, rest: str = "") -> Paragraph:
    spans = [InlineSpan(text=text, styles=[InlineStyle.BOLD] if bold else [])]
    if rest:
        spans.append(InlineSpan(text=rest))
    return Paragraph(spans=spans, provenance=P)


def test_10q_parts_disambiguate_repeated_item_numbers() -> None:
    blocks = [
        _para("PART I", bold=True),
        _para("Item 1. Financial Statements", bold=True),
        _para("Statements follow."),
        _para("PART II", bold=True),
        _para("Item 1. Legal Proceedings", bold=True),
        _para("None."),
    ]
    out = section(blocks, accession="acc")
    assert out.items == ["I-1", "II-1"]
    paths = [b.provenance.path for b in out.blocks if isinstance(b, Heading)]
    assert paths == ["part/I", "item/I-1", "part/II", "item/II-1"]


def test_toc_paragraph_duplicates_keep_the_body_occurrence() -> None:
    blocks = [
        _para("Item 1. Business", bold=True),
        _para("Item 7. MD&A", bold=True),
        _para("Item 1. Business", bold=True),
        _para("We build ships."),
        _para("Item 7. MD&A", bold=True),
        _para("Revenue grew."),
    ]
    out = section(blocks, accession=None)
    headings = [(spans_text(b.spans), b.provenance.path) for b in out.blocks if isinstance(b, Heading)]
    assert headings == [("Item 1. Business", "item/1"), ("Item 7. MD&A", "item/7")]
    texts = [spans_text(b.spans) for b in out.blocks if isinstance(b, Paragraph)]
    assert texts[:2] == ["Item 1. Business", "Item 7. MD&A"]  # TOC lines stay as cover text


def test_bold_heading_with_plain_body_in_one_paragraph_is_split() -> None:
    out = section(
        [_para("Item 8.01 Other Events.", bold=True, rest=" On May 1 we announced a dividend.")], accession=None
    )
    assert isinstance(out.blocks[0], Heading) and spans_text(out.blocks[0].spans) == "Item 8.01 Other Events."
    assert isinstance(out.blocks[1], Paragraph) and "dividend" in spans_text(out.blocks[1].spans)


def test_plain_sentence_starting_with_item_is_text() -> None:
    out = section([_para("Item 7 of this report discusses liquidity in detail.")], accession=None)
    assert out.items == [] and isinstance(out.blocks[0], Paragraph)


def test_sub_headings_and_furniture() -> None:
    blocks = [
        _para("Item 1. Business", bold=True),
        _para("Overview", bold=True),
        _para("Text."),
        _para("12"),
        Paragraph(spans=[InlineSpan(text="Table of Contents", href="#toc")], provenance=P),
        _para("Table of Contents"),  # a plain caption, not page furniture
        Paragraph(spans=[InlineSpan(text="Segment detail", styles=[InlineStyle.ITALIC])], provenance=P),
    ]
    out = section(blocks, accession=None)
    levels = [(b.level, spans_text(b.spans)) for b in out.blocks if isinstance(b, Heading)]
    assert levels == [(2, "Item 1. Business"), (3, "Overview"), (4, "Segment detail")]
    assert out.furniture_removed == 2 and out.inferred_headings == 2
    off = section(blocks, accession=None, infer_headings=False)
    assert [b.level for b in off.blocks if isinstance(b, Heading)] == [2]


def _cell(text: str, r: int, c: int, cs: int = 1, bold: bool = False) -> TableCell:
    spans = [InlineSpan(text=text, styles=[InlineStyle.BOLD] if bold else [])] if text else []
    return TableCell(spans=spans, row=r, col=c, col_span=cs)


def test_tidy_table_folds_currency_and_negatives() -> None:
    cells = [
        _cell("", 0, 0),
        _cell("2025", 0, 1, cs=3, bold=True),
        _cell("", 0, 4),
        _cell("2024", 0, 5, cs=3, bold=True),
    ]
    row = ["Net loss", "$", "(1,204", ")", "", "$", "312", ""]
    cells += [_cell(v, 1, c) for c, v in enumerate(row)]
    cells += [_cell("", 2, c) for c in range(8)]
    t = Table(cells=cells, n_rows=3, n_cols=8, provenance=P)
    out = tidy_table(t)
    assert isinstance(out, Table)
    assert (out.n_rows, out.n_cols, out.header_rows) == (2, 3, 1)
    grid = [[spans_text(c.spans) if c else None for c in r] for r in out.grid()]
    assert grid == [["", "2025", "2024"], ["Net loss", "$(1,204)", "$312"]]
    assert t.n_cols == 8  # input not modified


def test_tidy_table_single_cell_becomes_paragraph_and_empty_disappears() -> None:
    one = Table(cells=[_cell("", 0, 0), _cell("Note", 0, 1)], n_rows=1, n_cols=2, provenance=P)
    assert isinstance(tidy_table(one), Paragraph)
    empty = Table(cells=[_cell("", 0, 0)], n_rows=1, n_cols=1, provenance=P)
    assert tidy_table(empty) is None


def test_parse_filing_reads_dei_facts_and_css_bold() -> None:
    html = (
        '<html><body><div style="display:none"><ix:header><ix:hidden>'
        '<ix:nonNumeric name="dei:EntityCentralIndexKey" contextRef="c">0000000001</ix:nonNumeric>'
        "</ix:hidden></ix:header></div>"
        '<div><span style="font-weight:700">Item 2.02 Results</span></div>'
        '<div><span>Revenue was <ix:nonFraction name="us-gaap:Revenues">5</ix:nonFraction> million.</span></div>'
        "<table><tr><td><div><span>a</span></div></td><td><div><span>b</span></div></td></tr>"
        "<tr><td><div><span>c</span></div></td><td><div><span>d</span></div></td></tr></table>"
        "</body></html>"
    )
    parsed = parse_filing(html.encode(), source="s", base=None)
    assert parsed.facts == {"EntityCentralIndexKey": "0000000001"}
    first = parsed.blocks[0]
    assert isinstance(first, Paragraph) and InlineStyle.BOLD in first.spans[0].styles
    assert spans_text(parsed.blocks[1].spans) == "Revenue was 5 million."  # type: ignore[union-attr]
    assert isinstance(parsed.blocks[2], Table)
    assert "0000000001" not in " ".join(spans_text(b.spans) for b in parsed.blocks[:2])  # type: ignore[union-attr]
