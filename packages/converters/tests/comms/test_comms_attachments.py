"""Attachment conversion and its warnings (ROADMAP P1-T04: attachment conversion warnings verified)."""

from __future__ import annotations

from email.message import EmailMessage

from intomd.ir import Table, WarningKind
from intomd.registry import ConvertOptions
from intomd_converters.comms.attachments import Row, attachments_table
from intomd_converters.comms.build import table_rows


def _statuses(doc) -> dict[str, str]:
    table = next(b for b in doc.blocks if isinstance(b, Table) and b.attrs.get("role") == "attachments")
    grid = table.grid()
    return {grid[r][0].spans[0].text: grid[r][3].spans[0].text for r in range(1, table.n_rows)}


def _kinds(doc) -> dict[str, str]:
    return {str(w.detail.get("name")): str(w.kind) for w in doc.warnings if "name" in w.detail}


def _with(mk, *atts: tuple[bytes, str, str, str]) -> EmailMessage:
    m = mk("Files", "See attached.\n")
    for data, maintype, subtype, name in atts:
        m.add_attachment(data, maintype=maintype, subtype=subtype, filename=name)
    return m


def test_converted_attachment_becomes_child_with_provenance(convert, mk) -> None:
    m = _with(mk, (b"# Notes\n\nTuesday: 14 herons.\n", "text", "markdown", "notes.md"))
    doc = convert(m.as_bytes(), name="mail.eml").document
    assert _statuses(doc)["notes.md"].startswith("converted (")
    child = doc.children[0]
    assert child.metadata.source == "mail.eml!attachments/notes.md"
    assert all(b.provenance.path == "attachments/1" for b in child.blocks)
    assert doc.metadata.extra["attachments"] == 1


def test_unsupported_attachment_warns_unconverted(convert, mk) -> None:
    doc = convert(_with(mk, (bytes(range(256)) * 8, "application", "octet-stream", "blob.bin")).as_bytes()).document
    assert _statuses(doc)["blob.bin"] == "not converted (unsupported type)"
    assert _kinds(doc)["blob.bin"] == WarningKind.ATTACHMENT_UNCONVERTED
    assert doc.children == []


def test_failed_attachment_warns_failed(convert, mk) -> None:
    broken = b"%PDF-1.7\n1 0 obj << /Type /Catalog >> broken beyond repair"
    doc = convert(_with(mk, (broken, "application", "pdf", "report.pdf")).as_bytes()).document
    assert _kinds(doc)["report.pdf"] == WarningKind.ATTACHMENT_FAILED
    assert _statuses(doc)["report.pdf"] == "failed"


def test_oversized_attachment_is_skipped(convert, mk) -> None:
    doc = convert(_with(mk, (b"x" * 5000, "text", "plain", "big.txt")).as_bytes(), max_attachment_bytes=1000).document
    assert _statuses(doc)["big.txt"] == "skipped (too large)"
    w = next(w for w in doc.warnings if w.kind == WarningKind.ATTACHMENT_SKIPPED)
    assert w.detail["reason"] == "too_large"


def test_attachment_cap_and_list_mode(convert, mk) -> None:
    m = _with(mk, *((f"file {i}\n".encode(), "text", "plain", f"f{i}.txt") for i in range(4)))
    capped = convert(m.as_bytes(), max_attachments=2).document
    assert list(_statuses(capped).values()).count("skipped (attachment cap)") == 2
    listed = convert(m.as_bytes(), attachments="list").document
    assert set(_statuses(listed).values()) == {"listed (not converted)"}
    assert listed.children == []
    assert all(w.detail["reason"] == "policy" for w in listed.warnings if w.kind == WarningKind.ATTACHMENT_SKIPPED)


def test_follow_attachments_off_skips(convert, mk) -> None:
    m = _with(mk, (b"hello\n", "text", "plain", "a.txt"))
    doc = convert(m.as_bytes(), options=ConvertOptions(follow_attachments=False)).document
    assert _statuses(doc)["a.txt"] == "skipped (depth limit)"
    assert any(w.kind == WarningKind.ATTACHMENT_SKIPPED for w in doc.warnings)


def test_tnef_and_smime_are_reported(convert, mk) -> None:
    m = _with(
        mk,
        (b"\x78\x9f\x3e\x22" + bytes(40), "application", "ms-tnef", "winmail.dat"),
        (b"0\x82\x01", "application", "pkcs7-mime", "smime.p7m"),
    )
    doc = convert(m.as_bytes()).document
    kinds = _kinds(doc)
    assert kinds["winmail.dat"] == WarningKind.TNEF_UNPARSED
    assert kinds["smime.p7m"] == WarningKind.SMIME_NOT_DECRYPTED
    assert doc.children == []


def test_forwarded_message_converts_recursively_with_depth_limit(convert, mk) -> None:
    inner = mk("Level 3", "deepest\n", mid="<l3@x>")
    for level in (2, 1):
        outer = mk(f"Level {level}", f"level {level}\n", mid=f"<l{level}@x>")
        outer.add_attachment(inner)
        inner = outer
    deep = convert(inner.as_bytes(), options=ConvertOptions(max_attachment_depth=1)).document
    assert deep.children[0].converter_id == "comms.eml"
    assert deep.children[0].metadata.title == "Level 2"
    assert _statuses(deep.children[0])["Level 3.eml"] == "skipped (depth limit)"
    full = convert(inner.as_bytes()).document
    assert full.children[0].children[0].metadata.title == "Level 3"


def test_duplicate_names_are_disambiguated(convert, mk) -> None:
    m = _with(mk, (b"one\n", "text", "plain", "a.txt"), (b"two\n", "text", "plain", "a.txt"))
    doc = convert(m.as_bytes(), name="m.eml").document
    assert sorted(c.metadata.source for c in doc.children) == ["m.eml!attachments/a (2).txt", "m.eml!attachments/a.txt"]


def test_path_traversal_names_are_reduced_to_basename(convert, mk) -> None:
    doc = convert(_with(mk, (b"x\n", "text", "plain", "../../etc/passwd")).as_bytes()).document
    assert "passwd" in _statuses(doc)


def test_attachments_table_shape() -> None:
    from intomd.ir import Provenance

    t = attachments_table([Row("a.txt", "text/plain", 2048, "converted")], Provenance(source="x"))
    assert t.n_rows == 2 and t.n_cols == 4 and table_rows(t) == [("a.txt", "text/plain")]
