from __future__ import annotations

import io
import os
import time
import zipfile
from pathlib import Path

import pytest

from intomd.detect import EMPTY_MIME, OCTET, URI_MIME, detect, extension_mime, is_executable, normalize_mime
from intomd.inputs import InputRef

PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d4944415478da63f8ff"
    "ff3f0005fe02fea7d6a4c90000000049454e44ae426082"
)
PY = (
    b"#!/usr/bin/env python3\nimport os\n\n\ndef main() -> None:\n    print(os.getcwd())\n\n\n"
    b"if __name__ == '__main__':\n    main()\n"
)


def _docx() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.'
            'wordprocessingml.document.main+xml"/></Types>',
        )
        z.writestr("_rels/.rels", '<?xml version="1.0"?><Relationships/>')
        z.writestr("word/document.xml", '<?xml version="1.0"?><w:document xmlns:w="x"><w:body/></w:document>')
    return buf.getvalue()


def _zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("a.txt", "hello " * 100)
    return buf.getvalue()


MP3 = b"ID3\x04\x00\x00\x00\x00\x00\x00" + bytes([0xFF, 0xFB, 0x90, 0x64]) + b"\x00" * 400
CASES: list[tuple[str, bytes, set[str]]] = [
    (
        "a.txt",
        b"The quick brown fox jumps over the lazy dog.\nSecond line of plain prose text here.\n" * 5,
        {"text/plain"},
    ),
    (
        "a.md",
        b"# Title\n\nSome *markdown* text with a [link](https://example.org).\n\n- item one\n- item two\n",
        {"text/markdown"},
    ),
    ("a.csv", b"name,qty,price\napple,3,1.20\npear,5,0.80\nplum,9,2.10\nfig,1,3.00\n", {"text/csv"}),
    ("a.json", b'{"name": "intomd", "items": [1, 2, 3], "nested": {"ok": true, "v": null}}\n', {"application/json"}),
    ("a.html", b"<!DOCTYPE html><html><head><title>T</title></head><body><p>Hello</p></body></html>\n", {"text/html"}),
    ("a.pdf", b"%PDF-1.7\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n" * 3 + b"%%EOF\n", {"application/pdf"}),
    ("a.zip", _zip(), {"application/zip"}),
    ("a.png", PNG, {"image/png"}),
    ("a.mp3", MP3, {"audio/mpeg"}),
    ("a.docx", _docx(), {"application/vnd.openxmlformats-officedocument.wordprocessingml.document", "application/zip"}),
    ("empty.txt", b"", {EMPTY_MIME}),
    ("noise.bin", os.urandom(4096), {OCTET}),
    ("script.png", PY, {"text/x-python"}),
    ("image.py", PNG, {"image/png"}),
    ("a.yaml", b"name: intomd\nversion: 1\nitems:\n  - a\n  - b\nnested:\n  key: value\n", {"application/yaml"}),
    (
        "a.xml",
        b'<?xml version="1.0" encoding="UTF-8"?>\n<root><item id="1">a</item><item id="2">b</item></root>\n',
        {"application/xml"},
    ),
    ("noext", b"Just some plain words written without any file extension at all, several lines.\n" * 4, {"text/plain"}),
    ("a.toml", b'[project]\nname = "intomd"\nversion = "0.1.0"\n\n[tool.x]\nkey = true\n', {"application/toml"}),
    (
        "a.svg",
        b'<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><rect width="10" height="10"/></svg>\n',
        {"image/svg+xml"},
    ),
    ("a.py", PY, {"text/x-python"}),
]


@pytest.mark.parametrize(("name", "data", "expected"), CASES, ids=[c[0] for c in CASES])
def test_detection_table(name: str, data: bytes, expected: set[str]) -> None:
    r = InputRef.from_bytes(data, filename=name)
    d = detect(r)
    assert d.mime in expected, d
    assert r.detected is d


def test_rename_cases_resolve_by_content(tmp_path: Path) -> None:
    p = tmp_path / "script.png"
    p.write_bytes(PY)
    assert detect(InputRef.from_path(p)).mime == "text/x-python"


def test_url_without_body() -> None:
    assert detect(InputRef.from_url("https://example.org/a.pdf")).mime == URI_MIME


def test_helpers() -> None:
    assert normalize_mime("Text/X-Markdown; charset=utf-8") == "text/markdown"
    assert extension_mime("x.DOCX") is not None
    assert extension_mime("noext") is None
    assert is_executable("application/x-dosexec") and not is_executable("text/plain")


def test_executables_detected() -> None:
    elf = b"\x7fELF\x02\x01\x01\x00" + b"\x00" * 8 + b"\x02\x00\x3e\x00" + b"\x00" * 200
    pe = b"MZ" + b"\x90\x00" * 29 + b"\x80\x00\x00\x00" + b"\x00" * 64 + b"PE\x00\x00" + b"\x00" * 200
    assert is_executable(detect(InputRef.from_bytes(elf, filename="a.txt")).mime)
    assert is_executable(detect(InputRef.from_bytes(pe, filename="a.txt")).mime)


def test_large_file_is_fast(tmp_path: Path) -> None:
    p = tmp_path / "big.txt"
    p.write_bytes(b"lorem ipsum dolor sit amet " * (10 * 1024 * 1024 // 27))
    detect(InputRef.from_path(p, max_bytes=50 * 1024 * 1024))  # warm up model load
    t0 = time.perf_counter()
    d = detect(InputRef.from_path(p, max_bytes=50 * 1024 * 1024))
    elapsed = time.perf_counter() - t0
    assert d.mime == "text/plain"
    if not os.environ.get("CI"):
        assert elapsed < 0.2, elapsed
