"""data.json: JSON and JSON Lines (docs/spec/part2.md section 10, JsonConverter).

stdlib `json` with `parse_int`/`parse_float`/`parse_constant` hooks that keep every number as its source
spelling, so `1.10`, 19-digit ids and `1e400` survive. A document that fails to parse as JSON is retried as
JSON Lines; malformed lines (typically a trailing partial line) are skipped with `markup_partial`. Repair
(`json_repaired`) and JSON5 are not implemented. Error envelopes (`error`/`errors` keys) render first with
`api_error_payload`.
"""

from __future__ import annotations

import json
from typing import Any

from intomd.core.textclean import CleanStats
from intomd.inputs import InputRef
from intomd.ir import Document, Warning, WarningKind
from intomd.registry import ConversionError, ConvertOptions
from intomd_converters.data._base import DATA_LIMITS, finish, mime_of, new_document, read_capped, suffix_of, summary
from intomd_converters.data._common import DataOptions, RawNumber, decode_bytes, encoding_warning
from intomd_converters.data._tree import (
    TreeBuilder,
    clip,
    clip_warnings,
    depth_extra,
    depth_text,
    describe,
    emit_schema_and_data,
)

JSON_MIMES = ("application/json", "application/jsonl", "application/x-ndjson")
JSONL_SUFFIXES = (".jsonl", ".ndjson")
_ERROR_KEYS = ("error", "errors")


def loads(text: str) -> Any:
    return json.loads(text, parse_int=RawNumber, parse_float=RawNumber, parse_constant=RawNumber)


def parse_lines(text: str) -> tuple[list[Any], list[int], int]:
    """Parse JSON Lines. Returns (values, 1-based numbers of malformed lines, count of non-empty lines)."""
    values: list[Any] = []
    bad: list[int] = []
    nonempty = 0
    for n, line in enumerate(text.split("\n"), start=1):
        if not line.strip():
            continue
        nonempty += 1
        try:
            values.append(loads(line))
        except (ValueError, RecursionError):
            bad.append(n)
    return values, bad, nonempty


def _error_first(value: Any, warnings: list[Warning]) -> Any:
    if not isinstance(value, dict):
        return value
    keys = [k for k in _ERROR_KEYS if value.get(k) not in (None, [], {}, "")]
    if not keys:
        return value
    warnings.append(
        Warning(
            kind=WarningKind.API_ERROR_PAYLOAD,
            message=f"The JSON contains an error payload ({', '.join(keys)}); it is shown first.",
        )
    )
    return {**{k: value[k] for k in keys}, **{k: v for k, v in value.items() if k not in keys}}


class JsonConverter:
    id = "data.json"
    family = "data"
    priority = 10
    experimental = False
    requires_extras: tuple[str, ...] = ()
    mimes: tuple[str, ...] = JSON_MIMES
    limits = DATA_LIMITS

    def can_handle(self, ref: InputRef) -> float:
        mime = mime_of(ref)
        if mime in JSON_MIMES:
            return 0.95
        if suffix_of(ref) in (".json", *JSONL_SUFFIXES) and mime in ("text/plain", None):
            return 0.6
        return 0.0

    def convert(self, ref: InputRef, options: ConvertOptions) -> Document:
        opts = DataOptions.from_options(options)
        raw = read_capped(ref, opts.max_bytes, "JSON")
        decoded = decode_bytes(raw)
        text = decoded.text
        warnings: list[Warning] = []
        enc = encoding_warning(decoded)
        if enc is not None:
            warnings.append(enc)
        options.ctx.progress("parse", None, "parsing JSON")
        lines_mode = mime_of(ref) in ("application/jsonl", "application/x-ndjson") or suffix_of(ref) in JSONL_SUFFIXES
        value: Any = None
        kind = "JSON"
        parsed = False
        first_error: Exception | None = None
        # Whole-document parse first, even for JSON Lines mimes: Magika labels a one-line object `jsonl`.
        try:
            value = loads(text)
            parsed = True
        except RecursionError as e:
            raise ConversionError(
                "JSON nests too deeply to parse", user_message="This JSON nests too deeply to convert."
            ) from e
        except ValueError as e:
            first_error = e
        if not parsed:
            values, bad, nonempty = parse_lines(text)
            if not values or (not lines_mode and len(bad) * 2 > nonempty):
                detail = str(first_error) if first_error is not None else f"{len(bad)} malformed lines"
                raise ConversionError(
                    f"not valid JSON or JSON Lines: {detail}",
                    user_message="This file is not valid JSON.",
                )
            value, kind = values, "JSON Lines"
            if bad:
                warnings.append(
                    Warning(
                        kind=WarningKind.MARKUP_PARTIAL,
                        message=f"Skipped {len(bad)} malformed JSON Lines line(s): {', '.join(map(str, bad[:10]))}.",
                        count=len(bad),
                        detail={"lines": ",".join(map(str, bad[:50]))},
                    )
                )
        value = _error_first(value, warnings)
        clipped = clip(value, max_depth=opts.max_depth, max_nodes=opts.max_nodes)
        warnings.extend(clip_warnings(clipped, opts))
        doc = new_document(ref, encoding=decoded.encoding, confidence=decoded.confidence)
        doc.metadata.extra.update({"format": kind, **depth_extra(clipped, opts)})
        summary(doc, f"{kind} {describe(clipped.value)}; {depth_text(clipped, opts)}.")
        builder = TreeBuilder(source=ref.display, opts=opts, ctx=options.ctx)
        emit_schema_and_data(builder, clipped.value)
        doc.blocks.extend(builder.blocks)
        stats: CleanStats = builder.stats
        return finish(doc, stats, [*warnings, *builder.warnings])
