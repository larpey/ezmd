"""documents.pdfium_text: the default-install PDF converter (text layer via pypdfium2).

Always available. When Docling (the `docs` extra) is not installed it is the primary PDF engine and every
result carries `engine_fallback` so users know headings come from font sizes / outline / structure tree and
tables are best-effort.
"""

from __future__ import annotations

import importlib.util

from ezmd.context import Limits
from ezmd.inputs import InputRef
from ezmd.ir import Document, Warning, WarningKind
from ezmd.registry import ConvertOptions
from ezmd_converters.pdf.common import (
    MAX_PDF_BYTES,
    PDF_MIME,
    apply_metadata,
    finish,
    form_blocks,
    new_document,
    open_sanitized,
    parse_options,
    pdf_can_handle,
)
from ezmd_converters.pdf.doclingmodels import DOWNLOAD_HINT, missing_message, models_status
from ezmd_converters.pdf.textengine import text_document

PDF_LIMITS = Limits(max_bytes=MAX_PDF_BYTES, max_pages=2000, timeout_s=600.0)


def docling_installed() -> bool:
    try:
        return importlib.util.find_spec("docling") is not None
    except (ImportError, ValueError):
        return False


_TEXT_LAYER = (
    "used the pypdfium2 text-layer engine: headings come from the structure tree, outline, or font sizes, and "
    "tables are best-effort."
)


def _docling_fallback(options: ConvertOptions) -> Warning | None:
    """Why the Docling engine did not run, when it is the requested engine: not installed, or installed
    without its models (then every PDF would silently lose Docling's layout)."""
    if not docling_installed():
        return Warning(
            kind=WarningKind.ENGINE_FALLBACK,
            message=f"Docling is not installed (pip install 'ezmd[docs]'); {_TEXT_LAYER}",
            detail={"engine": "pdfium", "wanted": "docling", "extra": "docs"},
        )
    if options.allow_network:
        return None
    status = models_status()
    if status.ok:
        return None
    return Warning(
        kind=WarningKind.ENGINE_FALLBACK,
        severity="warning",
        message=f"{missing_message(status)}; {_TEXT_LAYER} To use Docling, run: {DOWNLOAD_HINT}.",
        detail={"engine": "pdfium", "wanted": "docling", "missing": ",".join(status.missing)},
    )


class PdfiumTextConverter:
    id = "documents.pdfium_text"
    family = "documents"
    priority = 10
    experimental = False
    requires_extras: tuple[str, ...] = ()
    mimes: tuple[str, ...] = (PDF_MIME,)
    limits = PDF_LIMITS

    def can_handle(self, ref: InputRef) -> float:
        return pdf_can_handle(ref, 0.95, 0.85)

    def convert(self, ref: InputRef, options: ConvertOptions) -> Document:
        popts = parse_options(options)
        doc = new_document(ref)
        san = open_sanitized(ref, popts, doc)
        if san is None:
            return doc.finalize()
        try:
            apply_metadata(doc, san)
            fallback = _docling_fallback(options) if popts.engine == "docling" else None
            if fallback is not None:
                doc.warnings.append(fallback)
            text_document(doc, str(san.path), san.info, popts, options)
            doc.blocks.extend(form_blocks(san.info, popts, ref.display))
        finally:
            san.cleanup()
        return finish(doc)
