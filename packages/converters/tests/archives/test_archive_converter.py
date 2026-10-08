from __future__ import annotations

import bz2
import io
import lzma
import tarfile
import zipfile

import pytest

from ezmd.detect import detect
from ezmd.inputs import Detected, InputRef
from ezmd.ir import Document, ListBlock, Table, WarningKind
from ezmd.pipeline import convert_ref
from ezmd.registry import ConvertOptions
from ezmd_converters.archives.converter import ArchiveConverter

STAMP = (2024, 1, 1, 0, 0, 0)


def zip_of(members: list[tuple[str, bytes]]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in members:
            zf.writestr(zipfile.ZipInfo(name, date_time=STAMP), data)
    return buf.getvalue()


def tar_of(members: list[tuple[str, bytes]]) -> bytes:
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w") as tf:
        for name, data in members:
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tf.addfile(info, io.BytesIO(data))
    return raw.getvalue()


def run(data: bytes, name: str) -> Document:
    ref = InputRef.from_bytes(data, filename=name)
    try:
        return convert_ref(ref).document
    finally:
        ref.cleanup()


def test_zip_lists_tree_and_table_and_converts_children() -> None:
    doc = run(zip_of([("docs/a.md", b"# Alpha\n\nbody"), ("b.txt", b"plain")]), "bundle.zip")
    assert doc.converter_id == "archives.archive"
    tree = next(b for b in doc.blocks if isinstance(b, ListBlock))
    assert [i.spans[0].text for i in tree.items] == ["docs/", "b.txt"]
    assert tree.items[0].children[0].spans[0].text == "a.md"
    table = next(b for b in doc.blocks if isinstance(b, Table))
    assert table.n_rows == 3 and table.n_cols == 5
    assert [c.metadata.source for c in doc.children] == ["bundle.zip!docs/a.md", "bundle.zip!b.txt"]
    child = doc.children[0]
    assert child.converter_id == "text.markdown_passthrough"
    assert all(b.provenance.source == "bundle.zip!docs/a.md" and b.provenance.path == "docs/a.md" for b in child.blocks)
    assert all(b.provenance.source == "bundle.zip" for b in doc.blocks)


def test_counts_tree_of_nested_members_and_link_targets() -> None:
    import tarfile as tf_mod

    inner = zip_of([("calibration.txt", b"cal")])
    doc = run(zip_of([("logs/", b""), ("logs/old.zip", inner), ("../bad", b"x"), ("a.txt", b"a")]), "c.zip")
    extra = doc.metadata.extra
    assert (extra["archive_files"], extra["archive_directories"], extra["archive_rejected"]) == (2, 1, 1)
    assert extra["archive_entries"] == 4
    tree = next(b for b in doc.blocks if isinstance(b, ListBlock))
    logs = tree.items[0]
    assert logs.spans[0].text == "logs/"
    old = logs.children[0]
    assert old.spans[0].text == "old.zip"
    assert [c.spans[0].text for c in old.children] == ["calibration.txt"]
    summary = doc.blocks[0]
    assert "2 files, 1 directory, 0 links, 0 other entries, 1 rejected" in summary.spans[0].text  # type: ignore[union-attr]

    raw = io.BytesIO()
    with tf_mod.open(fileobj=raw, mode="w") as t:
        link = tf_mod.TarInfo("latest")
        link.type = tf_mod.SYMTYPE
        link.linkname = "data/notes.txt"
        t.addfile(link)
    linked = run(raw.getvalue(), "l.tar")
    table = next(b for b in linked.blocks if isinstance(b, Table))
    status = next(c.spans[0].text for c in table.cells if c.col == 4 and c.row == 1)
    assert "data/notes.txt" in status and "never followed" in status
    assert linked.metadata.extra["archive_links"] == 1


def test_nested_zip_counts_against_parent_budget() -> None:
    inner = zip_of([("x.txt", b"x" * 400)])
    outer = zip_of([("inner.zip", inner), ("y.txt", b"y" * 400)])
    ref = InputRef.from_bytes(outer, filename="o.zip")
    detect(ref)
    cap = len(inner) + 400 + 100
    doc = ArchiveConverter().convert(ref, ConvertOptions(extra={"specialized.archive_max_total": cap}))
    # Declared sizes fit (inner.zip + y.txt), but inner.zip + its x.txt + y.txt do not: the nested
    # archive is charged to the same budget, so y.txt is never extracted.
    assert WarningKind.ARCHIVE_BOMB_SUSPECTED in {w.kind for w in doc.warnings}
    nested = doc.children[0]
    assert nested.metadata.source == "o.zip!inner.zip"
    assert [c.metadata.source for c in nested.children] == ["o.zip!inner.zip!x.txt"]
    assert all(b.provenance.path == "x.txt" for b in nested.children[0].blocks)


@pytest.mark.parametrize(
    ("name", "packer"),
    [
        ("t.tar", lambda b: b),
        ("t.tar.bz2", bz2.compress),
        ("t.tar.xz", lzma.compress),
    ],
)
def test_tar_variants(name: str, packer: object) -> None:
    assert callable(packer)
    doc = run(packer(tar_of([("dir/a.txt", b"alpha text"), ("b.md", b"# B")])), name)
    assert [c.metadata.source for c in doc.children] == [f"{name}!dir/a.txt", f"{name}!b.md"]
    assert str(doc.metadata.extra["archive_format"]).startswith("tar")


def test_single_file_gzip_routes_inner_type() -> None:
    import gzip

    doc = run(gzip.compress(b"# Title\n\ntext", mtime=0), "readme.md.gz")
    assert [c.metadata.source for c in doc.children] == ["readme.md.gz!readme.md"]
    assert doc.children[0].converter_id == "text.markdown_passthrough"


def test_unconvertible_member_is_warned() -> None:
    doc = run(zip_of([("blob.bin", bytes(range(256)) * 4), ("ok.txt", b"fine")]), "m.zip")
    unconverted = next(w for w in doc.warnings if w.kind == WarningKind.ATTACHMENT_UNCONVERTED)
    assert "blob.bin" in unconverted.message


def test_document_zip_extensions_defer_to_their_converters() -> None:
    conv = ArchiveConverter()
    ref = InputRef.from_bytes(b"PK\x03\x04", filename="book.epub")
    ref.detected = Detected(mime="application/zip", extension=".epub", confidence=1.0)
    assert conv.can_handle(ref) < 0.5
    ref2 = InputRef.from_bytes(b"PK\x03\x04", filename="plain.zip")
    ref2.detected = Detected(mime="application/zip", extension=".zip", confidence=1.0)
    assert conv.can_handle(ref2) == 1.0


def test_epub_inside_zip_is_converted_by_the_epub_converter() -> None:
    import importlib.util
    from pathlib import Path

    gen = Path(__file__).resolve().parents[4] / "fixtures" / "ebooks" / "epub3-novel" / "input.epub"
    if not gen.exists() or importlib.util.find_spec("lxml") is None:
        pytest.skip("EPUB fixture not generated")
    doc = run(zip_of([("books/novel.epub", gen.read_bytes())]), "shelf.zip")
    assert doc.children[0].converter_id == "documents.epub"
    assert doc.children[0].metadata.title == "The Lighthouse Keeper"


def test_corrupt_archive_raises_conversion_error() -> None:
    from ezmd.registry import ConversionError

    ref = InputRef.from_bytes(b"PK\x03\x04" + b"\x00" * 40, filename="bad.zip")
    detect(ref)
    with pytest.raises(ConversionError):
        ArchiveConverter().convert(ref, ConvertOptions())


def test_sevenzip_without_extra_reports_extra_required(monkeypatch: pytest.MonkeyPatch) -> None:
    from ezmd_converters.archives import sevenzip

    monkeypatch.setattr(sevenzip, "available", lambda: False)
    ref = InputRef.from_bytes(b"7z\xbc\xaf\x27\x1c" + b"\x00" * 64, filename="x.7z")
    detect(ref)
    doc = ArchiveConverter().convert(ref, ConvertOptions())
    assert WarningKind.EXTRA_REQUIRED in {w.kind for w in doc.warnings}
    assert doc.blocks


def test_invisible_characters_in_member_names_are_removed_and_counted() -> None:
    name = "re" + chr(0x202E) + "port.txt"
    doc = run(zip_of([(name, b"text")]), "n.zip")
    assert [c.metadata.source for c in doc.children] == ["n.zip!report.txt"]
    warn = next(w for w in doc.warnings if w.kind == WarningKind.REMOVED_HIDDEN_ELEMENTS)
    assert warn.detail["invisible_chars"] == 1
