"""Text family: plain text and Markdown passthrough."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ezmd.registry import Converter, Unavailable

CHAINS: dict[str, list[str]] = {
    "text/plain": ["text.plain"],
    "text/markdown": ["text.markdown_passthrough", "text.plain"],
}


def converters() -> list[Converter | Unavailable]:
    from ezmd_converters.text.markdown import MarkdownPassthroughConverter
    from ezmd_converters.text.plain import PlainTextConverter

    return [PlainTextConverter(), MarkdownPassthroughConverter()]
