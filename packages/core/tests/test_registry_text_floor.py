"""Unclaimed text falls to the plain-text converter instead of "no converter" (the text floor)."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest
from core_factories import P, S

from ezmd.inputs import Detected, InputRef
from ezmd.ir import Document, Metadata, Paragraph, SourceType, WarningKind
from ezmd.registry import ConversionError, ConverterRegistry, ConvertOptions, mime_matches


@dataclass
class Picky:
    """A converter that claims only its MIME types, like the real ones."""

    id: str
    mimes: tuple[str, ...]
    confidence: float = 0.5
    priority: int = 0
    family: str = "text"
    experimental: bool = False
    requires_extras: tuple[str, ...] = ()
    calls: list[str] = field(default_factory=list)

    def can_handle(self, ref: InputRef) -> float:
        mime = ref.detected.mime if ref.detected else None
        return self.confidence if mime and any(mime_matches(m, mime) for m in self.mimes) else 0.0

    def convert(self, ref: InputRef, options: ConvertOptions) -> Document:
        self.calls.append(ref.display)
        doc = Document(metadata=Metadata(source=ref.display, source_type=SourceType.TEXT))
        doc.blocks.append(Paragraph(spans=[S(self.id)], provenance=P()))
        return doc.finalize()


def _ref(data: bytes, name: str, mime: str) -> InputRef:
    r = InputRef.from_bytes(data, filename=name)
    r.detected = Detected(mime=mime, extension="." + name.rsplit(".", 1)[-1], confidence=0.8)
    return r


def _registry() -> tuple[ConverterRegistry, Picky]:
    text = Picky("text.plain", ("text/plain", "text/*"))
    reg = ConverterRegistry()
    reg.register(Picky("data.json", ("application/json",)))
    reg.register(text)
    return reg, text


def test_text_with_an_unclaimed_type_is_read_as_plain_text() -> None:
    reg, text = _registry()
    sql = b"select name, qty from orders where qty > 3 order by name;\n" * 20
    res = reg.convert(_ref(sql, "report.sql", "application/x-sql"), ConvertOptions())
    assert res.converter_id == "text.plain" and text.calls == ["report.sql"]
    kinds = [w.kind for w in res.warnings]
    assert WarningKind.UNKNOWN_TYPE_READ_AS_TEXT in kinds and WarningKind.ENGINE_FALLBACK not in kinds
    assert res.warnings[0].detail["mime"] == "application/x-sql"


def test_binary_with_an_unclaimed_type_is_still_refused() -> None:
    reg, text = _registry()
    noise = bytes(range(256)) * 8
    with pytest.raises(ConversionError, match="no converter for"):
        reg.convert(_ref(noise, "blob.dat", "application/x-unknown-binary"), ConvertOptions())
    assert text.calls == []


def test_the_floor_needs_the_plain_text_converter() -> None:
    reg = ConverterRegistry()
    reg.register(Picky("data.json", ("application/json",)))
    with pytest.raises(ConversionError, match="no converter for"):
        reg.convert(_ref(b"plain words\n" * 10, "a.sql", "application/x-sql"), ConvertOptions())
