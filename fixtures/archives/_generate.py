"""Generate the archive fixtures (self-authored text, CC0). Run: uv run python fixtures/archives/_generate.py

Deterministic: fixed zip timestamps, tar mtimes, and gzip header mtime 0. Bomb archives are never committed;
the bomb tests in packages/converters/tests/archives/ build them in memory.
"""

from __future__ import annotations

import gzip
import io
import tarfile
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
STAMP = (2024, 5, 1, 12, 0, 0)
MTIME = 1714564800  # 2024-05-01 12:00:00 UTC
NL = chr(10)


def zip_bytes(members: list[tuple[str, bytes | None]]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, data in members:
            info = zipfile.ZipInfo(name, date_time=STAMP)
            if data is None:
                info.external_attr = (0o40755 << 16) | 0x10
                zf.writestr(info, b"")
                continue
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            zf.writestr(info, data)
    return buf.getvalue()


def write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


README = (
    "# Survey Kit"
    + NL
    + NL
    + "This archive holds the field survey kit."
    + NL
    + NL
    + "- `notes.txt`: raw notes"
    + NL
    + "- `docs/method.md`: the method"
    + NL
).encode()
NOTES = ("Tuesday: 14 herons at the east marsh." + NL + NL + "Wednesday: fog, no count." + NL).encode()
METHOD = (
    "# Method"
    + NL
    + NL
    + "## Counting"
    + NL
    + NL
    + "Count from the same hide every morning."
    + NL
    + NL
    + "| Step | Action |"
    + NL
    + "|---|---|"
    + NL
    + "| 1 | Arrive before dawn |"
    + NL
    + "| 2 | Count for 20 minutes |"
    + NL
).encode()
INNER = ("Calibration log: binoculars checked on 2024-04-30." + NL).encode()


def zip_mixed() -> None:
    nested = zip_bytes([("calibration.txt", INNER)])
    data = zip_bytes(
        [
            ("README.md", README),
            ("notes.txt", NOTES),
            ("docs/", None),
            ("docs/method.md", METHOD),
            ("extras/archive-of-logs.zip", nested),
        ]
    )
    write(HERE / "zip-mixed" / "input.zip", data)


def tar_gz() -> None:
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w", format=tarfile.PAX_FORMAT) as tf:
        for name, payload in (("kit/README.md", README), ("kit/data/notes.txt", NOTES)):
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            info.mtime = MTIME
            info.mode = 0o644
            info.uname = info.gname = ""
            tf.addfile(info, io.BytesIO(payload))
        link = tarfile.TarInfo("kit/latest.txt")
        link.type = tarfile.SYMTYPE
        link.linkname = "data/notes.txt"
        link.mtime = MTIME
        tf.addfile(link)
    out = io.BytesIO()
    with gzip.GzipFile(fileobj=out, mode="wb", mtime=0, filename="") as gz:
        gz.write(raw.getvalue())
    write(HERE / "tar-gz" / "input.tar.gz", out.getvalue())


def zip_slip() -> None:
    data = zip_bytes(
        [
            ("ok.txt", ("This file is safe and should be converted." + NL).encode()),
            ("../../evil.txt", b"overwrite attempt" + NL.encode()),
            ("/etc/cron.d/evil", b"absolute path attempt" + NL.encode()),
            ("sub/../../escape.txt", b"normalized traversal attempt" + NL.encode()),
        ]
    )
    write(HERE / "zip-slip" / "input.zip", data)


def sevenzip() -> None:
    """Needs py7zr: `uv run --with py7zr python fixtures/archives/_generate.py`. Skipped without it."""
    try:
        import py7zr
    except ImportError:
        print("py7zr not installed; sevenzip fixture not regenerated")
        return
    import os
    import tempfile

    out = HERE / "sevenzip" / "input.7z"
    out.parent.mkdir(parents=True, exist_ok=True)
    buf = io.BytesIO()
    # py7zr stamps writestr() members with the current time; write from files whose mtime is pinned so the
    # golden does not depend on when or in which timezone it was generated.
    with tempfile.TemporaryDirectory() as tmp, py7zr.SevenZipFile(buf, "w") as z:
        for name, payload in (("kit/README.md", README), ("kit/notes.txt", NOTES)):
            src = Path(tmp) / name.replace("/", "_")
            src.write_bytes(payload)
            os.utime(src, (MTIME, MTIME))
            z.write(src, name)
    out.write_bytes(buf.getvalue())


if __name__ == "__main__":
    zip_mixed()
    tar_gz()
    zip_slip()
    sevenzip()
