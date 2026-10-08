"""intomd.render.sidecar: the `<name>.intomd.json` sidecar (docs/spec/part3.md section 13).

Mirrors the frontmatter and adds sections, tables, figures, links, speakers, segments, slides, footnotes,
warnings with detail, per-block provenance, injection findings, render counters, chunks (rag), and the IR
document itself. Byte offsets (`offset_start`, `offset_end`) are relative to the body.
"""

from __future__ import annotations

from intomd.ir import Slide, WarningKind
from intomd.render.base import Chunk
from intomd.render.context import RenderContext, Unit
from intomd.render.injection import InjectionReport
from intomd.render.tokens import tokens_estimated

__all__ = ["SIDECAR_SCHEMA", "build_sidecar", "locate_units"]

SIDECAR_SCHEMA = "intomd.sidecar/1"


def locate_units(body: str, units: list[Unit]) -> dict[int, tuple[int, int]]:
    """Byte offsets of each unit's text inside the body, searched in order. Keyed by unit index."""
    out: dict[int, tuple[int, int]] = {}
    pos = 0
    for i, u in enumerate(units):
        if not u.text:
            continue
        idx = body.find(u.text, pos)
        if idx < 0:
            continue
        start = len(body[:idx].encode("utf-8"))
        out[i] = (start, start + len(u.text.encode("utf-8")))
        pos = idx + len(u.text)
    return out


def _sections(units: list[Unit], offsets: dict[int, tuple[int, int]], body_len: int) -> list[dict[str, object]]:
    heads = [(i, u) for i, u in enumerate(units) if u.kind == "heading" and u.heading is not None]
    out: list[dict[str, object]] = []
    for n, (i, u) in enumerate(heads):
        h = u.heading
        if h is None:
            continue
        start = offsets.get(i, (None, None))[0]
        nxt = next((offsets[j][0] for j, _ in heads[n + 1 :] if j in offsets), body_len)
        out.append(
            {
                "id": h.anchor,
                "number": h.number,
                "title": h.title,
                "original_title": h.original_title,
                "level": h.level,
                "original_level": h.original_level,
                "block_id": h.block_id,
                "time_start": h.time_start,
                "time_end": h.time_end,
                "offset_start": start,
                "offset_end": nxt if start is not None else None,
            }
        )
    return out


def build_sidecar(
    ctx: RenderContext,
    *,
    frontmatter: dict[str, object],
    body: str,
    units: list[Unit],
    chunks: list[Chunk],
    report: InjectionReport,
    tokens_total: int,
) -> dict[str, object]:
    offsets = locate_units(body, units)
    lists = {k: [dict(e) for e in v] for k, v in ctx.sidecar_lists.items()}
    for i, u in enumerate(units):
        if u.sidecar_key and i in offsets:
            name, idx = u.sidecar_key
            lists[name][idx]["offset_start"], lists[name][idx]["offset_end"] = offsets[i]
    doc = ctx.doc
    dump = doc.model_dump(mode="json", exclude={"children"})
    if ctx.profile.name != "full":
        for block in dump.get("blocks", []):
            if isinstance(block, dict) and block.get("type") == "transcript_segment":
                block.pop("words", None)
    provenance = [
        {"block_id": b.id, "type": b.type, **b.provenance.model_dump(mode="json", exclude_none=True)}
        for b in doc.blocks
    ]
    sidecar: dict[str, object] = {
        "schema": SIDECAR_SCHEMA,
        "profile": ctx.profile.name,
        "frontmatter": frontmatter,
        "heading_shift": ctx.heading_shift,
        "sections": _sections(units, offsets, len(body.encode("utf-8"))),
        "tables": lists.get("tables", []),
        "figures": lists.get("figures", []),
        "links": [{"text": r.text, "href": r.href, "original_href": r.original} for r in ctx.links.records],
        "speakers": [{"label": k, "name": v} for k, v in ctx.speaker_names.items()],
        "segments": lists.get("segments", []),
        "slides": [{"index": b.index, "title": b.title, "block_id": b.id} for b in doc.blocks if isinstance(b, Slide)],
        "footnotes": lists.get("footnotes", []),
        "warnings": [w.model_dump(mode="json") for w in [*ctx.result.all_warnings, *ctx.warnings]],
        "provenance": provenance,
        "injection_findings": [f.to_dict() for f in report.findings],
        "counts": {
            "furniture_removed": ctx.furniture_removed,
            "images_dropped_decorative": ctx.images_dropped_decorative,
            "removed_nonprinting": ctx.stats.removed_nonprinting + _upstream_nonprinting(ctx),
            "fence_defanged": ctx.fence_defanged,
            "headers_synthesized": ctx.header_synthesized,
        },
        "tokens_total": tokens_total,
        "tokens_estimated": tokens_estimated(),
        "metrics": ctx.result.metrics.model_dump(mode="json"),
        "document": dump,
    }
    if ctx.profile.chunks.enabled:
        sidecar["chunks"] = [c.to_dict() for c in chunks]
    return sidecar


def _upstream_nonprinting(ctx: RenderContext) -> int:
    """Characters a converter already stripped, reported through its removed_hidden_elements warning."""
    return sum(
        w.count or 0
        for w in ctx.result.all_warnings
        if w.kind in (WarningKind.REMOVED_HIDDEN_ELEMENTS, WarningKind.REMOVED_INVISIBLE_CHARS)
    )
