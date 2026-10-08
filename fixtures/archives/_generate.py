"""Generate the archive fixtures (self-authored text, CC0). Run: uv run python fixtures/archives/_generate.py

Deterministic: fixed zip timestamps, tar mtimes, and gzip header mtime 0. Large bomb archives are never
committed (zip-bomb-ratio is about 2 KB on disk); the bomb tests in packages/converters/tests/archives/
build them in memory.
"""

from __future__ import annotations

import gzip
import io
import struct
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


def tar_gz_bytes(members: list[tuple[str, bytes]]) -> bytes:
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w", format=tarfile.PAX_FORMAT) as tf:
        for name, payload in members:
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            info.mtime = MTIME
            info.mode = 0o644
            info.uname = info.gname = ""
            tf.addfile(info, io.BytesIO(payload))
    out = io.BytesIO()
    with gzip.GzipFile(fileobj=out, mode="wb", mtime=0, filename="") as gz:
        gz.write(raw.getvalue())
    return out.getvalue()


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def minimal_docx(paragraphs: list[tuple[str | None, str]]) -> bytes:
    """A hand-built WordprocessingML package: [(style id or None, text)]; Heading1 is a built-in style id."""
    body = "".join(
        "<w:p>"
        + (f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else "")
        + f"<w:r><w:t>{text}</w:t></w:r></w:p>"
        for style, text in paragraphs
    )
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        + f'<w:document xmlns:w="{W_NS}"><w:body>{body}</w:body></w:document>'
    )
    styles = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        + f'<w:styles xmlns:w="{W_NS}">'
        + '<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/>'
        + '<w:pPr><w:outlineLvl w:val="0"/></w:pPr></w:style></w:styles>'
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        + '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        + '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        + '<Default Extension="xml" ContentType="application/xml"/>'
        + '<Override PartName="/word/document.xml" '
        + 'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
        + '<Override PartName="/word/styles.xml" '
        + 'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
        + "</Types>"
    )
    rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        + '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        + '<Relationship Id="rId1" '
        + 'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        + 'Target="word/document.xml"/></Relationships>'
    )
    doc_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        + '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        + '<Relationship Id="rId1" '
        + 'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" '
        + 'Target="styles.xml"/></Relationships>'
    )
    return zip_bytes(
        [
            ("[Content_Types].xml", content_types.encode()),
            ("_rels/.rels", rels.encode()),
            ("word/document.xml", document.encode()),
            ("word/_rels/document.xml.rels", doc_rels.encode()),
            ("word/styles.xml", styles.encode()),
        ]
    )


LOCAL_SIG = struct.pack("<I", 0x04034B50)
CENTRAL_SIG = struct.pack("<I", 0x02014B50)


def mark_encrypted(data: bytes, name: str) -> bytes:
    """Set general-purpose bit 0 (traditional PKWARE encryption) on one member's local and central headers.
    The payload stays plain deflate: the converter must list the entry as encrypted and never read it."""
    buf = bytearray(data)
    target = name.encode()
    for sig, flag_off, name_off in ((LOCAL_SIG, 6, 30), (CENTRAL_SIG, 8, 46)):
        pos = buf.find(sig)
        while pos != -1:
            n = struct.unpack_from("<H", buf, pos + (26 if sig == LOCAL_SIG else 28))[0]
            if bytes(buf[pos + name_off : pos + name_off + n]) == target:
                flags = struct.unpack_from("<H", buf, pos + flag_off)[0]
                struct.pack_into("<H", buf, pos + flag_off, flags | 0x1)
            pos = buf.find(sig, pos + 4)
    return bytes(buf)


SITES_CSV = ("site,herons,egrets" + NL + "east marsh,14,3" + NL + "west reed bed,6,9" + NL).encode()


def zip_nested_mixed() -> None:
    report = minimal_docx(
        [
            ("Heading1", "Season Report"),
            (None, "Heron numbers rose at the east marsh for the third year."),
            (None, "The west reed bed was flooded in April."),
        ]
    )
    inner = tar_gz_bytes([("season/report.docx", report), ("season/sites.csv", SITES_CSV)])
    data = zip_bytes(
        [
            ("README.txt", ("Season bundle: the tarball holds the report and the site table." + NL).encode()),
            ("bundle/season.tar.gz", inner),
            ("private/ringing-permits.txt", ("Permit numbers are not for publication." + NL).encode()),
        ]
    )
    write(HERE / "zip-nested-mixed" / "input.zip", mark_encrypted(data, "private/ringing-permits.txt"))


def zip_bomb_ratio() -> None:
    """A ~2 KB zip whose one member inflates to 2 MiB of zeros (about 1000:1), past the 100:1 per-entry cap
    once the 1 MiB ratio floor is crossed. The archive is refused up front: entries are listed, none read."""
    data = zip_bytes(
        [
            ("readme.txt", ("Nothing to see here." + NL).encode()),
            ("payload.bin", bytes(2 * 1024 * 1024)),
        ]
    )
    write(HERE / "zip-bomb-ratio" / "input.zip", data)


if __name__ == "__main__":
    zip_mixed()
    tar_gz()
    zip_slip()
    sevenzip()
    zip_nested_mixed()
    zip_bomb_ratio()
