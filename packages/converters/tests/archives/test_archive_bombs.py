"""Archive bomb and unsafe-entry tests (ROADMAP P1-T06 acceptance: "archive bomb tests pass").

Every bomb is built in memory inside the test; nothing large is ever committed.
"""

from __future__ import annotations

import gzip
import io
import tarfile
import zipfile

import pytest

from intomd.detect import detect
from intomd.inputs import InputRef
from intomd.ir import Document, WarningKind
from intomd.registry import ConvertOptions
from intomd_converters.archives.converter import ArchiveConverter
from intomd_converters.archives.guard import CHUNK, RATIO_FLOOR, ArchiveLimits, safe_member_path

MB = 1024 * 1024
STAMP = (2024, 1, 1, 0, 0, 0)


def convert(data: bytes, name: str = "a.zip", **extra: int | str) -> Document:
    ref = InputRef.from_bytes(data, filename=name)
    detect(ref)
    try:
        return ArchiveConverter().convert(ref, ConvertOptions(extra=dict(extra)))
    finally:
        ref.cleanup()


def kinds(doc: Document) -> set[WarningKind]:
    return {w.kind for w in doc.warnings}


def extracted(doc: Document) -> int:
    value = doc.metadata.extra["archive_bytes_extracted"]
    assert isinstance(value, int)
    return value


def zip_of(members: list[tuple[str, bytes]], *, mode: int = 0o100644) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in members:
            info = zipfile.ZipInfo(name, date_time=STAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = mode << 16
            zf.writestr(info, data)
    return buf.getvalue()


def zeros_zip(size: int, name: str = "zeros.bin") -> bytes:
    buf = io.BytesIO()
    block = bytes(MB)
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=1) as zf:
        info = zipfile.ZipInfo(name, date_time=STAMP)
        info.compress_type = zipfile.ZIP_DEFLATED
        with zf.open(info, "w", force_zip64=True) as f:
            for _ in range(size // MB):
                f.write(block)
    return buf.getvalue()


@pytest.mark.slow
def test_one_gigabyte_of_zeros_is_refused_without_extracting() -> None:
    data = zeros_zip(1024 * MB)
    assert len(data) < 8 * MB
    doc = convert(data)
    assert WarningKind.ARCHIVE_BOMB_SUSPECTED in kinds(doc)
    assert extracted(doc) == 0
    assert doc.children == []
    assert doc.blocks, "the listing is still produced"


def test_ratio_bomb_under_the_total_cap_is_refused() -> None:
    doc = convert(zeros_zip(64 * MB))
    bomb = next(w for w in doc.warnings if w.kind == WarningKind.ARCHIVE_BOMB_SUSPECTED)
    assert bomb.detail["reason"] == "ratio"
    assert extracted(doc) == 0


def test_lying_declared_size_cannot_push_past_the_header() -> None:
    data = bytearray(zeros_zip(8 * MB))
    # Shrink the declared uncompressed size in both headers; zipfile stops at the declared size and the
    # CRC check fails, so the entry is reported unreadable and nothing beyond 16 bytes is produced.
    lfh = 0
    cdh = data.find(b"PK\x01\x02")
    for off in (lfh + 22, cdh + 24):
        if data[off : off + 4] == b"\xff\xff\xff\xff":
            continue
        data[off : off + 4] = (16).to_bytes(4, "little")
    doc = convert(bytes(data))
    assert extracted(doc) <= 16 + CHUNK
    assert doc.children == []


def _nested_bomb(levels: int, copies: int, leaf: bytes) -> bytes:
    data = leaf
    for level in range(levels):
        data = zip_of([(f"level{level}-{i}.zip", data) for i in range(copies)])
    return data


def test_small_nested_42zip_style_bomb() -> None:
    leaf = zeros_zip(16 * MB, "leaf.bin")
    bomb = _nested_bomb(5, 4, leaf)
    assert len(bomb) < 2 * MB
    doc = convert(bomb)
    found = kinds(doc)
    assert WarningKind.ARCHIVE_BOMB_SUSPECTED in found or WarningKind.ARCHIVE_TRUNCATED in found
    # Nothing near the 4**5 * 16 MB the bomb would expand to is ever produced.
    assert extracted(doc) < 32 * MB
    assert _child_depth(doc) <= ArchiveLimits().max_depth - 1


def _child_depth(doc: Document) -> int:
    return 1 + max((_child_depth(c) for c in doc.children), default=0) if doc.children else 0


def test_nesting_depth_limit_stops_at_three_levels() -> None:
    data = zip_of([("deep.txt", b"bottom")])
    for level in range(5):
        data = zip_of([(f"n{level}.zip", data), (f"note{level}.txt", f"level {level}".encode())])
    doc = convert(data)
    trunc = [w for w in doc.warnings if w.kind == WarningKind.ARCHIVE_TRUNCATED]
    assert trunc and any(w.detail.get("reason") == "max_depth" for w in trunc)
    assert doc.truncated
    # Top level is depth 1; nested archives open at depths 2 and 3 only.
    archives = [c for c in doc.children if c.converter_id == "archives.archive"]
    assert len(archives) == 1
    second = next(c for c in archives[0].children if c.converter_id == "archives.archive")
    assert not any(c.converter_id == "archives.archive" for c in second.children)
    assert second.metadata.source == "a.zip!n4.zip!n3.zip"


def test_zip_slip_traversal_is_rejected_and_rest_converted() -> None:
    doc = convert(zip_of([("../../evil.txt", b"evil"), ("good.txt", b"good text")]))
    assert WarningKind.ARCHIVE_PATH_REJECTED in kinds(doc)
    assert [c.metadata.source for c in doc.children] == ["a.zip!good.txt"]


@pytest.mark.parametrize("name", ["/etc/passwd", "C:/Windows/evil.txt", "\\\\server\\share\\x.txt", "a\\..\\..\\b.txt"])
def test_absolute_and_backslash_paths_are_rejected(name: str) -> None:
    doc = convert(zip_of([(name, b"evil"), ("ok.txt", b"fine")]))
    assert WarningKind.ARCHIVE_PATH_REJECTED in kinds(doc)
    assert [c.metadata.source for c in doc.children] == ["a.zip!ok.txt"]


def test_safe_member_path_rules() -> None:
    assert safe_member_path("a/./b//c.txt") == ("a/b/c.txt", None)
    assert safe_member_path("../x") == (None, "traversal")
    assert safe_member_path("a/../../x") == (None, "traversal")
    assert safe_member_path("/x") == (None, "absolute")
    assert safe_member_path("D:x") == (None, "absolute")


def _tar(members: list[tarfile.TarInfo], payloads: dict[str, bytes], compress: bool = True) -> bytes:
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w") as tf:
        for m in members:
            body = payloads.get(m.name)
            if body is not None:
                m.size = len(body)
            tf.addfile(m, io.BytesIO(body) if body is not None else None)
    return gzip.compress(raw.getvalue(), mtime=0) if compress else raw.getvalue()


def test_symlink_and_device_in_tar_are_skipped() -> None:
    link = tarfile.TarInfo("passwd")
    link.type = tarfile.SYMTYPE
    link.linkname = "/etc/passwd"
    hard = tarfile.TarInfo("hard")
    hard.type = tarfile.LNKTYPE
    hard.linkname = "../../outside"
    fifo = tarfile.TarInfo("pipe")
    fifo.type = tarfile.FIFOTYPE
    ok = tarfile.TarInfo("ok.txt")
    data = _tar([link, hard, fifo, ok], {"ok.txt": b"plain text"})
    doc = convert(data, "t.tar.gz")
    skipped = next(w for w in doc.warnings if w.kind == WarningKind.ARCHIVE_ENTRY_SKIPPED)
    assert skipped.count == 3
    assert [c.metadata.source for c in doc.children] == ["t.tar.gz!ok.txt"]


def test_symlink_in_zip_is_skipped() -> None:
    data = zip_of([("link", b"/etc/passwd")], mode=0o120777)
    doc = convert(data)
    assert WarningKind.ARCHIVE_ENTRY_SKIPPED in kinds(doc)
    assert doc.children == []


def test_tar_traversal_is_rejected() -> None:
    evil = tarfile.TarInfo("../../etc/evil")
    ok = tarfile.TarInfo("fine.txt")
    doc = convert(_tar([evil, ok], {"../../etc/evil": b"x", "fine.txt": b"fine"}, compress=False), "t.tar")
    assert WarningKind.ARCHIVE_PATH_REJECTED in kinds(doc)
    assert len(doc.children) == 1


def test_too_many_entries_truncates_at_ten_thousand() -> None:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for i in range(10_001):
            zf.writestr(zipfile.ZipInfo(f"d{i:05d}/", date_time=STAMP), b"")
    doc = convert(buf.getvalue())
    trunc = next(w for w in doc.warnings if w.kind == WarningKind.ARCHIVE_TRUNCATED)
    assert trunc.detail["reason"] == "max_entries"
    assert doc.truncated
    assert doc.metadata.extra["archive_entries"] == 10_000


def test_declared_entry_flood_is_refused_before_parsing() -> None:
    data = zip_of([(f"f{i}.txt", b"x") for i in range(50)])
    doc = convert(data, **{"specialized.archive_max_entries": 4})
    assert WarningKind.ARCHIVE_BOMB_SUSPECTED in kinds(doc)
    assert doc.children == []


def _encrypt_flag(data: bytes) -> bytes:
    buf = bytearray(data)
    pos = 0
    while (pos := buf.find(b"PK\x03\x04", pos)) >= 0:
        buf[pos + 6] |= 0x01
        pos += 4
    pos = 0
    while (pos := buf.find(b"PK\x01\x02", pos)) >= 0:
        buf[pos + 8] |= 0x01
        pos += 4
    return bytes(buf)


def test_encrypted_zip_is_listed_not_extracted() -> None:
    data = _encrypt_flag(zip_of([("secret.txt", b"classified"), ("plan.md", b"# Plan")]))
    doc = convert(data)
    enc = next(w for w in doc.warnings if w.kind == WarningKind.ARCHIVE_ENCRYPTED)
    assert enc.count == 2
    assert doc.children == []
    assert extracted(doc) == 0
    table = next(b for b in doc.blocks if b.type == "table")
    assert "encrypted" in [c.spans[0].text for c in table.cells if c.col == 4 and c.spans]


def test_tar_gz_stream_bomb_stops_at_the_total_cap() -> None:
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w") as tf:
        for i in range(3):
            info = tarfile.TarInfo(f"big{i}.bin")
            info.size = 12 * MB
            tf.addfile(info, io.BytesIO(bytes(12 * MB)))
    data = gzip.compress(raw.getvalue(), compresslevel=1, mtime=0)
    cap = 20 * MB
    doc = convert(data, "b.tar.gz", **{"specialized.archive_max_total": cap})
    assert WarningKind.ARCHIVE_BOMB_SUSPECTED in kinds(doc)
    assert extracted(doc) <= cap + CHUNK


def test_single_gzip_of_zeros_trips_the_ratio_cap_while_streaming() -> None:
    data = gzip.compress(bytes(48 * MB), compresslevel=1, mtime=0)
    doc = convert(data, "zeros.gz")
    bomb = next(w for w in doc.warnings if w.kind == WarningKind.ARCHIVE_BOMB_SUSPECTED)
    assert bomb.detail["reason"] == "ratio"
    # Stops one chunk after crossing 100x the compressed size, far short of the 48 MB payload.
    assert extracted(doc) <= max(RATIO_FLOOR, 100 * len(data)) + CHUNK
    assert extracted(doc) < 48 * MB // 2
    assert doc.children == []


def test_env_var_sets_the_total_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTOMD_ARCHIVE_MAX_BYTES", "1000")
    doc = convert(zip_of([("a.txt", b"a" * 600), ("b.txt", b"b" * 600)]))
    assert WarningKind.ARCHIVE_BOMB_SUSPECTED in kinds(doc)
    assert ArchiveLimits.from_options(ConvertOptions()).max_total == 1000


def test_sevenzip_bomb_and_listing() -> None:
    py7zr = pytest.importorskip("py7zr")
    buf = io.BytesIO()
    with py7zr.SevenZipFile(buf, "w") as z:
        z.writestr(b"# Seven\n\nzip text\n", "doc.md")
        z.writestr(bytes(8 * MB), "zeros.bin")
    doc = convert(buf.getvalue(), "s.7z")
    assert WarningKind.ARCHIVE_BOMB_SUSPECTED in kinds(doc)
    assert extracted(doc) <= RATIO_FLOOR + 8 * MB
    small = io.BytesIO()
    with py7zr.SevenZipFile(small, "w") as z:
        z.writestr(b"# Seven\n\nzip text\n", "doc.md")
    ok = convert(small.getvalue(), "s.7z")
    assert [c.metadata.source for c in ok.children] == ["s.7z!doc.md"]
