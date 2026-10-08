"""The three web/pages converters (docs/spec/part2.md section 5).

- `web.trafilatura`: Trafilatura chooses the article; blocks are rebuilt from the matching DOM elements.
  Falls back to the rule extractor when Trafilatura returns under 200 characters or under 25 percent of the
  page text, and to the full body when no paragraph survives.
- `web.rules`: Defuddle-style rules (boilerplate removal by tag, role, and class/id; main-content selection).
- `web.html_raw`: the whole `<body>` with only structural boilerplate removed; warns
  `readability_fallback_full_body`.

All three run the same hygiene pass and metadata extraction, accept `text/html` and `application/xhtml+xml`
bodies, and never fetch. `ref.url` (the final URL) resolves relative links; without it `<base href>` is used,
and otherwise links stay relative.
"""

from __future__ import annotations

from intomd.context import Limits
from intomd.inputs import InputRef
from intomd.ir import Document
from intomd.registry import ConvertOptions
from intomd_converters.web.pipeline import DEFAULT_MAX_BYTES, Engine, build_document

MIMES = ("text/html", "application/xhtml+xml")
WEB_LIMITS = Limits(max_bytes=DEFAULT_MAX_BYTES, timeout_s=45.0)


class _WebConverter:
    id = "web.base"
    family = "web"
    priority = 0
    experimental = False
    requires_extras: tuple[str, ...] = ()
    mimes: tuple[str, ...] = MIMES
    limits = WEB_LIMITS
    engine: Engine = "rules"
    confidence = 0.8

    def can_handle(self, ref: InputRef) -> float:
        mime = ref.detected.mime if ref.detected else None
        if mime in MIMES and ref.has_body:
            return self.confidence
        return 0.0

    def convert(self, ref: InputRef, options: ConvertOptions) -> Document:
        return build_document(ref, options, self.engine, self.id)


class TrafilaturaConverter(_WebConverter):
    id = "web.trafilatura"
    priority = 20
    engine: Engine = "trafilatura"
    confidence = 0.9


class RulesConverter(_WebConverter):
    id = "web.rules"
    priority = 10
    engine: Engine = "rules"
    confidence = 0.85


class FullBodyConverter(_WebConverter):
    id = "web.html_raw"
    priority = 0
    engine: Engine = "full_body"
    confidence = 0.5
