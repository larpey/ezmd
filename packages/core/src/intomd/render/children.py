"""intomd.render.children: render `Document.children` (archive members, email attachments) inline.

The renderer works on one flat block list, so child Documents are flattened into the parent before
rendering (docs/spec/part2.md step 28, part3.md section D):

- After the parent body, each child becomes a section headed `<child path>` (the child's `metadata.source`
  after the last `!`, else the first block's `provenance.path`, else its source). The section is a
  top-level section for a direct child and one level deeper per nesting level.
- The child's own title H1 (and a matching `role="title"` paragraph) becomes that section heading and is
  not repeated; the child's other headings shift under the section (child H2 sits one level below it).
- Child block ids are prefixed (`c1-b0003`, `c1.2-b0001` for a grandchild) so ids, footnotes, anchors
  and annotations never collide with the parent's; numbering and `{#sec-N}` anchors simply continue.
- Child warnings are merged into the parent with `detail["child"] = <path>`; child `sidecar_extra`
  entries are merged under the same key with a `child` field.

The original parent Document (without children) is kept for the sidecar's `document` dump.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import TypeAdapter

from intomd.ir import (
    RESERVED_SIDECAR_KEYS,
    Block,
    ConversionResult,
    Document,
    Heading,
    InlineSpan,
    Paragraph,
    Provenance,
    SidecarScalar,
    SourceType,
    Warning,
    spans_text,
)

__all__ = ["CHILD_SECTION_ATTR", "ChildIndex", "ChildInfo", "child_path", "flatten_children"]

CHILD_SECTION_ATTR = "intomd_child_section"
"""Block attr marking the synthetic section heading of a child Document (value: the child path)."""

_ID_KEYS = frozenset({"id", "parent_id", "footnote_ref", "anchor_block_id", "reply_to", "continued_from", "section_id"})
_BLOCK_ADAPTER: TypeAdapter[Block] = TypeAdapter(Block)


@dataclass(frozen=True, slots=True)
class ChildInfo:
    prefix: str
    """Block id prefix of this child (`c1-`, `c1.2-`)."""
    path: str
    depth: int
    converter: str
    title: str | None
    block_count: int
    source_type: SourceType
    section_id: str
    """Block id of the synthetic section heading."""

    def to_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "converter": self.converter or None,
            "title": self.title,
            "block_count": self.block_count,
            "depth": self.depth,
            "source_type": str(self.source_type),
            "section_block_id": self.section_id,
        }


@dataclass(slots=True)
class ChildIndex:
    """What the renderer needs to know about flattened children."""

    infos: list[ChildInfo] = field(default_factory=list)
    block_child: dict[str, str] = field(default_factory=dict)
    """Child block id -> child prefix."""
    source: Document | None = None
    """The parent Document as the converter returned it (children excluded from the dump)."""
    truncated: bool = False

    def __bool__(self) -> bool:
        return bool(self.infos)

    def prefix_of(self, block_id: str) -> str | None:
        return self.block_child.get(block_id)

    def is_child_block(self, block_id: str) -> bool:
        return block_id in self.block_child

    def source_type_of(self, block_id: str, default: SourceType) -> SourceType:
        prefix = self.block_child.get(block_id)
        if prefix is None:
            return default
        for info in self.infos:
            if info.prefix == prefix:
                return info.source_type
        return default


def child_path(child: Document, index: int) -> str:
    source = (child.metadata.source or "").strip()
    if "!" in source:
        tail = source.rsplit("!", 1)[1].strip()
        if tail:
            return tail
    for b in child.blocks:
        if b.provenance.path:
            return b.provenance.path
    return source or f"child-{index}"


def _title(child: Document) -> str | None:
    if child.metadata.title and child.metadata.title.strip():
        return " ".join(child.metadata.title.split())
    for b in child.blocks:
        if isinstance(b, Heading) and b.level == 1:
            text = " ".join(spans_text(b.spans).split())
            if text:
                return text
        if isinstance(b, Paragraph) and b.role == "title":
            text = " ".join(spans_text(b.spans).split())
            if text:
                return text
    return None


def _consumed(child: Document, title: str | None) -> set[str]:
    if not title:
        return set()
    key = title.casefold()
    out: set[str] = set()
    first = next((b for b in child.blocks if isinstance(b, Heading)), None)
    if first is not None and first.level == 1 and " ".join(spans_text(first.spans).split()).casefold() == key:
        out.add(first.id)
    for b in child.blocks:
        if isinstance(b, Paragraph) and b.role == "title" and " ".join(spans_text(b.spans).split()).casefold() == key:
            out.add(b.id)
    return out


def _prefix_ids(value: Any, prefix: str) -> Any:
    """Prefix every block-id reference in a dumped block (never inside `attrs`)."""
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k, v in value.items():
            if k == "attrs":
                out[k] = v
            elif k in _ID_KEYS and isinstance(v, str) and v:
                out[k] = prefix + v
            else:
                out[k] = _prefix_ids(v, prefix)
        return out
    if isinstance(value, list):
        return [_prefix_ids(v, prefix) for v in value]
    return value


def _child_block(b: Block, prefix: str, depth: int, top: int) -> Block:
    """`top` is the shallowest heading level left in the child after its title is consumed: it lands one level
    below the section heading and every other heading keeps its distance from it, so a child with several H1s
    keeps H2 below H1 (uniform shift)."""
    data = _prefix_ids(b.model_dump(mode="python"), prefix)
    if isinstance(b, Heading):
        data["level"] = min(6, depth + 1 + b.level - top)
    return _BLOCK_ADAPTER.validate_python(data)


def _child_warning(w: Warning, prefix: str, path: str) -> Warning:
    detail: dict[str, str | int | float] = {**w.detail, "child": path}
    return w.model_copy(update={"detail": detail, "block_id": prefix + w.block_id if w.block_id else None})


@dataclass(slots=True)
class _Flat:
    blocks: list[Block] = field(default_factory=list)
    warnings: list[Warning] = field(default_factory=list)
    extra: dict[str, list[dict[str, SidecarScalar]]] = field(default_factory=dict)
    index: ChildIndex = field(default_factory=ChildIndex)


def _check_extra(doc: Document) -> None:
    reserved = sorted(RESERVED_SIDECAR_KEYS.intersection(doc.sidecar_extra))
    if reserved:
        raise ValueError(f"sidecar_extra keys collide with built-in sidecar keys: {reserved}")


def _walk(doc: Document, parts: list[str], depth: int, flat: _Flat) -> None:
    for n, child in enumerate(doc.children, start=1):
        _check_extra(child)
        cparts = [*parts, str(n)]
        prefix = "c" + ".".join(cparts) + "-"
        path = child_path(child, n)
        title = _title(child)
        consumed = _consumed(child, title)
        section_id = prefix + "section"
        # A consumed title heading must not vanish from the body: the section heading carries it
        # (`README.md: Survey Kit`) unless it would only repeat the path.
        label = path
        if consumed and title and title.casefold() not in (path.casefold(), path.rsplit("/", 1)[-1].casefold()):
            label = f"{path}: {title}"
        flat.blocks.append(
            Heading(
                id=section_id,
                level=min(depth, 6),
                spans=[InlineSpan(text=label)],
                provenance=Provenance(source=child.metadata.source or path, path=path),
                attrs={CHILD_SECTION_ATTR: path},
            )
        )
        flat.index.block_child[section_id] = prefix
        levels = [b.level for b in child.blocks if isinstance(b, Heading) and b.id not in consumed]
        top = min(levels) if levels else 2
        for b in child.blocks:
            if b.id in consumed:
                continue
            nb = _child_block(b, prefix, depth, top)
            flat.blocks.append(nb)
            flat.index.block_child[nb.id] = prefix
        flat.warnings.extend(_child_warning(w, prefix, path) for w in child.warnings)
        for key, entries in child.sidecar_extra.items():
            flat.extra.setdefault(key, []).extend({**e, "child": path} for e in entries)
        flat.index.truncated |= child.truncated
        flat.index.infos.append(
            ChildInfo(
                prefix=prefix,
                path=path,
                depth=depth,
                converter=child.converter_id,
                title=title,
                block_count=len(child.blocks),
                source_type=child.metadata.source_type,
                section_id=section_id,
            )
        )
        _walk(child, cparts, depth + 1, flat)


def flatten_children(result: ConversionResult) -> tuple[ConversionResult, ChildIndex]:
    """The result with every child Document flattened into the parent's block list (see module doc).
    A result without children is returned unchanged with an empty index."""
    doc = result.document
    _check_extra(doc)
    if not doc.children:
        return result, ChildIndex()
    flat = _Flat()
    _walk(doc, [], 1, flat)
    extra = {k: list(v) for k, v in doc.sidecar_extra.items()}
    for key, entries in flat.extra.items():
        extra.setdefault(key, []).extend(entries)
    merged = Document(
        schema_version=doc.schema_version,
        metadata=doc.metadata,
        blocks=[*doc.blocks, *flat.blocks],
        warnings=[*doc.warnings, *flat.warnings],
        converter_id=doc.converter_id,
        content_hash=doc.content_hash,
        truncated=doc.truncated or flat.index.truncated,
        sidecar_extra=extra,
    )
    flat.index.source = doc
    return result.model_copy(update={"document": merged}), flat.index
