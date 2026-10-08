"""ezmd.render.jsonr: the `json` format, a payload of {markdown, frontmatter, sidecar, chunks}."""

from __future__ import annotations

import json

from ezmd.ir import ConversionResult
from ezmd.profiles import Profile
from ezmd.render.base import RenderedOutput, TokenCounter
from ezmd.render.markdown import RenderOptions, render_markdown
from ezmd.render.tokens import TiktokenCounter

__all__ = ["JsonRenderer"]


class JsonRenderer:
    """Wraps the Markdown rendering in a JSON document. `markdown` and `body` hold the JSON text."""

    format = "json"

    def __init__(self, counter: TokenCounter | None = None, options: RenderOptions | None = None) -> None:
        self.counter: TokenCounter = counter or TiktokenCounter()
        self.options = options or RenderOptions()

    def render(self, result: ConversionResult, profile: Profile) -> RenderedOutput:
        md = render_markdown(result, profile, self.options, self.counter)
        payload = {
            "markdown": md.markdown,
            "frontmatter": md.frontmatter,
            "sidecar": md.sidecar,
            "chunks": [c.to_dict() for c in md.chunks],
        }
        text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        return RenderedOutput(
            markdown=text,
            frontmatter=md.frontmatter,
            sidecar=md.sidecar,
            chunks=md.chunks,
            attachments=md.attachments,
            tokens=md.tokens,
            truncated=md.truncated,
            warnings=md.warnings,
            injection_risk=md.injection_risk,
            body=text,
        )
