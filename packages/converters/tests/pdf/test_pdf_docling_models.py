"""Docling model presence is checked without importing Docling or torch, so a `docs` install without models
fails fast and loudly instead of spending ~20 s per PDF importing torch before falling back."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from conftest import FIXTURES

from ezmd.detect import detect
from ezmd.inputs import InputRef
from ezmd.ir import WarningKind
from ezmd.registry import ConversionError, ConverterRegistry, ConvertOptions
from ezmd_converters.pdf import converter as converter_mod
from ezmd_converters.pdf import doclingengine
from ezmd_converters.pdf.converter import PdfiumTextConverter
from ezmd_converters.pdf.doclingengine import DoclingPdfConverter
from ezmd_converters.pdf.doclingmodels import DOWNLOAD_HINT, models_status

LAYOUT = "docling-project--docling-layout-heron"
TABLES = "docling-project--docling-models"


def _hf_repo(hub: Path, folder: str) -> None:
    (hub / f"models--{folder}" / "snapshots" / "0123abcd").mkdir(parents=True)
    (hub / f"models--{folder}" / "snapshots" / "0123abcd" / "config.json").write_text("{}", encoding="utf-8")


def _artifacts(root: Path, *folders: str) -> Path:
    for f in folders:
        (root / f).mkdir(parents=True)
        (root / f / "config.json").write_text("{}", encoding="utf-8")
    return root


def test_artifacts_dir_with_both_models_is_ok(tmp_path: Path) -> None:
    env = {"EZMD_DOCLING_ARTIFACTS": str(_artifacts(tmp_path, LAYOUT, TABLES))}
    status = models_status(env)
    assert status.ok and status.missing == () and str(tmp_path) in status.location


def test_artifacts_dir_reports_each_missing_model(tmp_path: Path) -> None:
    env = {"EZMD_DOCLING_ARTIFACTS": str(_artifacts(tmp_path, TABLES))}
    assert models_status(env).missing == ("layout",)
    assert models_status({"EZMD_DOCLING_ARTIFACTS": str(tmp_path / "nope")}).missing == ("layout", "tableformer")


def test_empty_model_folder_does_not_count(tmp_path: Path) -> None:
    (tmp_path / LAYOUT).mkdir()
    _artifacts(tmp_path, TABLES)
    assert models_status({"EZMD_DOCLING_ARTIFACTS": str(tmp_path)}).missing == ("layout",)


def test_hugging_face_cache_is_used_without_artifacts(tmp_path: Path) -> None:
    hub = tmp_path / "hub"
    env = {"HF_HUB_CACHE": str(hub)}
    assert models_status(env).missing == ("layout", "tableformer")
    _hf_repo(hub, LAYOUT)
    _hf_repo(hub, TABLES)
    status = models_status(env)
    assert status.ok and "Hugging Face" in status.location
    assert models_status({"HF_HOME": str(tmp_path)}).ok  # HF_HOME/hub


def _ref() -> InputRef:
    ref = InputRef.from_path(FIXTURES / "simple-table" / "input.pdf")
    ref.display = "input.pdf"
    detect(ref)
    return ref


def _no_models(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("EZMD_DOCLING_ARTIFACTS", str(tmp_path / "empty"))


def test_docling_fails_fast_without_models(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _no_models(monkeypatch, tmp_path)

    def must_not_load(*_a: Any) -> Any:
        raise AssertionError("Docling was imported although its models are missing")

    monkeypatch.setattr(doclingengine, "_docling_converter", must_not_load)
    with pytest.raises(ConversionError) as e:
        DoclingPdfConverter().convert(_ref(), ConvertOptions())
    assert e.value.retryable_with_fallback
    assert "models" in e.value.user_message and "docling-tools models download" in e.value.user_message


def test_fallback_without_models_warns_loudly_once(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _no_models(monkeypatch, tmp_path)
    monkeypatch.setattr(converter_mod, "docling_installed", lambda: True)
    reg = ConverterRegistry()
    reg.register(DoclingPdfConverter())
    reg.register(PdfiumTextConverter())
    reg.set_chain("application/pdf", ["documents.docling_pdf", "documents.pdfium_text"])
    result = reg.convert(_ref(), ConvertOptions())
    assert result.converter_id == "documents.pdfium_text"
    fallbacks = [w for w in result.all_warnings if w.kind == WarningKind.ENGINE_FALLBACK]
    assert len(fallbacks) == 1, fallbacks
    assert fallbacks[0].severity == "warning"
    assert DOWNLOAD_HINT in fallbacks[0].message and "not downloaded" in fallbacks[0].message
