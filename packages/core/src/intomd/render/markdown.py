"""intomd.render.markdown: the Markdown renderer (docs/spec/part3.md section D).

Pipeline: title and heading plan -> units per block -> footnote and page-marker placement -> cursor and token
budget -> head blocks and H1 -> (rag) chunking -> injection scan -> (agent) untrusted fence -> frontmatter
and sidecar. The body is deterministic for a given IR, profile and options; `fetched_at`, `converted_at`
and (with `agent_salt=random`) the fence id are the only nondeterministic values.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, datetime

from intomd.ir import ConversionResult, Image, SourceType, WarningKind
from intomd.profiles import Profile
from intomd.render import assemble
from intomd.render.base import Chunk, RenderedOutput, TokenCounter
from intomd.render.chunker import chunk_units
from intomd.render.context import RenderContext, Unit
from intomd.render.frontmatter import FrontmatterInputs, build_frontmatter, dump_yaml
from intomd.render.headings import plan_headings, resolve_title
from intomd.render.injection import InjectionReport, defang, fence_id, scan, wrap_untrusted
from intomd.render.sidecar import build_sidecar
from intomd.render.tokens import TiktokenCounter, count_tokens
from intomd.render.transcript import prepare_speakers
from intomd.render.units import build_units

__all__ = ["MarkdownRenderer", "RenderOptions", "render_markdown"]

_COMMENT = re.compile(r"<!--.*?-->", re.S)
_FENCE_TAG = re.compile(r"^</?untrusted_content\b[^\n]*$", re.M)
_WORD = re.compile(r"\w")


@dataclass(frozen=True, slots=True)
class RenderOptions:
    """Render-time inputs that are not profile options."""

    converted_at: datetime | None = None
    fetched_at: datetime | None = None
    sidecar_path: str | None = None
    cursor: str | None = None


def ensure_finalized(result: ConversionResult) -> ConversionResult:
    """Renderers need block ids and the IR hash. Finalize a deep copy when a converter skipped it
    (the caller's object is never mutated)."""
    doc = result.document
    if doc.content_hash and all(b.id for b in doc.blocks):
        return result
    return result.model_copy(update={"document": doc.model_copy(deep=True).finalize()})


def _base_url(result: ConversionResult) -> str | None:
    m = result.document.metadata
    for candidate in (m.canonical_url, m.source):
        if candidate and candidate.lower().startswith(("http://", "https://")):
            return candidate
    return None


def word_count(body: str) -> int:
    text = _FENCE_TAG.sub("", _COMMENT.sub(" ", body))
    return sum(1 for tok in text.split() if _WORD.search(tok))


def _scan_metadata(result: ConversionResult) -> dict[str, str]:
    m = result.document.metadata
    meta = {
        "title": m.title or "",
        "description": m.description or "",
        "author": m.author or "",
        "authors": ", ".join(m.authors),
        "keywords": ", ".join(m.keywords),
    }
    alts = [b.alt for b in result.document.blocks if isinstance(b, Image) and b.alt]
    if alts:
        meta["alt_text"] = " | ".join(alts)
    return meta


def _warning_codes(ctx: RenderContext) -> list[str]:
    codes: list[str] = []
    for w in [*ctx.result.all_warnings, *ctx.warnings]:
        if ctx.profile.minimal_frontmatter and w.severity == "info":
            continue
        if str(w.kind) not in codes:
            codes.append(str(w.kind))
    return codes


def _clean_lines(text: str) -> str:
    return "\n".join(line.rstrip() for line in text.split("\n")).rstrip("\n") + "\n"


def _docid(ctx: RenderContext) -> str:
    h = ctx.doc.content_hash.removeprefix("sha256:")
    return h[:12] if h else hashlib.sha256(ctx.doc.plain_text().encode("utf-8")).hexdigest()[:12]


@dataclass(slots=True)
class _Body:
    inner: str
    units: list[Unit]
    chunks: list[Chunk]
    truncation: dict[str, object]


def _build_body(ctx: RenderContext, title: str, options: RenderOptions) -> _Body:
    profile = ctx.profile
    consumed = plan_headings(ctx, title)
    prepare_speakers(ctx, ctx.doc)
    built = build_units(ctx, consumed)
    units = assemble.place_footnotes(ctx, built.units)
    units = assemble.place_page_markers(ctx, units)
    units, figures_dropped = assemble.drop_figures_for_budget(ctx, units, profile.max_tokens)
    start = assemble.cursor_start(units, options.cursor, profile.name)
    page = assemble.apply_budget(ctx, units, start, profile.max_tokens)
    truncation = page.truncation
    if figures_dropped and not truncation:
        truncation = {"reason": "max_tokens", "limit": profile.max_tokens or 0}
    # The head (summary, orientation, contents, H1) opens page 1 only; the links list closes the last page,
    # so concatenating every page rebuilds the unpaged body.
    head = [*assemble.head_units(ctx, built.summary, units), assemble.title_unit(ctx, title)] if start == 0 else []
    tail = assemble.links_units(ctx) if page.next_unit is None else []
    units = page.units
    if profile.untrusted_fence:
        for u in [*head, *units, *tail]:
            u.text, n = defang(u.text)
            ctx.fence_defanged += n
    chunks: list[Chunk] = []
    if profile.chunks.enabled:
        rules = profile.chunks
        chunks, pieces = chunk_units(
            [*units, *tail],
            title=title,
            docid=_docid(ctx),
            chunk_tokens=rules.chunk_tokens,
            min_chunk_tokens=rules.min_chunk_tokens,
            overlap_tokens=rules.overlap_tokens,
        )
        inner = "\n\n".join([*(u.text for u in head), *pieces])
    else:
        inner = "\n\n".join(u.text for u in [*head, *units, *tail] if u.text)
    return _Body(_clean_lines(inner), [*head, *units, *tail], chunks, truncation)


def render_markdown(
    result: ConversionResult,
    profile: Profile,
    options: RenderOptions | None = None,
    counter: TokenCounter | None = None,
) -> RenderedOutput:
    options = options or RenderOptions()
    result = ensure_finalized(result)
    ctx = RenderContext(profile=profile, result=result, base_url=_base_url(result))
    title = resolve_title(ctx)
    built = _build_body(ctx, title, options)
    meta = result.document.metadata
    report: InjectionReport = scan(
        built.inner,
        _scan_metadata(result),
        bidi_or_tags=ctx.stats.bidi_or_tags,
        chat=meta.source_type == SourceType.CHAT,
    )
    if report.warning:
        families = sorted({f.family for f in report.findings})
        ctx.warn(
            WarningKind.INJECTION_SUSPECTED,
            f"The content contains text that looks like instructions to an AI system ({report.risk} risk).",
            risk=report.risk,
            score=report.score,
            families=", ".join(families),
        )
    fid: str | None = None
    body = built.inner
    if profile.untrusted_fence:
        inner_hash = "sha256:" + hashlib.sha256(built.inner.encode("utf-8")).hexdigest()
        fid = fence_id(inner_hash, meta.source, "random" if profile.agent_salt == "random" else None)
        body = wrap_untrusted(built.inner, fid, meta.source, report.risk)
    tokens_map = count_tokens(body)
    converted = (options.converted_at or datetime.now(UTC)).replace(microsecond=0)
    truncated = result.truncated or ctx.truncated
    inputs = FrontmatterInputs(
        title=title,
        word_count=word_count(body),
        tokens=tokens_map,
        content_hash="sha256:" + hashlib.sha256(body.encode("utf-8")).hexdigest(),
        injection_risk=report.risk,
        warnings=_warning_codes(ctx),
        converted_at=converted,
        truncated=truncated,
        fetched_at=options.fetched_at,
        truncation=built.truncation,
        fence_id=fid,
        chunks=len(built.chunks) if profile.chunks.enabled else None,
        chunk_tokens=profile.chunks.chunk_tokens if profile.chunks.enabled else None,
        sidecar_path=options.sidecar_path,
        exports={"tables": [a.path for a in ctx.attachments]} if ctx.attachments else {},
        speakers=list(dict.fromkeys(ctx.speaker_names.values())),
    )
    fm = build_frontmatter(result, profile.name, profile.minimal_frontmatter, inputs, profile.include_extra_metadata)
    markdown = (dump_yaml(fm) if profile.frontmatter else "") + body
    counter = counter or TiktokenCounter()
    sidecar = None
    if profile.sidecar:
        sidecar = build_sidecar(
            ctx,
            frontmatter=fm,
            body=body,
            units=built.units,
            chunks=built.chunks,
            report=report,
            tokens_total=count_tokens(markdown)["o200k_base"],
        )
    return RenderedOutput(
        markdown=markdown,
        frontmatter=fm,
        sidecar=sidecar,
        chunks=built.chunks,
        attachments=list(ctx.attachments),
        tokens=counter.count(markdown),
        truncated=truncated,
        warnings=[*result.all_warnings, *ctx.warnings],
        injection_risk=report.risk,
        body=body,
    )


class MarkdownRenderer:
    format = "md"

    def __init__(self, counter: TokenCounter | None = None, options: RenderOptions | None = None) -> None:
        self.counter: TokenCounter = counter or TiktokenCounter()
        self.options = options or RenderOptions()

    def render(self, result: ConversionResult, profile: Profile) -> RenderedOutput:
        return render_markdown(result, profile, self.options, self.counter)
