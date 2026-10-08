"""Converter authoring checklist (docs/spec/part1.md 5.5), enforced against every registered converter."""

from __future__ import annotations

import re
import time
import tomllib
from pathlib import Path

import pytest

from intomd.detect import detect
from intomd.inputs import Detected, InputRef
from intomd.ir import Document
from intomd.registry import FAMILIES, ConversionError, Converter, ConvertOptions, default_registry

ROOT = Path(__file__).resolve().parents[3]
ID_RE = re.compile(r"^[a-z]+\.[a-z0-9_]+$")
SURROGATE = re.compile("[\ud800-\udfff]")

CONVERTERS: list[Converter] = default_registry().available()


def _ids() -> list[str]:
    return [c.id for c in CONVERTERS]


def _text_of(doc: Document) -> list[str]:
    out = [doc.plain_text()]
    for b in doc.blocks:
        out.append(b.model_dump_json())
    return out


def test_registry_has_builtins() -> None:
    assert {"text.plain", "text.markdown_passthrough"} <= set(_ids())


@pytest.mark.parametrize("conv", CONVERTERS, ids=_ids())
def test_id_and_family(conv: Converter) -> None:
    assert ID_RE.match(conv.id), conv.id
    assert conv.family in FAMILIES
    assert conv.id.split(".", 1)[0] == conv.family or conv.family in conv.id


@pytest.mark.parametrize("conv", CONVERTERS, ids=_ids())
def test_can_handle_nothing_is_zero_and_fast(conv: Converter) -> None:
    ref = InputRef.from_bytes(b"x", filename="x")
    ref.detected = Detected(mime="application/x-intomd-nothing", extension=None, confidence=1.0)
    assert conv.can_handle(ref) == 0.0
    # Best of 5 so one scheduler hiccup on a shared CI runner cannot fail the 10 ms contract.
    timings = []
    for _ in range(5):
        t0 = time.perf_counter()
        conv.can_handle(ref)
        timings.append(time.perf_counter() - t0)
    assert min(timings) < 0.01


@pytest.mark.parametrize("conv", CONVERTERS, ids=_ids())
def test_empty_file(conv: Converter) -> None:
    ref = InputRef.from_bytes(b"", filename="empty")
    detect(ref)
    try:
        doc = conv.convert(ref, ConvertOptions())
    except ConversionError:
        return
    assert doc.blocks or doc.warnings, "empty Document with no warnings"
    assert doc.content_hash


@pytest.mark.parametrize("conv", CONVERTERS, ids=_ids())
@pytest.mark.parametrize("payload", [b"a", b"\x00", b"\xff", b"#"])
def test_one_byte_file(conv: Converter, payload: bytes) -> None:
    ref = InputRef.from_bytes(payload, filename="one")
    detect(ref)
    try:
        doc = conv.convert(ref, ConvertOptions())
    except ConversionError:
        return
    _check_doc(doc)


def _check_doc(doc: Document) -> None:
    assert doc.content_hash, "finalize() not called"
    for b in doc.blocks:
        assert b.provenance.source
    for t in _text_of(doc):
        assert "\x00" not in t and "\\u0000" not in t
        assert not SURROGATE.search(t)


@pytest.mark.parametrize("conv", CONVERTERS, ids=_ids())
def test_hostile_text_is_clean(conv: Converter) -> None:
    ref = InputRef.from_bytes(b"# Head\x00ing\n\nbody \xed\xa0\x80 text\xe2\x80\xae\n", filename="h.md")
    detect(ref)
    try:
        doc = conv.convert(ref, ConvertOptions())
    except ConversionError:
        return
    _check_doc(doc)


@pytest.mark.parametrize("conv", CONVERTERS, ids=_ids())
# Converters that are only available when a system tool is installed, and whose golden therefore has to
# be generated on a machine that has it. Tracked for the fixture corpus task (P1-T19).
NEEDS_TOOL_FOR_FIXTURE = {"documents.libreoffice": "soffice (LibreOffice) is needed to generate the golden"}


def test_has_fixture(conv: Converter) -> None:
    if conv.id in NEEDS_TOOL_FOR_FIXTURE:
        pytest.skip(NEEDS_TOOL_FOR_FIXTURE[conv.id])
    metas = list((ROOT / "fixtures").glob("*/*/meta.toml"))
    used = {tomllib.loads(m.read_text(encoding="utf-8")).get("converter") for m in metas}
    assert conv.id in used, f"{conv.id} has no fixture under fixtures/"
