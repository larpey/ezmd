"""Generate the self-made EDGAR fixtures (run from the repo root: `uv run python fixtures/edgar/_generate.py`).

`synthetic-10k/input.htm` imitates the HTML that filing agents emit (Workiva style): inline XBRL with a hidden
`ix:header`, CSS-styled spans instead of `<b>`, a table of contents table, page-break furniture (page
numbers and "Table of Contents" links), item headings, bold and italic sub-headings, and a financial
statement with spacer columns, separate `$` cells, and split negative numbers. The company is fictitious.
"""

from __future__ import annotations

from pathlib import Path

HERE = Path(__file__).resolve().parent
B = "color:#000000;font-family:'Times New Roman',sans-serif;font-size:10pt;font-weight:700;line-height:120%"
N = "color:#000000;font-family:'Times New Roman',sans-serif;font-size:10pt;font-weight:400;line-height:120%"
IT = "color:#000000;font-family:'Times New Roman',sans-serif;font-size:10pt;font-style:italic;font-weight:400"
WING = "font-family:'Wingdings',sans-serif;font-size:10pt"


def div(text: str, style: str = N, align: str | None = None) -> str:
    a = f' style="text-align:{align}"' if align else ""
    return f'<div{a}><span style="{style}">{text}</span></div>'


def page_break(n: int) -> str:
    return (
        f'<div style="text-align:center"><span style="{N}">{n}</span></div>'
        '<hr style="page-break-after:always"/>'
        f'<div><span style="{N}"><a href="#toc">Table of Contents</a></span></div>'
    )


def cell(text: str, *, colspan: int = 1, bold: bool = False) -> str:
    cs = f' colspan="{colspan}"' if colspan > 1 else ""
    style = B if bold else N
    inner = f'<div><span style="{style}">{text}</span></div>' if text else f'<div><span style="{N}"></span></div>'
    return f'<td{cs} style="padding:2px">{inner}</td>'


def fin_row(label: str, a: str, b: str, *, dollar: bool = False, neg_a: bool = False, neg_b: bool = False) -> str:
    def amount(v: str, neg: bool) -> str:
        sign = cell("$") if dollar else cell("")
        if neg:
            return sign + cell(f"({v}") + cell(")")
        return sign + cell(v) + cell("")

    return "<tr>" + cell(label) + cell("") + amount(a, neg_a) + cell("") + amount(b, neg_b) + "</tr>"


def financial_table() -> str:
    head = (
        "<tr>"
        + cell("")
        + cell("")
        + cell("Year ended December 31,", colspan=7, bold=True)
        + "</tr><tr>"
        + cell("")
        + cell("")
        + cell("2025", colspan=3, bold=True)
        + cell("")
        + cell("2024", colspan=3, bold=True)
        + "</tr>"
    )
    rows = [
        fin_row("Charter revenue", "48,210", "41,877", dollar=True),
        fin_row("Voyage expenses", "19,402", "17,050", neg_a=True, neg_b=True),
        fin_row("Depreciation", "6,115", "5,980", neg_a=True, neg_b=True),
        fin_row("Operating income", "22,693", "18,847", dollar=True),
        fin_row("Foreign exchange loss", "1,204", "312", neg_a=True, neg_b=True),
        fin_row("Net income", "21,489", "18,535", dollar=True),
    ]
    return f'<table style="border-collapse:collapse;width:100%">{head}{"".join(rows)}</table>'


def toc() -> str:
    entries = [
        ("PART I", ""),
        ("Item 1.", "Business"),
        ("Item 1A.", "Risk Factors"),
        ("Item 1B.", "Unresolved Staff Comments"),
        ("PART II", ""),
        ("Item 7.", "Management's Discussion and Analysis of Financial Condition and Results of Operations"),
        ("Item 7A.", "Quantitative and Qualitative Disclosures About Market Risk"),
        ("Item 8.", "Financial Statements and Supplementary Data"),
        ("PART IV", ""),
        ("Item 15.", "Exhibits and Financial Statement Schedules"),
    ]
    rows = ""
    for n, (a, b) in enumerate(entries):
        link = '<a href="#i' + str(n) + '">' + a + "</a>"
        rows += "<tr>" + cell(link) + cell(b) + cell(str(3 + n)) + "</tr>"
    return f'<div id="toc"></div>{div("TABLE OF CONTENTS", B, "center")}<table>{rows}</table>'


def header() -> str:
    facts = [
        ("dei:EntityCentralIndexKey", "0009999999"),
        ("dei:AmendmentFlag", "false"),
        ("dei:DocumentFiscalYearFocus", "2025"),
        ("dei:DocumentFiscalPeriodFocus", "FY"),
        ("dei:CurrentFiscalYearEndDate", "--12-31"),
        ("dei:EntityFilerCategory", "Non-accelerated Filer"),
    ]
    hidden = "".join(f'<ix:nonNumeric contextRef="c-1" name="{n}">{v}</ix:nonNumeric>' for n, v in facts)
    return (
        '<div style="display:none"><ix:header><ix:hidden>'
        + hidden
        + '</ix:hidden><ix:resources><xbrli:context id="c-1"><xbrli:entity><xbrli:identifier '
        'scheme="http://www.sec.gov/CIK">0009999999</xbrli:identifier></xbrli:entity></xbrli:context>'
        "</ix:resources></ix:header></div>"
    )


def fact(name: str, value: str) -> str:
    return f'<ix:nonNumeric contextRef="c-1" name="dei:{name}">{value}</ix:nonNumeric>'


def cover() -> str:
    return "".join(
        [
            div("UNITED STATES", B, "center"),
            div("SECURITIES AND EXCHANGE COMMISSION", B, "center"),
            div("Washington, D.C. 20549", B, "center"),
            div("FORM " + fact("DocumentType", "10-K"), B, "center"),
            div(
                f'<span style="{WING}">x</span> ANNUAL REPORT PURSUANT TO SECTION 13 OR 15(d) OF THE SECURITIES '
                "EXCHANGE ACT OF 1934"
            ),
            div("For the fiscal year ended " + fact("DocumentPeriodEndDate", "December 31, 2025")),
            div("Commission File Number " + fact("EntityFileNumber", "001-99999")),
            div(fact("EntityRegistrantName", "Harbor Lane Shipping Corp."), B, "center"),
            div("(Exact name of registrant as specified in its charter)", IT, "center"),
            "<table><tr><td><div><span>Title of each class</span></div></td><td><div><span>Trading Symbol(s)</span>"
            "</div></td></tr><tr><td><div><span>Common Stock, $0.01 par value</span></div></td><td><div><span>"
            + fact("TradingSymbol", "HLSC")
            + "</span></div></td></tr></table>",
            div(f'Emerging growth company <span style="{WING}">o</span>'),
            div(
                "As of February 27, 2026, the registrant had "
                '<ix:nonFraction contextRef="c-1" name="dei:EntityCommonStockSharesOutstanding" unitRef="shares" '
                'decimals="INF" scale="0">12,500,000</ix:nonFraction> shares of common stock outstanding.'
            ),
        ]
    )


def body() -> str:
    lorem = (
        "Harbor Lane operates a fleet of eleven feeder container vessels on short-sea routes between regional "
        "ports. Charter terms are typically twelve to thirty-six months."
    )
    parts = [
        header(),
        cover(),
        page_break(1),
        toc(),
        page_break(2),
        div("PART I", B, "center"),
        div('<a id="i1"></a>Item 1. Business', B),
        div("Overview", B),
        div(lorem),
        div("Fleet", B),
        div("The fleet had an average age of 9.4 years at December 31, 2025. See Item 7 for charter coverage."),
        page_break(3),
        div("Item 1A. Risk Factors", B),
        div("Risks related to our industry", IT),
        div("Charter rates are volatile and a sustained decline would reduce revenue and cash flow."),
        div("Item 1B. Unresolved Staff Comments", B),
        div("None."),
        page_break(4),
        div("PART II", B, "center"),
        div("Item 7. Management's Discussion and Analysis of Financial Condition and Results of Operations", B),
        div("Results of Operations", B),
        div("Charter revenue increased 15.1 percent to $48.2 million, driven by two vessels delivered in 2025."),
        div("Item 7A. Quantitative and Qualitative Disclosures About Market Risk", B),
        div("Our exposure to interest rate risk is limited because all borrowings carry fixed rates."),
        page_break(5),
        div("Item 8. Financial Statements and Supplementary Data", B),
        div("Consolidated Statements of Income (in thousands)", B, "center"),
        financial_table(),
        page_break(6),
        div("PART IV", B, "center"),
        div("Item 15. Exhibits and Financial Statement Schedules", B),
        '<table><tr><td><div><span style="' + B + '">Exhibit</span></div></td><td><div><span style="' + B + '">'
        "Description</span></div></td></tr><tr><td><div><span>21.1</span></div></td><td><div><span>Subsidiaries "
        "of the registrant</span></div></td></tr><tr><td><div><span>31.1</span></div></td><td><div><span>"
        "Certification of the Chief Executive Officer</span></div></td></tr></table>",
        div("SIGNATURES", B, "center"),
        div(
            "Pursuant to the requirements of the Securities Exchange Act of 1934, the registrant has duly caused this "
            "report to be signed on its behalf by the undersigned, thereunto duly authorized."
        ),
        div("/s/ Mara Quill, Chief Executive Officer, March 3, 2026"),
    ]
    return "".join(parts)


def synthetic_10k() -> str:
    return (
        "<?xml version='1.0' encoding='ASCII'?>\n"
        '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:ix="http://www.xbrl.org/2013/inlineXBRL" '
        'xmlns:dei="http://xbrl.sec.gov/dei/2025" xmlns:xbrli="http://www.xbrl.org/2003/instance">'
        "<head><title>hlsc-20251231</title></head><body>" + body() + "</body></html>\n"
    )


def main() -> None:
    out = HERE / "synthetic-10k"
    out.mkdir(exist_ok=True)
    (out / "input.htm").write_text(synthetic_10k(), encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
