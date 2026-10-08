"""OCR hand-off hook for pages without a text layer (docs/spec/part2.md 1b step 4, 1i).

The OCR pipeline (`ezmd.ocr.pipeline.ocr_page(image, hints)`, Part 3) ships in Phase 2 (P2-T05). Until it
is importable, `ocr_page` returns None and the converter emits the stub paragraph "Page N has no text layer;
OCR not installed" with `ocr_unavailable`. When it lands, this is the only function that changes: render the
page, call the pipeline, and return its IR blocks (they carry bboxes and confidences).
"""

from __future__ import annotations

import importlib
import importlib.util
from typing import Any

from ezmd.ir import Block

OCR_DPI = 300
MAX_OCR_PIXELS = 50_000_000
"""Same 50 MP cap Pillow uses for images (docs/spec/part1.md 8.2)."""


def ocr_available() -> bool:
    try:
        return importlib.util.find_spec("ezmd.ocr.pipeline") is not None
    except ModuleNotFoundError:
        return False


def ocr_page(pdf_path: str, page_index: int, *, languages: list[str], source: str) -> list[Block] | None:
    """OCR one page (0-based) of the sanitized PDF. None when no OCR pipeline is installed."""
    if not ocr_available():
        return None
    pipeline: Any = importlib.import_module("ezmd.ocr.pipeline")
    import pypdfium2 as pdfium  # type: ignore[import-untyped]

    pdf = pdfium.PdfDocument(pdf_path)
    try:
        page = pdf[page_index]
        w, h = page.get_size()
        scale = OCR_DPI / 72.0
        if w * h * scale * scale > MAX_OCR_PIXELS:
            scale = (MAX_OCR_PIXELS / (w * h)) ** 0.5
        image = page.render(scale=scale).to_pil()
        page.close()
    finally:
        pdf.close()
    hints = {"languages": languages, "page": page_index + 1, "source": source, "dpi": scale * 72.0}
    blocks = pipeline.ocr_page(image, hints)
    return list(blocks) if blocks else []
