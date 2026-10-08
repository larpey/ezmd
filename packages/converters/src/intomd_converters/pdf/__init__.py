"""PDF converters (family "documents"): Docling layout engine (`docs` extra) and the default pypdfium2
text-layer engine. Every input is sanitized with pikepdf first (docs/spec/part1.md 8.2)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from intomd.registry import Converter, Unavailable

CHAINS: dict[str, list[str]] = {
    "application/pdf": ["documents.docling_pdf", "documents.pdfium_text"],
}


def converters() -> list[Converter | Unavailable]:
    from intomd.registry import Unavailable
    from intomd_converters.pdf.converter import PdfiumTextConverter, docling_installed

    out: list[Converter | Unavailable] = [PdfiumTextConverter()]
    reason = "Docling is not installed; install the `docs` extra (pip install 'intomd[docs]')."
    if docling_installed():
        try:
            from intomd_converters.pdf.doclingengine import DoclingPdfConverter

            out.append(DoclingPdfConverter())
            return out
        except Exception as e:  # a broken Docling install must not take the text-layer engine down with it
            reason = f"Docling failed to import: {type(e).__name__}: {e}"
    out.append(
        Unavailable(
            id="documents.docling_pdf",
            family="documents",
            reason=reason,
            requires_extras=("docs",),
            mimes=("application/pdf",),
        )
    )
    return out
