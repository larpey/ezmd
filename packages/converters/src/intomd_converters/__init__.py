"""Built-in converters for intomd. `builtin_converters()` is called by `intomd.builtin`."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from intomd.registry import Converter


def builtin_converters() -> list[Converter]:
    from intomd_converters.text.markdown import MarkdownPassthroughConverter
    from intomd_converters.text.plain import PlainTextConverter

    return [PlainTextConverter(), MarkdownPassthroughConverter()]
