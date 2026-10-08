from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path

import pikepdf
import pytest
from pikepdf import Array, Dictionary, Name, String

from ezmd.detect import detect
from ezmd.inputs import InputRef
from ezmd.ir import Document
from ezmd.registry import ConvertOptions, ExtraValue
from ezmd_converters.pdf.converter import PdfiumTextConverter

FIXTURES = Path(__file__).resolve().parents[4] / "fixtures" / "pdf"

TextOp = tuple[float, float, str, float, bool]
"""(x, y, text, size, bold) in PDF user space."""


def content(ops: Sequence[TextOp]) -> bytes:
    out: list[tuple[list[object], str]] = []
    for x, y, text, size, bold in ops:
        out += [
            ([], "BT"),
            ([Name("/F2" if bold else "/F1"), size], "Tf"),
            ([x, y], "Td"),
            ([String(text.encode("cp1252"))], "Tj"),
            ([], "ET"),
        ]
    return pikepdf.unparse_content_stream(out)


def new_pdf(pages: Sequence[Sequence[TextOp]], *, rotate: int = 0) -> pikepdf.Pdf:
    pdf = pikepdf.new()
    fonts = Dictionary(
        F1=Dictionary(Type=Name.Font, Subtype=Name.Type1, BaseFont=Name.Helvetica, Encoding=Name.WinAnsiEncoding),
        F2=Dictionary(
            Type=Name.Font, Subtype=Name.Type1, BaseFont=Name("/Helvetica-Bold"), Encoding=Name.WinAnsiEncoding
        ),
    )
    for ops in pages:
        page = Dictionary(
            Type=Name.Page,
            MediaBox=Array([0, 0, 612, 792]),
            Resources=Dictionary(Font=fonts),
            Contents=pdf.make_indirect(pikepdf.Stream(pdf, content(ops))),
        )
        if rotate:
            page.Rotate = rotate
        pdf.pages.append(pikepdf.Page(page))
    return pdf


def save(pdf: pikepdf.Pdf, path: Path, **kw: object) -> Path:
    pdf.save(path, **kw)  # type: ignore[arg-type]
    return path


def convert_path(path: Path, extra: dict[str, ExtraValue] | None = None, **opts: object) -> Document:
    ref = InputRef.from_path(path)
    ref.display = path.name
    detect(ref)
    options = ConvertOptions(extra=dict(extra or {}), **opts)  # type: ignore[arg-type]
    try:
        return PdfiumTextConverter().convert(ref, options)
    finally:
        ref.cleanup()


@pytest.fixture
def make_pdf(tmp_path: Path) -> Callable[..., Path]:
    counter = iter(range(1000))

    def build(pages: Sequence[Sequence[TextOp]], **kw: object) -> Path:
        rotate = int(kw.pop("rotate", 0))  # type: ignore[call-overload]
        return save(new_pdf(pages, rotate=rotate), tmp_path / f"t{next(counter)}.pdf", **kw)

    return build
