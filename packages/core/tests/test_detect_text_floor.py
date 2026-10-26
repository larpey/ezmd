"""Printable text is never `application/octet-stream`, whatever Magika calls it."""

from __future__ import annotations

from ezmd.detect import OCTET, detect, looks_like_text
from ezmd.inputs import InputRef

# The shape of a Protein Data Bank file: Magika labels it "proteindb", which has no MIME type and used to
# become application/octet-stream, outranking libmagic's text verdict and the .txt extension.
PDB = (
    b"HEADER    HYDROLASE(ACID PROTEINASE)               13-APR-94   1SIP      1SIP   2\n"
    b"COMPND    SIMULATED PROTEINASE\n"
    b"SOURCE    SYNTHETIC CONSTRUCT\n"
    b"AUTHOR    A.EXAMPLE\n"
    b"REMARK   2 RESOLUTION. 2.10 ANGSTROMS.\n"
    + b"".join(
        f"ATOM  {i:5d}  CA  ALA A{i:4d}     {10.0 + i:8.3f}{20.0 - i:8.3f}{5.0 + i / 3:8.3f}  1.00 20.00".encode()
        + b"           C\n"
        for i in range(1, 60)
    )
    + b"END\n"
)


def test_pdb_text_is_text_whatever_the_extension() -> None:
    for name in ("090978.txt", "090978.tmp", "090978"):
        d = detect(InputRef.from_bytes(PDB, filename=name))
        assert d.mime != OCTET and d.mime.startswith("text/"), (name, d)


def test_looks_like_text() -> None:
    assert looks_like_text(b"plain words, numbers 123 and\tpunctuation.\n" * 10)
    assert looks_like_text("Umlaute: äöü, accents: éè, dashes: –\n".encode())
    assert looks_like_text(b"Latin-1 caf\xe9 and more words here\n" * 5)
    assert not looks_like_text(b"\x00\x01\x02\x03binary\x00\x00")
    assert not looks_like_text(bytes(range(256)) * 4)
    assert not looks_like_text(b"")
