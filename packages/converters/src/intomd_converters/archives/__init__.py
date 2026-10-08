"""Archives family: zip, tar (plain, gz, bz2, xz), single-file gz/bz2/xz, and 7z via the optional `7z` extra.

Every archive is opened under the part1 8.2 limits in `archives.guard`; members are converted through the
registry and attached as child Documents.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from intomd.registry import Converter, Unavailable

CHAINS: dict[str, list[str]] = {
    "application/x-tar": ["archives.archive"],
    "application/gzip": ["archives.archive"],
    "application/x-gzip": ["archives.archive"],
    "application/x-bzip2": ["archives.archive"],
    "application/x-xz": ["archives.archive"],
    "application/x-7z-compressed": ["archives.archive"],
}
"""`application/zip` has no pinned chain on purpose: DOCX, EPUB, and other zip-based formats are often
detected as plain zip, and their converters must be able to outrank the generic archive converter."""


def converters() -> list[Converter | Unavailable]:
    from intomd.registry import Unavailable
    from intomd_converters.archives import sevenzip
    from intomd_converters.archives.converter import ArchiveConverter

    out: list[Converter | Unavailable] = [ArchiveConverter()]
    if not sevenzip.available():
        out.append(
            Unavailable(
                id="archives.sevenzip",
                family="archives",
                reason="7z archives need py7zr (LGPL-2.1-or-later), installed by the optional 7z extra",
                requires_extras=("7z",),
                mimes=("application/x-7z-compressed",),
            )
        )
    return out
