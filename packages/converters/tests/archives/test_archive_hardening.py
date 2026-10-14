"""Red-team budget nits (D-0057): every decompressed byte is counted, zip directories are bounded before
zipfile parses them, every XML-looking part is DOCTYPE-checked, Docling stays offline, and document zips
inside archives share the archive's budget."""

from __future__ import annotations

import importlib.util
import io
import sys
import tarfile
import types
import zipfile
from pathlib import Path
from typing import Any

import pytest

from ezmd.detect import detect
from ezmd.inputs import InputRef
from ezmd.registry import ConversionError, ConvertOptions


def _zip(members: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return buf.getvalue()


def _no_zipfile_parse(monkeypatch: pytest.MonkeyPatch, module: Any) -> None:
    def refuse(*_a: object, **_k: object) -> None:
        raise AssertionError("the central directory was parsed before the entry cap was checked")

    monkeypatch.setattr(module.zipfile, "ZipFile", refuse)


# -- code/archive.py: repository tar and zip readers --------------------------------------------


def test_repo_tar_counts_bytes_of_skipped_members(tmp_path: Path) -> None:
    """tarfile decompresses the data of members it skips (unknown types); those bytes count too."""
    from ezmd_converters.code.archive import ArchiveLimits, read_archive

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        info = tarfile.TarInfo("repo/blob")
        info.type = b"Z"  # not a regular file: skipped, but tarfile still reads past its data
        info.size = 3 * 1024 * 1024
        tf.addfile(info, io.BytesIO(b"\x00" * info.size))
        ok = tarfile.TarInfo("repo/README.md")
        ok.size = 5
        tf.addfile(ok, io.BytesIO(b"hello"))
    path = tmp_path / "repo.tar.gz"
    path.write_bytes(buf.getvalue())
    with pytest.raises(ConversionError, match=r"byte limit|ratio"):
        read_archive(path, ArchiveLimits(max_total_bytes=1024 * 1024))


def test_repo_zip_entry_cap_before_directory_parse(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from ezmd_converters.code import archive

    path = tmp_path / "repo.zip"
    path.write_bytes(_zip({f"r/f{i}.txt": b"x" for i in range(120)}))
    _no_zipfile_parse(monkeypatch, archive)
    monkeypatch.setattr(archive.zipfile, "is_zipfile", lambda _p: True)
    with pytest.raises(ConversionError, match="entries"):
        archive.read_archive(path, archive.ArchiveLimits(max_entries=10))


# -- office/_package.py ----------------------------------------------------------------------------


def test_office_entry_cap_before_directory_parse(monkeypatch: pytest.MonkeyPatch) -> None:
    from ezmd_converters.office import _package

    data = _zip({f"f{i}.xml": b"x" for i in range(_package.MAX_ENTRIES + 1)})
    _no_zipfile_parse(monkeypatch, _package)
    with pytest.raises(ConversionError, match="entries"):
        _package.OfficePackage(data)


def test_forged_entry_count_does_not_hide_a_huge_directory() -> None:
    """The EOCD count can lie; the central-directory size is bounded too."""
    from ezmd_converters.archives.backends import zip_directory_problem

    data = bytearray(_zip({f"f{i}.xml": b"x" for i in range(1000)}))
    eocd = data.rfind(b"PK\x05\x06")
    data[eocd + 8 : eocd + 12] = (1).to_bytes(2, "little") * 2  # claim one entry on disk and in total
    assert zip_directory_problem(io.BytesIO(bytes(data)), max_entries=10) is not None
    assert zip_directory_problem(io.BytesIO(_zip({"a.xml": b"x"})), max_entries=10) is None


_DOCTYPE_PART = b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "boom">]><x>&a;</x>'
_CT = (
    b'<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    b'<Default Extension="xml" ContentType="application/xml"/></Types>'
)


@pytest.mark.parametrize("name", ["customXml/item1.dat", "word/glossary/doc.glossary", "docProps/thumb"])
def test_doctype_check_covers_every_xml_looking_part(name: str) -> None:
    from ezmd_converters.office._package import OfficePackage

    pkg = OfficePackage(_zip({"[Content_Types].xml": _CT, name: b"\xef\xbb\xbf  " + _DOCTYPE_PART}))
    with pytest.raises(ConversionError):
        pkg.sanitized_bytes()


def test_binary_parts_are_not_parsed_as_xml() -> None:
    from ezmd_converters.office._package import OfficePackage

    blob = b"\x89PNG\r\n\x1a\n<!DOCTYPE in binary data"
    pkg = OfficePackage(_zip({"[Content_Types].xml": _CT, "word/media/image1.png": blob}))
    assert pkg.sanitized_bytes()


# -- archives: 7z solid blocks, nested document zips ---------------------------------------------


@pytest.mark.skipif(importlib.util.find_spec("py7zr") is None, reason="needs the 7z extra")
def test_sevenzip_charges_bytes_of_entries_it_does_not_keep() -> None:
    import py7zr

    from ezmd_converters.archives.guard import ArchiveLimits, Budget
    from ezmd_converters.archives.sevenzip import sevenzip_entries

    buf = io.BytesIO()
    with py7zr.SevenZipFile(buf, "w") as z:
        z.writestr(b"\x00" * (1536 * 1024), "big.bin")  # over max_entry: not kept, still decompressed
        z.writestr(b"small", "small.txt")
    raw = buf.getvalue()
    budget = Budget(ArchiveLimits(max_total=2 * 1024 * 1024, max_entry=1024 * 1024, max_ratio=10_000))
    entries, _enc, bomb = sevenzip_entries(io.BytesIO(raw), budget, len(raw), None)
    assert bomb is None and budget.used_bytes >= 1536 * 1024  # before: only the 5 kept bytes were charged
    assert {e.name for e in entries if e.read is not None} == {"small.txt"}


def test_document_zip_in_an_archive_shares_the_archive_budget() -> None:
    from ezmd.ir import WarningKind
    from ezmd_converters.archives.converter import ArchiveConverter

    docx = _zip({"[Content_Types].xml": _CT, "word/document.xml": b"<w/>" + b" " * (900 * 1024)})
    outer = _zip({"report.docx": docx, "notes.txt": b"hello"})
    ref = InputRef.from_bytes(outer, filename="bundle.zip")
    detect(ref)
    opts = ConvertOptions(extra={"specialized.archive_max_total": 600 * 1024})
    doc = ArchiveConverter().convert(ref, opts)
    assert any(w.kind == WarningKind.ARCHIVE_BOMB_SUSPECTED for w in doc.warnings), doc.warnings
    assert not [c for c in doc.children if c.metadata.source and c.metadata.source.endswith("report.docx")]


# -- Docling stays offline ---------------------------------------------------------------------------


def test_docling_forces_hf_offline(monkeypatch: pytest.MonkeyPatch) -> None:
    from ezmd_converters.pdf import doclingengine
    from ezmd_converters.pdf.doclingmodels import ModelsStatus

    monkeypatch.setenv("HF_HUB_OFFLINE", "0")
    constants = types.ModuleType("huggingface_hub.constants")
    constants.HF_HUB_OFFLINE = False  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "huggingface_hub.constants", constants)
    monkeypatch.setattr(doclingengine, "models_status", lambda: ModelsStatus("x", ()))
    seen: dict[str, object] = {}

    def stop(*_a: object) -> None:
        import os

        seen["env"] = os.environ.get("HF_HUB_OFFLINE")
        seen["const"] = constants.HF_HUB_OFFLINE  # type: ignore[attr-defined]
        raise RuntimeError("stop before Docling runs")

    monkeypatch.setattr(doclingengine, "_docling_converter", stop)
    fixtures = Path(__file__).resolve().parents[4] / "fixtures" / "pdf" / "simple-table" / "input.pdf"
    ref = InputRef.from_path(fixtures)
    detect(ref)
    with pytest.raises(RuntimeError, match="stop before"):
        doclingengine.DoclingPdfConverter().convert(ref, ConvertOptions())
    assert seen == {"env": "1", "const": True}
