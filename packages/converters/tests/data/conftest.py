from __future__ import annotations

from collections.abc import Callable

import pytest

from ezmd.detect import detect
from ezmd.inputs import InputRef
from ezmd.ir import Document
from ezmd.registry import ConvertOptions, ExtraValue

Convert = Callable[..., Document]


@pytest.fixture
def convert() -> Convert:
    """convert(converter, data, name, **data_options) -> finalized Document (detection run first)."""

    def _run(conv: object, data: bytes, name: str, **opts: ExtraValue) -> Document:
        ref = InputRef.from_bytes(data, filename=name)
        detect(ref)
        options = ConvertOptions(extra={f"data.{k}": v for k, v in opts.items()})
        try:
            return conv.convert(ref, options)  # type: ignore[attr-defined, no-any-return]
        finally:
            ref.cleanup()

    return _run
