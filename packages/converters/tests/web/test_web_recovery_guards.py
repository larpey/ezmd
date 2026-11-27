"""When the rule extractor may replace Trafilatura's article, and what the dropped-text measure ignores (D-0086).

The extractors are stubbed with fixed blocks where the shape of their output is the point, so each page shows
exactly the loss and structure under test. The pages are synthetic.
"""

from __future__ import annotations

import pytest

from ezmd.detect import detect
from ezmd.inputs import InputRef
from ezmd.ir import Block, Document, InlineSpan, Paragraph, Provenance, Table, TableCell, WarningKind
from ezmd.registry import ConvertOptions
from ezmd_converters.web import pipeline
from ezmd_converters.web.build import Builder
from ezmd_converters.web.coverage import dropped_text
from ezmd_converters.web.dom import HtmlElement, body_of, parse_html
from ezmd_converters.web.engines import TrafilaturaConverter

_PROV = Provenance(source="x", path="body")


def _sentence(n: int) -> str:
    return f"Entry {n}: station {n * 3 + 1} sighted {n + 7} tenders by bell number {n * 11 + 2} at the point."


def _text(first: int, count: int) -> str:
    return " ".join(_sentence(n) for n in range(first, first + count))


def _para(text: str) -> Paragraph:
    return Paragraph(spans=[InlineSpan(text=text)], provenance=_PROV)


def _table(rows: int) -> Table:
    cells = [TableCell(spans=[InlineSpan(text=_sentence(100 + r))], row=r, col=0) for r in range(rows)]
    return Table(cells=cells, n_rows=rows, n_cols=1, provenance=_PROV)


def _html(paragraphs: list[str], extra: str = "") -> str:
    body = "".join(f"<p>{p}</p>" for p in paragraphs)
    return f"<html><head><title>Manual</title></head><body><main>{body}{extra}</main></body></html>"


def _convert(monkeypatch: pytest.MonkeyPatch, html: str, traf: list[Block], rules: list[Block]) -> Document:
    def fake_trafilatura(page: pipeline.Page, b: Builder) -> bool:
        b.blocks.extend(traf)
        return True

    def fake_rules(page: pipeline.Page, b: Builder) -> None:
        b.blocks.extend(rules)

    monkeypatch.setattr(pipeline, "_trafilatura", fake_trafilatura)
    monkeypatch.setattr(pipeline, "_rules", fake_rules)
    ref = InputRef.from_bytes(html.encode("utf-8"), filename="page.html")
    detect(ref)
    return TrafilaturaConverter().convert(ref, ConvertOptions())


def _switched(doc: Document) -> bool:
    return any(w.kind == WarningKind.ENGINE_FALLBACK for w in doc.warnings)


def _dropped_warning(doc: Document) -> int | None:
    found = [w for w in doc.warnings if w.kind == WarningKind.EXTRACTION_DROPPED_TEXT]
    return int(found[0].detail["dropped_chars"]) if found else None


def test_a_short_page_that_loses_under_500_characters_does_not_switch(monkeypatch: pytest.MonkeyPatch) -> None:
    kept, lost = [_sentence(n) for n in range(6)], [_sentence(n) for n in range(6, 10)]
    traf: list[Block] = [_para(s) for s in kept]
    doc = _convert(monkeypatch, _html(kept + lost), traf, [_para(s) for s in kept + lost])
    assert not _switched(doc) and _sentence(9) not in doc.plain_text()
    dropped = _dropped_warning(doc)
    assert dropped is not None and 250 <= dropped < 350
    assert 0.3 < dropped / len("".join(kept + lost)) < 0.45


KEPT = [_text(0, 8), _text(8, 8)]
LOST = [_text(16, 5), _text(21, 5)]


def test_a_real_body_loss_with_intact_structure_switches(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = "".join(f"<tr><td>{_sentence(100 + r)}</td></tr>" for r in range(4))
    traf: list[Block] = [*(_para(p) for p in KEPT), _table(4)]
    rules: list[Block] = [*(_para(p) for p in KEPT + LOST), _table(4)]
    doc = _convert(monkeypatch, _html(KEPT + LOST, f"<table>{rows}</table>"), traf, rules)
    assert _switched(doc) and _sentence(25) in doc.plain_text()
    assert _dropped_warning(doc) is None


def test_a_table_collapsed_into_one_paragraph_keeps_trafilatura(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = "".join(f"<tr><td>{_sentence(100 + r)}</td></tr>" for r in range(30))
    traf: list[Block] = [*(_para(p) for p in KEPT), _table(30)]
    collapsed = _para(" ".join(_sentence(100 + r) for r in range(30)))
    rules: list[Block] = [*(_para(p) for p in KEPT + LOST), collapsed]
    doc = _convert(monkeypatch, _html(KEPT + LOST, f"<table>{rows}</table>"), traf, rules)
    assert not _switched(doc)
    assert any(isinstance(b, Table) and b.n_rows == 30 for b in doc.blocks)
    assert (_dropped_warning(doc) or 0) >= 500


@pytest.mark.parametrize(
    ("traf_rows", "rules_rows", "rules_words", "refused"),
    [
        (4, 3, 0, True),
        (4, 4, 0, False),
        (0, 0, 299, False),
        (0, 0, 300, True),
    ],
)
def test_structure_guard_boundaries(traf_rows: int, rules_rows: int, rules_words: int, refused: bool) -> None:
    traf: list[Block] = [_para("word " * 100)] + ([_table(traf_rows)] if traf_rows else [])
    rules: list[Block] = [_para("word " * (rules_words or 100))] + ([_table(rules_rows)] if rules_rows else [])
    assert pipeline._loses_structure(traf, rules) is refused


def test_a_long_paragraph_trafilatura_also_has_is_not_a_collapse() -> None:
    assert not pipeline._loses_structure([_para("word " * 200)], [_para("word " * 399)])
    assert pipeline._loses_structure([_para("word " * 200)], [_para("word " * 400)])


def _body(inner: str) -> HtmlElement:
    return body_of(parse_html(f"<html><body><main>{inner}</main></body></html>"))


def test_heading_text_counts_as_kept() -> None:
    title = "The Keeper Records Every Tender That Calls At The Light"
    inner = f"<p>{_text(0, 5)}</p><ul><li><h3>{title}</h3></li></ul><h2>{title}</h2><p>{_text(5, 5)}</p>"
    w = dropped_text(_body(inner), _text(0, 5))
    assert w is not None
    assert w.detail["dropped_chars"] == len(_text(5, 5))
    assert w.detail["page_chars"] == len(_text(0, 10)) - 1 + 2 * len(title)


BROWSER = "You are using an outdated browser. Please upgrade your browser to view this site correctly. "
LEAVING = "You are now leaving this website. We do not control the pages you are about to visit. "
NOTICE = "The harbor office answers for none of what is printed on the pages of other parties. " * 3


@pytest.mark.parametrize(
    "banner",
    [
        f"<p>{BROWSER}</p><p>{LEAVING}</p><p>{BROWSER}</p>",
        f'<div class="browser-upgrade"><p>{NOTICE}</p></div>',
        f'<div id="outdated-browser"><p>{NOTICE}</p></div>',
        f'<div class="exit-popup"><p>{NOTICE}</p></div>',
        f'<div class="modal exit-intent_overlay"><p>{NOTICE}</p></div>',
    ],
)
def test_browser_and_exit_banners_are_not_lost_text(banner: str) -> None:
    assert dropped_text(_body(f"{banner}<p>{_text(0, 5)}</p>"), _text(0, 5)) is None


@pytest.mark.parametrize(
    "block",
    [
        f"<p>{BROWSER}{_text(5, 5)}</p>",
        f'<div class="exit-interviews"><p>{NOTICE}</p></div>',
    ],
)
def test_prose_that_only_resembles_a_banner_is_still_counted(block: str) -> None:
    assert dropped_text(_body(f"{block}<p>{_text(0, 5)}</p>"), _text(0, 5)) is not None
