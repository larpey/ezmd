"""Steps every PDF engine shares: options, size cap, sanitization, document metadata, the scan classifier with
`pages_without_text` / `ocr_unavailable`, the AcroForm table, and the final warning set."""

from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field

from intomd.inputs import InputRef
from intomd.ir import (
    Block,
    Document,
    Heading,
    InlineSpan,
    Metadata,
    Paragraph,
    Provenance,
    SourceType,
    Table,
    TableCell,
    Warning,
    WarningKind,
)
from intomd.registry import ConversionError, ConvertOptions
from intomd_converters.pdf.options import PdfOptions, pdf_options
from intomd_converters.pdf.pdfinfo import PdfInfo
from intomd_converters.pdf.sanitize import EncryptedNoPassword, Sanitized, UnreadablePdf, sanitize
from intomd_converters.pdf.textlayer import PageText

PDF_MIME = "application/pdf"
MAX_PDF_BYTES = 500 * 1024 * 1024
"""docs/spec/part2.md 13.4 local default."""
NO_TEXT_CHARS = 20
"""A page with fewer extractable characters has no usable text layer (1c step 4)."""
ENCRYPTED_STUB = "Encrypted PDF; no valid password supplied"


def pdf_can_handle(ref: InputRef, exact: float, by_ext: float) -> float:
    mime = ref.detected.mime if ref.detected else None
    if mime == PDF_MIME:
        return exact
    if ref.display.lower().endswith(".pdf"):
        return by_ext
    return 0.0


def parse_options(options: ConvertOptions) -> PdfOptions:
    try:
        return pdf_options(options)
    except ValueError as e:
        raise ConversionError(str(e), user_message=str(e), retryable_with_fallback=False) from e


def new_document(ref: InputRef) -> Document:
    return Document(metadata=Metadata(source=ref.display, source_type=SourceType.PDF, mime=PDF_MIME))


def open_sanitized(ref: InputRef, popts: PdfOptions, doc: Document) -> Sanitized | None:
    """Sanitize the input. Returns None after turning `doc` into the encrypted stub (1c step 3)."""
    if ref.size() > MAX_PDF_BYTES:
        raise ConversionError(
            f"PDF is {ref.size()} bytes; cap is {MAX_PDF_BYTES}",
            user_message="This PDF is larger than the 500 MB limit.",
            retryable_with_fallback=False,
        )
    try:
        return sanitize(ref.path(), passwords=popts.passwords(), max_pages=popts.max_pages, source=ref.display)
    except EncryptedNoPassword:
        doc.blocks.append(Paragraph(spans=[InlineSpan(text=ENCRYPTED_STUB)], provenance=Provenance(source=ref.display)))
        doc.warnings.append(
            Warning(
                kind=WarningKind.ENCRYPTED_NO_PASSWORD,
                message="The PDF is encrypted with a user password and no supplied password opened it.",
            )
        )
        return None
    except UnreadablePdf as e:
        raise ConversionError(
            f"pikepdf could not parse the PDF: {e}",
            user_message="This PDF is damaged and could not be read.",
            retryable_with_fallback=False,
        ) from e


def apply_metadata(doc: Document, san: Sanitized) -> None:
    info: PdfInfo = san.info
    meta = doc.metadata
    meta.title = info.title
    meta.author = info.author
    meta.authors = [info.author] if info.author else []
    meta.description = info.subject
    meta.keywords = info.keywords
    meta.published = info.created
    meta.modified = info.modified
    if info.language:
        meta.language = info.language
        meta.language_source = "declared"
    meta.pages = san.pages_total
    meta.extra["pdf_pages_converted"] = san.pages_kept
    meta.extra["pdf_tagged"] = info.tagged
    doc.truncated = doc.truncated or san.truncated
    doc.warnings.extend(san.warnings)


@dataclass(slots=True)
class ScanReport:
    modes: list[str] = field(default_factory=list)
    without_text: list[int] = field(default_factory=list)
    """1-based pages."""
    to_ocr: list[int] = field(default_factory=list)


def classify(pages: Sequence[PageText], popts: PdfOptions) -> ScanReport:
    """docs/spec/part2.md 1c step 4, applied to every page (cheap with pdfium) instead of a 12-page sample."""
    rep = ScanReport()
    for p in pages:
        unusable = p.chars and p.private_use > 0.05 * p.chars
        chars = 0 if unusable else p.chars
        if chars >= 200 and p.image_fraction < 0.9:
            mode = "born_digital"
        elif chars < NO_TEXT_CHARS and p.image_fraction > 0.5:
            mode = "scanned"
        else:
            mode = "hybrid"
        rep.modes.append(mode)
        if chars < NO_TEXT_CHARS:
            rep.without_text.append(p.number)
        wants = popts.ocr == "force" or (popts.ocr == "auto" and chars < NO_TEXT_CHARS and p.image_fraction > 0.0)
        if wants:
            rep.to_ocr.append(p.number)
    return rep


def scan_warnings(doc: Document, rep: ScanReport, popts: PdfOptions, ocr_missing: list[int]) -> None:
    counts = Counter(rep.modes)
    doc.metadata.extra["pdf_page_modes"] = ",".join(f"{k}={v}" for k, v in sorted(counts.items()))
    if rep.without_text:
        listed = ",".join(str(n) for n in rep.without_text)
        doc.metadata.extra["pdf_pages_without_text"] = listed
        hint = "OCR is off" if popts.ocr == "off" else "OCR is not installed"
        doc.warnings.append(
            Warning(
                kind=WarningKind.PAGES_WITHOUT_TEXT,
                message=f"{len(rep.without_text)} page(s) have no text layer ({hint}): {listed}.",
                count=len(rep.without_text),
                page=rep.without_text[0],
                detail={"pages": listed},
            )
        )
    if ocr_missing:
        listed = ",".join(str(n) for n in ocr_missing)
        doc.warnings.append(
            Warning(
                kind=WarningKind.OCR_UNAVAILABLE,
                message=f"OCR is not installed, so {len(ocr_missing)} page(s) without text were not read: {listed}.",
                count=len(ocr_missing),
                detail={"pages": listed},
            )
        )


def ocr_stub(source: str, page: int, width: float, height: float) -> Paragraph:
    from intomd.ir import BBox

    return Paragraph(
        spans=[InlineSpan(text=f"Page {page} has no text layer; OCR not installed")],
        provenance=Provenance(
            source=source,
            source_page=page,
            bbox=BBox(x0=0, y0=0, x1=width, y1=height, page_width=width, page_height=height),
        ),
        attrs={"pdf_stub": "ocr_unavailable"},
    )


def form_blocks(info: PdfInfo, popts: PdfOptions, source: str) -> list[Block]:
    """AcroForm fields as a `Form fields` table appended after the body (1c step 9)."""
    if popts.forms == "off" or not info.fields:
        return []
    header = ["Field", "Type", "Value", "Page"]
    rows = [header] + [[f.name, f.kind, f.value, "" if f.page is None else str(f.page + 1)] for f in info.fields]
    cells = [
        TableCell(spans=[InlineSpan(text=t)] if t else [], row=r, col=c, is_header=r == 0)
        for r, row in enumerate(rows)
        for c, t in enumerate(row)
    ]
    first_page = next((f.page + 1 for f in info.fields if f.page is not None), 1)
    prov = Provenance(source=source, source_page=first_page)
    return [
        Heading(level=2, spans=[InlineSpan(text="Form fields")], provenance=prov),
        Table(cells=cells, n_rows=len(rows), n_cols=4, header_rows=1, provenance=prov, attrs={"pdf_table": "acroform"}),
    ]


def finish(doc: Document) -> Document:
    if doc.metadata.title is None:
        first = next((b for b in doc.blocks if isinstance(b, Heading) and b.level == 1), None)
        if first is not None:
            doc.metadata.title = "".join(s.text for s in first.spans)
    if not doc.blocks and not any(w.severity == "error" for w in doc.warnings):
        doc.warnings.append(
            Warning(kind=WarningKind.EXTRACTION_EMPTY, message="No text or images could be extracted from the PDF.")
        )
    return doc.finalize()
