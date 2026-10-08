from __future__ import annotations

from intomd.ir import Heading, Image, ListBlock, Paragraph, Quote, Table, WarningKind, spans_text
from intomd.registry import ConvertOptions
from intomd_converters.comms.body_text import text_blocks, unflow
from intomd_converters.comms.build import table_rows
from intomd_converters.comms.decode import decode_bytes

PLAIN = (
    "Hi Bob,\n\nThe count is done. We saw fourteen \nbirds on Tuesday.\n\n- tally\n- boat\n\n-- \nAnn Reed\nSurvey\n\n"
    "On Mon, 30 Sep 2024 at 09:12, Bob Stone <bob@example.org> wrote:\n> Could you send the count?\n>> Older line.\n"
)


def test_plain_message_headers_body_and_roles(convert, mk) -> None:
    m = mk("Heron count", PLAIN)
    m["Cc"] = "Office <office@example.org>"
    m["Bcc"] = "Audit <audit@example.org>"
    result = convert(m.as_bytes())
    doc = result.document
    assert result.converter_id == "comms.eml"
    assert isinstance(doc.blocks[0], Heading) and spans_text(doc.blocks[0].spans) == "Heron count"
    rows = dict(table_rows(next(b for b in doc.blocks if isinstance(b, Table))))
    assert rows["From"] == "Ann Reed <ann@example.org>"
    assert rows["Cc"] == "Office <office@example.org>"
    assert rows["Bcc"] == "Audit <audit@example.org>"  # spec 9c step 1: Bcc when present
    assert rows["Date"] == "2024-10-01T10:00:00+00:00"
    assert doc.metadata.title == "Heron count" and doc.metadata.author == "Ann Reed"
    assert doc.metadata.extra["body_source"] == "text"
    sig = [b for b in doc.blocks if b.attrs.get("role") == "signature"]
    assert [spans_text(b.spans) for b in sig if isinstance(b, Paragraph)] == ["Ann Reed\nSurvey"]
    assert sig[0].attrs["line_breaks"] == "hard"
    header = [b for b in doc.blocks if b.attrs.get("role") == "reply_header"]
    assert len(header) == 1
    history = [b for b in doc.blocks if isinstance(b, Quote)]
    assert [q.depth for q in history] == [1, 2]
    assert all(q.attrs.get("role") == "reply_history" for q in history)
    assert any(isinstance(b, ListBlock) for b in doc.blocks)
    assert all(b.provenance.source_id == "<m1@example.org>" for b in doc.blocks)
    assert {b.provenance.path for b in doc.blocks} >= {"headers", "body"}
    assert doc.sidecar_extra["email_headers"][0]["name"] == "From"


def test_strip_and_keep_quote_modes(convert, mk) -> None:
    stripped = convert(mk("Heron count", PLAIN).as_bytes(), strip_quotes="strip").document
    assert not any(isinstance(b, Quote) for b in stripped.blocks)
    w = next(w for w in stripped.warnings if w.kind == WarningKind.QUOTED_HISTORY_REMOVED)
    assert w.count == 2
    kept = convert(mk("Heron count", PLAIN).as_bytes(), strip_quotes="keep").document
    assert sum(isinstance(b, Quote) for b in kept.blocks) == 2
    assert not any(b.attrs.get("role") in ("reply_history", "reply_header") for b in kept.blocks)


def test_quote_without_reply_header_is_not_history(convert, mk) -> None:
    body = "The contract says:\n\n> The tenant pays rent monthly.\n\nAgreed?\n"
    doc = convert(mk("Clause", body).as_bytes(), strip_quotes="strip").document
    quotes = [b for b in doc.blocks if isinstance(b, Quote)]
    assert len(quotes) == 1 and "role" not in quotes[0].attrs  # 9e step 5: strip needs a reply header


def test_format_flowed_unwraps_soft_breaks() -> None:
    assert unflow("one \ntwo\n> a \n> b\n", delsp=False) == ["one two", "> a b", ""]
    assert unflow("ab\ncd \nef", delsp=True) == ["ab", "cdef"]


def test_outlook_original_message_marks_rest_as_history() -> None:
    from intomd.ir import Provenance

    blocks = text_blocks(
        "Yes.\n\n-----Original Message-----\nFrom: Bob\nSent: Monday\n\nOld text.\n", Provenance(source="x")
    )
    assert blocks[1].attrs["role"] == "reply_header"
    assert all(b.attrs.get("role") == "reply_history" and isinstance(b, Quote) for b in blocks[2:])


HTML = """<html><body><p>Hello <b>team</b>.</p><ul><li>one</li><li>two</li></ul>
<div class="gmail_signature"><p>Carol Diaz, Survey Lead</p></div>
<div class="gmail_quote"><div class="gmail_attr">On Fri, Sep 27, 2024 Ann wrote:<br></div>
<blockquote class="gmail_quote"><p>Please post the report.</p></blockquote></div></body></html>"""


def test_html_body_through_web_module_with_gmail_markers(convert, mk) -> None:
    m = mk("Report", "Hello team. one two\n")
    m.add_alternative(HTML, subtype="html")
    doc = convert(m.as_bytes()).document
    assert doc.metadata.extra["body_source"] == "html"
    assert any(isinstance(b, ListBlock) for b in doc.blocks)
    roles = {b.attrs.get("role") for b in doc.blocks}
    assert {"signature", "reply_header", "reply_history"} <= roles
    assert len({b.id for b in doc.blocks}) == len(doc.blocks)
    text = convert(m.as_bytes(), body="text").document
    assert text.metadata.extra["body_source"] == "text"
    stripped = convert(m.as_bytes(), strip_quotes="strip").document
    assert not any(isinstance(b, Quote) for b in stripped.blocks)


def test_html_only_body_and_inline_cid_image(convert, mk, tmp_path) -> None:
    m = mk("Map", "See map.\n")
    m.add_alternative('<p>See map.</p><img src="cid:img1@x" alt="the map">', subtype="html")
    m.get_payload()[1].add_related(b"\x89PNG fake", maintype="image", subtype="png", cid="<img1@x>", filename="m.png")
    opts = ConvertOptions(image_dir=str(tmp_path))
    doc = convert(m.as_bytes(), options=opts).document
    img = next(b for b in doc.blocks if isinstance(b, Image))
    assert img.ref == "images/m.png"
    assert (tmp_path / "images" / "m.png").read_bytes() == b"\x89PNG fake"
    assert doc.children == []  # referenced inline images are not converted as attachments


def test_unknown_cid_warns_missing_resource(convert, mk) -> None:
    m = mk("Map", "x\n")
    m.add_alternative('<p>Look</p><img src="cid:nowhere@x" alt="gone">', subtype="html")
    doc = convert(m.as_bytes()).document
    assert any(w.kind == WarningKind.MISSING_RESOURCE for w in doc.warnings)


def test_encoded_words_and_raw_utf8_headers(convert) -> None:
    raw = (
        "From: =?utf-8?b?Sm9zw6kgw4FsdmFyZXo=?= <jose@example.org>\r\n"
        "To: =?x-unknown?q?M=FCller?= <m@example.org>\r\n"
        "Subject: Café =?iso-8859-1?q?r=E9sum=E9?=\r\n"
        "Date: Wed, 02 Oct 2024 12:00:00 +0000\r\nMessage-ID: <e1@x>\r\n\r\nBody.\r\n"
    ).encode()
    doc = convert(raw).document
    rows = dict(table_rows(next(b for b in doc.blocks if isinstance(b, Table))))
    assert rows["From"] == "José Álvarez <jose@example.org>"
    assert rows["To"] == "Müller <m@example.org>"
    assert rows["Subject"] == "Café résumé"


def test_wrong_declared_charset_falls_back() -> None:
    raw = "Déjà quatorze hérons à l'étang.".encode("cp1252")
    d = decode_bytes(raw, "us-ascii")
    assert d.text == "Déjà quatorze hérons à l'étang."
    assert d.declared_failed
    assert decode_bytes(b"plain", "no-such-charset").declared_failed
    assert decode_bytes("café".encode(), "utf-8").text == "café"


def test_all_headers_option_renders_every_header(convert, mk) -> None:
    m = mk()
    m["Received"] = "from relay.example.org by mx.example.org"
    doc = convert(m.as_bytes(), all_headers=True).document
    table = [b for b in doc.blocks if isinstance(b, Table) and b.attrs.get("role") == "all_headers"]
    assert table and ("Received", "from relay.example.org by mx.example.org") in table_rows(table[0])


def test_eml_detected_as_html_still_routes_to_email(convert) -> None:
    raw = b"To: b@x.org\r\nFrom: a@x.org\r\nSubject: Hi\r\nContent-Type: text/html\r\n\r\n"
    raw += b"<html><body><p>Hi</p></body></html>"
    assert convert(raw, name="x.eml").converter_id == "comms.eml"


def test_headers_only_message_is_not_empty(convert) -> None:
    doc = convert(b"From: a@x.org\r\nSubject: Empty\r\nDate: Wed, 02 Oct 2024 12:00:00 +0000\r\n\r\n").document
    assert doc.blocks and doc.metadata.extra["body_source"] == "none"
