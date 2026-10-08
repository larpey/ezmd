"""Shared thread renderer to IR (part2 7c step 2): H1 title, the post body, `Comments (N)`, one `Comment`
block per node in display order with depth, score, and parent in `attrs`; deleted and dead nodes are kept as
placeholders so the tree shape survives (7c step 3). Provenance: `source_id` = node id, `path` =
`comments/<id>` (7c step 4)."""

from __future__ import annotations

from intomd.ir import (
    Block,
    Comment,
    Document,
    Heading,
    InlineSpan,
    Link,
    Metadata,
    Paragraph,
    Provenance,
    SourceType,
    Warning,
    WarningKind,
)
from intomd_converters.social.model import Thread, ThreadNode

PLACEHOLDER = {"deleted": "[deleted]", "removed": "[removed]", "dead": "[dead]"}


def _body(node: ThreadNode) -> str:
    if node.body:
        return node.body
    for flag in node.flags:
        if flag in PLACEHOLDER:
            return PLACEHOLDER[flag]
    return "[no text]"


def thread_document(thread: Thread, *, source: str, engine: str, max_comments: int) -> Document:
    def prov(node: ThreadNode, path: str) -> Provenance:
        return Provenance(source=source, path=path, source_id=node.id or None, engine=engine)

    root = thread.root
    blocks: list[Block] = [Heading(level=1, spans=[InlineSpan(text=thread.title)], provenance=prov(root, "post"))]
    if thread.url:
        blocks.append(Link(href=thread.url, text=thread.url, provenance=prov(root, "post")))
    if root.body:
        blocks.append(Paragraph(spans=[InlineSpan(text=root.body)], provenance=prov(root, "post")))
    nodes = thread.walk()
    shown = nodes[:max_comments]
    blocks.append(
        Heading(level=2, spans=[InlineSpan(text=f"Comments ({len(nodes)})")], provenance=prov(root, "comments"))
    )
    for node in shown:
        attrs = {"depth": str(node.depth)}
        if node.score is not None:
            attrs["score"] = str(node.score)
        if node.parent_id:
            attrs["parent_id"] = node.parent_id
        if node.flags:
            attrs["flags"] = ",".join(node.flags)
        blocks.append(
            Comment(
                author=node.author,
                created=node.created,
                spans=[InlineSpan(text=_body(node))],
                reply_to=node.parent_id,
                attrs=attrs,
                provenance=prov(node, f"comments/{node.id}"),
            )
        )
    warnings: list[Warning] = []
    if len(nodes) > len(shown):
        warnings.append(
            Warning(
                kind=WarningKind.COMMENTS_TRUNCATED,
                message=f"Showing {len(shown)} of {len(nodes)} comments.",
                count=len(nodes) - len(shown),
            )
        )
    if thread.collapsed:
        warnings.append(
            Warning(
                kind=WarningKind.COMMENTS_COLLAPSED,
                severity="info",
                message=f"{thread.collapsed} collapsed comments were not expanded.",
                count=thread.collapsed,
            )
        )
    return Document(
        metadata=Metadata(
            title=thread.title,
            source=source,
            source_type=SourceType.SOCIAL,
            author=root.author,
            published=root.created,
            extra={f"social.{k}": v for k, v in {"source": thread.source, **thread.extra}.items() if v},
        ),
        blocks=blocks,
        warnings=warnings,
    )
