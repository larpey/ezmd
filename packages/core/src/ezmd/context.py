"""ezmd.context: the per-conversion context every converter reaches as `options.ctx` (D-0017).

A ConvertContext carries what a long-running converter needs beyond its input: a progress callback,
the cooperative deadline (docs/spec/part2.md 13.5), child conversion for attachments and archive members
(sharing the parent's deadline and attachment depth), the converter's `Limits` (13.4), and a slot for the
latest partial Document so the registry can return it with `timeout_partial` when the deadline hits.

The default context is a no-op: no progress callback, generic limits, and the process-wide registry for
child conversions. The registry binds the real registry and the converter's limits before each call.
"""

from __future__ import annotations

import dataclasses
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ezmd.ir import ConversionResult, Document, InputRefInfo, Metadata, SourceType, Warning, WarningKind

if TYPE_CHECKING:
    from ezmd.inputs import InputRef
    from ezmd.registry import ConverterRegistry, ConvertOptions

__all__ = ["CHILD_RESERVE", "TIMEOUT_CODE", "ConvertContext", "Limits", "ProgressFn"]

log = logging.getLogger(__name__)

ProgressFn = Callable[[str, float | None, str], None]
"""on_progress(stage, fraction in [0, 1] or None when unknown, human message)."""

TIMEOUT_CODE = "timeout"
"""`ConversionError.code` raised by `check_deadline()`."""

CHILD_RESERVE = 0.10
"""Share of the remaining budget the parent keeps for finalization when it dispatches a child (13.5.3)."""


@dataclass(frozen=True, slots=True)
class Limits:
    """Caps a converter declares (docs/spec/part2.md 13.4). None means "no converter-specific cap"; the
    ConvertOptions values (max_pages, max_duration_seconds, max_seconds) still apply."""

    max_bytes: int | None = None
    max_pages: int | None = None
    max_rows: int | None = None
    max_cols: int | None = None
    max_sheets: int | None = None
    max_entries: int | None = None
    """Messages, notes, archive entries, comments, chapters, or slides, depending on the family."""
    max_depth: int | None = None
    max_chars: int | None = None
    """Per-item text cap (notebook outputs, log lines)."""
    max_duration_seconds: float | None = None
    timeout_s: float | None = None
    """Cooperative budget for one `convert()` call; the registry's hard watchdog fires at timeout_s + 30."""


@dataclass(slots=True)
class ConvertContext:
    """Progress, deadline, child conversion, limits, and partial results for one conversion.

    on_progress: optional callback; exceptions it raises are logged and ignored so a broken progress
        sink cannot fail a conversion.
    depth: attachment depth of this conversion (0 for the top-level input).
    limits: the running converter's Limits (bound by the registry from `Converter.limits`).
    partial: the latest Document passed to `publish_partial`, returned on a deadline hit.
    """

    on_progress: ProgressFn | None = None
    depth: int = 0
    limits: Limits = field(default_factory=Limits)
    partial: Document | None = None
    _options: ConvertOptions | None = field(default=None, repr=False)
    _registry: ConverterRegistry | None = field(default=None, repr=False)

    def bind(
        self, options: ConvertOptions, registry: ConverterRegistry | None = None, limits: Limits | None = None
    ) -> ConvertContext:
        """Attach the options (for the deadline), the registry (for children), and the limits. Returns self."""
        self._options = options
        if registry is not None:
            self._registry = registry
        if limits is not None:
            self.limits = limits
        return self

    def progress(self, stage: str, fraction: float | None = None, message: str = "") -> None:
        """Report progress. `fraction` is clamped to [0, 1]; None means indeterminate."""
        if self.on_progress is None:
            return
        frac = None if fraction is None else min(1.0, max(0.0, fraction))
        try:
            self.on_progress(stage, frac, message)
        except Exception:
            log.warning("progress callback failed for stage %s", stage, exc_info=True)

    def remaining(self) -> float | None:
        """Seconds left before the deadline, or None when the context is not bound to options."""
        return self._options.deadline() if self._options is not None else None

    def check_deadline(self) -> None:
        """Raise ConversionError(code="timeout", retryable_with_fallback=False) once the budget is spent.
        Converters call this at every page, file, message, row-batch, or network boundary."""
        left = self.remaining()
        if left is None or left > 0:
            return
        from ezmd.registry import ConversionError

        assert self._options is not None
        raise ConversionError(
            f"conversion exceeded its {self._options.max_seconds:.0f} s budget",
            user_message=f"The conversion hit its time limit of {self._options.max_seconds:.0f} seconds.",
            retryable_with_fallback=False,
            code=TIMEOUT_CODE,
        )

    def publish_partial(self, doc: Document) -> None:
        """Record the Document built so far. On a deadline hit the registry returns it, marked truncated,
        with a `timeout_partial` warning."""
        self.partial = doc

    def convert_child(self, ref: InputRef, *, label: str) -> ConversionResult:
        """Convert an attachment, archive member, or linked file through the full pipeline.

        The child runs at depth + 1 and shares this conversion's deadline, minus the CHILD_RESERVE share of
        the remaining budget kept back for the parent. Beyond `options.max_attachment_depth` (or when
        `follow_attachments` is off) the child is not converted: the result is an empty Document carrying
        an `attachment_skipped` warning. Raises ConversionError when the child fails or the deadline has
        passed, and FetchRequired when the child needs a fetch.
        """
        from ezmd.pipeline import convert_ref
        from ezmd.registry import ConvertOptions

        options = self._options or ConvertOptions()
        child_depth = self.depth + 1
        if not options.follow_attachments:
            return _skipped(ref, label, f"{label} was not converted: attachments are disabled.", child_depth)
        if child_depth > options.max_attachment_depth:
            reason = (
                f"{label} was not converted: depth {child_depth} exceeds the limit of {options.max_attachment_depth}."
            )
            return _skipped(ref, label, reason, child_depth)
        self.check_deadline()
        left = options.deadline()
        child_ctx = ConvertContext(on_progress=self.on_progress, depth=child_depth, _registry=self._registry)
        child_options = dataclasses.replace(
            options, ctx=child_ctx, max_seconds=options.max_seconds - left * CHILD_RESERVE
        )
        self.progress("child", None, label)
        return convert_ref(ref, child_options, registry=self._registry)


def _skipped(ref: InputRef, label: str, message: str, depth: int) -> ConversionResult:
    doc = Document(
        metadata=Metadata(source=label, source_type=SourceType.OTHER),
        warnings=[
            Warning(
                kind=WarningKind.ATTACHMENT_SKIPPED,
                message=message,
                detail={"label": label, "depth": depth},
            )
        ],
    ).finalize()
    return ConversionResult(
        document=doc,
        converter_id="",
        input_ref=InputRefInfo(kind=ref.kind, display=label, mime=ref.declared_mime),
    )
