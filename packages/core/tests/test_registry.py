from __future__ import annotations

import importlib.metadata as md
from dataclasses import dataclass, field

import pytest
from core_factories import P, S

from ezmd.inputs import Detected, FetchRequired, InputRef
from ezmd.ir import Document, Metadata, Paragraph, SourceType, Warning, WarningKind
from ezmd.registry import ConversionError, ConverterRegistry, ConvertOptions, mime_matches


@dataclass
class Fake:
    id: str
    confidence: float = 0.5
    priority: int = 0
    behavior: str = "ok"  # ok | error | fatal | crash | empty | empty_warned | fetch
    family: str = "text"
    experimental: bool = False
    requires_extras: tuple[str, ...] = ()
    mimes: tuple[str, ...] = ("text/plain",)
    calls: list[str] = field(default_factory=list)

    def can_handle(self, ref: InputRef) -> float:
        return self.confidence

    def convert(self, ref: InputRef, options: ConvertOptions) -> Document:
        self.calls.append(ref.display)
        doc = Document(metadata=Metadata(source=ref.display, source_type=SourceType.TEXT))
        match self.behavior:
            case "error":
                raise ConversionError("nope", user_message="Nope.")
            case "fatal":
                raise ConversionError("fatal", user_message="Fatal.", retryable_with_fallback=False)
            case "crash":
                raise RuntimeError("engine bug")
            case "fetch":
                raise FetchRequired("https://e.org/x", residential=False, reason="need body")
            case "empty":
                return doc.finalize()
            case "empty_warned":
                doc.warnings.append(Warning(kind=WarningKind.PAGES_WITHOUT_TEXT, message="no text"))
                return doc.finalize()
        doc.blocks.append(Paragraph(spans=[S(self.id)], provenance=P()))
        return doc.finalize()


def ref(mime: str = "text/plain") -> InputRef:
    r = InputRef.from_bytes(b"hello", filename="a.txt")
    r.detected = Detected(mime=mime, extension=".txt", confidence=1.0)
    return r


def registry(*fakes: Fake) -> ConverterRegistry:
    reg = ConverterRegistry()
    for f in fakes:
        reg.register(f)
    return reg


def test_resolution_order_confidence_then_priority_then_id() -> None:
    reg = registry(Fake("text.b", 0.5, 1), Fake("text.a", 0.5, 1), Fake("text.c", 0.9, 0), Fake("text.z", 0.0, 99))
    assert [c.id for _, c in reg.candidates(ref())] == ["text.c", "text.a", "text.b"]


def test_duplicate_registration_rejected() -> None:
    reg = registry(Fake("text.a"))
    with pytest.raises(ValueError, match="duplicate"):
        reg.register(Fake("text.a"))


def test_chain_overrides_confidence_and_skips_unknown_ids() -> None:
    reg = registry(Fake("text.hi", 0.9), Fake("text.lo", 0.2))
    reg.set_chain("text/plain", ["text.missing", "text.lo", "text.hi"])
    assert [c.id for _, c in reg.candidates(ref())] == ["text.lo", "text.hi"]


def test_wildcard_chain_matched_after_exact() -> None:
    reg = registry(Fake("text.a", 0.5), Fake("text.b", 0.5))
    reg.set_chain("audio/*", ["text.b", "text.a"])
    reg.set_chain("*/*", ["text.a"])
    assert [c.id for _, c in reg.candidates(ref("audio/mpeg"))] == ["text.b", "text.a"]
    assert [c.id for _, c in reg.candidates(ref("video/mp4"))] == ["text.a"]
    reg.set_chain("audio/mpeg", ["text.a"])
    assert [c.id for _, c in reg.candidates(ref("audio/mpeg"))] == ["text.a"]


def test_mime_matches() -> None:
    assert mime_matches("audio/*", "audio/wav") and not mime_matches("audio/*", "video/mp4")
    assert mime_matches("*/*", "x/y") and mime_matches("a/b", "a/b") and not mime_matches("a/b", "a/c")


@pytest.mark.parametrize("behavior", ["error", "crash", "empty"])
def test_fallback_to_next_converter(behavior: str) -> None:
    first, second = Fake("text.first", 0.9, behavior=behavior), Fake("text.second", 0.5)
    res = registry(first, second).convert(ref(), ConvertOptions())
    assert res.converter_id == "text.second"
    assert res.metrics.engines_tried == ["text.first", "text.second"]
    assert [w.kind for w in res.warnings] == [WarningKind.ENGINE_FALLBACK]
    assert res.document.converter_id == "text.second"


def test_non_retryable_error_stops_chain() -> None:
    second = Fake("text.second", 0.5)
    with pytest.raises(ConversionError) as ei:
        registry(Fake("text.first", 0.9, behavior="fatal"), second).convert(ref(), ConvertOptions())
    assert ei.value.user_message == "Fatal."
    assert second.calls == []


def test_all_fail_reports_tried_ids_and_last_user_message() -> None:
    with pytest.raises(ConversionError) as ei:
        registry(Fake("text.a", 0.9, behavior="crash"), Fake("text.b", 0.5, behavior="error")).convert(
            ref(), ConvertOptions()
        )
    assert "text.a" in str(ei.value) and "text.b" in str(ei.value)
    assert ei.value.user_message == "Nope."
    assert ei.value.retryable_with_fallback is False


def test_empty_with_warnings_is_last_resort() -> None:
    res = registry(Fake("text.a", 0.9, behavior="empty_warned"), Fake("text.b", 0.5, behavior="error")).convert(
        ref(), ConvertOptions()
    )
    assert res.converter_id == "text.a"
    assert res.document.blocks == []
    assert [w.kind for w in res.all_warnings] == [WarningKind.PAGES_WITHOUT_TEXT]


def test_fetch_required_passes_through() -> None:
    with pytest.raises(FetchRequired):
        registry(Fake("text.a", 0.9, behavior="fetch"), Fake("text.b", 0.5)).convert(ref(), ConvertOptions())


def test_no_candidates() -> None:
    with pytest.raises(ConversionError) as ei:
        registry(Fake("text.a", 0.0)).convert(ref(), ConvertOptions())
    assert ei.value.user_message == "This file type is not supported yet."


def test_explicit_converter_id_and_unknown_id() -> None:
    reg = registry(Fake("text.a", 0.9), Fake("text.b", 0.0))
    assert reg.convert(ref(), ConvertOptions(), converter_id="text.b").converter_id == "text.b"
    with pytest.raises(ConversionError):
        reg.convert(ref(), ConvertOptions(), converter_id="text.zzz")


def test_experimental_warning() -> None:
    res = registry(Fake("text.x", 0.9, experimental=True)).convert(ref(), ConvertOptions())
    assert WarningKind.EXPERIMENTAL_CONVERTER in [w.kind for w in res.warnings]


class _EP:
    def __init__(self, name: str, obj: object, fail: bool = False) -> None:
        self.name = name
        self._obj = obj
        self._fail = fail
        self.dist = None

    def load(self) -> object:
        if self._fail:
            raise ImportError("missing dependency")
        return self._obj


def test_broken_entry_point_is_isolated() -> None:
    reg = ConverterRegistry()
    eps = [_EP("good", lambda: Fake("text.plugin", 0.9)), _EP("bad", None, fail=True), _EP("notconv", lambda: 42)]
    reg.load_entry_points(lambda: eps)  # type: ignore[arg-type,return-value]
    ids = {r.converter.id: r for r in reg.registrations()}
    assert "text.plugin" in ids and ids["text.plugin"].import_error is None
    assert ids["broken.bad"].import_error == "missing dependency"
    assert "broken.notconv" in ids
    assert [c.id for c in reg.available()] == ["text.plugin"]
    with pytest.raises(KeyError):
        reg.get("broken.bad")
    assert reg.convert(ref(), ConvertOptions()).converter_id == "text.plugin"


def test_entry_point_group_name() -> None:
    assert ConverterRegistry.ENTRY_POINT_GROUP == "ezmd.converters"
    assert isinstance(md.entry_points(group=ConverterRegistry.ENTRY_POINT_GROUP), md.EntryPoints)


def test_deadline() -> None:
    o = ConvertOptions(max_seconds=100)
    assert 99 < o.deadline() <= 100
    o2 = ConvertOptions(max_seconds=0)
    assert o2.deadline() <= 0


def test_unavailable_converter_is_listed_and_skipped() -> None:
    from ezmd.registry import Unavailable

    reg = ConverterRegistry()
    reg.register(
        Unavailable(id="text.heavy", family="text", reason="needs the [docs] extra", requires_extras=("docs",))
    )
    reg.register(Fake("text.light", 0.5))
    reg.set_chain("text/plain", ["text.heavy", "text.light"])
    regs = {r.converter.id: r for r in reg.registrations()}
    assert regs["text.heavy"].import_error == "needs the [docs] extra"
    assert [c.id for c in reg.available()] == ["text.light"]
    assert reg.convert(ref(), ConvertOptions()).converter_id == "text.light"


def test_family_discovery_and_chains() -> None:
    import ezmd_converters

    assert "text" in ezmd_converters.family_names()
    ids = {c.id for c in ezmd_converters.builtin_converters()}
    assert {"text.plain", "text.markdown_passthrough"} <= ids
    assert ezmd_converters.builtin_chains()["text/markdown"][0] == "text.markdown_passthrough"


def test_specialist_outranks_chain_members() -> None:
    reg = registry(Fake("text.generic", 0.9), Fake("code.special", 0.95), Fake("code.weak", 0.3))
    reg.set_chain("text/plain", ["text.generic"])
    assert [c.id for _, c in reg.candidates(ref())] == ["code.special", "text.generic"]
    reg2 = registry(Fake("text.generic", 0.9), Fake("code.weaker", 0.5))
    reg2.set_chain("text/plain", ["text.generic"])
    assert [c.id for _, c in reg2.candidates(ref())] == ["text.generic"]
