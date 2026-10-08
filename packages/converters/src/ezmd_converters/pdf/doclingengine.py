"""documents.docling_pdf: Docling (MIT) layout engine, the default PDF engine when the `docs` extra is installed.

docs/spec/part2.md 1b/1c: `DocumentConverter` with `PdfPipelineOptions` on the default docling-parse backend,
run in page batches (`pdf.batch_pages`, default 25) with a deadline check between batches; Docling items are
mapped to IR blocks with page + bbox provenance; running headers/footers are dropped and counted. A pypdfium2
pass over the sanitized copy supplies the scan classifier (`pages_without_text`) and heading levels from the
structure tree, outline, or font sizes, because Docling's layout model labels section headers without a
reliable hierarchy. Docling's own OCR is disabled: OCR goes through the ezmd OCR pipeline (Phase 2).

Models are never downloaded unless `options.allow_network` is true: `HF_HUB_OFFLINE=1` is set before Docling
is imported. Pre-fetch them with `docling-tools models download` and point `EZMD_DOCLING_ARTIFACTS` at the
directory. Any Docling failure raises a retryable ConversionError so the registry falls back to
`documents.pdfium_text` (with `engine_fallback`).
"""

from __future__ import annotations

import importlib
import importlib.metadata
import os
import threading
from typing import Any

from ezmd.inputs import InputRef
from ezmd.ir import (
    BBox,
    Block,
    CodeBlock,
    Document,
    Equation,
    Footnote,
    Heading,
    InlineSpan,
    ListBlock,
    ListItem,
    PageBreak,
    Paragraph,
    Provenance,
    Table,
    TableCell,
    Warning,
    WarningKind,
)
from ezmd.registry import ConversionError, ConvertOptions
from ezmd_converters.pdf.common import (
    apply_metadata,
    finish,
    form_blocks,
    new_document,
    ocr_stub,
    open_sanitized,
    parse_options,
    pdf_can_handle,
    scan_warnings,
)
from ezmd_converters.pdf.converter import PDF_LIMITS
from ezmd_converters.pdf.layout import norm_text, running_lines
from ezmd_converters.pdf.ocr import ocr_page
from ezmd_converters.pdf.textengine import heading_sources, heading_warnings, scan_only

_LOCK = threading.Lock()
_CONVERTERS: dict[tuple[str | None, bool], Any] = {}
_SKIP_ENGINES = ("pdfium", "pypdf")


def _mod(name: str) -> Any:
    """Import a Docling module dynamically: Docling is an optional extra, so it is never imported statically."""
    return importlib.import_module(name)


def _docling_converter(artifacts: str | None, tables: bool) -> Any:
    key = (artifacts, tables)
    with _LOCK:
        conv = _CONVERTERS.get(key)
        if conv is None:
            base_models = _mod("docling.datamodel.base_models")
            pipeline_options = _mod("docling.datamodel.pipeline_options")
            document_converter = _mod("docling.document_converter")

            opts = pipeline_options.PdfPipelineOptions()
            opts.do_ocr = False
            opts.do_table_structure = tables
            opts.generate_page_images = False
            opts.generate_picture_images = False
            if artifacts:
                opts.artifacts_path = artifacts
            fmt = document_converter.PdfFormatOption(pipeline_options=opts)
            conv = document_converter.DocumentConverter(format_options={base_models.InputFormat.PDF: fmt})
            _CONVERTERS[key] = conv
        return conv


def _text(item: Any) -> str:
    return " ".join(str(getattr(item, "text", "") or "").split())


class _Mapper:
    """Docling items -> IR blocks for one batch, keeping list and page-marker state across batches."""

    def __init__(self, source: str, levels: dict[str, int], page_markers: bool) -> None:
        self.source = source
        self.levels = levels
        self.page_markers = page_markers
        self.blocks: list[Block] = []
        self.furniture = 0
        self.pictures = 0
        self.unrecognized: list[int] = []
        self.pages_seen: set[int] = set()
        self._title_seen = False
        self._list: ListBlock | None = None
        self._list_depth = 0

    def prov(self, item: Any, ddoc: Any) -> Provenance:
        prov = getattr(item, "prov", None) or []
        if not prov:
            return Provenance(source=self.source, engine="docling")
        pv = prov[0]
        page_no = int(pv.page_no)
        page = ddoc.pages.get(page_no)
        bbox = None
        if page is not None and page.size is not None:
            w, h = float(page.size.width), float(page.size.height)
            bb = pv.bbox.to_top_left_origin(page_height=h)
            x0, x1 = sorted((max(0.0, min(w, bb.l)), max(0.0, min(w, bb.r))))
            y0, y1 = sorted((max(0.0, min(h, bb.t)), max(0.0, min(h, bb.b))))
            bbox = BBox(x0=round(x0, 2), y0=round(y0, 2), x1=round(x1, 2), y1=round(y1, 2), page_width=w, page_height=h)
        return Provenance(source=self.source, source_page=page_no, bbox=bbox, engine="docling")

    def _marker(self, prov: Provenance) -> None:
        page = prov.source_page
        if page is None or page in self.pages_seen:
            return
        self.pages_seen.add(page)
        if self.page_markers:
            self._close_list()
            self.blocks.append(PageBreak(page_number=page, provenance=Provenance(source=self.source, source_page=page)))

    def _close_list(self) -> None:
        if self._list is not None:
            self.blocks.append(self._list)
            self._list = None

    def batch(self, ddoc: Any) -> None:
        doc_types = _mod("docling_core.types.doc")
        ContentLayer, DocItemLabel = doc_types.ContentLayer, doc_types.DocItemLabel  # noqa: N806

        layers = {ContentLayer.BODY, ContentLayer.FURNITURE}
        captions: set[str] = set()
        for item, depth in ddoc.iterate_items(included_content_layers=layers):
            label = getattr(item, "label", None)
            if getattr(item, "content_layer", None) == ContentLayer.FURNITURE or label in (
                DocItemLabel.PAGE_HEADER,
                DocItemLabel.PAGE_FOOTER,
            ):
                self.furniture += 1
                continue
            prov = self.prov(item, ddoc)
            self._marker(prov)
            if label == DocItemLabel.LIST_ITEM:
                self._list_item(item, depth, prov)
                continue
            self._close_list()
            self._item(item, label, prov, ddoc, captions)
        self._close_list()

    def _list_item(self, item: Any, depth: int, prov: Provenance) -> None:
        text = _text(item)
        if not text:
            return
        li = ListItem(spans=[InlineSpan(text=text)], provenance=prov)
        ordered = bool(getattr(item, "enumerated", False))
        if self._list is None or (self._list.ordered != ordered and depth <= self._list_depth):
            self._close_list()
            self._list = ListBlock(ordered=ordered, items=[], provenance=prov)
            self._list_depth = depth
        level = max(0, min(depth - self._list_depth, 5))
        siblings = self._list.items
        for _ in range(level):
            if not siblings:
                break
            siblings = siblings[-1].children
        siblings.append(li)

    def _item(self, item: Any, label: Any, prov: Provenance, ddoc: Any, captions: set[str]) -> None:
        DocItemLabel = _mod("docling_core.types.doc").DocItemLabel  # noqa: N806

        text = _text(item)
        ref = str(getattr(item, "self_ref", ""))
        if label == DocItemLabel.TITLE:
            self._title_seen = True
            if text:
                self.blocks.append(
                    Heading(level=self.levels.get(norm_text(text), 1), spans=[InlineSpan(text=text)], provenance=prov)
                )
        elif label == DocItemLabel.SECTION_HEADER:
            base = int(getattr(item, "level", 1) or 1) + (1 if self._title_seen else 0)
            level = self.levels.get(norm_text(text), max(1, min(base, 6)))
            if text:
                self.blocks.append(Heading(level=level, spans=[InlineSpan(text=text)], provenance=prov))
        elif label == DocItemLabel.TABLE:
            table = self._table(item, prov, ddoc)
            if table is not None:
                for cap in getattr(item, "captions", []) or []:
                    captions.add(str(getattr(cap, "cref", "")))
                self.blocks.append(table)
        elif label in (DocItemLabel.PICTURE, DocItemLabel.CHART):
            self.pictures += 1
            for cap in getattr(item, "captions", []) or []:
                captions.add(str(getattr(cap, "cref", "")))
            caption = item.caption_text(ddoc) if hasattr(item, "caption_text") else ""
            if caption:
                self.blocks.append(Paragraph(spans=[InlineSpan(text=caption)], role="caption", provenance=prov))
        elif label == DocItemLabel.CODE:
            code = str(getattr(item, "text", "") or "")
            if code.strip():
                lang = str(getattr(item, "code_language", "") or "").lower()
                self.blocks.append(
                    CodeBlock(code=code, language=None if lang in ("", "unknown") else lang, provenance=prov)
                )
        elif label == DocItemLabel.FORMULA:
            if text:
                self.blocks.append(Equation(latex=text, provenance=prov))
            elif prov.source_page is not None:
                self.unrecognized.append(prov.source_page)
        elif label == DocItemLabel.FOOTNOTE:
            if text:
                marker = text.split(" ", 1)[0].rstrip(".)") if text[:1].isdigit() else "*"
                body = text.split(" ", 1)[1] if text[:1].isdigit() and " " in text else text
                self.blocks.append(Footnote(marker=marker, spans=[InlineSpan(text=body)], provenance=prov))
        elif label == DocItemLabel.CAPTION:
            if ref not in captions and text:
                self.blocks.append(Paragraph(spans=[InlineSpan(text=text)], role="caption", provenance=prov))
        elif text:
            href = getattr(item, "hyperlink", None)
            href_s = (
                str(href) if href is not None and str(href).startswith(("http://", "https://", "mailto:")) else None
            )
            self.blocks.append(Paragraph(spans=[InlineSpan(text=text, href=href_s)], provenance=prov))

    def _table(self, item: Any, prov: Provenance, ddoc: Any) -> Table | None:
        data = getattr(item, "data", None)
        if data is None or not data.num_rows or not data.num_cols:
            return None
        n_rows, n_cols = int(data.num_rows), int(data.num_cols)
        seen: set[tuple[int, int]] = set()
        cells: list[TableCell] = []
        for c in data.table_cells:
            r, k = int(c.start_row_offset_idx), int(c.start_col_offset_idx)
            if (r, k) in seen or r >= n_rows or k >= n_cols:
                continue
            seen.add((r, k))
            rs = max(1, min(int(c.end_row_offset_idx) - r, n_rows - r))
            cs = max(1, min(int(c.end_col_offset_idx) - k, n_cols - k))
            text = " ".join(str(c.text or "").split())
            cells.append(
                TableCell(
                    spans=[InlineSpan(text=text)] if text else [],
                    row=r,
                    col=k,
                    row_span=rs,
                    col_span=cs,
                    is_header=bool(c.column_header),
                )
            )
        header_rows = 0
        while header_rows < n_rows and any(c.row == header_rows and c.is_header for c in cells):
            header_rows += 1
        caption = item.caption_text(ddoc) if hasattr(item, "caption_text") else ""
        return Table(
            cells=cells,
            n_rows=n_rows,
            n_cols=n_cols,
            header_rows=header_rows,
            caption=[InlineSpan(text=caption)] if caption else None,
            provenance=prov,
        )


class DoclingPdfConverter:
    id = "documents.docling_pdf"
    family = "documents"
    priority = 20
    experimental = False
    requires_extras: tuple[str, ...] = ("docs",)
    mimes: tuple[str, ...] = ("application/pdf",)
    limits = PDF_LIMITS

    def can_handle(self, ref: InputRef) -> float:
        if os.environ.get("EZMD_PDF_ENGINE", "").lower() in _SKIP_ENGINES:
            return 0.0
        return pdf_can_handle(ref, 1.0, 0.9)

    def convert(self, ref: InputRef, options: ConvertOptions) -> Document:
        popts = parse_options(options)
        if popts.engine != "docling":
            raise ConversionError(f"pdf.engine={popts.engine} requested; skipping Docling")
        if not options.allow_network:
            os.environ.setdefault("HF_HUB_OFFLINE", "1")
        doc = new_document(ref)
        san = open_sanitized(ref, popts, doc)
        if san is None:
            return doc.finalize()
        try:
            apply_metadata(doc, san)
            path = str(san.path)
            layer, rep = scan_only(path, san.info, popts, options)
            running = running_lines(layer.pages)
            headings = heading_sources(layer, san.info, popts, running)
            levels: dict[str, int] = {}
            for p in layer.pages:
                for ln in p.lines:
                    lvl = headings.level(ln) if ln.order not in running else None
                    if lvl is not None:
                        levels.setdefault(norm_text(ln.text), lvl)
            mapper = _Mapper(ref.display, levels, popts.page_markers)
            self._run(path, san.pages_kept, popts.batch_pages, mapper, doc, options)
            ocr_missing = self._ocr(mapper, rep.to_ocr, rep.without_text, layer, path, ref.display, options)
            doc.blocks.extend(mapper.blocks)
            scan_warnings(doc, rep, popts, ocr_missing)
            self._warnings(doc, mapper)
            heading_warnings(doc, headings, san.info)
            doc.blocks.extend(form_blocks(san.info, popts, ref.display))
        finally:
            san.cleanup()
        return finish(doc)

    def _run(self, path: str, pages: int, batch: int, mapper: _Mapper, doc: Document, options: ConvertOptions) -> None:
        conv = _docling_converter(os.environ.get("EZMD_DOCLING_ARTIFACTS") or None, True)
        ctx = options.ctx
        for start in range(1, pages + 1, batch):
            end = min(pages, start + batch - 1)
            if start > 1:
                try:
                    ctx.check_deadline()
                except ConversionError:
                    doc.truncated = True
                    doc.warnings.append(
                        Warning(
                            kind=WarningKind.TIMEOUT_PARTIAL,
                            message=f"The time limit was reached at page {start}; later pages are missing.",
                            page=start,
                        )
                    )
                    return
            ctx.progress("pdf.docling", (start - 1) / max(pages, 1), f"pages {start}-{end} of {pages}")
            try:
                result = conv.convert(path, page_range=(start, end), raises_on_error=True)
            except Exception as e:
                raise ConversionError(
                    f"docling failed on pages {start}-{end}: {type(e).__name__}: {e}",
                    user_message="The layout engine failed on this PDF.",
                ) from e
            mapper.batch(result.document)
            ctx.publish_partial(doc.model_copy(update={"blocks": [*doc.blocks, *mapper.blocks]}))

    @staticmethod
    def _ocr(
        mapper: _Mapper,
        to_ocr: list[int],
        without: list[int],
        layer: Any,
        path: str,
        source: str,
        options: ConvertOptions,
    ) -> list[int]:
        """OCR pages through the hook; without an OCR pipeline, insert the stub after the page's last block
        (pages without text only). Returns the pages that needed OCR and did not get it."""
        sizes = {p.number: (p.width, p.height) for p in layer.pages}
        missing: list[int] = []
        for page in sorted(to_ocr, reverse=True):
            got = ocr_page(path, page - 1, languages=options.languages, source=source)
            if got is None:
                missing.append(page)
                if page not in without:
                    continue
                w, h = sizes.get(page, (612.0, 792.0))
                insert: list[Block] = [ocr_stub(source, page, w, h)]
            else:
                insert = got
            idx = len(mapper.blocks)
            for i, b in enumerate(mapper.blocks):
                bp = b.provenance.source_page
                if bp is not None and bp > page:
                    idx = i
                    break
            mapper.blocks[idx:idx] = insert
        return sorted(missing)

    @staticmethod
    def _warnings(doc: Document, mapper: _Mapper) -> None:
        version = "unknown"
        for dist in ("docling-slim", "docling"):
            try:
                version = importlib.metadata.version(dist)
                break
            except importlib.metadata.PackageNotFoundError:  # noqa: S112 - try the other distribution name
                continue
        doc.metadata.extra["pdf_engine"] = f"docling@{version}"
        if mapper.furniture:
            doc.metadata.extra["pdf_running_headers"] = mapper.furniture
            doc.warnings.append(
                Warning(
                    kind=WarningKind.REMOVED_RUNNING_HEADER_FOOTER,
                    message=f"Removed {mapper.furniture} running header/footer items.",
                    count=mapper.furniture,
                )
            )
        if mapper.pictures:
            doc.metadata.extra["pdf_pictures"] = mapper.pictures
        if mapper.unrecognized:
            pages = ",".join(str(p) for p in sorted(set(mapper.unrecognized)))
            doc.warnings.append(
                Warning(
                    kind=WarningKind.EQUATION_UNRECOGNIZED,
                    message=f"Equations on page(s) {pages} could not be converted to LaTeX.",
                    count=len(mapper.unrecognized),
                    detail={"pages": pages},
                )
            )
