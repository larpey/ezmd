"""The text-layer engine: pypdfium2 characters -> lines -> running header/footer removal -> best-effort
tables -> column reading order -> headings (structure tree, outline, font size) -> IR blocks."""

from __future__ import annotations

from dataclasses import dataclass, field

import pypdfium2 as pdfium  # type: ignore[import-untyped]

from intomd.core.textclean import CleanStats
from intomd.ir import Block, Document, Warning, WarningKind
from intomd.registry import ConversionError, ConvertOptions
from intomd_converters.pdf.assemble import Assembler, HeadingSources, PageGeom, vocabulary
from intomd_converters.pdf.common import ScanReport, classify, ocr_stub, scan_warnings
from intomd_converters.pdf.layout import (
    Item,
    body_font_size,
    detect_tables,
    interleaved,
    norm_text,
    order_items,
    running_lines,
    size_levels,
)
from intomd_converters.pdf.ocr import ocr_page
from intomd_converters.pdf.options import PdfOptions
from intomd_converters.pdf.pdfinfo import PdfInfo
from intomd_converters.pdf.textlayer import PageText, read_page

ORDER_STRIDE = 1_000_000
"""Keeps `Line.order` unique across pages (no page has a million lines)."""


@dataclass(slots=True)
class TextLayer:
    pages: list[PageText] = field(default_factory=list)
    stats: CleanStats = field(default_factory=CleanStats)
    timed_out_at: int | None = None
    """1-based page where the deadline hit; None when every page was read."""


def read_text_layer(path: str, info: PdfInfo, options: ConvertOptions) -> TextLayer:
    """Read every page of the sanitized PDF; on the cooperative deadline, stop and keep what was read."""
    layer = TextLayer()
    ctx = options.ctx
    pdf = pdfium.PdfDocument(path)
    try:
        n = len(pdf)
        for i in range(n):
            try:
                ctx.check_deadline()
            except ConversionError:
                layer.timed_out_at = i + 1
                break
            ctx.progress("pdf.text", i / max(n, 1), f"page {i + 1} of {n}")
            layer.pages.append(read_page(pdf, i, info.links.get(i, []), layer.stats, i * ORDER_STRIDE))
    finally:
        pdf.close()
    return layer


def heading_sources(layer: TextLayer, info: PdfInfo, popts: PdfOptions, skip: set[int]) -> HeadingSources:
    body = body_font_size(layer.pages)
    src = HeadingSources(sizes=size_levels(layer.pages, body, skip))
    if info.struct_state == "usable" and popts.structure_tree != "ignore":
        src.struct = info.struct_headings
        src.use_struct = True
        src.struct_only = popts.structure_tree == "only"
    for level, title, page in info.outline:
        key = norm_text(title)
        src.outline.setdefault((key, page), level)
        src.outline_any.setdefault(key, level)
    return src


def text_document(doc: Document, path: str, info: PdfInfo, popts: PdfOptions, options: ConvertOptions) -> None:
    """Fill `doc` with blocks from the text layer of the sanitized PDF at `path`."""
    layer = read_text_layer(path, info, options)
    running = set() if popts.keep_running_headers else running_lines(layer.pages)
    headings = heading_sources(layer, info, popts, running)
    all_lines = [ln for p in layer.pages for ln in p.lines if ln.order not in running]
    asm = Assembler(doc.metadata.source, "pdfium", headings, vocabulary(all_lines), popts.dehyphenate)
    rep = classify(layer.pages, popts)
    uncertain: list[int] = []
    ocr_missing: list[int] = []
    for p in layer.pages:
        lines = [ln for ln in p.lines if ln.order not in running]
        tables, rest = detect_tables(lines)
        items = [Item(ln.x0, ln.y0, ln.x1, ln.y1, ln.order, line=ln) for ln in rest]
        items += [Item(t.x0, t.y0, t.x1, t.y1, t.order, table=t) for t in tables]
        ordered, columns = order_items(items, 0.0, p.width)
        if columns and interleaved(ordered):
            uncertain.append(p.number)
        geom = PageGeom(p.number, p.width, p.height)
        asm.page(geom, ordered, popts.page_markers)
        if p.number in rep.to_ocr:
            blocks = ocr_page(path, p.number - 1, languages=options.languages, source=doc.metadata.source)
            if blocks is None:
                if p.number in rep.without_text:
                    asm.blocks.append(ocr_stub(doc.metadata.source, p.number, p.width, p.height))
                ocr_missing.append(p.number)
            else:
                asm.blocks.extend(blocks)
    doc.blocks.extend(asm.blocks)
    _warnings(doc, layer, running, headings, info, uncertain)
    scan_warnings(doc, rep, popts, ocr_missing)


def _warnings(
    doc: Document,
    layer: TextLayer,
    running: set[int],
    headings: HeadingSources,
    info: PdfInfo,
    uncertain: list[int],
) -> None:
    if layer.timed_out_at is not None:
        doc.truncated = True
        doc.warnings.append(
            Warning(
                kind=WarningKind.TIMEOUT_PARTIAL,
                message=f"The time limit was reached at page {layer.timed_out_at}; later pages are missing.",
                page=layer.timed_out_at,
            )
        )
    if running:
        texts = sorted({ln.text for p in layer.pages for ln in p.lines if ln.order in running})
        doc.metadata.extra["pdf_running_headers"] = len(running)
        doc.warnings.append(
            Warning(
                kind=WarningKind.REMOVED_RUNNING_HEADER_FOOTER,
                message=f"Removed {len(running)} running header/footer lines repeated across pages.",
                count=len(running),
                detail={"examples": " | ".join(texts[:5])[:300]},
            )
        )
    heading_warnings(doc, headings, info)
    if uncertain:
        listed = ",".join(str(n) for n in uncertain)
        doc.warnings.append(
            Warning(
                kind=WarningKind.READING_ORDER_UNCERTAIN,
                message=f"Multi-column text was reordered by layout on page(s) {listed}; check the reading order.",
                page=uncertain[0],
                count=len(uncertain),
                detail={"pages": listed},
            )
        )
    if layer.stats.total:
        doc.warnings.append(
            Warning(
                kind=WarningKind.REMOVED_HIDDEN_ELEMENTS,
                message=f"Removed {layer.stats.total} control or invisible characters.",
                count=layer.stats.total,
            )
        )


def heading_warnings(doc: Document, headings: HeadingSources, info: PdfInfo) -> None:
    """`heading_source_structure_tree` / `structure_tree_unusable` and the `pdf_heading_source` metadata."""
    doc.metadata.extra["pdf_heading_source"] = (
        max(headings.used, key=lambda k: headings.used[k]) if headings.used else "none"
    )
    struct_used = headings.used.get("structure_tree", 0)
    if struct_used and headings.disagreements > 0.3 * struct_used:
        doc.warnings.append(
            Warning(
                kind=WarningKind.HEADING_SOURCE_STRUCTURE_TREE,
                message=(
                    f"Heading levels come from the PDF structure tree; it disagreed with the visual font sizes on "
                    f"{headings.disagreements} of {struct_used} headings."
                ),
                count=headings.disagreements,
            )
        )
    if info.tagged and info.struct_state == "unusable":
        doc.warnings.append(
            Warning(
                kind=WarningKind.STRUCTURE_TREE_UNUSABLE,
                message="The PDF is tagged but its structure tree is empty or unusable; layout heuristics were used.",
            )
        )


def scan_only(path: str, info: PdfInfo, popts: PdfOptions, options: ConvertOptions) -> tuple[TextLayer, ScanReport]:
    """Text layer plus scan classification, for engines that do their own layout (Docling)."""
    layer = read_text_layer(path, info, options)
    return layer, classify(layer.pages, popts)


__all__ = ["Block", "TextLayer", "heading_sources", "heading_warnings", "read_text_layer", "scan_only", "text_document"]
