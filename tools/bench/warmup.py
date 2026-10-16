"""Warm-up inputs converted once when a worker starts, so model loading and lazy server start-up (Docling
models, MinerU weights, Marker's vLLM container) count toward `startup_seconds`, not the first document.

They are generated here, not taken from any corpus, so no tool can cache a result it is later scored on. The PDF
has a born-digital page and the same page as an image only, so OCR and VLM code paths load too.
"""

from __future__ import annotations

import io
from pathlib import Path

from tools.bench.config import Tool, cache_dir

_LINES = (
    "Warm-up page",
    "This page exists only to load models before measurement starts.",
    "It has a heading, two sentences, and a short list:",
    "1. first item",
    "2. second item",
)
NL = b"\n"


def _stream(dictionary: bytes, data: bytes) -> bytes:
    return dictionary + NL + b"stream" + NL + data + NL + b"endstream"


def _assemble(objects: list[bytes]) -> bytes:
    out = bytearray(b"%PDF-1.4" + NL)
    offsets = []
    for i, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj" % i + NL + body + NL + b"endobj" + NL
    xref = len(out)
    out += b"xref" + NL + b"0 %d" % (len(objects) + 1) + NL + b"0000000000 65535 f " + NL
    for off in offsets:
        out += b"%010d 00000 n " % off + NL
    out += b"trailer" + NL + b"<< /Size %d /Root 1 0 R >>" % (len(objects) + 1) + NL
    out += b"startxref" + NL + b"%d" % xref + NL + b"%%EOF" + NL
    return bytes(out)


def _text_page(contents: int, font: int) -> tuple[bytes, bytes, bytes]:
    """(page, contents stream, font) objects; the latter two must be numbered `contents` and `font`."""
    text = ("BT /F1 14 Tf 72 720 Td 18 TL " + " ".join(f"({line}) '" for line in _LINES) + " ET").encode("latin-1")
    page = b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents %d 0 R " % contents
    page += b"/Resources << /Font << /F1 %d 0 R >> >> >>" % font
    return (
        page,
        _stream(b"<< /Length %d >>" % len(text), text),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    )


def _pdf_bytes() -> bytes:
    """One born-digital page with a text layer."""
    page, contents, font = _text_page(4, 5)
    return _assemble(
        [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>", page, contents, font]
    )


def _jpeg_of_text_page() -> tuple[bytes, int, int]:
    """The text page rendered to a JPEG (pypdfium2 and Pillow are ezmd dependencies in the dev environment)."""
    import pypdfium2

    pdf = pypdfium2.PdfDocument(_pdf_bytes())
    image = pdf[0].render(scale=150 / 72).to_pil().convert("RGB")
    buf = io.BytesIO()
    image.save(buf, format="JPEG", quality=85)
    return buf.getvalue(), image.width, image.height


def _two_page_pdf_bytes() -> bytes:
    jpeg, w, h = _jpeg_of_text_page()
    text_page, contents, font = _text_page(5, 6)
    draw = b"q 612 0 0 792 0 0 cm /Im1 Do Q"
    scan_page = (
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 7 0 R "
        b"/Resources << /XObject << /Im1 8 0 R >> >> >>"
    )
    image = b"<< /Type /XObject /Subtype /Image /Width %d /Height %d /ColorSpace /DeviceRGB " % (w, h)
    image += b"/BitsPerComponent 8 /Filter /DCTDecode /Length %d >>" % len(jpeg)
    return _assemble(
        [
            b"<< /Type /Catalog /Pages 2 0 R >>",  # 1
            b"<< /Type /Pages /Kids [3 0 R 4 0 R] /Count 2 >>",  # 2
            text_page,  # 3
            scan_page,  # 4
            contents,  # 5
            font,  # 6
            _stream(b"<< /Length %d >>" % len(draw), draw),  # 7
            _stream(image, jpeg),  # 8
        ]
    )


def _html() -> str:
    items = "".join(f"<li>{line[3:]}</li>" for line in _LINES[3:])
    body = f"<h1>{_LINES[0]}</h1><p>{_LINES[1]}</p><p>{_LINES[2]}</p><ol>{items}</ol>"
    return f"<!doctype html><html><head><title>Warm-up</title></head><body><article>{body}</article></body></html>"


def warmup_dir() -> Path:
    # Under corpora/ so the Docker workers see it through the read-only corpora mount.
    return cache_dir() / "corpora" / "_warmup"


def warmup_input(tool: Tool) -> Path | None:
    d = warmup_dir()
    d.mkdir(parents=True, exist_ok=True)
    if tool.supports(".pdf"):
        path = d / "warmup.pdf"
        if not path.exists():
            path.write_bytes(_two_page_pdf_bytes())
        return path
    if tool.supports(".html"):
        path = d / "warmup.html"
        if not path.exists():
            path.write_text(_html(), encoding="utf-8")
        return path
    return None
