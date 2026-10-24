"""Superscript and subscript spans: `^x^` / `~x~` with extended Markdown, Unicode script digits without it."""

from __future__ import annotations

from render_builders import make_result, prov, span

from ezmd.ir import InlineStyle, Paragraph
from ezmd.render import render


def _body(*spans: object, **overrides: object) -> str:
    res = make_result([Paragraph(spans=list(spans), provenance=prov())])  # type: ignore[arg-type]
    return render(res, "full", **overrides).body


def test_digit_superscripts_become_unicode_without_extended_markdown() -> None:
    body = _body(span("costs 1.0 · 10"), span("20", InlineStyle.SUPERSCRIPT), span(" FLOPs"))
    assert "costs 1.0 · 10²⁰ FLOPs" in body


def test_digit_subscripts_become_unicode_and_letters_stay_plain() -> None:
    body = _body(span("H"), span("2", InlineStyle.SUBSCRIPT), span("O and d"), span("model", InlineStyle.SUBSCRIPT))
    assert "H₂O and dmodel" in body


def test_non_digit_superscript_stays_plain() -> None:
    assert "Vaswani∗ et al." in _body(span("Vaswani"), span("∗", InlineStyle.SUPERSCRIPT), span(" et al."))


def test_extended_markdown_keeps_caret_syntax() -> None:
    body = _body(span("10"), span("20", InlineStyle.SUPERSCRIPT), extended_markdown="true")
    assert "10^20^" in body
