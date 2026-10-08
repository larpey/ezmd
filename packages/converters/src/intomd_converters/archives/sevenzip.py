"""archives.sevenzip: 7z listing and in-memory extraction through py7zr (LGPL-2.1-or-later, optional `7z` extra).

py7zr is imported lazily and used unmodified as a separately installed package (dynamic use, allowed by
tools/license_allowlist.toml); docs/spec/part2.md section 12 keeps it out of the default install. Every byte
py7zr produces goes through a writer that charges the shared Budget, so the total, per-entry, and
whole-archive ratio caps hold even though 7z solid blocks do not declare per-entry compressed sizes.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime
from typing import IO, Any

from intomd_converters.archives.backends import ArchiveOpenError, Entry, EntryKind
from intomd_converters.archives.guard import BombError, Budget, EntryTooLarge, ratio_exceeded, safe_member_path


def available() -> bool:
    try:
        import py7zr  # type: ignore[import-not-found,unused-ignore]  # noqa: F401
    except ImportError:
        return False
    return True


class _Counter:
    def __init__(self, budget: Budget, archive_size: int) -> None:
        self.budget = budget
        self.archive_size = archive_size
        self.produced = 0

    def add(self, n: int) -> None:
        self.produced += n
        self.budget.charge(n)
        if ratio_exceeded(self.produced, self.archive_size, self.budget.limits.max_ratio):
            self.budget.bombed = self.budget.bombed or "ratio"
            raise BombError("ratio", f"the archive expands more than {self.budget.limits.max_ratio}:1")


def _factory(counter: _Counter, max_entry: int) -> Any:
    from py7zr.io import Py7zIO, WriterFactory  # type: ignore[import-not-found,unused-ignore]

    class Writer(Py7zIO):  # type: ignore[misc,unused-ignore]
        def __init__(self) -> None:
            self.buf = bytearray()

        def write(self, s: bytes | bytearray) -> int:
            self.buf += s
            if len(self.buf) > max_entry:
                raise EntryTooLarge("entry exceeds the per-entry limit")
            counter.add(len(s))
            return len(s)

        def read(self, size: int | None = None) -> bytes:
            return b""

        def seek(self, offset: int, whence: int = 0) -> int:
            return 0

        def flush(self) -> None:
            return None

        def size(self) -> int:
            return len(self.buf)

    class Factory(WriterFactory):  # type: ignore[misc,unused-ignore]
        def __init__(self) -> None:
            self.products: dict[str, Writer] = {}

        def create(self, filename: str) -> Py7zIO:
            w = Writer()
            self.products[filename] = w
            return w

    return Factory()


def sevenzip_entries(
    fp: IO[bytes], budget: Budget, archive_size: int, password: str | None
) -> tuple[list[Entry], bool, str | None]:
    """List every entry and extract the readable ones in one pass. Returns (entries, encrypted, bomb_reason).

    Entries come back with `read` returning the already-extracted bytes. When a cap trips mid-extraction,
    `bomb_reason` is set and no entry is readable.
    """
    import py7zr  # type: ignore[import-not-found,unused-ignore]

    try:
        archive = py7zr.SevenZipFile(fp, mode="r", password=password)
    except py7zr.exceptions.PasswordRequired:
        return [], True, None
    except (py7zr.exceptions.Bad7zFile, py7zr.exceptions.UnsupportedCompressionMethodError, OSError, EOFError) as e:
        raise ArchiveOpenError(str(e)) from e
    with archive:
        encrypted = bool(archive.needs_password()) and not password
        infos = archive.list()
        entries: list[Entry] = []
        targets: list[str] = []
        declared_total = 0
        for info in infos:
            kind: EntryKind = (
                "dir" if info.is_directory else "symlink" if info.is_symlink else "file" if info.is_file else "other"
            )
            modified = info.creationtime if isinstance(info.creationtime, datetime) else None
            entries.append(
                Entry(
                    name=info.filename + ("/" if kind == "dir" else ""),
                    kind=kind,
                    size=int(info.uncompressed) if info.uncompressed is not None else None,
                    compressed=int(info.compressed) if info.compressed else None,
                    modified=modified,
                    encrypted=encrypted,
                )
            )
            path, _reason = safe_member_path(info.filename)
            size = int(info.uncompressed or 0)
            if kind == "file" and path is not None and not encrypted and size <= budget.limits.max_entry:
                targets.append(info.filename)
                declared_total += size
        if encrypted or not targets:
            return entries, encrypted, None
        if declared_total > budget.remaining:
            budget.bombed = budget.bombed or "max_total"
            return entries, encrypted, "max_total"
        counter = _Counter(budget, archive_size)
        factory = _factory(counter, budget.limits.max_entry)
        try:
            archive.extract(targets=targets, factory=factory)
        except BombError as e:
            return entries, encrypted, e.reason
        except EntryTooLarge:
            budget.bombed = budget.bombed or "max_entry"
            return entries, encrypted, "max_entry"
        except (py7zr.exceptions.Bad7zFile, OSError, EOFError, ValueError) as e:
            raise ArchiveOpenError(str(e)) from e
    for entry in entries:
        name = entry.name.rstrip("/")
        product = factory.products.get(name)
        if product is not None:
            data = bytes(product.buf)
            entry.read = _const(data)
    return entries, encrypted, None


def _const(data: bytes) -> Any:
    def read() -> bytes:
        return data

    return read


def iter_entries(entries: list[Entry]) -> Iterator[Entry]:
    yield from entries
