"""Native Outlook .msg reader (olefile) on compound files built by fixtures/comms/_cfb.py."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

from intomd.inputs import InputRef
from intomd.ir import Table, WarningKind
from intomd.pipeline import convert_ref
from intomd.registry import ConversionError, ConvertOptions
from intomd_converters.comms.build import table_rows
from intomd_converters.comms.msg import MsgConverter
from intomd_converters.comms.msg_native import MsgReadError, read_msg
from intomd_converters.comms.options import CommsOptions
from intomd_converters.comms.rtf import PREBUF, decompress, html_from_rtf, text_from_rtf

ROOT = Path(__file__).resolve().parents[4]


def _load_cfb() -> ModuleType:
    spec = importlib.util.spec_from_file_location("intomd_fixture_cfb", ROOT / "fixtures" / "comms" / "_cfb.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


cfb = _load_cfb()

# MS-OXRTFCP 3.1.1 example: the compressed form of "{\rtf1\ansi\ansicpg1252\pard hello world}\r\n".
SPEC_EXAMPLE = bytes.fromhex(
    "2d0000002b0000004c5a4675f1c5c7a703000a007263706731323542320af32068656c090020627705b06c647d0a800fa0"
)


def test_lzfu_matches_the_spec_example() -> None:
    raw, crc_ok = decompress(SPEC_EXAMPLE)
    assert raw == b"{\\rtf1\\ansi\\ansicpg1252\\pard hello world}\r\n"
    assert crc_ok


def test_lzfu_roundtrip_and_hostile_rawsize() -> None:
    raw = b"{\\rtf1\\ansi " + b"herons and egrets " * 200 + b"}"
    blob = cfb.compress_rtf(raw, PREBUF)
    assert decompress(blob) == (raw, True)
    assert len(decompress(blob, max_raw=100)[0]) == 100
    stored = bytes.fromhex("0f000000030000004d454c4100000000") + b"abc"
    assert decompress(stored)[0] == b"abc"


def test_html_deencapsulation() -> None:
    rtf = (
        b"{\\rtf1\\ansi\\ansicpg1252\\fromhtml1 {\\fonttbl{\\f0 Arial;}}{\\*\\htmltag64 <p>}\\htmlrtf {\\b\\htmlrtf0 "
        b"Caf\\'e9 \\{x\\}\\htmlrtf}\\htmlrtf0 {\\*\\htmltag72 </p>}\\par}"
    )
    html = html_from_rtf(rtf)
    assert html is not None and "<p>" in html and "Café {x}" in html and "Arial" not in html
    assert html_from_rtf(b"{\\rtf1\\ansi plain}") is None
    assert "plain" in text_from_rtf(b"{\\rtf1\\ansi plain}")


def _spec(**kw: object) -> object:
    base = {
        "strings": {0x0037: "Plan", 0x0C1A: "Ann Reed", 0x5D01: "ann@example.org", 0x1000: "Body text."},
        "times": {0x0039: 1727773200},
        "recipients": [("Bob", "bob@example.org", 1), ("Carol", "carol@example.org", 2), ("Audit", "a@x.org", 3)],
    }
    base.update(kw)
    return cfb.MsgSpec(**base)


def test_native_reader_headers_recipients_and_body() -> None:
    pm = read_msg(cfb.write_msg(_spec()), CommsOptions())
    assert pm.headers["From"] == "Ann Reed <ann@example.org>"
    assert pm.headers["To"] == "Bob <bob@example.org>"
    assert pm.headers["Cc"] == "Carol <carol@example.org>"
    assert pm.headers["Bcc"] == "Audit <a@x.org>"
    assert pm.headers["Date"] == "2024-10-01T09:00:00+00:00"
    assert pm.text == "Body text."


def test_ansi_strings_use_the_code_page() -> None:
    spec = _spec(strings={}, ansi={0x0037: "Résumé".encode("cp1252")})
    assert read_msg(cfb.write_msg(spec), CommsOptions()).headers["Subject"] == "Résumé"


def test_compressed_rtf_body_becomes_html() -> None:
    rtf = b"{\\rtf1\\ansi\\fromhtml1 {\\*\\htmltag64 <p>}Hello {\\*\\htmltag64 <b>}there{\\*\\htmltag64 </b>}}"
    spec = _spec(strings={0x0037: "R"}, binary={0x1009: cfb.compress_rtf(rtf, PREBUF)})
    pm = read_msg(cfb.write_msg(spec), CommsOptions())
    assert pm.html == "<p>Hello <b>there</b>"


def test_large_streams_use_regular_sectors() -> None:
    body = "x" * 9000
    att = cfb.MsgAttachment("big.txt", b"line\n" * 2000, "text/plain")
    pm = read_msg(cfb.write_msg(_spec(strings={0x0037: "Big", 0x1000: body}, attachments=[att])), CommsOptions())
    assert pm.text == body and pm.attachments[0].size == 10000


def test_embedded_messages_nest_to_the_depth_limit() -> None:
    inner = cfb.MsgSpec(strings={0x0037: "Level 3", 0x1000: "deepest"})
    for level in (2, 1):
        inner = cfb.MsgSpec(
            strings={0x0037: f"Level {level}", 0x1000: f"level {level}"},
            attachments=[cfb.MsgAttachment(f"l{level + 1}.msg", embedded=inner)],
        )
    top = _spec(attachments=[cfb.MsgAttachment("l1.msg", embedded=inner)])
    pm = read_msg(cfb.write_msg(top), CommsOptions(max_attachment_depth=2))
    level1 = pm.attachments[0].message
    assert level1 is not None and level1.subject == "Level 1"
    level2 = level1.attachments[0].message
    assert level2 is not None and level2.attachments[0].message is None  # depth 3 > 2: listed, not read


def test_converter_end_to_end_with_children(tmp_path) -> None:
    att = [
        cfb.MsgAttachment("notes.txt", b"Bring waders.\n", "text/plain"),
        cfb.MsgAttachment("in.msg", embedded=cfb.MsgSpec(strings={0x0037: "Inner"})),
    ]
    data = cfb.write_msg(_spec(attachments=att))
    ref = InputRef.from_bytes(data, filename="plan.msg")
    result = convert_ref(ref)
    doc = result.document
    assert result.converter_id == "comms.msg"
    assert dict(table_rows(next(b for b in doc.blocks if isinstance(b, Table))))["Subject"] == "Plan"
    assert [c.metadata.source for c in doc.children] == [
        "plan.msg!attachments/notes.txt",
        "plan.msg!attachments/in.msg",
    ]
    assert doc.metadata.extra["engine"].startswith("olefile")


def test_oversized_attachment_is_listed_not_read() -> None:
    att = cfb.MsgAttachment("big.bin", bytes(6000), "application/octet-stream")
    ref = InputRef.from_bytes(cfb.write_msg(_spec(attachments=[att])), filename="m.msg")
    opts = ConvertOptions(extra={"comms.max_attachment_bytes": 1000})
    doc = convert_ref(ref, opts).document
    assert any(w.kind == WarningKind.ATTACHMENT_SKIPPED and w.detail["reason"] == "too_large" for w in doc.warnings)


def test_not_a_msg_is_refused() -> None:
    with pytest.raises(MsgReadError):
        read_msg(b"short", CommsOptions())
    with pytest.raises(MsgReadError):
        read_msg(cfb.write_cfb({"WordDocument": b"x" * 100}), CommsOptions())
    corrupt = bytearray(cfb.write_msg(_spec()))
    corrupt[48:52] = b"\xff\xff\xff\x7f"  # first directory sector out of range
    ref = InputRef.from_bytes(bytes(corrupt), filename="bad.msg")
    from intomd.detect import detect

    detect(ref)
    with pytest.raises(ConversionError):
        MsgConverter().convert(ref, ConvertOptions())


def test_embedded_message_reports_its_stream_size() -> None:
    inner = cfb.MsgSpec(strings={0x0037: "Inner", 0x1000: "x" * 50})
    pm = read_msg(cfb.write_msg(_spec(attachments=[cfb.MsgAttachment("in.msg", embedded=inner)])), CommsOptions())
    assert pm.attachments[0].size >= 100 + 10  # body (UTF-16) + subject + properties stream
