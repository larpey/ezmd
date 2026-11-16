"""Buttons that title an open section (FAQ questions, accordion headers) are text, not chrome (D-0086)."""

from __future__ import annotations

import pytest

from ezmd.detect import detect
from ezmd.inputs import InputRef
from ezmd.ir import Document
from ezmd.registry import ConvertOptions
from ezmd_converters.web.engines import FullBodyConverter, RulesConverter, TrafilaturaConverter

ANSWER = "The keeper lights the lamp at dusk and trims the wick twice before the first watch is called. " * 3
ENGINES = [TrafilaturaConverter(), RulesConverter(), FullBodyConverter()]


def _convert(html: str, conv: object) -> Document:
    ref = InputRef.from_bytes(html.encode("utf-8"), filename="page.html")
    detect(ref)
    return conv.convert(ref, ConvertOptions())  # type: ignore[attr-defined]


def _faq(item: str) -> str:
    body = "".join(item.format(n=n, answer=f"{ANSWER} Answer number {n}.") for n in range(6))
    return f"""<html lang="en"><head><title>Keeper questions</title></head><body><main><h1>Keeper questions</h1>
    <p>{ANSWER}</p>{body}</main></body></html>"""


Q = "When does keeper {n} light the lamp?"
SHAPES = {
    "button in heading": f'<div class="faq"><h3><button aria-expanded="true">{Q}</button></h3><p>{{answer}}</p></div>',
    "heading in button": f'<div class="faq"><button aria-expanded="true"><h3>{Q}</h3></button><p>{{answer}}</p></div>',
    "controls a panel": (
        f'<div class="faq"><button aria-expanded="true" aria-controls="a{{n}}">{Q}</button>'
        '<div id="a{n}"><p>{answer}</p></div></div>'
    ),
}


@pytest.mark.parametrize("conv", ENGINES)
@pytest.mark.parametrize("shape", list(SHAPES))
def test_open_faq_questions_are_kept(conv: object, shape: str) -> None:
    text = _convert(_faq(SHAPES[shape]), conv).plain_text()
    for n in range(6):
        assert f"When does keeper {n} light the lamp?" in text
        assert f"Answer number {n}." in text


def test_menu_and_more_buttons_stay_out() -> None:
    links = "".join(f'<li><a href="/s{i}">Station {i}</a></li>' for i in range(8))
    html = f"""<html><head><title>Station</title></head><body><main><h1>Station</h1><p>{ANSWER}</p>
    <button aria-expanded="false" aria-controls="menu">Open the menu</button><ul id="menu">{links}</ul>
    <button aria-expanded="false" aria-controls="none">Show more</button>
    <button aria-expanded="true"><svg></svg></button></main></body></html>"""
    text = _convert(html, RulesConverter()).plain_text()
    assert "Open the menu" not in text and "Show more" not in text
