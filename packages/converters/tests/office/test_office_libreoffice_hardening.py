"""LibreOffice hardening (D-0056): the throwaway profile never updates links, recalculates, or runs active
content, and a server that requires a sandbox refuses to run soffice without bubblewrap."""

from __future__ import annotations

import http.server
import io
import logging
import threading
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import pytest

from ezmd.core import sandbox
from ezmd.inputs import InputRef
from ezmd.registry import ConversionError, ConvertOptions
from ezmd_converters.office import libreoffice
from ezmd_converters.office.libreoffice import LibreOfficeConverter, find_soffice

OOR = "{http://openoffice.org/2001/registry}"


def _settings() -> dict[str, str]:
    root = ET.fromstring(libreoffice._XCU)
    out = {}
    for item in root.iter("item"):
        prop = item.find("prop")
        assert prop is not None
        value = prop.find("value")
        out[f"{item.get(OOR + 'path')}/{prop.get(OOR + 'name')}"] = "" if value is None else str(value.text)
    return out


def test_profile_never_updates_links_or_recalculates() -> None:
    s = _settings()
    expected = {
        "/org.openoffice.Office.Common/Security/Scripting/MacroSecurityLevel": "3",
        "/org.openoffice.Office.Common/Security/Scripting/DisableMacrosExecution": "true",
        "/org.openoffice.Office.Common/Security/Scripting/BlockUntrustedRefererLinks": "true",
        "/org.openoffice.Office.Common/Security/Scripting/DisableActiveContent": "true",
        "/org.openoffice.Office.Common/Security/Scripting/DisablePythonRuntime": "true",
        # Calc's enumeration: 0 always, 1 never, 2 on request
        "/org.openoffice.Office.Calc/Content/Update/Link": "1",
        # Writer's enumeration: 0 always, 1 on request, 2 never
        "/org.openoffice.Office.Writer/Content/Update/Link": "2",
        "/org.openoffice.Office.Writer/Content/Update/Field": "false",
        "/org.openoffice.Office.Writer/Content/Update/Chart": "false",
        # WEBSERVICE() and other external-data formulas only run on a recalculation
        "/org.openoffice.Office.Calc/Formula/Load/OOXMLRecalcMode": "1",
        "/org.openoffice.Office.Calc/Formula/Load/ODFRecalcMode": "1",
    }
    assert {k: s.get(k) for k in expected} == expected


def _fake_soffice(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> list[object]:
    fake = tmp_path / "soffice"
    fake.write_text("x")
    monkeypatch.setenv("LIBREOFFICE_PATH", str(fake))
    calls: list[object] = []
    monkeypatch.setattr(libreoffice, "_run", lambda *a: calls.append(a) or b"")
    monkeypatch.setattr(libreoffice, "_native", lambda *a: "converted")
    return calls


def _ref() -> InputRef:
    ref = InputRef.from_bytes(b"\xd0\xcf\x11\xe0legacy", filename="old.doc")
    from ezmd.detect import detect

    detect(ref)
    return ref


def test_required_sandbox_without_bwrap_refuses(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls = _fake_soffice(monkeypatch, tmp_path)
    monkeypatch.setattr(sandbox, "bwrap_available", lambda: False)
    opts = ConvertOptions(extra={"office.require_sandbox": True})
    with pytest.raises(ConversionError) as e:
        LibreOfficeConverter().convert(_ref(), opts)
    assert calls == [] and "sandbox" in e.value.user_message and "bubblewrap" in e.value.user_message
    # a configuration problem, not a transient one: a stable code, and no retry or fallback
    assert e.value.code == "sandbox_unavailable" and not e.value.retryable_with_fallback
    assert "EZMD_REQUIRE_SANDBOX" in e.value.user_message


def test_required_sandbox_defaults_on_for_servers(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls = _fake_soffice(monkeypatch, tmp_path)
    monkeypatch.setattr(sandbox, "bwrap_available", lambda: False)
    monkeypatch.setenv("EZMD_REQUIRE_SANDBOX", "1")
    with pytest.raises(ConversionError):
        LibreOfficeConverter().convert(_ref(), ConvertOptions())
    monkeypatch.delenv("EZMD_REQUIRE_SANDBOX")
    monkeypatch.setenv("EZMD_SERVER", "1")
    with pytest.raises(ConversionError):
        LibreOfficeConverter().convert(_ref(), ConvertOptions())
    assert calls == []


def test_unsandboxed_local_run_warns_and_proceeds(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    calls = _fake_soffice(monkeypatch, tmp_path)
    monkeypatch.setattr(sandbox, "bwrap_available", lambda: False)
    monkeypatch.delenv("EZMD_REQUIRE_SANDBOX", raising=False)
    monkeypatch.delenv("EZMD_SERVER", raising=False)
    monkeypatch.setattr(libreoffice, "_warned", False)
    with caplog.at_level(logging.WARNING, logger="ezmd_converters.office.libreoffice"):
        assert LibreOfficeConverter().convert(_ref(), ConvertOptions()) == "converted"
    assert len(calls) == 1
    assert any("without a sandbox" in r.getMessage() for r in caplog.records)


# -- real LibreOffice: a document linking a local file and an http URL ---------------------------


def _linking_odt(secret: Path, url: str) -> bytes:
    content = f"""<?xml version="1.0" encoding="UTF-8"?>
<office:document-content xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0"
 xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0"
 xmlns:draw="urn:oasis:names:tc:opendocument:xmlns:drawing:1.0"
 xmlns:svg="urn:oasis:names:tc:opendocument:xmlns:svg-compatible:1.0"
 xmlns:xlink="http://www.w3.org/1999/xlink" office:version="1.3">
<office:body><office:text>
<text:p>Visible paragraph.</text:p>
<text:section text:name="Linked"><text:section-source xlink:href="{secret.as_uri()}" xlink:type="simple"
 text:filter-name="Text"/><text:p>stale cached text</text:p></text:section>
<text:p><draw:frame draw:name="img" svg:width="1cm" svg:height="1cm"><draw:image xlink:href="{url}"
 xlink:type="simple" xlink:show="embed" xlink:actuate="onLoad"/></draw:frame></text:p>
</office:text></office:body></office:document-content>"""
    manifest = """<?xml version="1.0" encoding="UTF-8"?>
<manifest:manifest xmlns:manifest="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0" manifest:version="1.3">
<manifest:file-entry manifest:full-path="/" manifest:media-type="application/vnd.oasis.opendocument.text"/>
<manifest:file-entry manifest:full-path="content.xml" manifest:media-type="text/xml"/>
</manifest:manifest>"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(zipfile.ZipInfo("mimetype"), "application/vnd.oasis.opendocument.text")
        zf.writestr("META-INF/manifest.xml", manifest, compress_type=zipfile.ZIP_DEFLATED)
        zf.writestr("content.xml", content, compress_type=zipfile.ZIP_DEFLATED)
    return buf.getvalue()


@pytest.mark.slow
@pytest.mark.skipif(find_soffice() is None, reason="needs LibreOffice")
def test_linked_file_and_url_are_not_fetched(tmp_path: Path) -> None:
    hits: list[str] = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            hits.append(self.path)
            self.send_response(404)
            self.end_headers()

        def log_message(self, *_a: object) -> None:
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        secret = tmp_path / "secret.txt"
        secret.write_text("TOP-SECRET-CANARY-7731", encoding="utf-8")
        data = _linking_odt(secret, f"http://127.0.0.1:{server.server_port}/canary.png")
        ref = InputRef.from_bytes(data, filename="links.odt")
        out = libreoffice._run(find_soffice() or "", ref, "docx", 120)
    finally:
        server.shutdown()
    assert hits == [], hits
    with zipfile.ZipFile(io.BytesIO(out)) as zf:
        blob = b"".join(zf.read(n) for n in zf.namelist())
    assert b"TOP-SECRET-CANARY-7731" not in blob
    assert b"Visible paragraph." in blob
