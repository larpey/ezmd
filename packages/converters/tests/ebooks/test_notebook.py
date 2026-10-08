from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from intomd.detect import detect
from intomd.inputs import InputRef
from intomd.ir import CodeBlock, Document, Footnote, Heading, Image, Paragraph, Raw, Table, WarningKind, spans_text
from intomd.pipeline import convert_ref
from intomd.registry import ConversionError, ConvertOptions
from intomd_converters.ebooks.notebook import NotebookConverter

ROOT = Path(__file__).resolve().parents[4]
FIXTURE = ROOT / "fixtures" / "ebooks" / "ipynb-analysis" / "input.ipynb"
NL = chr(10)
ESC = chr(27)


def nb(cells: list[dict[str, Any]], **meta: Any) -> bytes:
    return json.dumps({"nbformat": 4, "nbformat_minor": 5, "metadata": meta, "cells": cells}).encode()


def code(src: str, outputs: list[dict[str, Any]] | None = None, n: int = 1) -> dict[str, Any]:
    return {"cell_type": "code", "execution_count": n, "metadata": {}, "source": src, "outputs": outputs or []}


def md(src: str, **extra: Any) -> dict[str, Any]:
    return {"cell_type": "markdown", "metadata": {}, "source": src, **extra}


def convert(data: bytes, options: ConvertOptions | None = None) -> Document:
    ref = InputRef.from_bytes(data, filename="n.ipynb")
    detect(ref)
    return NotebookConverter().convert(ref, options or ConvertOptions())


def test_fixture_cells_outputs_and_provenance() -> None:
    if not FIXTURE.exists():
        pytest.skip("run fixtures/ebooks/_generate.py first")
    ref = InputRef.from_path(FIXTURE)
    result = convert_ref(ref)
    doc = result.document
    assert result.converter_id == "documents.ipynb"
    assert doc.metadata.title == "Wading Bird Survey"
    codes = [b for b in doc.blocks if isinstance(b, CodeBlock)]
    assert [c.language for c in codes] == ["python", "output", "python", "python", "python", "output"]
    assert codes[0].attrs["execution_count"] == "1"
    assert codes[1].code == "2 rows" and codes[1].attrs["role"] == "output"
    err = codes[-1]
    assert err.attrs["role"] == "error" and ESC not in err.code and "ZeroDivisionError" in err.code
    table = next(b for b in doc.blocks if isinstance(b, Table))
    assert table.provenance.path == "cells[2].outputs[0]"
    images = [b for b in doc.blocks if isinstance(b, Image)]
    assert [i.ref for i in images] == ["images/cell0-sketch.png", "images/c4o0.png"]
    assert any(isinstance(b, Raw) and b.format == "rst" for b in doc.blocks)
    assert "header_synthesized" not in table.attrs  # the header row is real; its index cell is empty
    assert table.header_rows == 1
    para = next(b for b in doc.blocks if isinstance(b, Paragraph))
    assert [s.math for s in para.spans if s.math] == ["r = n / d"]
    assert all(b.provenance.path and b.provenance.path.startswith("cells[") for b in doc.blocks)
    assert codes[0].provenance.source_id == "load"


def test_code_cells_are_verbatim() -> None:
    src = "x = {'a':1}" + NL + NL + NL + "def f( y ):" + NL + "    return  y   # odd  spacing" + NL + "  " + NL
    doc = convert(nb([code(src)]))
    block = doc.blocks[0]
    assert isinstance(block, CodeBlock)
    assert block.code == src.rstrip(NL)


def test_math_display_and_inline() -> None:
    doc = convert(nb([md("$$" + NL + "a^2 + b^2 = c^2" + NL + "$$"), md("Cost is 5$ and $x$ but `$y$` stays code")]))
    eq = doc.blocks[0]
    assert eq.type == "equation" and getattr(eq, "latex", None) == "a^2 + b^2 = c^2"
    para = doc.blocks[1]
    assert isinstance(para, Paragraph)
    assert [s.math for s in para.spans if s.math] == ["x"]


def test_raw_cell_language_names() -> None:
    from intomd_converters.ebooks.notebook import raw_language

    assert raw_language("text/x-rst") == "rst"
    assert raw_language("text/latex") == "latex"
    assert raw_language("") == "text"
    assert raw_language("application/x-weird+thing") == "weird+thing"


def test_outputs_off_and_text_modes() -> None:
    bundle = {"image/png": "iVBORw0KGgo=", "text/plain": "img"}
    data = nb([code("x", [{"output_type": "display_data", "data": bundle}])])
    off = convert(data, ConvertOptions(extra={"text.notebook_outputs": "off"}))
    assert [b.type for b in off.blocks] == ["code"]
    text = convert(data, ConvertOptions(extra={"text.notebook_outputs": "text"}))
    assert [b.type for b in text.blocks] == ["code", "code"]
    full = convert(data)
    assert [b.type for b in full.blocks] == ["code", "image"]


def test_output_cap_truncates_and_warns() -> None:
    long = "line" + NL
    data = nb([code("print()", [{"output_type": "stream", "name": "stdout", "text": long * 5000}])])
    doc = convert(data, ConvertOptions(extra={"text.notebook_max_output_chars": 100}))
    out = doc.blocks[1]
    assert isinstance(out, CodeBlock) and out.code.endswith("[output truncated]") and len(out.code) < 140
    warn = next(w for w in doc.warnings if w.kind == WarningKind.TRUNCATED)
    assert warn.detail["reason"] == "notebook_output"


def test_markdown_output_and_footnotes_unique_per_cell() -> None:
    data = nb(
        [
            md("Alpha[^1]" + NL + NL + "[^1]: first"),
            md("Beta[^1]" + NL + NL + "[^1]: second"),
            code("x", [{"output_type": "execute_result", "data": {"text/markdown": "## Result" + NL + NL + "ok"}}]),
        ]
    )
    doc = convert(data)
    notes = [b for b in doc.blocks if isinstance(b, Footnote)]
    assert len({n.id for n in notes}) == 2
    refs = [s.footnote_ref for b in doc.blocks if isinstance(b, Paragraph) for s in b.spans if s.footnote_ref]
    assert refs == [n.id for n in notes]
    heads = [spans_text(b.spans) for b in doc.blocks if isinstance(b, Heading)]
    assert heads == ["Result"]


def test_honor_tags_hides_cells_with_a_warning() -> None:
    data = nb([md("shown"), {**md("secret"), "metadata": {"tags": ["remove-cell"]}}])
    assert "secret" in convert(data).plain_text()
    doc = convert(data, ConvertOptions(extra={"text.notebook_honor_tags": True}))
    assert "secret" not in doc.plain_text()
    assert WarningKind.REMOVED_HIDDEN_ELEMENTS in {w.kind for w in doc.warnings}


def test_kernel_language_sets_fence() -> None:
    doc = convert(nb([code("1 + 1")], kernelspec={"language": "R", "name": "ir"}))
    assert isinstance(doc.blocks[0], CodeBlock) and doc.blocks[0].language == "r"


def test_old_nbformat_is_read_best_effort() -> None:
    data = json.dumps(
        {"nbformat": 3, "worksheets": [{"cells": [{"cell_type": "code", "input": "print(1)", "outputs": []}]}]}
    ).encode()
    doc = convert(data)
    assert WarningKind.NOTEBOOK_INVALID in {w.kind for w in doc.warnings}
    assert "print(1)" in doc.plain_text()


def test_empty_and_invalid_notebooks() -> None:
    empty = convert(nb([]))
    assert not empty.blocks and WarningKind.EXTRACTION_EMPTY in {w.kind for w in empty.warnings}
    with pytest.raises(ConversionError):
        convert(b"{not json")
    with pytest.raises(ConversionError):
        convert(b"[1, 2]")


def test_hostile_text_is_cleaned() -> None:
    doc = convert(nb([md("bad" + chr(0) + "text" + chr(0x202E))]))
    assert chr(0) not in doc.plain_text() and chr(0x202E) not in doc.plain_text()


def test_images_written_when_image_dir_set(tmp_path: Path) -> None:
    import base64

    png = base64.b64encode(b"fakepng").decode()
    data = nb([code("plot()", [{"output_type": "display_data", "data": {"image/png": png}}])])
    convert(data, ConvertOptions(image_dir=str(tmp_path)))
    assert (tmp_path / "images" / "c0o0.png").read_bytes() == b"fakepng"
