from __future__ import annotations

from collections.abc import Callable

import pytest

from intomd.ir import CodeBlock, Document, Heading, Table, WarningKind
from intomd.registry import ConversionError
from intomd_converters.data.xml_conv import XmlConverter

NL = chr(10)
Convert = Callable[..., Document]


def _tables(doc: Document) -> list[Table]:
    """Data tables only: schema, structure and namespace summaries are left out."""
    out = []
    for b in doc.blocks:
        if isinstance(b, Table):
            first = next((c for c in b.cells if c.row == 0 and c.col == 0), None)
            if first is None or first.spans[0].text not in ("Path", "Element path", "Prefix"):
                out.append(b)
    return out


def _cells(t: Table) -> list[list[str]]:
    return [["".join(s.text for s in c.spans) if c else "" for c in row] for row in t.grid()]


def test_records_namespaces_and_xpath(convert: Convert) -> None:
    items_xml = "".join(f'<item id="{i}"><v>{i}.5</v></item>' for i in range(6))
    data = ('<r xmlns="urn:a" xmlns:x="urn:x"><x:t>T</x:t>' + items_xml + "<pair><k>a</k></pair>" * 2 + "</r>").encode()
    doc = convert(XmlConverter(), data, "a.xml")
    all_tables = [b for b in doc.blocks if isinstance(b, Table)]
    assert _cells(all_tables[0])[1:] == [["(default)", "urn:a"], ["x", "urn:x"]]
    assert ["/r/item", "6", "@id", ""] in _cells(all_tables[1])
    top, items, _pair1, pair2 = _tables(doc)
    assert _cells(top)[1:] == [["x:t", "T"]]
    assert _cells(items)[:2] == [["@id", "v"], ["0", "0.5"]] and items.n_rows == 7
    assert items.column_types == ["int", "float"]
    assert items.provenance.path == "/r/item"
    heads = [(b.level, b.spans[0].text, b.provenance.path) for b in doc.blocks if isinstance(b, Heading)]
    assert (3, "item", "/r/item") in heads and (4, "pair 2", "/r/pair[2]") in heads
    assert _cells(pair2) == [["Key", "Value"], ["k", "a"]]
    code = [b for b in doc.blocks if isinstance(b, CodeBlock)]
    assert code and code[-1].language == "xml"


def test_xxe_external_entity_not_resolved(convert: Convert, tmp_path: object) -> None:
    data = (
        b'<?xml version="1.0"?><!DOCTYPE d [<!ENTITY x SYSTEM "file:///etc/passwd">'
        b'<!ENTITY n SYSTEM "http://127.0.0.1:9/x">]><d><a>&x;</a><b>&n;</b><c>ok &amp; &#65;</c></d>'
    )
    doc = convert(XmlConverter(), data, "x.xml")
    text = doc.plain_text()
    assert "root:" not in text and "passwd" not in text and "ENTITY" not in text
    assert _cells(_tables(doc)[0])[1:] == [["a", ""], ["b", ""], ["c", "ok & A"]]
    w = next(w for w in doc.warnings if w.kind == WarningKind.UNSUPPORTED_FEATURE)
    assert w.count == 2


def test_billion_laughs_not_expanded(convert: Convert) -> None:
    ents = ['<!ENTITY l0 "lol">'] + [f'<!ENTITY l{i} "{("&l" + str(i - 1) + ";") * 10}">' for i in range(1, 10)]
    data = ('<?xml version="1.0"?><!DOCTYPE z [' + "".join(ents) + "]><z><q>&l9;</q></z>").encode()
    doc = convert(XmlConverter(), data, "b.xml")
    assert "lol" not in doc.plain_text()


def test_mixed_content_and_repeated_text(convert: Convert) -> None:
    data = b"<p>Hello <b>bold</b> tail<i>a</i><i>b</i></p>"
    doc = convert(XmlConverter(), data, "m.xml")
    rows = _cells(_tables(doc)[0])
    assert ["#text", "Hello tail"] in rows and ["i", '["a", "b"]'] in rows


def test_leaf_root(convert: Convert) -> None:
    doc = convert(XmlConverter(), b"<only>just text</only>", "l.xml")
    assert "just text" in doc.plain_text()


def test_deep_xml_truncated(convert: Convert) -> None:
    data = ("<a>" * 100 + "x" + "</a>" * 100).encode()
    doc = convert(XmlConverter(), data, "d.xml")
    assert WarningKind.DEPTH_TRUNCATED in [w.kind for w in doc.warnings]


def test_malformed_raises(convert: Convert) -> None:
    with pytest.raises(ConversionError):
        convert(XmlConverter(), b"<a><b></a>", "bad.xml")
