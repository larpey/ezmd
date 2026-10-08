"""`specialized.edgar`: SEC EDGAR filings, filing indexes, company lookups, and full-text search.

Offline first: when the input already has a body (an uploaded or pre-fetched filing, a fixture) nothing is
fetched. Without a body the converter fetches only when `options.allow_network` is true, with the declared
SEC identity and the shared 5 requests/second limit; otherwise it asks the pipeline for the body with
`FetchRequired` (Archives and search URLs) or fails with a clear message (accession and company lookups,
which need several API calls).
"""

from __future__ import annotations

from typing import Any

from ezmd.context import Limits
from ezmd.inputs import FetchRequired, InputRef
from ezmd.ir import Document, Warning, WarningKind
from ezmd.registry import ConversionError, ConvertOptions
from ezmd_converters.edgar.client import EdgarClient, Transport, netguard_transport, require_identity
from ezmd_converters.edgar.document import filing_document, index_document, search_document
from ezmd_converters.edgar.html import parse_filing, submission_document
from ezmd_converters.edgar.index import FilingIndex, IndexDoc, parse_index, search_blocks
from ezmd_converters.edgar.urls import EdgarTarget, company_target, parse_target

MIMES: tuple[str, ...] = (
    "text/html",
    "application/xhtml+xml",
    "application/json",
    "text/plain",
    "text/x-uri",
    "application/xml",
)
TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:0>10}.json"
SEARCH_URL = "https://efts.sec.gov/LATEST/search-index?q={q}"
DEFAULT_FORM = "10-K"
MAX_EXHIBITS = 10
_CONVERTIBLE = (".htm", ".html", ".txt", ".xml", ".pdf")
# An uploaded filing has no EDGAR URL to claim it by; inline XBRL (every EDGAR primary document since
# 2019) declares this namespace on the root element, and detection may call the file XML because of its
# `<?xml ...?>` declaration. The sniff reads only the head of the body.
IXBRL_NAMESPACE = b"http://www.xbrl.org/2013/inlineXBRL"
_SNIFF_BYTES = 64 * 1024
_SNIFF_MIMES = ("text/html", "application/xhtml+xml", "application/xml")


def _opt_bool(options: ConvertOptions, key: str, default: bool) -> bool:
    v = options.extra.get(f"specialized.{key}", default)
    return v if isinstance(v, bool) else str(v).lower() in ("1", "true", "yes", "on")


def _opt_str(options: ConvertOptions, key: str) -> str | None:
    v = options.extra.get(f"specialized.{key}")
    return str(v).strip() or None if v is not None else None


def _is_inline_xbrl(ref: InputRef) -> bool:
    """True for a body that is an inline XBRL (X)HTML document: an uploaded EDGAR filing."""
    mime = ref.detected.mime if ref.detected else None
    if not ref.has_body or mime not in _SNIFF_MIMES:
        return False
    try:
        head = ref.head(_SNIFF_BYTES)
    except OSError:
        return False
    return IXBRL_NAMESPACE in head and b"<html" in head.lower()


class EdgarConverter:
    id = "specialized.edgar"
    family = "specialized"
    priority = 50
    experimental = False
    requires_extras: tuple[str, ...] = ()
    mimes: tuple[str, ...] = MIMES
    limits = Limits(max_bytes=50 * 1024 * 1024, max_entries=MAX_EXHIBITS, timeout_s=300.0)

    def __init__(self, transport: Transport | None = None) -> None:
        self._transport = transport

    def can_handle(self, ref: InputRef) -> float:
        target = parse_target(ref.url) or parse_target(ref.display)
        if target is None:
            return 0.95 if _is_inline_xbrl(ref) else 0.0
        mime = ref.detected.mime if ref.detected else None
        if ref.has_body and mime not in MIMES:
            return 0.0
        return 0.95

    def _target(self, ref: InputRef, options: ConvertOptions) -> EdgarTarget:
        target = parse_target(ref.url) or parse_target(ref.display)
        if target is None and _opt_str(options, "edgar_form"):
            target = company_target(ref.display, _opt_str(options, "edgar_form"))
        if target is None and ref.has_body:
            # Forced conversion (`--converter specialized.edgar`) of a saved filing without an EDGAR URL.
            url = ref.url if ref.url and ref.url.startswith(("http://", "https://")) else None
            return EdgarTarget(kind="document", url=url)
        if target is None:
            raise ConversionError(
                f"not an EDGAR input: {ref.display}", user_message="This is not a SEC EDGAR URL or accession number."
            )
        return target

    def convert(self, ref: InputRef, options: ConvertOptions) -> Document:
        target = self._target(ref, options)
        options.ctx.progress("edgar", 0.0, "resolving filing")
        lookup = target.kind in ("company", "accession")
        if ref.has_body and not lookup:
            doc = self._from_body(
                ref.read(), target, options, source=target.url or ref.display, headers=ref.fetched_headers
            )
        elif options.allow_network:
            doc = self._fetch(target, options)
        else:
            fetch_url = target.url if target.kind in ("document", "index", "search") else None
            if fetch_url:
                raise FetchRequired(fetch_url, residential=False, reason="EDGAR document body not fetched")
            raise ConversionError(
                f"EDGAR {target.kind} lookup needs network access",
                user_message="Looking up an EDGAR filing by accession number or company needs network access; "
                "pass the filing's sec.gov Archives URL or enable network access.",
                retryable_with_fallback=ref.has_body,
            )
        options.ctx.progress("edgar", 1.0, "done")
        return doc.finalize()

    # Offline -------------------------------------------------------------------------------------------

    def _from_body(
        self,
        raw: bytes,
        target: EdgarTarget,
        options: ConvertOptions,
        *,
        source: str,
        headers: dict[str, str] | None = None,
        idx: FilingIndex | None = None,
    ) -> Document:
        cap = options.ctx.limits.max_bytes or self.limits.max_bytes
        if cap is not None and len(raw) > cap:
            raise ConversionError(f"EDGAR body {len(raw)} bytes exceeds {cap}", user_message="The filing is too large.")
        if not raw.strip():
            raise ConversionError("empty EDGAR body", user_message="The EDGAR response was empty.")
        if target.kind == "search" or raw.lstrip()[:1] in (b"{", b"["):
            blocks = search_blocks(raw, source, target.query)
            if blocks is None:
                raise ConversionError("unrecognized EDGAR JSON", user_message="Unrecognized EDGAR JSON response.")
            return search_document(blocks, source=source, query=target.query)
        sub = submission_document(raw)
        if sub is not None:
            raw = sub[1]
        index = parse_index(raw, headers)
        if index is not None:
            return index_document(index, source=source, target=target)
        options.ctx.check_deadline()
        parsed = parse_filing(raw, source=source, base=source if source.startswith("http") else None, headers=headers)
        doc = filing_document(
            parsed,
            source=source,
            target=target,
            idx=idx,
            infer_headings=_opt_bool(options, "edgar_infer_headings", True),
        )
        if not doc.blocks[1:]:
            doc.warnings.append(Warning(kind=WarningKind.EXTRACTION_EMPTY, message="The filing has no text."))
        return doc

    # Network -------------------------------------------------------------------------------------------

    def _client(self, options: ConvertOptions) -> EdgarClient:
        identity = require_identity(options)
        return EdgarClient(identity=identity, options=options, transport=self._transport or netguard_transport())

    def _fetch(self, target: EdgarTarget, options: ConvertOptions) -> Document:
        client = self._client(options)
        if target.kind == "search":
            url = target.url or SEARCH_URL.format(q=target.query or "")
            res = client.get(url, accept="application/json")
            return self._from_body(res.body, target, options, source=url)
        if target.kind == "company":
            target = self._resolve_company(client, target, options)
        if target.kind == "document" and target.filename and target.filename.lower().endswith(".txt"):
            res = client.get(target.url or f"{target.folder_url}/{target.filename}")
            return self._from_body(res.body, target, options, source=res.url)
        idx = self._index(client, target)
        doc_url = target.document_url if target.kind == "document" else None
        if doc_url is None:
            primary = idx.primary() if idx else None
            if primary is None or not primary.url:
                raise ConversionError("filing index lists no documents", user_message="The EDGAR filing is empty.")
            doc_url = primary.url
        options.ctx.progress("edgar", 0.4, "fetching filing document")
        res = client.get(doc_url)
        doc = self._from_body(res.body, target, options, source=doc_url, headers=res.headers, idx=idx)
        if idx is not None and _opt_bool(options, "edgar_exhibits", False):
            self._exhibits(client, idx, options, doc)
        return doc

    def _index(self, client: EdgarClient, target: EdgarTarget) -> FilingIndex | None:
        url = target.index_url
        if url is None:
            return None
        res = client.get(url)
        idx = parse_index(res.body, res.headers)
        if idx is None:
            raise ConversionError(f"unrecognized EDGAR index page {url}", user_message="Unrecognized EDGAR index page.")
        return idx

    def _resolve_company(self, client: EdgarClient, target: EdgarTarget, options: ConvertOptions) -> EdgarTarget:
        company = target.company or ""
        cik = company if company.isdigit() else self._ticker_cik(client, company)
        form = (target.form or _opt_str(options, "edgar_form") or DEFAULT_FORM).upper()
        year = _opt_str(options, "edgar_year")
        data = client.get_json(SUBMISSIONS_URL.format(cik=int(cik)))
        recent = data.get("filings", {}).get("recent", {}) if isinstance(data, dict) else {}
        forms, accs, docs = recent.get("form", []), recent.get("accessionNumber", []), recent.get("primaryDocument", [])
        dates = recent.get("reportDate", []) or recent.get("filingDate", [])
        for i, f in enumerate(forms):
            if str(f).upper() != form or i >= len(accs) or i >= len(docs):
                continue
            if year and not str(dates[i] if i < len(dates) else "").startswith(year):
                continue
            return EdgarTarget(kind="document", cik=str(int(cik)), accession=str(accs[i]), filename=str(docs[i]))
        raise ConversionError(
            f"no {form} filing for {company}",
            user_message=f"No {form} filing was found for {company}.",
            retryable_with_fallback=False,
        )

    def _ticker_cik(self, client: EdgarClient, ticker: str) -> str:
        data: Any = client.get_json(TICKERS_URL)
        rows = data.values() if isinstance(data, dict) else []
        for row in rows:
            if isinstance(row, dict) and str(row.get("ticker", "")).upper() == ticker.upper():
                return str(int(row["cik_str"]))
        raise ConversionError(
            f"unknown ticker {ticker}",
            user_message=f"The ticker {ticker} is not in the SEC list.",
            retryable_with_fallback=False,
        )

    def _exhibits(self, client: EdgarClient, idx: FilingIndex, options: ConvertOptions, doc: Document) -> None:
        """Convert exhibits as child documents (`specialized.edgar_exhibits=true`), at most MAX_EXHIBITS."""
        todo: list[IndexDoc] = [e for e in idx.exhibits() if e.url and e.name.lower().endswith(_CONVERTIBLE)]
        for n, ex in enumerate(todo[:MAX_EXHIBITS]):
            options.ctx.progress("edgar", 0.5 + 0.5 * n / max(1, len(todo)), f"exhibit {ex.name}")
            res = client.get(ex.url)
            child_ref = InputRef.from_bytes(res.body, filename=ex.name, declared_mime=res.content_type or None)
            child_ref.url = ex.url
            child_ref.display = ex.url
            try:
                result = options.ctx.convert_child(child_ref, label=f"{ex.type} {ex.name}")
            except ConversionError as e:
                doc.warnings.append(
                    Warning(kind=WarningKind.ATTACHMENT_FAILED, message=f"Exhibit {ex.name} failed: {e.user_message}")
                )
                continue
            finally:
                child_ref.cleanup()
            doc.children.append(result.document)
        if len(todo) > MAX_EXHIBITS:
            doc.warnings.append(
                Warning(
                    kind=WarningKind.ATTACHMENT_SKIPPED,
                    message=f"Converted the first {MAX_EXHIBITS} of {len(todo)} exhibits.",
                    count=len(todo) - MAX_EXHIBITS,
                )
            )
