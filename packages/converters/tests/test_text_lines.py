"""Shared plain-text line joining (intomd_converters.text.lines) through text.plain and the renderer."""

from __future__ import annotations

from intomd.inputs import InputRef
from intomd.ir import Paragraph, spans_text
from intomd.pipeline import convert_ref
from intomd.render import render
from intomd_converters.text.lines import join_lines

PROSE = (
    "The heron survey on the east marsh ran for three weeks in early spring\n"
    "Before the water rose. Volunteers counted at dawn and again at dusk, and\n"
    "Every count was entered the same evening by the field office team.\n"
    "The totals are in the appendix."
)
POEM = "The marsh is still\nThe herons wait\nThe water's edge\nIs never late\n\nAt dawn they rise\nAt dusk they land\n"


def _paragraphs(text: str) -> list[Paragraph]:
    ref = InputRef.from_bytes(text.encode(), filename="notes.txt")
    try:
        doc = convert_ref(ref).document
    finally:
        ref.cleanup()
    return [b for b in doc.blocks if isinstance(b, Paragraph)]


def test_wrapped_prose_with_capitalized_line_starts_is_one_paragraph() -> None:
    paras = _paragraphs(PROSE)
    assert len(paras) == 1 and "line_breaks" not in paras[0].attrs  # source newlines kept, rendered as one
    body = render(convert_ref(InputRef.from_bytes(PROSE.encode(), filename="p.txt")), "full").body
    assert "early spring Before the water rose." in body and "\\\n" not in body


def test_list_with_lowercase_continuation_is_not_absorbed() -> None:
    lines = [x.text for x in join_lines(["- Milk", "items below", "    indented code", "next"])]
    assert lines == ["- Milk", "items below", "    indented code", "next"]
    assert [x.kind for x in join_lines(["- Milk", "items below"])] == ["list", "prose"]
    out = render(convert_ref(InputRef.from_bytes(b"- Milk\nitems below\nnext\n", filename="l.txt")), "full").body
    assert "Milk" in out and "items below" in out and "Milk items below" not in out


def test_poem_keeps_lines_within_each_stanza() -> None:
    paras = _paragraphs(POEM)
    assert [spans_text(p.spans).count("\n") for p in paras] == [3, 1]
    assert all(p.attrs["line_breaks"] == "hard" for p in paras)
    body = render(convert_ref(InputRef.from_bytes(POEM.encode(), filename="poem.txt")), "full").body
    assert "The marsh is still\\\nThe herons wait" in body
    txt = render(convert_ref(InputRef.from_bytes(POEM.encode(), filename="poem.txt")), "full", "txt").body
    assert "The marsh is still\nThe herons wait" in txt


def test_mixed_prose_and_list() -> None:
    text = "Bring these items to the marsh tomorrow morning, before the boat leaves at\nseven:\n- waders\n- scope\n"
    logical = join_lines(text.splitlines())
    assert [x.kind for x in logical] == ["prose", "list", "list"]
    assert logical[0].text.endswith("leaves at seven:")


def test_flowed_input_is_never_joined() -> None:
    assert [x.text for x in join_lines(["a", "b"], flowed=True)] == ["a", "b"]
