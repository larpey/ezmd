from __future__ import annotations

from pathlib import Path

import pytest

from intomd.cli.options import parse_opts, split_options
from intomd.inputs import InputRef
from intomd.ir import WarningKind
from intomd.pipeline import UnsupportedMediaType, convert_ref
from intomd.registry import ConversionError

ELF = b"\x7fELF\x02\x01\x01\x00" + b"\x00" * 8 + b"\x02\x00\x3e\x00" + b"\x00" * 200


def test_convert_text_end_to_end() -> None:
    r = convert_ref(InputRef.from_bytes(b"Hello\n=====\n\nWorld.\n", filename="a.txt"))
    assert r.converter_id == "text.plain"
    assert r.input_ref.size_bytes == 20 and r.input_ref.sha256
    assert r.document.metadata.title == "Hello"


def test_executable_refused() -> None:
    with pytest.raises(UnsupportedMediaType):
        convert_ref(InputRef.from_bytes(ELF, filename="report.pdf"))


def test_declared_mismatch_warned() -> None:
    ref = InputRef.from_bytes(b"# Title\n\nbody text here\n", filename="a.md", declared_mime="application/pdf")
    r = convert_ref(ref)
    assert WarningKind.CONTENT_TYPE_MISMATCH in [w.kind for w in r.warnings]


def test_misnamed_file_warned() -> None:
    png = bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d4944415478da63f8ff"
        "ff3f0005fe02fea7d6a4c90000000049454e44ae426082"
    )
    with pytest.raises(ConversionError) as ei:
        convert_ref(InputRef.from_bytes(png, filename="notes.txt"))
    assert ei.value.user_message == "This file type is not supported yet."


def test_unsupported_type() -> None:
    with pytest.raises(ConversionError):
        convert_ref(InputRef.from_bytes(b"%PDF-1.7\n" + b"0" * 100, filename="a.pdf"))


def test_opts_parsing() -> None:
    opts = parse_opts(["max_pages=10", "ocr=false", "extra.x=1.5", "chunks.chunk_tokens=512", "languages=en,de"])
    o, prof = split_options(opts)
    assert o.max_pages == 10 and o.ocr is False and o.extra == {"x": 1.5} and o.languages == ["en", "de"]
    assert prof == {"chunks.chunk_tokens": 512}
    with pytest.raises(ValueError):
        parse_opts(["novalue"])
    with pytest.raises(ValueError):
        parse_opts(["=x"])


def test_fixture_input_url_and_options(tmp_path: Path) -> None:
    from intomd.testing.fixtures import Fixture, convert_fixture

    d = tmp_path / "web" / "page"
    d.mkdir(parents=True)
    (d / "input.txt").write_text("Hello\n=====\n\nbody\n", encoding="utf-8")
    meta = {
        "converter": "text.plain",
        "input": {"url": "https://example.org/a/page", "options": {"max_pages": 3, "extra.flag": True}},
    }
    r = convert_fixture(Fixture(path=d, meta=meta))
    assert r.input_ref.display == "https://example.org/a/page"


def test_typescript_is_not_misnamed() -> None:
    from intomd.ir import WarningKind

    src = b"export function greet(name: string): string {\n  return `Hello, ${name}`;\n}\n" * 5
    r = convert_ref(InputRef.from_bytes(src, filename="greet.ts"), converter_id="text.plain")
    assert WarningKind.MISNAMED_FILE not in [w.kind for w in r.all_warnings]


def test_fixture_requires_binaries() -> None:
    from intomd.testing.fixtures import missing_requirements

    assert missing_requirements({"requires_binaries": ["definitely-not-a-real-tool-xyz"]}) is not None
    assert missing_requirements({"requires_binaries": []}) is None
    assert missing_requirements({"requires_binaries": "soffice"}) is not None


def test_counts_include_children() -> None:
    from intomd.ir import Document, Metadata, Paragraph, Provenance, SourceType
    from intomd.ir import InlineSpan as Span

    child = Document(
        metadata=Metadata(source="a.zip!x.txt", source_type=SourceType.TEXT),
        blocks=[Paragraph(spans=[Span(text="two words")], provenance=Provenance(source="x"))],
    )
    parent = Document(metadata=Metadata(source="a.zip", source_type=SourceType.ARCHIVE), children=[child])
    assert parent.counts().paragraphs == 0
    totals = parent.counts(include_children=True)
    assert totals.paragraphs == 1 and totals.words == 2


def test_archive_extensions_map_to_archive_mimes() -> None:
    from intomd.detect import extension_mime

    assert extension_mime("a.7z") == "application/x-7z-compressed"
    assert extension_mime("a.tar") == "application/x-tar"
