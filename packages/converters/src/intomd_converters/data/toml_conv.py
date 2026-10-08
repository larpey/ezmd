"""data.toml: TOML via stdlib `tomllib` (docs/spec/part2.md section 10, TomlIniConverter, TOML part).

Floats keep their source spelling (`parse_float`), datetimes render in ISO 8601, top-level keys form a
Key/Value table, `[tables]` become headings by dotted path, and arrays of tables become records tables.
When the file has comments the raw source is kept as a `toml` code block. INI, `.properties` and `.env`
are not handled yet (see docs/converters/data.md).
"""

from __future__ import annotations

import tomllib

from intomd.core.textclean import CleanStats, clean_text
from intomd.inputs import InputRef
from intomd.ir import Document, Warning
from intomd.registry import ConversionError, ConvertOptions
from intomd_converters.data._base import (
    DATA_LIMITS,
    finish,
    mime_of,
    new_document,
    read_capped,
    source_block,
    suffix_of,
    summary,
)
from intomd_converters.data._common import DataOptions, RawNumber, decode_bytes, encoding_warning
from intomd_converters.data._tree import TreeBuilder, clip, clip_warnings, depth_extra, depth_text, describe

TOML_MIMES = ("application/toml",)


class TomlConverter:
    id = "data.toml"
    family = "data"
    priority = 10
    experimental = False
    requires_extras: tuple[str, ...] = ()
    mimes: tuple[str, ...] = TOML_MIMES
    limits = DATA_LIMITS

    def can_handle(self, ref: InputRef) -> float:
        mime = mime_of(ref)
        if mime in TOML_MIMES:
            return 0.95
        if suffix_of(ref) == ".toml" and mime in ("text/plain", None):
            return 0.6
        return 0.0

    def convert(self, ref: InputRef, options: ConvertOptions) -> Document:
        opts = DataOptions.from_options(options)
        decoded = decode_bytes(read_capped(ref, opts.max_bytes, "TOML"))
        stats = CleanStats()
        text = clean_text(decoded.text, stats)
        warnings: list[Warning] = []
        enc = encoding_warning(decoded)
        if enc is not None:
            warnings.append(enc)
        try:
            value = tomllib.loads(text, parse_float=RawNumber)
        except tomllib.TOMLDecodeError as e:
            raise ConversionError(f"invalid TOML: {e}", user_message="This file is not valid TOML.") from e
        except RecursionError as e:
            raise ConversionError("TOML nests too deeply", user_message="This TOML nests too deeply.") from e
        clipped = clip(value, max_depth=opts.max_depth, max_nodes=opts.max_nodes)
        warnings.extend(clip_warnings(clipped, opts))
        doc = new_document(ref, encoding=decoded.encoding, confidence=decoded.confidence)
        doc.metadata.extra.update({"format": "TOML", **depth_extra(clipped, opts)})
        summary(doc, f"TOML {describe(clipped.value)}; {depth_text(clipped, opts)}.")
        builder = TreeBuilder(source=ref.display, opts=opts, ctx=options.ctx, stats=stats)
        builder.emit(clipped.value, "/", 2)
        doc.blocks.extend(builder.blocks)
        source_block(doc, text, "toml")
        return finish(doc, stats, [*warnings, *builder.warnings])
