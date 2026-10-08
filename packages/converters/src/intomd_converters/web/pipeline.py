"""The web/pages conversion pipeline shared by the three web converters (docs/spec/part2.md section 5).

decode (with the byte cap) -> parse -> signals and metadata on the raw tree -> hygiene (hidden elements,
invisible characters) -> extraction (Trafilatura, Defuddle-style rules, or the full body) -> post-checks
and fallbacks -> warnings -> metadata assembly. Never fetches: `options.allow_network` is not consulted
because nothing here needs the network; linked pages and PDFs are reported, not followed.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlsplit

from intomd.inputs import InputRef
from intomd.ir import (
    Block,
    Document,
    Heading,
    InlineSpan,
    Metadata,
    Paragraph,
    Provenance,
    SourceType,
    Warning,
    WarningKind,
    spans_text,
)
from intomd.registry import ConvertOptions
from intomd_converters.web import meta as page_meta
from intomd_converters.web import signals
from intomd_converters.web.boilerplate import main_content, strip_boilerplate
from intomd_converters.web.build import Builder
from intomd_converters.web.dom import base_url, body_of, decode_html, parse_html, same_origin, truncate_on_tag
from intomd_converters.web.html_blocks import convert_block, convert_children, register_footnotes
from intomd_converters.web.hygiene import HygieneReport, pre_clean
from intomd_converters.web.report import page_warnings

Engine = Literal["trafilatura", "rules", "full_body"]

DEFAULT_MAX_BYTES = 50 * 1024 * 1024
"""Local default HTML cap (part2 13.4, web page row). The public profile lowers it through Limits."""
MIN_EXTRACT_CHARS = 200
MIN_EXTRACT_RATIO = 0.25


@dataclass(slots=True)
class Page:
    """Everything measured about a page before extraction."""

    root: object
    body: object
    url: str | None
    source: str
    meta: page_meta.PageMeta
    sig: signals.Signals
    hygiene: HygieneReport
    clean_chars: int
    full_text: str
    truncated: bool
    encoding: str
    encoding_confidence: float
    walls_removed: int = 0


def _http(url: str | None) -> str | None:
    return url if url and urlsplit(url).scheme in ("http", "https") else None


def load_page(ref: InputRef, options: ConvertOptions) -> Page:
    cap = options.ctx.limits.max_bytes or DEFAULT_MAX_BYTES
    size = ref.size()
    truncated = size > cap
    raw = ref.head(cap) if truncated else ref.read()
    text, encoding, confidence = decode_html(raw, ref.fetched_headers)
    if truncated:
        text = truncate_on_tag(text, max(1, len(text) - 1))
    root = parse_html(text)
    url = _http(ref.url) or _http(ref.display)
    base = base_url(root, url)
    sig = signals.measure(root)
    pm = page_meta.extract(root, url, base)
    options.ctx.check_deadline()
    hygiene = pre_clean(root)
    body = body_of(root)
    walls = signals.remove_walls(body)
    full_text = signals.visible_text(body)
    stripped = deepcopy(body)
    strip_boilerplate(stripped)
    source = url or ref.display
    if url and pm.canonical_url and same_origin(url, pm.canonical_url):
        source = pm.canonical_url
    return Page(
        root=root,
        body=body,
        url=url,
        source=source,
        meta=pm,
        sig=sig,
        hygiene=hygiene,
        clean_chars=len(signals.visible_text(stripped)),
        full_text=full_text,
        truncated=truncated,
        encoding=encoding,
        encoding_confidence=confidence,
        walls_removed=walls,
    )


def _chars(blocks: list[Block]) -> int:
    doc_text = Document(metadata=Metadata(source="x", source_type=SourceType.HTML), blocks=list(blocks)).plain_text()
    return len(doc_text)


def _rules(page: Page, b: Builder) -> None:
    stripped = deepcopy(page.body)
    strip_boilerplate(stripped)
    register_footnotes(stripped, b)
    convert_block(main_content(stripped), b)


def _full_body(page: Page, b: Builder) -> None:
    body = deepcopy(page.body)
    strip_boilerplate(body, aggressive=False)
    register_footnotes(body, b)
    convert_children(body, b)


def _trafilatura(page: Page, b: Builder) -> bool:
    from intomd_converters.web.tei import run_trafilatura, tei_to_blocks

    main = run_trafilatura(page.root, page.url)
    if main is None:
        return False
    register_footnotes(page.body, b)
    tei_to_blocks(main, page.body, b)
    return True


def extract(page: Page, engine: Engine, conv_id: str, options: ConvertOptions) -> tuple[Builder, list[Warning]]:
    """Run the extractor chain from `engine` downwards (5b steps 2 to 4 and 5c step 16)."""
    base = base_url(page.root, page.url)
    notes: list[Warning] = []

    def fresh() -> Builder:
        return Builder(source=page.source, base=base, engine=conv_id)

    b = fresh()
    if engine == "trafilatura":
        ok = _trafilatura(page, b)
        got = _chars(b.blocks) if ok else 0
        reason = fallback_reason(got, page.clean_chars)
        if reason is not None:
            if page.clean_chars:
                notes.append(
                    Warning(
                        kind=WarningKind.ENGINE_FALLBACK,
                        severity="info",
                        message=(
                            f"Trafilatura extracted {got} of {page.clean_chars} page characters ({reason}); "
                            "used the rule-based extractor instead."
                        ),
                        detail={
                            "engine": "trafilatura",
                            "reason": reason,
                            "extracted_chars": got,
                            "page_chars": page.clean_chars,
                        },
                    )
                )
            b = fresh()
            _rules(page, b)
    elif engine == "rules":
        _rules(page, b)
    options.ctx.check_deadline()
    has_para = any(isinstance(x, Paragraph) for x in b.blocks)
    if engine == "full_body" or (not has_para and page.clean_chars > 0 and _chars(b.blocks) < page.clean_chars):
        b = fresh()
        _full_body(page, b)
        notes.append(
            Warning(
                kind=WarningKind.READABILITY_FALLBACK_FULL_BODY,
                message="No article was detected; the whole page body was converted with boilerplate removed.",
            )
        )
    normalize_headings(b.blocks, page.meta.title)
    return b, notes


_STUB_TEXT = {
    WarningKind.EMPTY_BODY_JS_REQUIRED: (
        "This page shows its content only after JavaScript runs; the static HTML has no article text. "
        "Convert it with browser rendering or the browser extension."
    ),
    WarningKind.EXTRACTION_EMPTY: "No text could be extracted from this page.",
}


def _stub(doc: Document, source: str) -> Paragraph:
    """The stub note for a page with no extractable content (part2 5c step 16), naming the reason."""
    kind = next((w.kind for w in doc.warnings if w.kind in _STUB_TEXT), WarningKind.EXTRACTION_EMPTY)
    return Paragraph(
        spans=[InlineSpan(text=_STUB_TEXT[kind])],
        attrs={"stub": "true", "reason": str(kind)},
        provenance=Provenance(source=source, path="body"),
    )


def fallback_reason(got: int, page_chars: int) -> str | None:
    """Why Trafilatura's result is too small (part2 5b step 3), or None when it is acceptable. A result that keeps
    at least 90 percent of the cleaned page text is acceptable even on a page shorter than 200 characters."""
    if got > 0 and got >= 0.9 * page_chars:
        return None
    if got < MIN_EXTRACT_CHARS:
        return f"under {MIN_EXTRACT_CHARS} characters"
    if got < MIN_EXTRACT_RATIO * page_chars:
        return f"under {int(MIN_EXTRACT_RATIO * 100)} percent of the page text"
    return None


def normalize_headings(blocks: list[Block], title: str | None) -> None:
    """When the page uses <h1> for every section, keep the title H1 and shift the rest down a level."""
    heads = [x for x in blocks if isinstance(x, Heading)]
    h1s = [h for h in heads if h.level == 1]
    if len(h1s) < 2:
        return
    keep = h1s[0] if title and spans_text(h1s[0].spans).strip().casefold() == title.strip().casefold() else None
    for h in heads:
        if h is not keep:
            h.level = min(6, h.level + 1)


def build_document(ref: InputRef, options: ConvertOptions, engine: Engine, conv_id: str) -> Document:
    options.ctx.progress("parse", 0.1, "parsing HTML")
    page = load_page(ref, options)
    options.ctx.progress("extract", 0.4, "extracting the article")
    b, notes = extract(page, engine, conv_id, options)
    pm = page.meta
    metadata = Metadata(
        source=page.source,
        source_type=SourceType.WEB if page.url else SourceType.HTML,
        mime=ref.detected.mime if ref.detected else "text/html",
        title=pm.title,
        author=pm.author,
        authors=pm.authors,
        published=pm.published,
        modified=pm.modified,
        description=pm.description,
        keywords=pm.keywords,
        canonical_url=pm.canonical_url,
        site_name=pm.site_name,
        language=pm.language,
        language_source="declared" if pm.language else None,
        encoding=page.encoding,
        encoding_confidence=page.encoding_confidence,
    )
    doc = Document(metadata=metadata, blocks=b.blocks, truncated=page.truncated)
    extracted = _chars(b.blocks)
    if page.clean_chars:
        metadata.extra["readability_ratio"] = round(min(1.0, extracted / page.clean_chars), 2)
    pdfs = sorted({h for h in b.link_hrefs if urlsplit(h).path.lower().endswith(".pdf")})
    if pdfs:
        metadata.extra["outbound_pdfs"] = " ".join(pdfs[:20])
    if page.url and pm.canonical_url and not same_origin(page.url, pm.canonical_url):
        metadata.extra["canonical_cross_origin"] = True
    doc.warnings.extend(notes)
    doc.warnings.extend(page_warnings(page, b, extracted, metadata))
    if not doc.blocks:
        doc.blocks.append(_stub(doc, page.source))
    options.ctx.progress("done", 1.0, "converted")
    return doc.finalize()
