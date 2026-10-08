"""Docling engine tests. The mapping tests need the `docs` extra and pre-downloaded models
(`docling-tools models download layout tableformer -o DIR` and INTOMD_DOCLING_ARTIFACTS=DIR); they are skipped
otherwise. The fallback test needs neither: Docling is imported dynamically, so a failing engine can be faked."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
from typing import Any

import pytest
from conftest import FIXTURES

from intomd.detect import detect
from intomd.inputs import InputRef
from intomd.ir import Heading, PageBreak, Paragraph, Table, WarningKind, spans_text
from intomd.registry import ConversionError, ConverterRegistry, ConvertOptions
from intomd_converters.pdf import doclingengine
from intomd_converters.pdf.converter import PdfiumTextConverter
from intomd_converters.pdf.doclingengine import DoclingPdfConverter

_ARTIFACTS = os.environ.get("INTOMD_DOCLING_ARTIFACTS", "")
needs_docling = pytest.mark.skipif(
    importlib.util.find_spec("docling") is None or not _ARTIFACTS or not Path(_ARTIFACTS).is_dir(),
    reason="needs the `docs` extra and Docling models in INTOMD_DOCLING_ARTIFACTS",
)


def _ref(name: str) -> InputRef:
    ref = InputRef.from_path(FIXTURES / name / "input.pdf")
    ref.display = "input.pdf"
    detect(ref)
    return ref


def _registry() -> ConverterRegistry:
    reg = ConverterRegistry()
    reg.register(DoclingPdfConverter())
    reg.register(PdfiumTextConverter())
    reg.set_chain("application/pdf", ["documents.docling_pdf", "documents.pdfium_text"])
    return reg


def test_docling_failure_falls_back_to_text_layer(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_a: Any) -> Any:
        raise RuntimeError("models missing")

    monkeypatch.setattr(doclingengine, "_docling_converter", boom)
    result = _registry().convert(_ref("simple-table"), ConvertOptions())
    assert result.converter_id == "documents.pdfium_text"
    assert result.metrics.engines_tried == ["documents.docling_pdf", "documents.pdfium_text"]
    assert WarningKind.ENGINE_FALLBACK in [w.kind for w in result.all_warnings]
    assert any(isinstance(b, Table) for b in result.document.blocks)


def test_docling_skips_when_other_engine_requested() -> None:
    with pytest.raises(ConversionError) as e:
        DoclingPdfConverter().convert(_ref("simple-table"), ConvertOptions(extra={"pdf.engine": "pdfium"}))
    assert e.value.retryable_with_fallback


def test_docling_env_engine_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INTOMD_PDF_ENGINE", "pypdf")
    assert DoclingPdfConverter().can_handle(_ref("simple-table")) == 0.0
    monkeypatch.delenv("INTOMD_PDF_ENGINE")
    assert DoclingPdfConverter().can_handle(_ref("simple-table")) == 1.0


def test_docling_encrypted_stub_without_engine() -> None:
    doc = DoclingPdfConverter().convert(_ref("encrypted-user-password"), ConvertOptions())
    assert [str(w.kind) for w in doc.warnings] == ["encrypted_no_password"]


@needs_docling
def test_docling_report_headings_and_furniture() -> None:
    doc = DoclingPdfConverter().convert(_ref("born-digital-report"), ConvertOptions())
    heads = [(b.level, spans_text(b.spans)) for b in doc.blocks if isinstance(b, Heading)]
    assert heads[0] == (1, "Harbor Lane Annual Report")
    assert (3, "1.1 Scope") in heads and (2, "4. Capital plan") in heads
    text = doc.plain_text()
    assert "Confidential" not in text and "information about each fender" in text
    assert [b.page_number for b in doc.blocks if isinstance(b, PageBreak)] == [1, 2, 3, 4]
    assert WarningKind.REMOVED_RUNNING_HEADER_FOOTER in [w.kind for w in doc.warnings]
    assert str(doc.metadata.extra["pdf_engine"]).startswith("docling@")
    for b in doc.blocks:
        if not isinstance(b, PageBreak):
            assert b.provenance.source_page is not None and b.provenance.bbox is not None


@needs_docling
def test_docling_table_and_two_columns() -> None:
    doc = DoclingPdfConverter().convert(_ref("simple-table"), ConvertOptions())
    table = next(b for b in doc.blocks if isinstance(b, Table))
    grid = [[spans_text(c.spans) for c in table.cells if c.row == r] for r in range(table.n_rows)]
    assert grid[0] == ["Terminal", "Q1", "Q2", "Q3"] and grid[-1] == ["Bulk berth", "45", "52", "49"]
    doc2 = DoclingPdfConverter().convert(_ref("two-column-page"), ConvertOptions())
    paras = [spans_text(b.spans) for b in doc2.blocks if isinstance(b, Paragraph)]
    assert paras[0].startswith("Tides in the inner harbor") and paras[1].startswith("Wind set-up")


@needs_docling
def test_docling_image_only_page_and_structure_tree() -> None:
    doc = DoclingPdfConverter().convert(_ref("image-only-page"), ConvertOptions())
    kinds = [str(w.kind) for w in doc.warnings]
    assert "pages_without_text" in kinds and "ocr_unavailable" in kinds
    assert any(isinstance(b, Paragraph) and b.attrs.get("pdf_stub") for b in doc.blocks)
    tagged = DoclingPdfConverter().convert(_ref("tagged-structure-tree"), ConvertOptions())
    heads = [(b.level, spans_text(b.spans)) for b in tagged.blocks if isinstance(b, Heading)]
    assert heads == [(1, "Port safety handbook"), (2, "Personal protective equipment"), (2, "Night work")]
    assert "heading_source_structure_tree" in [str(w.kind) for w in tagged.warnings]
