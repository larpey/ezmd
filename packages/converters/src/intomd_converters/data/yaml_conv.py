"""data.yaml: YAML (docs/spec/part2.md section 10, YamlConverter).

Loads with a `yaml.SafeLoader` subclass only (never `yaml.load` with an unsafe loader). The subclass changes
three things, none of which can execute code: numbers keep their source spelling (`1.50` stays `1.50`),
timestamps stay strings, and tags SafeLoader does not know (`!!python/object/apply:os.system`, `!Ref`)
are rendered inert as the text `!tag <value>` with warning `yaml_unsafe_tags` instead of failing.
Multi-document files render each document under its own H2. Anchors and aliases are expanded by the loader
(`metadata.extra.anchors_expanded`); the clip step bounds alias bombs and self-referencing anchors.
When the file has comments, the raw source is kept as a `yaml` code block (comments are documentation).
"""

from __future__ import annotations

from typing import Any, ClassVar

import yaml

from intomd.core.textclean import CleanStats, clean_text
from intomd.inputs import InputRef
from intomd.ir import Document, Heading, InlineSpan, Warning, WarningKind
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
from intomd_converters.data._common import DataOptions, RawNumber, decode_bytes, encoding_warning, prov, to_json
from intomd_converters.data._tree import (
    TreeBuilder,
    clip,
    clip_warnings,
    depth_text,
    describe,
    emit_schema_and_data,
    pointer_index,
    schema_table,
)

YAML_MIMES = ("application/yaml",)
_STD_PREFIX = "tag:yaml.org,2002:"


class _Loader(yaml.SafeLoader):
    """SafeLoader that keeps scalars verbatim and turns unknown tags into inert strings."""

    unknown_tags: ClassVar[list[str]]

    def __init__(self, stream: str) -> None:
        super().__init__(stream)
        self.seen_tags: list[str] = []


def _verbatim(loader: _Loader, node: yaml.Node) -> RawNumber:
    assert isinstance(node, yaml.ScalarNode)
    return RawNumber(loader.construct_scalar(node))


def _plain(loader: _Loader, node: yaml.Node) -> str:
    assert isinstance(node, yaml.ScalarNode)
    return str(loader.construct_scalar(node))


def _unknown(loader: _Loader, node: yaml.Node) -> str:
    tag = str(node.tag)
    loader.seen_tags.append(tag)
    short = "!!" + tag[len(_STD_PREFIX) :] if tag.startswith(_STD_PREFIX) else tag
    value: Any
    if isinstance(node, yaml.ScalarNode):
        value = loader.construct_scalar(node)
        return f"{short} {value}".rstrip()
    if isinstance(node, yaml.SequenceNode):
        value = loader.construct_sequence(node, deep=True)
    else:
        assert isinstance(node, yaml.MappingNode)
        value = loader.construct_mapping(node, deep=True)
    return f"{short} {to_json(value)}"


_Loader.add_constructor(f"{_STD_PREFIX}int", _verbatim)
_Loader.add_constructor(f"{_STD_PREFIX}float", _verbatim)
_Loader.add_constructor(f"{_STD_PREFIX}timestamp", _plain)
_Loader.add_constructor(None, _unknown)  # type: ignore[arg-type]  # None is the fallback key


def load_documents(text: str) -> tuple[list[Any], list[str], str | None]:
    """All documents, the unknown tags seen, and the error that stopped loading (if any)."""
    loader = _Loader(text)
    docs: list[Any] = []
    error: str | None = None
    try:
        while loader.check_data():  # type: ignore[no-untyped-call]
            docs.append(loader.get_data())
    except yaml.YAMLError as e:
        error = str(e).replace("\n", " ")
    except RecursionError:
        error = "the YAML nests too deeply"
    finally:
        loader.dispose()
    return docs, loader.seen_tags, error


def has_anchors(text: str) -> bool:
    try:
        return any(isinstance(t, yaml.AnchorToken) for t in yaml.scan(text, Loader=yaml.SafeLoader))
    except yaml.YAMLError:
        return False


class YamlConverter:
    id = "data.yaml"
    family = "data"
    priority = 10
    experimental = False
    requires_extras: tuple[str, ...] = ()
    mimes: tuple[str, ...] = YAML_MIMES
    limits = DATA_LIMITS

    def can_handle(self, ref: InputRef) -> float:
        mime = mime_of(ref)
        if mime in YAML_MIMES:
            return 0.95
        if suffix_of(ref) in (".yaml", ".yml") and mime in ("text/plain", None):
            return 0.6
        return 0.0

    def convert(self, ref: InputRef, options: ConvertOptions) -> Document:
        opts = DataOptions.from_options(options)
        decoded = decode_bytes(read_capped(ref, opts.max_bytes, "YAML"))
        stats = CleanStats()
        text = clean_text(decoded.text, stats)
        warnings: list[Warning] = []
        enc = encoding_warning(decoded)
        if enc is not None:
            warnings.append(enc)
        options.ctx.progress("parse", None, "parsing YAML")
        docs, tags, error = load_documents(text)
        if error is not None:
            if not docs:
                raise ConversionError(f"invalid YAML: {error}", user_message="This file is not valid YAML.")
            warnings.append(
                Warning(
                    kind=WarningKind.MARKUP_PARTIAL,
                    message=f"YAML parsing stopped after {len(docs)} document(s): {error[:200]}",
                )
            )
        if tags:
            uniq = sorted(set(tags))
            warnings.append(
                Warning(
                    kind=WarningKind.YAML_UNSAFE_TAGS,
                    message=f"Unsupported YAML tags were not executed and are shown as text: {', '.join(uniq[:5])}.",
                    count=len(tags),
                    detail={"tags": ",".join(uniq[:20])},
                )
            )
        value: Any = docs[0] if len(docs) == 1 else docs
        clipped = clip(value, max_depth=opts.max_depth, max_nodes=opts.max_nodes)
        warnings.extend(clip_warnings(clipped, opts))
        doc = new_document(ref, encoding=decoded.encoding, confidence=decoded.confidence)
        anchors = has_anchors(text)
        doc.metadata.extra.update({"format": "YAML", "documents": len(docs), "anchors_expanded": anchors})
        builder = TreeBuilder(source=ref.display, opts=opts, ctx=options.ctx, stats=stats)
        if len(docs) == 1:
            summary(doc, f"YAML {describe(clipped.value)}; {depth_text(clipped, opts)}.")
            emit_schema_and_data(builder, clipped.value)
        else:
            summary(doc, f"YAML stream of {len(docs)} documents; {depth_text(clipped, opts, offset=1)}.")
            builder.heading(2, "Schema", "/")
            table, left = schema_table(clipped.value, ref.display, opts, stats)
            builder.blocks.append(table)
            if left:
                builder.paragraph(f"({left:,} more paths not shown.)", "/")
            builder.heading(2, "Data", "/")
            for i, part in enumerate(clipped.value if isinstance(clipped.value, list) else []):
                path = pointer_index("/", i)
                builder.blocks.append(
                    Heading(level=3, spans=[InlineSpan(text=f"Document {i + 1}")], provenance=prov(ref.display, path))
                )
                builder.emit(part, path, 4)
        doc.blocks.extend(builder.blocks)
        source_block(doc, text, "yaml")
        return finish(doc, stats, [*warnings, *builder.warnings])
