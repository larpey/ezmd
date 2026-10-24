"""Damaged copies of arXiv papers: documents with a known loss, to test whether a converter says so.

The born-digital corpus can show that a tool lost text silently, but not that a tool's warnings fire when they
should, because the papers are intact. These variants put a known hole in each paper:

- `scan`: every page rendered to an image at SCAN_DPI and written back as an image-only PDF. The text is all
  there to the eye and absent from the text layer: a scanned paper. A tool without OCR loses every word.
- `pages`: a block of PAGES_SHARE of the pages, starting a third of the way in (the title page stays), replaced
  by their renders. The rest of the text layer is intact, so a tool that reads the text layer loses that block
  and nothing else.
- `trunc`: the file cut at TRUNC_SHARE of its bytes. The cross-reference table and the last objects are gone;
  a reader either refuses the file, repairs it and says what it could not read, or repairs it quietly.

The witness for every variant is the original paper's text layer, so the loss is measured against what the
document really said. Variants are built once into the corpus cache; rendering is deterministic for a given
pypdfium2 and Pillow version.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

from tools.bench.corpora import DAMAGED_SAMPLE, arxiv_root

__all__ = ["DAMAGED_SAMPLE", "KINDS", "build", "damaged_dir", "damaged_pages", "textless_pages"]

KINDS = ("scan", "pages", "trunc")
SCAN_DPI = 150
PAGES_SHARE = 0.2
PAGES_START = 1 / 3
TRUNC_SHARE = 0.8


def damaged_dir() -> Path:
    return arxiv_root() / "damaged"


def damaged_pages(n_pages: int) -> list[int]:
    """0-based indexes of the pages the `pages` variant replaces: a block of PAGES_SHARE of the pages starting at
    PAGES_START of the document, at least one page, never the first."""
    if n_pages < 2:
        return [n_pages - 1] if n_pages == 1 else []
    length = max(1, round(n_pages * PAGES_SHARE))
    start = max(1, int(n_pages * PAGES_START))
    start = min(start, n_pages - length)
    return list(range(start, start + length))


def _render(src: Path, indexes: list[int]) -> list[Any]:
    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument(str(src))
    try:
        images = []
        for i in indexes:
            page = doc[i]
            images.append(page.render(scale=SCAN_DPI / 72).to_pil().convert("RGB"))
            page.close()
        return images
    finally:
        doc.close()


def _image_pdf(images: list[Any]) -> bytes:
    buf = io.BytesIO()
    images[0].save(buf, format="PDF", save_all=True, append_images=images[1:], resolution=SCAN_DPI)
    return buf.getvalue()


def page_count(src: Path) -> int:
    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument(str(src))
    try:
        return len(doc)
    finally:
        doc.close()


TEXTLESS_CHARS = 20
"""A page of the intact paper with fewer text-layer characters than this (a full-page figure) has no text to
lose; a warning that names it is right, so the scorer expects it alongside the damaged pages."""


def textless_pages(src: Path) -> list[int]:
    """1-based pages of `src` whose text layer holds fewer than TEXTLESS_CHARS characters."""
    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument(str(src))
    try:
        out = []
        for i, page in enumerate(doc):
            textpage = page.get_textpage()
            if len(textpage.get_text_range().strip()) < TEXTLESS_CHARS:
                out.append(i + 1)
            textpage.close()
            page.close()
        return out
    finally:
        doc.close()


def build_scan(src: Path, dest: Path) -> list[int]:
    n = page_count(src)
    dest.write_bytes(_image_pdf(_render(src, list(range(n)))))
    return list(range(n))


def build_pages(src: Path, dest: Path) -> list[int]:
    import pikepdf

    indexes = damaged_pages(page_count(src))
    images = _image_pdf(_render(src, indexes))
    with pikepdf.open(str(src)) as base, pikepdf.open(io.BytesIO(images)) as rendered:
        for k, i in enumerate(indexes):
            base.pages[i] = rendered.pages[k]
        base.save(str(dest))
    return indexes


def build_trunc(src: Path, dest: Path) -> list[int]:
    data = src.read_bytes()
    dest.write_bytes(data[: int(len(data) * TRUNC_SHARE)])
    return []


BUILDERS = {"scan": build_scan, "pages": build_pages, "trunc": build_trunc}


def build(kind: str, src: Path, dest: Path) -> dict[str, Any]:
    """Write the `kind` variant of `src` to `dest` and return its metadata (1-based damaged pages)."""
    if kind not in BUILDERS:
        raise ValueError(f"unknown damage kind {kind!r}; one of {KINDS}")
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".part")
    indexes = BUILDERS[kind](src, tmp)
    tmp.replace(dest)
    return {
        "kind": kind,
        "damaged_pages": [i + 1 for i in indexes],
        "pages": page_count(src),
        "textless_pages": textless_pages(src),
    }
