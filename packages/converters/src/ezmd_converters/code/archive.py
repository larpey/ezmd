"""Minimal safe reader for repository archives (zip and tar.gz) with the docs/spec/part1.md 8.2 limits.

Members are streamed into memory (never extracted to disk). Enforced: total uncompressed size
(`EZMD_ARCHIVE_MAX_BYTES`, default 500 MB), 10,000 entries, a 100:1 compression ratio per zip entry and for a
whole gzip stream (abort), no symlinks, hard links, devices, absolute paths, drive letters, or `..` components
(skipped with `archive_entry_skipped`), and encrypted zip entries are skipped (`archive_encrypted`). Nested
archives are never opened: the repo packer treats them as binary members.
"""

from __future__ import annotations

import os
import stat
import tarfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from ezmd.registry import ConversionError

__all__ = ["ArchiveLimits", "Member", "ReadResult", "read_archive"]

MAX_RATIO = 100
DEFAULT_MAX_TOTAL = 500 * 1024 * 1024
MAX_ENTRIES = 10_000


@dataclass(frozen=True, slots=True)
class ArchiveLimits:
    max_total_bytes: int = DEFAULT_MAX_TOTAL
    max_entries: int = MAX_ENTRIES
    max_member_bytes: int = 512 * 1024
    """Members above this are listed (size only) but their bytes are not read."""

    @classmethod
    def from_env(cls, max_member_bytes: int) -> ArchiveLimits:
        raw = os.environ.get("EZMD_ARCHIVE_MAX_BYTES", "")
        total = int(raw) if raw.isdigit() else DEFAULT_MAX_TOTAL
        return cls(max_total_bytes=total, max_member_bytes=max_member_bytes)


@dataclass(slots=True)
class Member:
    path: str
    """Normalized POSIX path relative to the repository root."""
    size: int
    data: bytes | None
    """None when the member exceeded `max_member_bytes` and was not read."""


@dataclass(slots=True)
class ReadResult:
    members: list[Member] = field(default_factory=list)
    skipped_unsafe: list[str] = field(default_factory=list)
    skipped_links: int = 0
    encrypted: int = 0
    truncated: bool = False
    commit: str | None = None
    root_name: str | None = None


def _bomb(msg: str) -> ConversionError:
    return ConversionError(
        msg,
        user_message="The archive expands beyond safe limits and was refused.",
        retryable_with_fallback=False,
    )


def safe_path(name: str) -> str | None:
    """Normalized relative POSIX path, or None when the name is absolute or escapes the root."""
    raw = name.replace("\\", "/")
    if raw.startswith("/") or (len(raw) > 1 and raw[1] == ":"):
        return None
    parts = [p for p in PurePosixPath(raw).parts if p not in ("", ".")]
    if not parts or any(p == ".." for p in parts):
        return None
    if any(ord(ch) < 32 for p in parts for ch in p):
        return None
    return "/".join(parts)


def read_archive(path: Path, limits: ArchiveLimits) -> ReadResult:
    result = _read_zip(path, limits) if zipfile.is_zipfile(path) else _read_tar(path, limits)
    _strip_common_root(result)
    return result


def _read_zip(path: Path, limits: ArchiveLimits) -> ReadResult:
    out = ReadResult()
    total = 0
    try:
        zf = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, OSError) as e:
        raise ConversionError(f"bad zip: {e}", user_message="The archive could not be read.") from e
    with zf:
        infos = zf.infolist()
        if len(infos) > limits.max_entries:
            out.truncated = True
            infos = infos[: limits.max_entries]
        for info in infos:
            if info.is_dir():
                continue
            mode = info.external_attr >> 16
            if stat.S_ISLNK(mode):
                out.skipped_links += 1
                continue
            rel = safe_path(info.filename)
            if rel is None:
                out.skipped_unsafe.append(info.filename[:200])
                continue
            if info.flag_bits & 0x1:
                out.encrypted += 1
                continue
            if info.file_size > MAX_RATIO * max(info.compress_size, 1) and info.file_size > 1024:
                raise _bomb(f"zip entry ratio exceeds {MAX_RATIO}:1")
            total += info.file_size
            if total > limits.max_total_bytes:
                raise _bomb("zip expands beyond the archive byte limit")
            data: bytes | None = None
            if info.file_size <= limits.max_member_bytes:
                try:
                    with zf.open(info) as f:
                        data = f.read(limits.max_member_bytes + 1)
                except (zipfile.BadZipFile, OSError, EOFError, ValueError):
                    out.skipped_unsafe.append(rel)
                    continue
                if len(data) > limits.max_member_bytes:
                    raise _bomb("zip entry is larger than its declared size")
            out.members.append(Member(path=rel, size=info.file_size, data=data))
    return out


def _read_tar(path: Path, limits: ArchiveLimits) -> ReadResult:
    out = ReadResult()
    compressed = max(path.stat().st_size, 1)
    total = 0
    count = 0
    try:
        tf = tarfile.open(path, mode="r:*")  # noqa: SIM115 - closed by the `with` below; open errors map here
    except (tarfile.TarError, OSError, EOFError) as e:
        raise ConversionError(f"bad tar: {e}", user_message="The archive could not be read.") from e
    with tf:
        try:
            for info in tf:
                count += 1
                if count > limits.max_entries:
                    out.truncated = True
                    break
                if info.isdir():
                    continue
                if info.issym() or info.islnk():
                    out.skipped_links += 1
                    continue
                if not info.isfile():
                    continue  # devices, fifos
                rel = safe_path(info.name)
                if rel is None:
                    out.skipped_unsafe.append(info.name[:200])
                    continue
                total += info.size
                if total > limits.max_total_bytes:
                    raise _bomb("tar expands beyond the archive byte limit")
                if total > MAX_RATIO * compressed and total > 1024 * 1024:
                    raise _bomb(f"tar stream ratio exceeds {MAX_RATIO}:1")
                data: bytes | None = None
                if info.size <= limits.max_member_bytes:
                    f = tf.extractfile(info)
                    data = f.read(limits.max_member_bytes + 1) if f is not None else None
                out.members.append(Member(path=rel, size=info.size, data=data))
        except (tarfile.TarError, OSError, EOFError) as e:
            if not out.members:
                raise ConversionError(f"bad tar: {e}", user_message="The archive could not be read.") from e
            out.truncated = True
        comment = tf.pax_headers.get("comment") if tf.pax_headers else None
        if isinstance(comment, str) and len(comment) == 40 and all(c in "0123456789abcdef" for c in comment):
            out.commit = comment
    return out


def _strip_common_root(result: ReadResult) -> None:
    """GitHub tarballs and zips wrap everything in one `<repo>-<ref>/` directory; drop it."""
    if not result.members:
        return
    firsts = {m.path.split("/", 1)[0] for m in result.members}
    if len(firsts) != 1 or any("/" not in m.path for m in result.members):
        return
    result.root_name = firsts.pop()
    result.members = [Member(path=m.path.split("/", 1)[1], size=m.size, data=m.data) for m in result.members]
