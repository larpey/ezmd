"""archives.backends: list and stream members of zip, tar (plain, gz, bz2, xz), and 7z archives.

Every backend yields `Entry` objects in archive order. `Entry.read()` returns the member's bytes through
`guard.read_member` (all caps enforced) and is only valid during that iteration step for streamed tars.
Nothing is ever written to disk.
"""

from __future__ import annotations

import bz2
import gzip
import io
import lzma
import stat
import struct
import tarfile
import zipfile
import zlib
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import IO, Literal, cast

from ezmd_converters.archives.guard import (
    LISTING_HARD_CAP_FACTOR,
    BombError,
    Budget,
    CountingReader,
    EntryTooLarge,
    ratio_exceeded,
    read_member,
)

EntryKind = Literal["file", "dir", "symlink", "hardlink", "device", "other"]
Compression = Literal["gz", "bz2", "xz", "none"]

ZIP_MAGIC = (b"PK\x03\x04", b"PK\x05\x06")
GZIP_MAGIC = b"\x1f\x8b"
BZ2_MAGIC = b"BZh"
XZ_MAGIC = b"\xfd7zXZ\x00"
SEVENZIP_MAGIC = b"7z\xbc\xaf\x27\x1c"


@dataclass(slots=True)
class Entry:
    name: str
    """Raw member name as stored in the archive."""
    kind: EntryKind
    size: int | None
    compressed: int | None
    modified: datetime | None
    encrypted: bool = False
    read: Callable[[], bytes] | None = None
    link_target: str | None = None


class ArchiveOpenError(Exception):
    """The archive is corrupt or not of the expected type."""


def sniff(head: bytes) -> str | None:
    """Archive kind from magic bytes: zip, 7z, gz, bz2, xz, tar, or None."""
    if head.startswith(ZIP_MAGIC):
        return "zip"
    if head.startswith(SEVENZIP_MAGIC):
        return "7z"
    if head.startswith(GZIP_MAGIC):
        return "gz"
    if head.startswith(BZ2_MAGIC):
        return "bz2"
    if head.startswith(XZ_MAGIC):
        return "xz"
    if len(head) >= 262 and head[257:262] == b"ustar":
        return "tar"
    return None


# ---------------------------------------------------------------------------
# zip
# ---------------------------------------------------------------------------


def zip_declared_entries(fp: IO[bytes]) -> int | None:
    """Entry count from the end-of-central-directory record, read without parsing the directory."""
    fp.seek(0, io.SEEK_END)
    size = fp.tell()
    tail_len = min(size, 65_536 + 22)
    fp.seek(size - tail_len)
    tail = fp.read(tail_len)
    pos = tail.rfind(b"PK\x05\x06")
    if pos < 0 or pos + 22 > len(tail):
        return None
    (total,) = struct.unpack("<H", tail[pos + 10 : pos + 12])
    if total == 0xFFFF:
        loc = tail.rfind(b"PK\x06\x06")
        if loc >= 0 and loc + 40 <= len(tail):
            (total64,) = struct.unpack("<Q", tail[loc + 32 : loc + 40])
            return int(total64)
        return None
    return int(total)


def _zip_kind(info: zipfile.ZipInfo) -> EntryKind:
    mode = info.external_attr >> 16
    if mode and stat.S_ISLNK(mode):
        return "symlink"
    if info.is_dir():
        return "dir"
    if mode and (stat.S_ISCHR(mode) or stat.S_ISBLK(mode) or stat.S_ISFIFO(mode) or stat.S_ISSOCK(mode)):
        return "device"
    return "file"


def _zip_time(info: zipfile.ZipInfo) -> datetime | None:
    try:
        return datetime(*info.date_time, tzinfo=UTC)
    except ValueError:
        return None


class ZipBackend:
    """Random-access zip listing. `refused` is set when the declared sizes alone break a cap, in which case
    entries are listed but none is readable."""

    def __init__(self, fp: IO[bytes], budget: Budget, password: str | None = None) -> None:
        self.budget = budget
        self.password = password.encode("utf-8") if password else None
        limits = budget.limits
        declared = zip_declared_entries(fp)
        fp.seek(0)
        if declared is not None and declared > limits.max_entries * LISTING_HARD_CAP_FACTOR:
            budget.bombed = "max_entries"
            raise BombError("max_entries", f"the archive declares {declared} entries")
        try:
            self.zf = zipfile.ZipFile(fp)
        except (zipfile.BadZipFile, zipfile.LargeZipFile, OSError, ValueError, EOFError) as e:
            raise ArchiveOpenError(str(e)) from e
        self.infos = self.zf.infolist()
        self.refused: str | None = None
        files = [i for i in self.infos if not i.is_dir()]
        total = sum(i.file_size for i in files)
        if total > budget.remaining:
            self.refused = "max_total"
        elif any(ratio_exceeded(i.file_size, i.compress_size, limits.max_ratio) for i in files):
            self.refused = "ratio"
        if self.refused:
            budget.bombed = budget.bombed or self.refused

    def names(self) -> list[str]:
        return [i.filename for i in self.infos]

    def entries(self) -> Iterator[Entry]:
        for info in self.infos:
            kind = _zip_kind(info)
            entry = Entry(
                name=info.filename,
                kind=kind,
                size=info.file_size,
                compressed=info.compress_size,
                modified=_zip_time(info),
                encrypted=bool(info.flag_bits & 0x1),
            )
            if kind == "file" and not self.refused:
                entry.read = self._reader(info)
            elif kind == "symlink":
                entry.link_target = self._link_target(info)
            yield entry

    def _link_target(self, info: zipfile.ZipInfo) -> str | None:
        """A zip symlink stores its target as the entry data; read at most 4 KiB of it."""
        if self.refused or info.file_size > 4096 or info.flag_bits & 0x1:
            return None
        try:
            with self.zf.open(info) as f:
                raw = read_member(f, self.budget, compressed_size=info.compress_size, declared_size=info.file_size)
        except (zipfile.BadZipFile, RuntimeError, NotImplementedError, OSError, EOFError, zlib.error, BombError):
            return None
        except EntryTooLarge:
            return None
        return raw.decode("utf-8", errors="replace")

    def _reader(self, info: zipfile.ZipInfo) -> Callable[[], bytes]:
        def read() -> bytes:
            try:
                with self.zf.open(info, pwd=self.password) as f:
                    return read_member(f, self.budget, compressed_size=info.compress_size, declared_size=info.file_size)
            except (
                zipfile.BadZipFile,
                RuntimeError,
                NotImplementedError,
                OSError,
                EOFError,
                lzma.LZMAError,
                zlib.error,
            ) as e:
                raise ArchiveOpenError(f"{info.filename}: {e}") from e

        return read

    def close(self) -> None:
        self.zf.close()


# ---------------------------------------------------------------------------
# tar and single-file compression
# ---------------------------------------------------------------------------


def decompressor(raw: IO[bytes], compression: Compression) -> IO[bytes]:
    if compression == "gz":
        return cast(IO[bytes], gzip.GzipFile(fileobj=raw, mode="rb"))
    if compression == "bz2":
        return bz2.BZ2File(raw, mode="rb")
    if compression == "xz":
        return lzma.LZMAFile(raw, mode="rb")
    return raw


_STREAM_ERRORS = (OSError, EOFError, lzma.LZMAError, zlib.error, tarfile.TarError, ValueError)


def is_tar_stream(open_raw: Callable[[], IO[bytes]], compression: Compression) -> bool:
    """Whether the (decompressed) stream starts with a valid tar header. Reads at most one block."""
    raw = open_raw()
    try:
        head = decompressor(raw, compression).read(512)
    except _STREAM_ERRORS:
        return False
    finally:
        raw.close()
    if len(head) < 512:
        return False
    if head[257:262] == b"ustar":
        return True
    try:
        tarfile.TarInfo.frombuf(head, "utf-8", "surrogateescape")
    except tarfile.TarError:
        return False
    return True


def _tar_kind(m: tarfile.TarInfo) -> EntryKind:
    if m.isreg():
        return "file"
    if m.isdir():
        return "dir"
    if m.issym():
        return "symlink"
    if m.islnk():
        return "hardlink"
    if m.ischr() or m.isblk() or m.isfifo():
        return "device"
    return "other"


def tar_entries(
    open_raw: Callable[[], IO[bytes]], compression: Compression, budget: Budget, compressed_size: int
) -> Iterator[Entry]:
    """Stream a tar (optionally compressed) member by member. Raises BombError from the stream guard."""
    raw = open_raw()
    try:
        counted = CountingReader(decompressor(raw, compression), budget, compressed_size)
        try:
            tf = tarfile.open(fileobj=counted, mode="r|")  # type: ignore[call-overload]  # noqa: SIM115 - closed by `with tf` below
        except tarfile.TarError as e:
            raise ArchiveOpenError(str(e)) from e
        with tf:
            while True:
                try:
                    member = tf.next()
                except BombError:
                    raise
                except _STREAM_ERRORS as e:
                    raise ArchiveOpenError(str(e)) from e
                if member is None:
                    break
                kind = _tar_kind(member)
                entry = Entry(
                    name=member.name + ("/" if kind == "dir" and not member.name.endswith("/") else ""),
                    kind=kind,
                    size=member.size if kind == "file" else None,
                    compressed=None,
                    modified=_tar_time(member),
                    link_target=member.linkname if kind in ("symlink", "hardlink") else None,
                )
                if kind == "file":
                    entry.read = _tar_reader(tf, member, budget)
                yield entry
    finally:
        raw.close()


def _tar_time(m: tarfile.TarInfo) -> datetime | None:
    try:
        return datetime.fromtimestamp(float(m.mtime), tz=UTC) if m.mtime else None
    except (OverflowError, OSError, ValueError):
        return None


def _tar_reader(tf: tarfile.TarFile, member: tarfile.TarInfo, budget: Budget) -> Callable[[], bytes]:
    def read() -> bytes:
        try:
            f = tf.extractfile(member)
        except _STREAM_ERRORS as e:
            raise ArchiveOpenError(f"{member.name}: {e}") from e
        if f is None:
            return b""
        try:
            return read_member(f, budget, compressed_size=None, declared_size=member.size)
        except BombError:
            raise
        except _STREAM_ERRORS as e:
            raise ArchiveOpenError(f"{member.name}: {e}") from e

    return read


def decompress_single(
    open_raw: Callable[[], IO[bytes]], compression: Compression, budget: Budget, compressed_size: int
) -> bytes:
    """Decompress a single-file .gz/.bz2/.xz under the total, entry, and ratio caps."""
    raw = open_raw()
    try:
        stream = decompressor(raw, compression)
        try:
            return read_member(stream, budget, compressed_size=compressed_size)
        except BombError:
            raise
        except _STREAM_ERRORS as e:
            raise ArchiveOpenError(str(e)) from e
    finally:
        raw.close()
