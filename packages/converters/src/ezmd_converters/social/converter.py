"""Experimental stub converter around one `SocialAdapter` (enabled only with EZMD_ENABLE_SOCIAL=1).

No network of its own: without a body it raises `FetchRequired` for the adapter's API URL; with a body (the
pipeline's fetch of that URL, or an uploaded recorded response) it parses and renders the thread.
"""

from __future__ import annotations

from ezmd.context import Limits
from ezmd.inputs import FetchRequired, InputRef
from ezmd.ir import Document
from ezmd.registry import ConversionError, ConvertOptions
from ezmd_converters.social.adapters import AdapterError, SocialAdapter
from ezmd_converters.social.render import thread_document

DEFAULT_MAX_COMMENTS = 200
MAX_BYTES = 20 * 1024 * 1024


class SocialStubConverter:
    family = "web"
    priority = 40
    experimental = True
    requires_extras: tuple[str, ...] = ()
    mimes: tuple[str, ...] = ("application/json", "text/plain", "text/x-uri")
    limits = Limits(max_bytes=MAX_BYTES, max_entries=DEFAULT_MAX_COMMENTS)

    def __init__(self, adapter: SocialAdapter, converter_id: str) -> None:
        self.adapter = adapter
        self.id = converter_id

    def _url(self, ref: InputRef) -> str | None:
        for candidate in (ref.url, ref.display):
            if candidate and self.adapter.thread_id(candidate) is not None:
                return candidate
        return None

    def can_handle(self, ref: InputRef) -> float:
        if self._url(ref) is None:
            return 0.0
        mime = ref.detected.mime if ref.detected else None
        if ref.has_body and mime not in self.mimes:
            return 0.0
        return 0.9

    def convert(self, ref: InputRef, options: ConvertOptions) -> Document:
        url = self._url(ref)
        if url is None:
            raise ConversionError(f"not a {self.adapter.name} thread: {ref.display}", user_message="Not a thread URL.")
        sort = str(options.extra.get("social.sort", "confidence"))
        if not ref.has_body:
            raise FetchRequired(
                self.adapter.api_url(url, sort=sort), residential=False, reason="thread JSON not fetched"
            )
        if ref.size() > MAX_BYTES:
            raise ConversionError("thread response too large", user_message="The thread is too large.")
        try:
            thread = self.adapter.parse(ref.read(), url)
        except AdapterError as e:
            raise ConversionError(str(e), user_message="The thread API did not return the expected JSON.") from e
        raw_max = options.extra.get("social.max_comments", DEFAULT_MAX_COMMENTS)
        max_comments = raw_max if isinstance(raw_max, int) and raw_max >= 0 else DEFAULT_MAX_COMMENTS
        options.ctx.check_deadline()
        return thread_document(thread, source=url, engine=self.id, max_comments=max_comments).finalize()
