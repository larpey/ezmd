"""data.xml: generic XML through defusedxml (docs/spec/part2.md section 10, XmlConverter; part1 8.2).

Parsing uses `defusedxml.ElementTree` with entities and external references forbidden, so nothing is ever
expanded or fetched. A document that declares entities or a DTD is re-parsed with the DOCTYPE removed and
every non-predefined entity reference dropped (warning `unsupported_feature`): XXE and billion-laughs
payloads produce no entity content and no network access.

The element tree becomes nested data and goes through the shared tree renderer: attributes are `@name`
keys, text next to child elements is `#text`, repeated child elements become a list (a records table when
they carry structure), and qualified names use the document's own namespace prefixes. Provenance paths
are XPath (`/catalog/book[2]/price`). Root-element dispatch to RSS/SVG/XBRL/JATS converters and source line
numbers are not implemented yet.
"""

from __future__ import annotations

import io
import re
from typing import Any
from xml.etree.ElementTree import Element, ParseError

from defusedxml import DefusedXmlException  # type: ignore[import-untyped,unused-ignore]
from defusedxml.ElementTree import iterparse  # type: ignore[import-untyped,unused-ignore]

from ezmd.core.textclean import CleanStats, clean_text
from ezmd.inputs import InputRef
from ezmd.ir import Document, Heading, InlineSpan, Table, Warning, WarningKind
from ezmd.registry import ConversionError, ConvertOptions
from ezmd_converters.data._base import (
    DATA_LIMITS,
    finish,
    mime_of,
    new_document,
    read_capped,
    source_block,
    suffix_of,
    summary,
)
from ezmd_converters.data._common import (
    ELLIPSIS,
    CellValue,
    DataOptions,
    decode_bytes,
    display_text,
    kv_table,
    make_table,
    prov,
)
from ezmd_converters.data._tree import TreeBuilder, clip, clip_warnings

XML_MIMES = ("application/xml",)
XML_MIN_RECORDS = 6
"""An element repeated over 5 times becomes a records table (10c step 9); fewer repeats are listed one by one."""
_DOCTYPE = re.compile(rb"<!DOCTYPE\b[^\[>]*(\[.*?\]\s*)?>", re.S | re.I)
_ENTITY_REF = re.compile(rb"&(?!(?:amp|lt|gt|quot|apos|#[0-9]+|#x[0-9A-Fa-f]+);)[A-Za-z_:][-A-Za-z0-9._:]*;")


def _parse(raw: bytes, *, forbid_dtd: bool) -> tuple[Element, dict[str, str]]:
    namespaces: dict[str, str] = {}
    it = iterparse(io.BytesIO(raw), events=("start-ns",), forbid_dtd=forbid_dtd)
    for _event, item in it:
        prefix, uri = item
        namespaces.setdefault(uri, prefix)
    root = it.root
    assert isinstance(root, Element)
    return root, namespaces


def parse_xml(raw: bytes) -> tuple[Element, dict[str, str], int, bytes]:
    """Root element, uri -> prefix map, entity references dropped plus one when the DOCTYPE was removed (0
    when the document had none), and the bytes that were parsed (the sanitized copy in that case)."""
    try:
        root, ns = _parse(raw, forbid_dtd=False)
        return root, ns, 0, raw
    except DefusedXmlException:
        pass
    stripped = _DOCTYPE.sub(b"", raw, count=1)
    stripped, dropped = _ENTITY_REF.subn(b"", stripped)
    root, ns = _parse(stripped, forbid_dtd=True)
    return root, ns, dropped + 1, stripped


STRUCTURE_TEXT_CHARS = 40


def structure_table(
    root: Element, names: _Names, source: str, opts: DataOptions, stats: CleanStats
) -> tuple[Table, int]:
    """Structural summary (10c step 9): element path, count, attributes, text sample, for up to
    `schema_max_paths` paths in document order. Returns the table and how many paths were left out."""
    seen: dict[str, list[Any]] = {}
    stack: list[tuple[Element, str]] = [(root, "")]
    while stack:
        el, parent = stack.pop()
        if not isinstance(el.tag, str):
            continue
        path = f"{parent}/{names.q(el.tag)}"
        entry = seen.setdefault(path, [0, {}, ""])
        entry[0] += 1
        for k in el.attrib:
            entry[1].setdefault("@" + names.q(k), None)
        text = (el.text or "").strip()
        if text and not entry[2]:
            entry[2] = text if len(text) <= STRUCTURE_TEXT_CHARS else text[: STRUCTURE_TEXT_CHARS - 1] + ELLIPSIS
        stack.extend((child, path) for child in reversed(list(el)))
    items = list(seen.items())
    shown = items[: opts.schema_max_paths]
    rows = [
        [display_text(p, stats), CellValue(str(e[0])), display_text(" ".join(e[1]), stats), display_text(e[2], stats)]
        for p, e in shown
    ]
    table = make_table(
        ["Element path", "Count", "Attributes", "Text sample"],
        rows,
        prov(source, "/"),
        column_types=["text", "int", "text", "text"],
    )
    return table, max(0, len(items) - opts.schema_max_paths)


class _Names:
    def __init__(self, namespaces: dict[str, str]) -> None:
        self.ns = namespaces

    def q(self, tag: str) -> str:
        if tag.startswith("{"):
            uri, _, local = tag[1:].partition("}")
            prefix = self.ns.get(uri, "")
            return f"{prefix}:{local}" if prefix else local
        return tag


def to_value(el: Element, names: _Names, depth: int, max_depth: int, counter: list[int]) -> Any:
    """Element -> nested data. Recursion is bounded by `max_depth` (deeper elements become "…")."""
    counter[0] += 1
    if depth > max_depth:
        counter[1] += 1
        return ELLIPSIS
    out: dict[str, Any] = {f"@{names.q(k)}": v for k, v in el.attrib.items()}
    text = (el.text or "").strip()
    children = list(el)
    if not children and not out:
        return text
    if text:
        out["#text"] = text
    for child in children:
        if not isinstance(child.tag, str):  # comments and processing instructions
            continue
        key = names.q(child.tag)
        value = to_value(child, names, depth + 1, max_depth, counter)
        tail = (child.tail or "").strip()
        if tail:
            out["#text"] = (out.get("#text", "") + " " + tail).strip()
        if key in out and not key.startswith("@"):
            existing = out[key]
            if isinstance(existing, _Repeated):
                existing.append(value)
            else:
                out[key] = _Repeated([existing, value])
        else:
            out[key] = value
    return {k: list(v) if isinstance(v, _Repeated) else v for k, v in out.items()}


class _Repeated(list[Any]):
    """Marks lists built from repeated elements (as opposed to a single element's value)."""


def xpath_child(parent: str, key: str) -> str:
    return f"{parent.rstrip('/')}/{key}"


def xpath_index(parent: str, index: int) -> str:
    return f"{parent}[{index + 1}]"


class XmlConverter:
    id = "data.xml"
    family = "data"
    priority = 10
    experimental = False
    requires_extras: tuple[str, ...] = ()
    mimes: tuple[str, ...] = XML_MIMES
    limits = DATA_LIMITS

    def can_handle(self, ref: InputRef) -> float:
        mime = mime_of(ref)
        if mime in XML_MIMES:
            return 0.9
        if suffix_of(ref) == ".xml" and mime in ("text/plain", None):
            return 0.6
        return 0.0

    def convert(self, ref: InputRef, options: ConvertOptions) -> Document:
        opts = DataOptions.from_options(options)
        raw = read_capped(ref, opts.max_bytes, "XML")
        options.ctx.progress("parse", None, "parsing XML")
        warnings: list[Warning] = []
        try:
            root, namespaces, dropped, parsed = parse_xml(raw)
        except (ParseError, DefusedXmlException, ValueError) as e:
            raise ConversionError(f"invalid XML: {e}", user_message="This file is not well-formed XML.") from e
        if dropped:
            warnings.append(
                Warning(
                    kind=WarningKind.UNSUPPORTED_FEATURE,
                    message="The XML declares a DTD or entities; they were ignored for safety and "
                    f"{dropped - 1} entity reference(s) were dropped.",
                    count=dropped - 1,
                    detail={"feature": "xml_entities"},
                )
            )
        names = _Names(namespaces)
        counter = [0, 0]
        value = to_value(root, names, 1, opts.max_depth, counter)
        clipped = clip(value, max_depth=opts.max_depth + 1, max_nodes=opts.max_nodes)
        if counter[1]:
            clipped.depth_cut += counter[1]
        warnings.extend(clip_warnings(clipped, opts))
        root_name = names.q(root.tag)
        doc = new_document(ref)
        doc.metadata.extra.update({"format": "XML", "root": root_name, "elements": counter[0]})
        ns_note = f"; {len(namespaces)} namespace(s)" if namespaces else ""
        summary(doc, f"XML document with root element {root_name} and {counter[0]:,} elements{ns_note}.")
        stats = CleanStats()
        root_path = f"/{root_name}"
        if namespaces:
            rows = [(prefix or "(default)", CellValue(uri)) for uri, prefix in namespaces.items()]
            table = kv_table(rows, prov(ref.display, root_path))
            table.cells[0].spans[0].text = "Prefix"
            table.cells[1].spans[0].text = "Namespace URI"
            doc.blocks.append(table)
        doc.blocks.append(Heading(level=2, spans=[InlineSpan(text="Structure")], provenance=prov(ref.display, "/")))
        structure, left = structure_table(root, names, ref.display, opts, stats)
        doc.blocks.append(structure)
        if left:
            summary(doc, f"({left:,} more element paths not shown; raise data.schema_max_paths to list them.)")
        doc.blocks.append(Heading(level=2, spans=[InlineSpan(text="Data")], provenance=prov(ref.display, "/")))
        builder = TreeBuilder(
            source=ref.display,
            opts=opts,
            ctx=options.ctx,
            child_path=xpath_child,
            index_path=xpath_index,
            stats=stats,
            typed_strings=True,
            min_records=XML_MIN_RECORDS,
        )
        builder.emit(clipped.value, root_path, 3, name=root_name)
        doc.blocks.extend(builder.blocks)
        source_block(doc, clean_text(decode_bytes(parsed).text, stats), "xml")
        return finish(doc, stats, [*warnings, *builder.warnings])
