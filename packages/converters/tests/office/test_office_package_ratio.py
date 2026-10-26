"""The package guard's compression-ratio rule: real parts compress far past 100:1."""

from __future__ import annotations

import io
import zipfile

import pytest

from ezmd.registry import ConversionError
from ezmd_converters.office import _package
from ezmd_converters.office._package import OfficePackage


def _zip(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for name, data in files.items():
            z.writestr(name, data)
    return buf.getvalue()


def _ratio(data: bytes, name: str) -> float:
    info = zipfile.ZipFile(io.BytesIO(data)).getinfo(name)
    return info.file_size / max(info.compress_size, 1)


def test_repetitive_document_xml_over_100_to_1_is_accepted() -> None:
    """A slide or sheet XML of thousands of near-identical elements: real files from the 2026-10-26 corpus runs
    compressed between 100:1 and 300:1 and were refused as bombs under the old 100:1 rule."""
    body = b"".join(b"<w:p><w:r><w:rPr><w:b/></w:rPr><w:t>Item %d</w:t></w:r></w:p>" % (i % 50) for i in range(60_000))
    assert len(body) > 2 * _package.RATIO_MIN_BYTES
    data = _zip({"[Content_Types].xml": b"<Types/>", "word/document.xml": body})
    ratio = _ratio(data, "word/document.xml")
    assert 100 < ratio < _package.MAX_RATIO, ratio
    OfficePackage(data)  # accepted


def test_a_repetitive_vector_image_is_accepted() -> None:
    """EMF metafiles of repeated records reached 730:1 in real decks."""
    record = b"\x01\x00\x00\x00\x2c\x00\x00\x00" + bytes(range(36))
    body = record * 60_000
    data = _zip({"[Content_Types].xml": b"<Types/>", "ppt/media/image1.emf": body})
    ratio = _ratio(data, "ppt/media/image1.emf")
    assert 100 < ratio < _package.MAX_RATIO, ratio
    OfficePackage(data)


def test_a_run_of_one_byte_is_still_a_bomb() -> None:
    for name in ("word/media/image1.png", "word/document.xml"):
        data = _zip({"[Content_Types].xml": b"<Types/>", name: b"\x00" * (8 * 1024 * 1024)})
        assert _ratio(data, name) > _package.MAX_RATIO
        with pytest.raises(ConversionError, match="compression ratio"):
            OfficePackage(data)
