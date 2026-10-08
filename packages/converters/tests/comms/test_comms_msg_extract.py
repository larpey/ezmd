"""Outlook MSG, extract-msg engine: Unavailable without the nonfree extra; the adapter tested against a stand-in."""

from __future__ import annotations

import sys
import types
from datetime import UTC, datetime

import pytest

from intomd.inputs import Detected, InputRef
from intomd.ir import Table, WarningKind
from intomd.registry import ConversionError, ConvertOptions, Unavailable
from intomd_converters.comms import converters, msg
from intomd_converters.comms.build import table_rows
from intomd_converters.comms.msg import OLE_MAGIC, SUBSTG
from intomd_converters.comms.msg import ExtractMsgConverter as MsgConverter


def test_registered_as_unavailable_without_extract_msg(monkeypatch) -> None:
    monkeypatch.setattr(msg, "extract_msg_available", lambda: False)
    entry = next(c for c in converters() if c.id == "comms.msg_extract")
    assert isinstance(entry, Unavailable)
    assert entry.requires_extras == ("nonfree",)
    assert "GPL" in entry.reason


def test_unavailable_msg_reports_the_extra() -> None:
    from intomd.registry import ConverterRegistry

    reg = ConverterRegistry()
    reg.register(
        Unavailable(
            id="comms.msg", family="comms", reason="needs nonfree", mimes=msg.MSG_MIMES, requires_extras=("nonfree",)
        )
    )
    ref = InputRef.from_bytes(OLE_MAGIC + bytes(600), filename="a.msg")
    ref.detected = Detected(mime="application/vnd.ms-outlook", extension=".msg", confidence=1.0)
    with pytest.raises(ConversionError) as e:
        reg.convert(ref, ConvertOptions())
    assert "intomd[nonfree]" in e.value.user_message


class _Att:
    def __init__(self, name: str, data: object, mimetype: str | None = None, cid: str | None = None) -> None:
        self.longFilename = name
        self.data = data
        self.mimetype = mimetype
        self.cid = cid


class _Msg:
    def __init__(self, subject: str, attachments: list[_Att] | None = None, headers: str = "") -> None:
        self.subject = subject
        self.sender = "Ann Reed <ann@example.org>"
        self.to = "Bob Stone <bob@example.org>"
        self.cc = None
        self.bcc = None
        self.messageId = f"<{subject.lower().replace(' ', '-')}@example.org>"
        self.date = datetime(2024, 10, 1, 9, 0, tzinfo=UTC)
        self.body = f"Body of {subject}.\r\n"
        self.htmlBody = None
        self.headerText = headers
        self.attachments = attachments or []
        self.closed = False

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def fake_extract_msg(monkeypatch, tmp_path):
    monkeypatch.setenv("INTOMD_CACHE_DIR", str(tmp_path))
    mod = types.ModuleType("extract_msg")
    opened: list[_Msg] = []

    def open_msg(path: str, strict: bool = False) -> _Msg:
        inner = _Msg("Inner note", [_Att("deep.txt", b"deep text\n", "text/plain")])
        m = _Msg(
            "Quarterly plan",
            [_Att("plan.txt", b"Plan: count herons.\n", "text/plain"), _Att("", inner)],
            headers="Received: from mx\r\nSubject: Quarterly plan\r\nList-Id: <plans.example.org>\r\n",
        )
        opened.append(m)
        return m

    mod.openMsg = open_msg  # type: ignore[attr-defined]
    mod.__version__ = "0.56.1"  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "extract_msg", mod)
    monkeypatch.delitem(sys.modules, "intomd_converters.comms.msg_engine", raising=False)
    import intomd_converters.comms as package

    monkeypatch.delattr(package, "msg_engine", raising=False)
    return opened


def _ref() -> InputRef:
    ref = InputRef.from_bytes(OLE_MAGIC + bytes(64) + SUBSTG + bytes(600), filename="plan.msg")
    ref.detected = Detected(mime="application/vnd.ms-outlook", extension=".msg", confidence=1.0)
    return ref


def test_msg_adapter_builds_the_shared_layout(fake_extract_msg) -> None:
    conv = MsgConverter()
    ref = _ref()
    assert conv.can_handle(ref) == 0.9  # second to the native reader
    doc = conv.convert(ref, ConvertOptions())
    rows = dict(table_rows(next(b for b in doc.blocks if isinstance(b, Table))))
    assert rows["Subject"] == "Quarterly plan"
    assert rows["From"] == "Ann Reed <ann@example.org>"  # MAPI fills what transport headers lack
    assert rows["List-Id"] == "<plans.example.org>"
    assert rows["Date"] == "2024-10-01T09:00:00+00:00"
    assert doc.metadata.extra["engine"] == "extract-msg 0.56.1"
    titles = [c.metadata.title for c in doc.children]
    assert "Inner note" in titles
    embedded = next(c for c in doc.children if c.metadata.title == "Inner note")
    assert embedded.children and embedded.children[0].metadata.source.endswith("attachments/deep.txt")
    assert fake_extract_msg[0].closed


def test_msg_open_failure_is_a_conversion_error(monkeypatch, fake_extract_msg) -> None:
    def boom(path: str, strict: bool = False) -> None:
        raise OSError("corrupt CFB")

    monkeypatch.setattr(sys.modules["extract_msg"], "openMsg", boom)
    with pytest.raises(ConversionError):
        MsgConverter().convert(_ref(), ConvertOptions())


def test_unreadable_attachment_warns_msg_partial(monkeypatch, fake_extract_msg) -> None:
    def odd(path: str, strict: bool = False) -> _Msg:
        return _Msg("Odd", [_Att("x", 12345)])

    monkeypatch.setattr(sys.modules["extract_msg"], "openMsg", odd)
    doc = MsgConverter().convert(_ref(), ConvertOptions())
    assert any(w.kind == WarningKind.MSG_PARTIAL for w in doc.warnings)


def test_plain_ole_file_is_not_claimed() -> None:
    ref = InputRef.from_bytes(OLE_MAGIC + bytes(2048), filename="book.xls")
    ref.detected = Detected(mime="application/cdfv2", extension=".xls", confidence=1.0)
    assert MsgConverter().can_handle(ref) == 0.0
