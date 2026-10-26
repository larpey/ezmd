"""OLE2 containers: libmagic's stream-name verdict beats Magika's guess, a generic container verdict resolves
from the extension, and an Excel binary workbook is told apart from an xlsx by its workbook.bin part."""

from __future__ import annotations

import io
import zipfile

import pytest

from ezmd import detect as d
from ezmd.inputs import InputRef

OLE = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + bytes(504) + b"\x00" * 1024


def _fake_engines(
    monkeypatch: pytest.MonkeyPatch, libmagic: str | None, label: str | None, mime: str | None, score: float
) -> None:
    monkeypatch.setattr(d._Engines, "libmagic", classmethod(lambda cls, sample: libmagic))
    monkeypatch.setattr(d, "_magika_guess", lambda sample: (label, mime, score))


def _detect(data: bytes, name: str) -> d.Detected:
    return d.detect(InputRef.from_bytes(data, filename=name))


def test_generic_container_verdict_resolves_from_the_extension(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_engines(monkeypatch, "application/cdfv2", "ppt", "application/vnd.ms-powerpoint", 0.5)
    assert _detect(OLE, "deck.ppt").mime == "application/vnd.ms-powerpoint"
    _fake_engines(monkeypatch, "application/vnd.ms-office", "unknown", None, 0.3)
    assert _detect(OLE, "mail.msg").mime == "application/vnd.ms-outlook"
    assert _detect(OLE, "diagram.vsd").mime == "application/vnd.visio"
    assert _detect(OLE, "memo.doc").mime == "application/msword"


def test_libmagic_stream_names_beat_a_confident_magika_guess(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_engines(monkeypatch, "application/msword", "xls", "application/vnd.ms-excel", 0.95)
    assert _detect(OLE, "report.doc").mime == "application/msword"
    _fake_engines(monkeypatch, "application/vnd.ms-powerpoint", "doc", "application/msword", 0.99)
    assert _detect(OLE, "slides.unk").mime == "application/vnd.ms-powerpoint"


def test_generic_container_with_no_other_evidence_stays_generic(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_engines(monkeypatch, "application/cdfv2", "unknown", None, 0.2)
    got = _detect(OLE, "blob").mime
    assert got not in ("application/msword", "application/vnd.ms-excel", "application/vnd.ms-powerpoint")


def test_magika_names_the_application_when_libmagic_is_generic(monkeypatch: pytest.MonkeyPatch) -> None:
    _fake_engines(monkeypatch, "application/cdfv2", "xls", "application/vnd.ms-excel", 0.97)
    assert _detect(OLE, "data.unk").mime == "application/vnd.ms-excel"


def _ooxml(names: list[str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        for n in names:
            z.writestr(n, b"x" * 64)
    return buf.getvalue()


def test_binary_workbook_is_not_an_xlsx(monkeypatch: pytest.MonkeyPatch) -> None:
    xlsx_mime = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    _fake_engines(monkeypatch, "application/zip", "xlsx", xlsx_mime, 0.99)
    assert _detect(_ooxml(["xl/workbook.bin", "xl/worksheets/sheet1.bin"]), "book.xlsb").mime == (
        "application/vnd.ms-excel.sheet.binary.macroenabled.12"
    )
    assert _detect(_ooxml(["xl/workbook.xml", "xl/worksheets/sheet1.xml"]), "book.xlsx").mime == xlsx_mime
