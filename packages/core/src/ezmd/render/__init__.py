"""ezmd.render: IR to bytes. Markdown (four profiles), JSON and plain text.

    render(result, profile="full", format="md", **overrides) -> RenderedOutput

`overrides` are profile options (dotted keys for nested rules, string values coerced) plus the render-time
options `converted_at` (alias `now`), `fetched_at`, `sidecar_path` and `cursor`.
"""

from __future__ import annotations

from datetime import UTC, datetime

from ezmd.ir import ConversionResult
from ezmd.profiles import Profile, apply_overrides, get_profile
from ezmd.render.base import Attachment, Chunk, RenderedOutput, Renderer, TokenCounter
from ezmd.render.jsonr import JsonRenderer
from ezmd.render.markdown import MarkdownRenderer, RenderOptions
from ezmd.render.plaintext import TextRenderer
from ezmd.render.tokens import TiktokenCounter, count_tokens

__all__ = [
    "FORMATS",
    "Attachment",
    "Chunk",
    "JsonRenderer",
    "MarkdownRenderer",
    "RenderOptions",
    "RenderedOutput",
    "Renderer",
    "TextRenderer",
    "TiktokenCounter",
    "TokenCounter",
    "count_tokens",
    "render",
]

FORMATS: dict[str, type[MarkdownRenderer] | type[JsonRenderer] | type[TextRenderer]] = {
    "md": MarkdownRenderer,
    "json": JsonRenderer,
    "txt": TextRenderer,
}
_FORMAT_ALIASES = {"markdown": "md", "text": "txt"}
_RENDER_OPTIONS = ("converted_at", "now", "fetched_at", "sidecar_path", "cursor")


def _as_datetime(value: object, key: str) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            raise ValueError(f"invalid datetime for {key!r}: {value!r}") from None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    raise ValueError(f"invalid datetime for {key!r}: {value!r}")


def _as_str(value: object, key: str) -> str | None:
    if value is None or isinstance(value, str):
        return value
    raise ValueError(f"invalid value for {key!r}: {value!r}")


def render(
    result: ConversionResult, profile: str | Profile = "full", format: str = "md", **overrides: object
) -> RenderedOutput:
    """Render a ConversionResult. Unknown formats, profiles and options raise ValueError."""
    fmt = _FORMAT_ALIASES.get(format, format)
    if fmt not in FORMATS:
        raise ValueError(f"unknown format {format!r}; expected one of md, markdown, json, txt")
    opts = {k: overrides.pop(k) for k in _RENDER_OPTIONS if k in overrides}
    prof = get_profile(profile, **overrides) if isinstance(profile, str) else apply_overrides(profile, **overrides)
    options = RenderOptions(
        converted_at=_as_datetime(opts.get("converted_at", opts.get("now")), "converted_at"),
        fetched_at=_as_datetime(opts.get("fetched_at"), "fetched_at"),
        sidecar_path=_as_str(opts.get("sidecar_path"), "sidecar_path"),
        cursor=_as_str(opts.get("cursor"), "cursor"),
    )
    return FORMATS[fmt](options=options).render(result, prof)
