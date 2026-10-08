"""ConvertContext, experimental exclusion, and truncation (D-0017 item 2)."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest
from core_factories import P, S

from ezmd.context import ConvertContext, Limits
from ezmd.inputs import MAX_FETCH_DEPTH, Detected, FetchRequired, InputRef
from ezmd.ir import Document, Metadata, Paragraph, SourceType, Warning, WarningKind
from ezmd.registry import ConversionError, ConverterRegistry, ConvertOptions


@dataclass
class Conv:
    id: str
    behavior: str = "ok"  # ok | page_cap | doc_truncated | timeout_partial | timeout | child | slow_child
    experimental: bool = False
    confidence: float = 0.5
    family: str = "text"
    priority: int = 0
    requires_extras: tuple[str, ...] = ()
    mimes: tuple[str, ...] = ("text/plain",)
    limits: Limits = field(default_factory=lambda: Limits(max_pages=7))
    seen: list[object] = field(default_factory=list)

    def can_handle(self, ref: InputRef) -> float:
        return self.confidence

    def convert(self, ref: InputRef, options: ConvertOptions) -> Document:
        ctx = options.ctx
        self.seen.append((ctx.depth, ctx.limits))
        doc = Document(metadata=Metadata(source=ref.display, source_type=SourceType.TEXT))
        doc.blocks.append(Paragraph(spans=[S(self.id)], provenance=P()))
        match self.behavior:
            case "page_cap":
                doc.warnings.append(Warning(kind=WarningKind.PAGE_CAP_REACHED, message="cap"))
            case "doc_truncated":
                doc.truncated = True
            case "timeout_partial":
                ctx.publish_partial(doc)
                options.max_seconds = 0
                ctx.check_deadline()
            case "timeout":
                options.max_seconds = 0
                ctx.check_deadline()
            case "child":
                child = ctx.convert_child(_ref(), label="inner.txt")
                doc.blocks.append(Paragraph(spans=[S(f"child:{child.converter_id}")], provenance=P()))
                self.seen.append(child)
        return doc.finalize()


def _ref() -> InputRef:
    r = InputRef.from_bytes(b"hello", filename="a.txt")
    r.detected = Detected(mime="text/plain", extension=".txt", confidence=1.0)
    return r


def _registry(*convs: Conv) -> ConverterRegistry:
    reg = ConverterRegistry()
    for c in convs:
        reg.register(c)
    return reg


def test_default_context_is_noop_and_bound_to_options() -> None:
    opts = ConvertOptions()
    opts.ctx.progress("parse", 0.5, "half")  # no callback: nothing happens
    opts.ctx.check_deadline()
    remaining = opts.ctx.remaining()
    assert remaining is not None and remaining > 0
    assert ConvertContext().remaining() is None
    ConvertContext().check_deadline()  # unbound: never raises


def test_progress_callback_and_clamping() -> None:
    calls: list[tuple[str, float | None, str]] = []
    ctx = ConvertContext(on_progress=lambda s, f, m: calls.append((s, f, m)))
    ctx.progress("pages", 1.7, "done")
    ctx.progress("pages", None, "?")

    def boom(stage: str, fraction: float | None, message: str) -> None:
        raise RuntimeError("sink down")

    ConvertContext(on_progress=boom).progress("x", 0.1, "")  # logged, not raised
    assert calls == [("pages", 1.0, "done"), ("pages", None, "?")]


def test_check_deadline_raises_timeout() -> None:
    opts = ConvertOptions(max_seconds=0)
    with pytest.raises(ConversionError) as ei:
        opts.ctx.check_deadline()
    assert ei.value.code == "timeout" and not ei.value.retryable_with_fallback
    assert "time limit" in ei.value.user_message


def test_registry_binds_limits_and_depth() -> None:
    conv = Conv("text.a")
    res = _registry(conv).convert(_ref(), ConvertOptions())
    assert conv.seen[0] == (0, Limits(max_pages=7))
    assert res.converter_id == "text.a" and not res.truncated


def test_timeout_returns_published_partial() -> None:
    res = _registry(Conv("text.a", "timeout_partial")).convert(_ref(), ConvertOptions())
    assert res.truncated and res.document.truncated
    assert WarningKind.TIMEOUT_PARTIAL in [w.kind for w in res.document.warnings]


def test_timeout_without_partial_fails_without_fallback() -> None:
    reg = _registry(Conv("text.a", "timeout", confidence=0.9), Conv("text.b"))
    with pytest.raises(ConversionError) as ei:
        reg.convert(_ref(), ConvertOptions())
    assert ei.value.code == "timeout"


def test_convert_child_depth_and_shared_deadline() -> None:
    conv = Conv("text.a", "child")
    reg = _registry(conv)
    res = reg.convert(_ref(), ConvertOptions(max_attachment_depth=1))
    child = conv.seen[-1]
    assert conv.seen[1][0] == 1  # type: ignore[index]  # the child ran at depth 1
    assert "child:text.a" in res.document.plain_text()
    # At depth 1 the grandchild exceeds max_attachment_depth=1 and is skipped, not converted.
    assert child.converter_id == "text.a"  # type: ignore[attr-defined]
    grand = child.document.plain_text()  # type: ignore[attr-defined]
    assert "child:" in grand


def test_convert_child_refused_beyond_depth() -> None:
    opts = ConvertOptions(max_attachment_depth=0)
    out = opts.ctx.convert_child(_ref(), label="deep.txt")
    assert not out.document.blocks
    assert [w.kind for w in out.document.warnings] == [WarningKind.ATTACHMENT_SKIPPED]
    off = ConvertOptions(follow_attachments=False).ctx.convert_child(_ref(), label="x.txt")
    assert off.document.warnings[0].kind == WarningKind.ATTACHMENT_SKIPPED


def test_convert_child_shares_parent_deadline() -> None:
    seen: list[float] = []

    @dataclass
    class Probe(Conv):
        def convert(self, ref: InputRef, options: ConvertOptions) -> Document:
            seen.append(options.deadline())
            return super().convert(ref, options)

    reg = _registry(Probe("text.p"))
    parent = ConvertOptions(max_seconds=100)
    parent.ctx.bind(parent, reg)
    parent.ctx.convert_child(_ref(), label="inner.txt")
    assert seen and seen[0] <= 90.5  # 10 percent of the remaining budget stays with the parent
    expired = ConvertOptions(max_seconds=0)
    with pytest.raises(ConversionError):
        expired.ctx.convert_child(_ref(), label="late.txt")


def test_experimental_excluded_when_disabled() -> None:
    reg = _registry(Conv("text.exp", experimental=True, confidence=0.9), Conv("text.stable", confidence=0.4))
    assert [c.id for _, c in reg.candidates(_ref(), ConvertOptions(experimental=False))] == ["text.stable"]
    assert [c.id for _, c in reg.candidates(_ref())] == ["text.exp", "text.stable"]
    res = reg.convert(_ref(), ConvertOptions(experimental=False))
    assert res.converter_id == "text.stable"
    on = reg.convert(_ref(), ConvertOptions())
    assert WarningKind.EXPERIMENTAL_CONVERTER in [w.kind for w in on.warnings]


def test_experimental_disabled_error() -> None:
    reg = _registry(Conv("text.exp", experimental=True))
    with pytest.raises(ConversionError) as ei:
        reg.convert(_ref(), ConvertOptions(experimental=False))
    assert ei.value.code == "experimental_disabled" and "experimental" in ei.value.user_message
    with pytest.raises(ConversionError) as forced:
        reg.convert(_ref(), ConvertOptions(experimental=False), converter_id="text.exp")
    assert forced.value.code == "experimental_disabled"
    with pytest.raises(ConversionError) as none:
        ConverterRegistry().convert(_ref(), ConvertOptions(experimental=False))
    assert none.value.code == "conversion_failed"


@pytest.mark.parametrize(("behavior", "expected"), [("ok", False), ("page_cap", True), ("doc_truncated", True)])
def test_truncated_is_or_over_codes_and_document(behavior: str, expected: bool) -> None:
    res = _registry(Conv("text.a", behavior)).convert(_ref(), ConvertOptions())
    assert res.truncated is expected


def test_fetch_required_depth() -> None:
    e = FetchRequired("https://e.org", residential=False, reason="r", fetch_depth=1)
    assert e.fetch_depth == 1 and FetchRequired("u", False, "r").fetch_depth == 0
    assert MAX_FETCH_DEPTH == 2
