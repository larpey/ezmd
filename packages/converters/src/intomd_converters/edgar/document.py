"""Assemble EDGAR Documents: a filing (title, cover facts, items, exhibits), a filing index, or full-text
search results (part2 12c steps 2, 3, 5, 6)."""

from __future__ import annotations

import re
from datetime import UTC, datetime

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
from intomd_converters.edgar.html import ENGINE, ParsedFiling
from intomd_converters.edgar.index import FilingIndex, docs_table, index_blocks, kv_table
from intomd_converters.edgar.items import Sectioned, section
from intomd_converters.edgar.urls import EdgarTarget

COVER_FACTS: tuple[tuple[str, str], ...] = (
    ("Form", "DocumentType"),
    ("Period", "DocumentPeriodEndDate"),
    ("CIK", "EntityCentralIndexKey"),
    ("Ticker", "TradingSymbol"),
    ("Exchange", "SecurityExchangeName"),
    ("Commission file number", "EntityFileNumber"),
    ("Filer status", "EntityFilerCategory"),
    ("Fiscal year end", "CurrentFiscalYearEndDate"),
    ("Shares outstanding", "EntityCommonStockSharesOutstanding"),
    ("Public float", "EntityPublicFloat"),
    ("Fiscal year focus", "DocumentFiscalYearFocus"),
    ("Fiscal period focus", "DocumentFiscalPeriodFocus"),
    ("Amendment", "AmendmentFlag"),
)
ITEM_FORMS = frozenset({"10-K", "10-K/A", "10-Q", "10-Q/A", "20-F", "8-K", "8-K/A", "S-1", "DEF 14A", "10-KT"})
_EX13 = re.compile(r"exhibit\s+13", re.I)


def _date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").replace(tzinfo=UTC)
    except ValueError:
        return None


def edgar_metadata(
    *, title: str, source: str, target: EdgarTarget | None, idx: FilingIndex | None, facts: dict[str, str]
) -> Metadata:
    cik = (idx.cik if idx else None) or (target.cik if target else None) or facts.get("EntityCentralIndexKey")
    accession = (idx.accession if idx else None) or (target.accession if target else None)
    extra: dict[str, str | int | float | bool | None] = {
        "edgar.cik": str(int(cik)) if cik and cik.isdigit() else cik,
        "edgar.company": facts.get("EntityRegistrantName") or (idx.company if idx else None),
        "edgar.form": facts.get("DocumentType") or (idx.form if idx else None),
        "edgar.filed": idx.filed if idx else None,
        "edgar.period": (idx.period if idx else None) or facts.get("DocumentPeriodEndDate"),
        "edgar.accession": accession,
        "edgar.url": source,
    }
    return Metadata(
        title=title,
        source=source,
        source_type=SourceType.HTML,
        mime="text/html",
        published=_date(idx.filed if idx else None),
        extra={k: v for k, v in extra.items() if v},
    )


def _title(facts: dict[str, str], idx: FilingIndex | None) -> str:
    company = facts.get("EntityRegistrantName") or (idx.company if idx else None)
    form = facts.get("DocumentType") or (idx.form if idx else None)
    period = facts.get("DocumentPeriodEndDate") or (idx.period if idx else None)
    return " ".join(p for p in (company, form, period) if p) or "EDGAR filing"


def _cover_rows(facts: dict[str, str], idx: FilingIndex | None, accession: str | None) -> list[tuple[str, str]]:
    rows = [(label, facts[key]) for label, key in COVER_FACTS if facts.get(key)]
    if idx is not None and idx.filed:
        rows.append(("Filed", idx.filed))
    if accession:
        rows.append(("Accession", accession))
    return rows


def _item8_by_reference(sec: Sectioned) -> bool:
    """Item 8 is a short pointer to Exhibit 13 (the annual report to shareholders)."""
    body: list[str] = []
    in8 = False
    for b in sec.blocks:
        if isinstance(b, Heading) and b.level == 2:
            in8 = (b.provenance.path or "").endswith("item/8") or (b.provenance.path or "").endswith("-8")
            continue
        if in8 and isinstance(b, Paragraph):
            body.append(spans_text(b.spans))
    text = " ".join(body)
    return bool(text) and len(text) < 600 and _EX13.search(text) is not None


def filing_document(
    parsed: ParsedFiling,
    *,
    source: str,
    target: EdgarTarget | None,
    idx: FilingIndex | None,
    infer_headings: bool,
) -> Document:
    accession = (idx.accession if idx else None) or (target.accession if target else None)
    facts = parsed.facts
    sec = section(parsed.blocks, accession=accession, infer_headings=infer_headings)
    title = _title(facts, idx)

    def prov(path: str) -> Provenance:
        return Provenance(source=source, path=path, source_id=accession, engine=ENGINE)

    blocks: list[Block] = [Heading(level=1, spans=[InlineSpan(text=title)], provenance=prov("cover"))]
    rows = _cover_rows(facts, idx, accession)
    if rows:
        blocks.append(kv_table(rows, prov("cover")))
    cover = [b for b in sec.blocks if b.provenance.path == "cover"]
    if cover:
        blocks.append(Heading(level=2, spans=[InlineSpan(text="Cover page")], provenance=prov("cover")))
    blocks.extend(sec.blocks)
    if idx is not None and idx.exhibits():
        blocks.append(Heading(level=2, spans=[InlineSpan(text="Exhibits")], provenance=prov("exhibits")))
        blocks.append(docs_table(idx.exhibits(), prov("exhibits")))
    doc = Document(
        metadata=edgar_metadata(title=title, source=source, target=target, idx=idx, facts=facts),
        blocks=blocks,
        warnings=filing_warnings(sec, parsed, facts.get("DocumentType") or (idx.form if idx else None)),
    )
    doc.metadata.encoding = parsed.encoding
    return doc


def filing_warnings(sec: Sectioned, parsed: ParsedFiling, form: str | None) -> list[Warning]:
    out: list[Warning] = []
    if form and form.upper() in ITEM_FORMS and not sec.items:
        out.append(
            Warning(
                kind=WarningKind.UNSUPPORTED_FEATURE,
                message=f"No item headings were recognized in this {form}; the output follows document order.",
                detail={"form": form},
            )
        )
    if _item8_by_reference(sec):
        out.append(
            Warning(
                kind=WarningKind.ATTACHMENT_UNCONVERTED,
                message="Item 8 incorporates the financial statements from Exhibit 13; convert that exhibit too "
                "(option specialized.edgar_exhibits=true with network access).",
            )
        )
    if sec.furniture_removed:
        out.append(
            Warning(
                kind=WarningKind.REMOVED_RUNNING_HEADER_FOOTER,
                severity="info",
                message=f"Removed {sec.furniture_removed} page numbers and repeated page links.",
                count=sec.furniture_removed,
            )
        )
    if sec.inferred_headings:
        out.append(
            Warning(
                kind=WarningKind.HEADING_INFERRED_FROM_FORMATTING,
                severity="info",
                message=f"{sec.inferred_headings} sub-headings were inferred from bold or italic lines.",
                count=sec.inferred_headings,
            )
        )
    hidden = parsed.hygiene.elements
    if hidden:
        out.append(
            Warning(
                kind=WarningKind.REMOVED_HIDDEN_ELEMENTS,
                message=f"Removed {hidden} hidden elements with text.",
                count=hidden,
            )
        )
    return out


def index_document(idx: FilingIndex, *, source: str, target: EdgarTarget | None) -> Document:
    title = " ".join(p for p in (idx.company, idx.form, idx.period) if p) or "EDGAR filing"
    return Document(
        metadata=edgar_metadata(title=title, source=source, target=target, idx=idx, facts={}),
        blocks=index_blocks(idx, source, with_title=True),
    )


def search_document(blocks: list[Block], *, source: str, query: str | None) -> Document:
    warnings: list[Warning] = []
    if len(blocks) < 2:
        warnings.append(Warning(kind=WarningKind.EXTRACTION_EMPTY, message="The full-text search returned no filings."))
    return Document(
        metadata=Metadata(
            title=spans_text(blocks[0].spans) if isinstance(blocks[0], Heading) else "EDGAR full-text search",
            source=source,
            source_type=SourceType.WEB,
            mime="application/json",
            extra={"edgar.query": query} if query else {},
        ),
        blocks=blocks,
        warnings=warnings,
    )
