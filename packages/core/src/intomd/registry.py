"""intomd.registry: converter protocol, options, registry with priority resolution, fallback chains,
and entry-point plugin discovery.

Implemented from docs/spec/part1.md section 5.2, plus wildcard chain matching (section 5.3).
"""

from __future__ import annotations

import importlib.metadata as md
import logging
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from intomd.inputs import FetchRequired, InputRef
from intomd.ir import ConversionResult, Document, Metrics, Warning, WarningKind

log = logging.getLogger(__name__)

FAMILIES = frozenset(
    {"documents", "web", "media", "images", "code", "comms", "data", "notes", "specialized", "text", "archives"}
)


class ConversionError(Exception):
    """A converter could not produce a Document. `retryable_with_fallback` tells the registry whether
    to try the next converter in the chain. `user_message` is safe to show to end users."""

    def __init__(self, message: str, *, user_message: str | None = None, retryable_with_fallback: bool = True) -> None:
        super().__init__(message)
        self.user_message = user_message or "Conversion failed."
        self.retryable_with_fallback = retryable_with_fallback


ExtraValue = str | int | float | bool


@dataclass(slots=True)
class ConvertOptions:
    """Options every converter receives. Converters read what they need and ignore the rest.
    Family-specific options go in `extra` and are documented per converter in Part 2."""

    max_pages: int | None = 500
    max_duration_seconds: float | None = 3 * 3600
    max_seconds: float = 600.0
    """Wall-clock budget for this conversion. Converters check `deadline()` in long loops."""
    ocr: bool = True
    """Allow OCR fallback when a page has no text layer."""
    asr_model: str | None = None
    diarize: bool = True
    languages: list[str] = field(default_factory=list)
    """Hint list of BCP-47 codes; empty means auto-detect."""
    extract_images: bool = True
    image_dir: str | None = None
    """Where extracted images are written (blob store key prefix or local dir). None disables extraction."""
    follow_attachments: bool = True
    max_attachment_depth: int = 3
    allow_network: bool = False
    """Whether the converter may make outbound requests beyond the already-fetched input (web crawl, feed follow).
    Workers run with this False unless the job is a fetch job."""
    tracked_changes: bool = True
    comments: bool = True
    formulas: bool = True
    gpu: bool = False
    extra: dict[str, ExtraValue] = field(default_factory=dict)
    _started: float = field(default_factory=time.monotonic)

    def deadline(self) -> float:
        """Seconds remaining. Converters raise ConversionError(retryable_with_fallback=False) when <= 0."""
        return self.max_seconds - (time.monotonic() - self._started)

    def restart_clock(self) -> None:
        self._started = time.monotonic()


@runtime_checkable
class Converter(Protocol):
    """A converter turns one InputRef into one Document.

    id: stable identifier `family.engine`, e.g. `documents.docling_pdf`, `web.trafilatura`.
    family: one of FAMILIES.
    priority: tie-breaker when two converters return equal confidence; higher wins.
    experimental: when True, every result gets an EXPERIMENTAL_CONVERTER warning.
    requires_extras: pip extras needed; the registry skips converters whose imports fail and logs why.
    mimes: mime types (may include wildcards) the converter is designed for; informational, used by
        capabilities. Resolution still goes through `can_handle`.
    """

    id: str
    family: str
    priority: int
    experimental: bool
    requires_extras: tuple[str, ...]
    mimes: tuple[str, ...]

    def can_handle(self, ref: InputRef) -> float:
        """Confidence in [0, 1] that this converter should handle `ref`. 0 means no. Use `ref.detected.mime`,
        `ref.display`, and `ref.url`. Must be cheap: no I/O beyond what is already loaded."""
        ...

    def convert(self, ref: InputRef, options: ConvertOptions) -> Document:
        """Produce a finalized Document or raise ConversionError. Must not catch BaseException.
        Must call `document.finalize()`. May raise FetchRequired for URL inputs without a body."""
        ...


@dataclass(slots=True)
class Registration:
    converter: Converter
    source: str
    """'builtin' or the entry point's distribution name."""
    import_error: str | None = None


def mime_matches(pattern: str, mime: str) -> bool:
    """`audio/*` matches `audio/mpeg`; `*/*` matches anything; otherwise exact."""
    if pattern == mime or pattern == "*/*":
        return True
    if pattern.endswith("/*"):
        return mime.split("/", 1)[0] == pattern[:-2]
    return False


EntryPointsFn = Callable[[], Iterable[md.EntryPoint]]


def _default_entry_points() -> Iterable[md.EntryPoint]:
    return md.entry_points(group=ConverterRegistry.ENTRY_POINT_GROUP)


class ConverterRegistry:
    """Holds converters, resolves the best one for an input, runs fallback chains.

    Resolution: all converters' `can_handle` are called; those returning > 0 are sorted by
    (confidence desc, priority desc, id asc). The pipeline tries them in that order until one succeeds
    or a ConversionError with retryable_with_fallback=False is raised. Explicit chains (section 5.3)
    can pin an order for a mime type and override confidence sorting. Exact chain keys are matched
    before wildcard keys; among wildcards the most specific (`audio/*` before `*/*`) wins.
    """

    ENTRY_POINT_GROUP = "intomd.converters"

    def __init__(self) -> None:
        self._regs: dict[str, Registration] = {}
        self._chains: dict[str, list[str]] = {}

    def register(self, converter: Converter, *, source: str = "builtin") -> None:
        if converter.id in self._regs:
            raise ValueError(f"duplicate converter id {converter.id}")
        self._regs[converter.id] = Registration(converter=converter, source=source)

    def set_chain(self, mime: str, converter_ids: list[str]) -> None:
        """Pin the order of converters for a mime type. Unknown ids are ignored at resolve time with a log line."""
        self._chains[mime] = list(converter_ids)

    def chain_for(self, mime: str) -> list[str] | None:
        if mime in self._chains:
            return self._chains[mime]
        wild = [k for k in self._chains if k.endswith("/*") and mime_matches(k, mime)]
        if not wild:
            return None
        wild.sort(key=lambda k: (k == "*/*", k))
        return self._chains[wild[0]]

    def load_entry_points(self, entry_points: EntryPointsFn | None = None) -> None:
        """Discover third-party converters. Each entry point must resolve to a Converter class or a zero-arg
        factory. Failures are recorded, not raised, so one broken plugin cannot take down the registry."""
        for ep in (entry_points or _default_entry_points)():
            try:
                obj = ep.load()
                conv = obj() if callable(obj) and not isinstance(obj, Converter) else obj
                if not isinstance(conv, Converter):
                    raise TypeError(f"{ep.name} did not produce a Converter")
                self.register(conv, source=ep.dist.name if ep.dist else ep.name)
            except Exception as e:
                log.warning("converter plugin %s failed to load: %s", ep.name, e)
                self._regs[f"broken.{ep.name}"] = Registration(
                    converter=_Broken(ep.name), source=ep.name, import_error=str(e)
                )

    def registrations(self) -> list[Registration]:
        return list(self._regs.values())

    def available(self) -> list[Converter]:
        return [r.converter for r in self._regs.values() if r.import_error is None]

    def get(self, converter_id: str) -> Converter:
        reg = self._regs[converter_id]
        if reg.import_error:
            raise KeyError(f"converter {converter_id} unavailable: {reg.import_error}")
        return reg.converter

    def candidates(self, ref: InputRef) -> list[tuple[float, Converter]]:
        mime = ref.detected.mime if ref.detected else None
        chain = self.chain_for(mime) if mime else None
        if chain is not None:
            ordered: list[tuple[float, Converter]] = []
            for cid in chain:
                reg = self._regs.get(cid)
                if reg is None or reg.import_error:
                    log.info("chain for %s skips unavailable converter %s", mime, cid)
                    continue
                score = reg.converter.can_handle(ref)
                if score > 0:
                    ordered.append((score, reg.converter))
            if ordered:
                return ordered
        scored = [(c.can_handle(ref), c) for c in self.available()]
        scored = [(s, c) for s, c in scored if s > 0]
        scored.sort(key=lambda sc: (-sc[0], -sc[1].priority, sc[1].id))
        return scored

    def convert(self, ref: InputRef, options: ConvertOptions, *, converter_id: str | None = None) -> ConversionResult:
        """Run the resolution and fallback chain. Raises ConversionError if every candidate fails,
        with the last error's message and all tried ids in the message. Raises FetchRequired through."""
        if converter_id is not None:
            try:
                cands = [(1.0, self.get(converter_id))]
            except KeyError as e:
                raise ConversionError(
                    str(e), user_message=f"Unknown converter {converter_id!r}.", retryable_with_fallback=False
                ) from e
        else:
            cands = self.candidates(ref)
        if not cands:
            raise ConversionError(
                f"no converter for {ref.display} (mime={ref.detected.mime if ref.detected else None})",
                user_message="This file type is not supported yet.",
                retryable_with_fallback=False,
            )
        tried: list[str] = []
        last: Exception | None = None
        empty: tuple[int, Converter, Document] | None = None
        for i, (_score, conv) in enumerate(cands):
            tried.append(conv.id)
            t0 = time.monotonic()
            try:
                doc = conv.convert(ref, options)
            except FetchRequired:
                raise
            except ConversionError as e:
                last = e
                log.info("converter %s failed on %s: %s", conv.id, ref.display, e)
                if not e.retryable_with_fallback:
                    break
                continue
            except Exception as e:
                last = e
                log.exception("converter %s crashed on %s", conv.id, ref.display)
                continue
            if not doc.blocks:
                # An empty document triggers the next converter. If it carries warnings (the
                # converter explained the emptiness) it is kept as a last resort so the user sees
                # why nothing came out rather than a bare failure (D-0006).
                if doc.warnings and empty is None:
                    empty = (i, conv, doc)
                last = ConversionError(f"{conv.id} produced an empty document")
                log.info("converter %s produced empty document for %s; trying next", conv.id, ref.display)
                continue
            return self._result(ref, conv, doc, i, tried, time.monotonic() - t0)
        if empty is not None:
            i, conv, doc = empty
            return self._result(ref, conv, doc, i, tried, 0.0)
        msg = f"all converters failed for {ref.display}: tried {tried}; last error: {last}"
        user = last.user_message if isinstance(last, ConversionError) else "Conversion failed."
        raise ConversionError(msg, user_message=user, retryable_with_fallback=False)

    @staticmethod
    def _result(
        ref: InputRef, conv: Converter, doc: Document, index: int, tried: list[str], seconds: float
    ) -> ConversionResult:
        if not doc.finalized:
            doc.finalize()
        pipeline_warnings: list[Warning] = []
        if index > 0:
            pipeline_warnings.append(
                Warning(
                    kind=WarningKind.FALLBACK_ENGINE_USED,
                    severity="info",
                    message=f"Primary converter failed; used {conv.id}.",
                    detail={"tried": ",".join(tried)},
                )
            )
        if conv.experimental:
            pipeline_warnings.append(
                Warning(
                    kind=WarningKind.EXPERIMENTAL_CONVERTER,
                    severity="info",
                    message=f"{conv.id} is experimental; see docs for known limitations.",
                )
            )
        truncated = any(
            w.kind in (WarningKind.TRUNCATED, WarningKind.PAGE_LIMIT_REACHED, WarningKind.DURATION_LIMIT_REACHED)
            for w in doc.warnings
        )
        doc.converter_id = conv.id
        metrics = Metrics(
            duration_seconds=seconds,
            engine=conv.id,
            engines_tried=list(tried),
            input_bytes=ref.size() if ref.has_body else None,
            counts=doc.counts(),
        )
        return ConversionResult(
            document=doc,
            warnings=pipeline_warnings,
            metrics=metrics,
            truncated=truncated,
            converter_id=conv.id,
            input_ref=ref.info(),
        )


class _Broken:
    """Placeholder so `GET /v1/capabilities` can list plugins that failed to import."""

    def __init__(self, name: str) -> None:
        self.id = f"broken.{name}"
        self.family = "broken"
        self.priority = -1
        self.experimental = True
        self.requires_extras: tuple[str, ...] = ()
        self.mimes: tuple[str, ...] = ()

    def can_handle(self, ref: InputRef) -> float:
        return 0.0

    def convert(self, ref: InputRef, options: ConvertOptions) -> Document:
        raise ConversionError("broken plugin", retryable_with_fallback=False)


_default: ConverterRegistry | None = None


def default_registry() -> ConverterRegistry:
    """Process-wide registry: builtins first, then entry points, then default chains."""
    global _default
    if _default is None:
        reg = ConverterRegistry()
        from intomd.builtin import register_builtins  # local import avoids cycles

        register_builtins(reg)
        reg.load_entry_points()
        from intomd.chains import DEFAULT_CHAINS

        for mime, ids in DEFAULT_CHAINS.items():
            reg.set_chain(mime, ids)
        _default = reg
    return _default


def reset_default_registry() -> None:
    """Testing hook: forget the process-wide registry."""
    global _default
    _default = None
