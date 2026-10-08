"""Core changes requested by converter families in Phase 1 (task P1-core-renderer): registry errors for
unavailable engines, OOXML variant and RTF alias detection, fixture `requires`, IR additions."""

from __future__ import annotations

from pathlib import Path

import pytest

from ezmd.detect import extension_mime, mime_family, normalize_mime, same_family
from ezmd.inputs import Detected, InputRef
from ezmd.ir import (
    Document,
    InlineSpan,
    Link,
    Metadata,
    Paragraph,
    Provenance,
    SourceType,
    inline_link_count,
)
from ezmd.registry import ConversionError, ConverterRegistry, ConvertOptions, Unavailable
from ezmd.testing.fixtures import missing_requirements

DOC = "application/msword"
DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _ref(mime: str) -> InputRef:
    ref = InputRef.from_bytes(b"\xd0\xcf\x11\xe0 legacy", filename="old.doc")
    ref.detected = Detected(mime=mime, extension=".doc", confidence=1.0)
    return ref


def test_unavailable_by_mime_names_reason_and_code() -> None:
    reg = ConverterRegistry()
    reg.register(
        Unavailable(id="documents.libreoffice", family="documents", reason="libreoffice_missing", mimes=(DOC,))
    )
    with pytest.raises(ConversionError) as info:
        reg.convert(_ref(DOC), ConvertOptions())
    err = info.value
    assert err.code == "libreoffice_missing"
    assert "LibreOffice is not installed" in err.user_message
    assert "(libreoffice_missing)" in err.user_message
    assert "not supported yet" not in err.user_message
    assert not err.retryable_with_fallback


def test_unavailable_named_by_chain_lists_extra() -> None:
    reg = ConverterRegistry()
    reg.register(
        Unavailable(
            id="documents.docling", family="documents", reason="Docling is not installed", requires_extras=("docs",)
        )
    )
    reg.set_chain(DOC, ["documents.docling"])
    with pytest.raises(ConversionError) as info:
        reg.convert(_ref(DOC), ConvertOptions())
    err = info.value
    assert err.code == "conversion_failed"
    assert err.user_message.startswith("Docling is not installed")
    assert "ezmd[docs]" in err.user_message


def test_unsupported_without_unavailable_is_unchanged() -> None:
    reg = ConverterRegistry()
    reg.register(Unavailable(id="audio.asr", family="media", reason="asr_unavailable", mimes=("audio/*",)))
    with pytest.raises(ConversionError) as info:
        reg.convert(_ref(DOC), ConvertOptions())
    assert info.value.user_message == "This file type is not supported yet."


@pytest.mark.parametrize("ext", [".docm", ".dotx", ".dotm"])
def test_word_variants_share_the_docx_family(ext: str) -> None:
    mime = extension_mime(f"a{ext}")
    assert mime is not None and mime != DOCX
    assert same_family(mime, DOCX)


@pytest.mark.parametrize(
    ("ext", "base"),
    [
        (".xlsm", "spreadsheetml.sheet"),
        (".xltx", "spreadsheetml.sheet"),
        (".pptm", "presentationml.presentation"),
        (".potx", "presentationml.presentation"),
    ],
)
def test_excel_and_powerpoint_variants(ext: str, base: str) -> None:
    mime = extension_mime(f"a{ext}")
    assert mime is not None
    assert mime_family(mime).endswith(base)


def test_rtf_aliases() -> None:
    assert normalize_mime("text/rtf") == "application/rtf"
    assert same_family("text/rtf", "application/rtf")
    assert not same_family(DOCX, "application/pdf")


def test_pipeline_no_misnamed_for_docm(tmp_path: Path) -> None:
    from ezmd.ir import ConversionResult, InputRefInfo
    from ezmd.pipeline import convert_ref

    class Fake:
        id = "documents.fake"
        family = "documents"
        priority = 0
        experimental = False
        requires_extras: tuple[str, ...] = ()
        mimes: tuple[str, ...] = (DOCX,)

        def can_handle(self, ref: InputRef) -> float:
            return 1.0

        def convert(self, ref: InputRef, options: ConvertOptions) -> Document:
            return Document(
                metadata=Metadata(source=ref.display, source_type=SourceType.DOCX),
                blocks=[Paragraph(spans=[InlineSpan(text="x")], provenance=Provenance(source=ref.display))],
            ).finalize()

    reg = ConverterRegistry()
    reg.register(Fake())
    ref = InputRef.from_bytes(b"PK fake", filename="macro.docm")
    ref.detected = Detected(mime=DOCX, extension=".docm", confidence=1.0, extension_mime=extension_mime("macro.docm"))
    result: ConversionResult = convert_ref(ref, ConvertOptions(), registry=reg)
    assert isinstance(result.input_ref, InputRefInfo)
    assert not [w for w in result.all_warnings if str(w.kind) == "misnamed_file"]


def test_fixture_requires() -> None:
    assert missing_requirements({}) is None
    assert missing_requirements({"requires_modules": ["json"]}) is None
    reason = missing_requirements({"requires_modules": ["ezmd_no_such_module_xyz"]})
    assert reason is not None and "ezmd_no_such_module_xyz" in reason
    unknown = missing_requirements({"requires": ["nonsense"]})
    assert unknown is not None and "unknown extra" in unknown
    import importlib.util

    docs = missing_requirements({"requires": ["docs"]})
    assert (docs is None) == (importlib.util.find_spec("docling") is not None)


def test_fixture_requires_skips_in_score_cli(tmp_path: Path) -> None:
    from typer.testing import CliRunner

    from ezmd.testing.cli import _score_app

    root = tmp_path / "fixtures"
    fx = root / "fam" / "needs-module"
    fx.mkdir(parents=True)
    (root / "thresholds.toml").write_text("default = 0.85\n", encoding="utf-8")
    (fx / "input.txt").write_text("hello\n", encoding="utf-8")
    (fx / "meta.toml").write_text(
        'converter = "text.plain"\nrequires_modules = ["ezmd_no_such_module_xyz"]\n'
        '[provenance]\norigin = "self-generated"\nlicense = "CC0-1.0"\n',
        encoding="utf-8",
    )
    out = CliRunner().invoke(_score_app, [str(fx)])
    assert out.exit_code == 0
    assert "SKIP" in out.output and "ezmd_no_such_module_xyz" in out.output


def test_sidecar_extra_reserved_keys_rejected_at_finalize() -> None:
    doc = Document(
        metadata=Metadata(source="a.py", source_type=SourceType.CODE),
        sidecar_extra={"tables": [{"x": 1}]},
    )
    with pytest.raises(ValueError, match="tables"):
        doc.finalize()
    ok = Document(
        metadata=Metadata(source="a.py", source_type=SourceType.CODE),
        sidecar_extra={"redactions": [{"line": 3, "kind": "aws_key"}]},
    ).finalize()
    assert ok.schema_version == "1.1"


def test_inline_links_counted() -> None:
    p = Paragraph(
        spans=[
            InlineSpan(text="a", href="https://a.example"),
            InlineSpan(text="b", href="https://a.example"),
            InlineSpan(text=" and "),
            InlineSpan(text="c", href="https://c.example"),
        ],
        provenance=Provenance(source="x"),
    )
    assert inline_link_count(p) == 2
    doc = Document(
        metadata=Metadata(source="x", source_type=SourceType.WEB),
        blocks=[p, Link(href="https://d.example", provenance=Provenance(source="x"))],
    ).finalize()
    assert doc.counts().links == 3


def test_metadata_slides_and_sheets_fields() -> None:
    m = Metadata(source="b.xlsx", source_type=SourceType.XLSX, sheets=["Budget", "Hidden"], slides=None)
    assert m.sheets == ["Budget", "Hidden"]
    assert InlineSpan(text="x", change="insert", change_author="Ann", change_id="7").change == "insert"
