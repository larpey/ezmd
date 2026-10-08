from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from intomd.detect import detect
from intomd.inputs import InputRef
from intomd.ir import Document
from intomd.registry import ConvertOptions

FIXTURES = Path(__file__).resolve().parents[4] / "fixtures" / "office"

Convert = Callable[..., Document]


def _run(conv: object, data: bytes, name: str, **extra: object) -> Document:
    ref = InputRef.from_bytes(data, filename=name)
    detect(ref)
    flags = {k: extra.pop(k) for k in ("tracked_changes", "comments", "formulas") if isinstance(extra.get(k), bool)}
    opts = ConvertOptions(extra={f"office.{k}": v for k, v in extra.items()}, **flags)  # type: ignore[arg-type]
    try:
        return conv.convert(ref, opts)  # type: ignore[attr-defined, no-any-return]
    finally:
        ref.cleanup()


@pytest.fixture
def run() -> Callable[..., Document]:
    return _run


@pytest.fixture
def fixture_bytes() -> Callable[[str], bytes]:
    def get(name: str) -> bytes:
        d = FIXTURES / name
        return next(p for p in d.iterdir() if p.name.startswith("input.")).read_bytes()

    return get
