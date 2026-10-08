"""archives.guard: decompression limits shared by the archive converter and zip-based document converters.

Implements docs/spec/part1.md 8.2 (binding): total uncompressed size `EZMD_ARCHIVE_MAX_BYTES` (default
500 MB), at most 10,000 entries, nesting depth 3, a 100:1 per-entry compression-ratio cap that aborts,
no symlinks, absolute paths or `..` components, members streamed into memory instead of extracted to disk,
and nested archives counted against the parent's budget (one `Budget` object is shared down the tree).

Declared sizes lie, so every read goes through `read_member`, which counts the bytes actually produced and
stops one chunk after a cap at the latest.
"""

from __future__ import annotations

import os
import posixpath
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import IO, TYPE_CHECKING

if TYPE_CHECKING:
    from ezmd.registry import ConvertOptions

MB = 1024 * 1024
DEFAULT_MAX_TOTAL = 500 * MB
"""EZMD_ARCHIVE_MAX_BYTES default (part1 8.2)."""
DEFAULT_MAX_ENTRY = 100 * MB
"""Largest single member read into memory; matches InputRef's default `max_bytes`."""
DEFAULT_MAX_ENTRIES = 10_000
DEFAULT_MAX_DEPTH = 3
MAX_RATIO = 100
RATIO_FLOOR = 1 * MB
"""The ratio cap applies once a member has produced more than this many bytes, so a tiny, highly
repetitive text file (a 20 KB log of one repeated line) is not mistaken for a bomb."""
CHUNK = 64 * 1024
LISTING_HARD_CAP_FACTOR = 10
"""A zip whose central directory announces more than factor * max_entries entries is not parsed at all."""

ENV_MAX_BYTES = "EZMD_ARCHIVE_MAX_BYTES"

_DRIVE = re.compile(r"^[A-Za-z]:")


class BombError(Exception):
    """A cap was exceeded while reading; extraction must stop (warning `archive_bomb_suspected`)."""

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


class EntryTooLarge(Exception):
    """One member is bigger than the per-entry cap; it is skipped, the rest of the archive continues."""


@dataclass(frozen=True, slots=True)
class ArchiveLimits:
    max_total: int = DEFAULT_MAX_TOTAL
    max_entry: int = DEFAULT_MAX_ENTRY
    max_entries: int = DEFAULT_MAX_ENTRIES
    max_depth: int = DEFAULT_MAX_DEPTH
    max_ratio: int = MAX_RATIO

    @classmethod
    def from_options(cls, options: ConvertOptions) -> ArchiveLimits:
        """Resolve limits: `options.extra["specialized.archive_*"]` wins, then the converter's bound
        `options.ctx.limits`, then `EZMD_ARCHIVE_MAX_BYTES`, then the part1 8.2 defaults."""
        lim = options.ctx.limits
        total = _env_int(ENV_MAX_BYTES) or lim.max_bytes or DEFAULT_MAX_TOTAL
        entries = lim.max_entries or DEFAULT_MAX_ENTRIES
        depth = lim.max_depth or DEFAULT_MAX_DEPTH
        extra = options.extra
        total = _extra_int(extra, "specialized.archive_max_total", total)
        entry = _extra_int(extra, "specialized.archive_max_entry", min(DEFAULT_MAX_ENTRY, total))
        entries = _extra_int(extra, "specialized.archive_max_entries", entries)
        depth = _extra_int(extra, "specialized.archive_max_depth", depth)
        return cls(max_total=total, max_entry=min(entry, total), max_entries=entries, max_depth=depth)


def _env_int(name: str) -> int | None:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return None
    try:
        value = int(raw)
    except ValueError:
        return None
    return value if value > 0 else None


def _extra_int(extra: dict[str, str | int | float | bool], key: str, default: int) -> int:
    value = extra.get(key)
    if isinstance(value, bool) or value is None:
        return default
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return number if number > 0 else default


@dataclass(slots=True)
class Budget:
    """Bytes and entries consumed so far across an archive and every archive nested in it."""

    limits: ArchiveLimits
    used_bytes: int = 0
    entries: int = 0
    bombed: str | None = None
    """Reason of the first cap hit; once set, nothing else is extracted."""
    notes: list[str] = field(default_factory=list)

    @property
    def remaining(self) -> int:
        return max(0, self.limits.max_total - self.used_bytes)

    def take_entry(self) -> bool:
        """Count one more entry; False once the entry cap is reached."""
        if self.entries >= self.limits.max_entries:
            return False
        self.entries += 1
        return True

    def charge(self, n: int) -> None:
        self.used_bytes += n
        if self.used_bytes > self.limits.max_total:
            self.bombed = self.bombed or "max_total"
            raise BombError(
                "max_total",
                f"the archive expands beyond the {self.limits.max_total} byte limit",
            )


def read_member(
    stream: IO[bytes],
    budget: Budget,
    *,
    compressed_size: int | None,
    declared_size: int | None = None,
) -> bytes:
    """Read one member fully into memory under every cap.

    Raises BombError when the shared total or the per-entry ratio cap is exceeded (abort the archive),
    EntryTooLarge when only this member exceeds the per-entry cap (skip it). Bytes produced are charged to
    the budget as they arrive, so a lying header cannot make us read past a cap by more than one chunk.
    """
    limits = budget.limits
    if declared_size is not None and declared_size > limits.max_entry:
        raise EntryTooLarge(f"declared size {declared_size} exceeds the per-entry limit {limits.max_entry}")
    if declared_size is not None and declared_size > budget.remaining:
        budget.bombed = budget.bombed or "max_total"
        raise BombError("max_total", f"an entry declares {declared_size} bytes; only {budget.remaining} remain")
    out = bytearray()
    while True:
        chunk = stream.read(CHUNK)
        if not chunk:
            break
        out += chunk
        budget.charge(len(chunk))
        if len(out) > limits.max_entry:
            raise EntryTooLarge(f"entry produced more than the per-entry limit of {limits.max_entry} bytes")
        if compressed_size is not None and ratio_exceeded(len(out), compressed_size, limits.max_ratio):
            budget.bombed = budget.bombed or "ratio"
            raise BombError("ratio", f"an entry expands more than {limits.max_ratio}:1")
    return bytes(out)


def ratio_exceeded(produced: int, compressed: int, max_ratio: int) -> bool:
    return produced > RATIO_FLOOR and produced > max_ratio * max(compressed, 1)


class CountingReader:
    """Wraps a decompressing stream (gzip, bz2, xz) and enforces the total and whole-stream ratio caps on the
    bytes it produces. Used for tar streams, where member headers live inside the compressed data."""

    def __init__(self, raw: IO[bytes], budget: Budget, compressed_size: int) -> None:
        self._raw = raw
        self._budget = budget
        self._compressed = compressed_size
        # Tar headers and padding come on top of member bytes; allow a little slack beyond the budget.
        self._cap = budget.remaining + RATIO_FLOOR
        self.produced = 0

    def read(self, n: int = -1) -> bytes:
        size = CHUNK if n is None or n < 0 else min(n, 4 * CHUNK)
        data = self._raw.read(size)
        self.produced += len(data)
        limits = self._budget.limits
        if self.produced > self._cap:
            self._budget.bombed = self._budget.bombed or "max_total"
            raise BombError("max_total", f"the stream expands beyond the {limits.max_total} byte limit")
        if ratio_exceeded(self.produced, self._compressed, limits.max_ratio):
            self._budget.bombed = self._budget.bombed or "ratio"
            raise BombError("ratio", f"the compressed stream expands more than {limits.max_ratio}:1")
        return data

    def readable(self) -> bool:
        return True


def safe_member_path(name: str) -> tuple[str | None, str | None]:
    """Normalize an archive member name. Returns (path, None) for a safe relative path, or (None, reason)
    with reason "absolute" or "traversal". Backslashes count as separators (zip files made on Windows)."""
    cleaned = name.replace("\\", "/")
    if cleaned.startswith("/") or _DRIVE.match(cleaned):
        return None, "absolute"
    parts = [p for p in cleaned.split("/") if p not in ("", ".")]
    if any(p == ".." for p in parts):
        return None, "traversal"
    if not parts:
        return None, "empty"
    return posixpath.join(*parts), None


OpenFn = Callable[[], IO[bytes]]
