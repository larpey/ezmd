"""ezmd.core.licensing: one-time license notices for engines installed through non-permissive extras.

docs/spec/part1.md section 2.6: a converter module for a forbidden-license extra calls
`notify_once("<extra>")` on first import. The notice goes to stderr once per machine; a stamp file
in the cache directory records that it was shown.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO


@dataclass(frozen=True, slots=True)
class ExtraLicense:
    extra: str
    license: str
    url: str
    summary: str


KNOWN_EXTRAS: dict[str, ExtraLicense] = {
    "pymupdf": ExtraLicense(
        "pymupdf",
        "AGPL-3.0",
        "https://github.com/pymupdf/PyMuPDF/blob/main/COPYING",
        "Network use of AGPL software can oblige you to publish your source; see the license.",
    ),
    "extract-msg": ExtraLicense(
        "extract-msg",
        "GPL-3.0",
        "https://github.com/TeamMsgExtractor/msg-extractor/blob/master/LICENSE.txt",
        "Distributing software that links GPL code can oblige you to license it under the GPL.",
    ),
    "chandra": ExtraLicense(
        "chandra",
        "OpenRAIL-M",
        "https://huggingface.co/datalab-to/chandra",
        "Model weights carry use-based restrictions; read them before commercial use.",
    ),
    "nonfree": ExtraLicense(
        "nonfree",
        "AGPL-3.0 / GPL-3.0",
        "https://github.com/larpey/ezmd/blob/main/docs/licenses.md",
        "This extra installs copyleft engines; see docs/licenses.md.",
    ),
}


def cache_dir() -> Path:
    base = os.environ.get("EZMD_CACHE_DIR")
    if base:
        return Path(base)
    return Path.home() / ".cache" / "ezmd"


def notify_once(extra: str, *, stream: TextIO | None = None, stamp_dir: Path | None = None) -> bool:
    """Print the license notice for `extra` unless it was already shown on this machine.
    Returns True when the notice was printed."""
    info = KNOWN_EXTRAS.get(extra) or ExtraLicense(extra, "see package metadata", "", "Check the license.")
    d = (stamp_dir or cache_dir()) / "license-notices"
    stamp = d / f"{extra}.shown"
    if stamp.exists():
        return False
    out = stream or sys.stderr
    url = f" {info.url}" if info.url else ""
    out.write(f"ezmd: the '{extra}' extra uses {info.license} software.{url}\n  {info.summary}\n")
    try:
        d.mkdir(parents=True, exist_ok=True)
        stamp.write_text(info.license, encoding="utf-8")
    except OSError:
        pass
    return True
