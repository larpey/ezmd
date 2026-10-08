"""EDGAR converter tests. Everything is offline: network flows use a fake transport serving recorded files."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from intomd.detect import detect
from intomd.inputs import FetchRequired, InputRef
from intomd.ir import Document, Heading, Table, WarningKind, spans_text
from intomd.pipeline import convert_ref
from intomd.registry import ConversionError, ConvertOptions
from intomd_converters.edgar import CHAINS, converters
from intomd_converters.edgar.client import IDENTITY_ENV, EdgarClient, RateLimiter, Response, resolve_identity
from intomd_converters.edgar.converter import EdgarConverter

ROOT = Path(__file__).resolve().parents[4]
FIX = ROOT / "fixtures" / "edgar"
FOLDER = "https://www.sec.gov/Archives/edgar/data/1376986/000137698626000026"
DOC_URL = f"{FOLDER}/tve-20260424.htm"
INDEX_URL = f"{FOLDER}/0001376986-26-000026-index.html"
IDENTITY = "Test Runner test@example.com"
EXHIBIT = (
    b"<html><body><p><b>OFFER LETTER</b></p><p>Dear Mr. Skaggs, this letter sets out your terms.</p></body></html>"
)


class FakeSec:
    """Serves recorded responses by URL and records the headers of every request."""

    def __init__(self, routes: dict[str, bytes | int]) -> None:
        self.routes = routes
        self.calls: list[tuple[str, dict[str, str]]] = []

    def __call__(self, url: str, headers: dict[str, str]) -> Response:
        self.calls.append((url, headers))
        body = self.routes.get(url, 404)
        if isinstance(body, int):
            return Response(status=body, headers={}, body=b"", url=url)
        ctype = "application/json" if body.lstrip()[:1] in (b"{", b"[") else "text/html"
        return Response(status=200, headers={"content-type": ctype}, body=body, url=url)


def _routes() -> dict[str, bytes | int]:
    return {
        DOC_URL: (FIX / "tva-8k" / "input.htm").read_bytes(),
        INDEX_URL: (FIX / "tva-8k-index" / "input.html").read_bytes(),
        f"{FOLDER}/offerletter.htm": EXHIBIT,
    }


def _opts(**extra: object) -> ConvertOptions:
    opts = ConvertOptions(allow_network=True)
    opts.extra.update({"specialized.edgar_identity": IDENTITY, **extra})  # type: ignore[arg-type]
    return opts


def _url_ref(url: str) -> InputRef:
    ref = InputRef.from_url(url)
    detect(ref)
    return ref


def _headings(doc: Document, level: int | None = None) -> list[str]:
    return [spans_text(b.spans) for b in doc.blocks if isinstance(b, Heading) and (level is None or b.level == level)]


def test_family_registers_one_converter_and_no_chain() -> None:
    convs = converters()
    assert [c.id for c in convs] == ["specialized.edgar"]
    assert CHAINS == {}


def test_offline_body_converts_items_with_provenance() -> None:
    ref = InputRef.from_path(FIX / "tva-8k" / "input.htm")
    ref.url = DOC_URL
    detect(ref)
    conv = EdgarConverter()
    assert conv.can_handle(ref) == pytest.approx(0.95)
    doc = conv.convert(ref, ConvertOptions())
    h2 = _headings(doc, 2)
    assert h2[0] == "Cover page"
    assert any(h.startswith("Item 5.02 Departure of Directors") for h in h2)
    assert "Item 9.01 Financial Statements and Exhibits." in h2
    assert doc.metadata.extra["edgar.accession"] == "0001376986-26-000026"
    assert doc.metadata.extra["edgar.cik"] == "1376986"
    item = next(b for b in doc.blocks if isinstance(b, Heading) and spans_text(b.spans).startswith("Item 5.02"))
    assert item.provenance.path == "item/5.02"
    assert all(b.provenance.source_id == "0001376986-26-000026" for b in doc.blocks)
    assert "dei:" not in doc.plain_text() and "0001376986</ix" not in doc.plain_text()


def test_pipeline_routes_edgar_url_ahead_of_web_chain() -> None:
    ref = InputRef.from_path(FIX / "tva-8k" / "input.htm")
    ref.url = DOC_URL
    ref.display = DOC_URL
    result = convert_ref(ref, ConvertOptions())
    assert result.converter_id == "specialized.edgar"


@pytest.mark.parametrize("fixture", ["tva-8k", "synthetic-10k"])
def test_uploaded_inline_xbrl_routes_to_edgar(fixture: str) -> None:
    """An uploaded filing has no EDGAR URL; the inline XBRL namespace claims it ahead of data.xml/web."""
    path = next((FIX / fixture).glob("input.*"))
    ref = InputRef.from_bytes(path.read_bytes(), filename=path.name)
    detect(ref)
    assert EdgarConverter().can_handle(ref) == pytest.approx(0.95)
    result = convert_ref(ref, ConvertOptions())
    assert result.converter_id == "specialized.edgar"
    assert _headings(result.document, 2)[0] == "Cover page"


def test_inline_xbrl_sniff_needs_html_and_the_namespace() -> None:
    xml = b'<?xml version="1.0"?><xbrl xmlns:ix="http://www.xbrl.org/2013/inlineXBRL"/>'
    ref = InputRef.from_bytes(xml, filename="facts.xml")
    detect(ref)
    assert EdgarConverter().can_handle(ref) == 0.0
    plain = InputRef.from_bytes(b"<html><body>inlineXBRL is mentioned here</body></html>", filename="a.htm")
    detect(plain)
    assert EdgarConverter().can_handle(plain) == 0.0


def test_plain_html_without_edgar_url_is_not_claimed() -> None:
    ref = InputRef.from_bytes(b"<html><body><p>Item 1. Business</p></body></html>", filename="a.html")
    detect(ref)
    assert EdgarConverter().can_handle(ref) == 0.0


def test_no_body_no_network_requests_fetch() -> None:
    with pytest.raises(FetchRequired) as e:
        EdgarConverter().convert(_url_ref(DOC_URL), ConvertOptions())
    assert e.value.url == DOC_URL


def test_accession_without_network_fails_clearly() -> None:
    ref = InputRef.from_bytes(b"x", filename="x")
    ref.data = None
    ref.display = "0001376986-26-000026"
    with pytest.raises(ConversionError) as e:
        EdgarConverter().convert(ref, ConvertOptions())
    assert "network" in e.value.user_message


def test_missing_identity_fails_before_any_request(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(IDENTITY_ENV, raising=False)
    fake = FakeSec(_routes())
    with pytest.raises(ConversionError) as e:
        EdgarConverter(transport=fake).convert(_url_ref(DOC_URL), ConvertOptions(allow_network=True))
    assert IDENTITY_ENV in e.value.user_message
    assert not e.value.retryable_with_fallback
    assert fake.calls == []


def test_identity_validation_and_precedence() -> None:
    assert resolve_identity(ConvertOptions(), {IDENTITY_ENV: "Jane jane@example.org"}) == "Jane jane@example.org"
    assert resolve_identity(ConvertOptions(), {IDENTITY_ENV: "no email here"}) is None
    assert resolve_identity(ConvertOptions(), {}) is None
    opts = ConvertOptions(extra={"specialized.edgar_identity": "Opt opt@example.org"})
    assert resolve_identity(opts, {IDENTITY_ENV: "Env env@example.org"}) == "Opt opt@example.org"


def test_network_document_flow_sends_identity_and_lists_exhibits() -> None:
    fake = FakeSec(_routes())
    doc = EdgarConverter(transport=fake).convert(_url_ref(DOC_URL), _opts())
    assert [u for u, _ in fake.calls] == [INDEX_URL, DOC_URL]
    assert all(h["user-agent"] == IDENTITY for _, h in fake.calls)
    assert doc.metadata.extra["edgar.filed"] == "2026-04-24"
    assert doc.metadata.published is not None
    assert "Exhibits" in _headings(doc, 2)
    exhibits = next(b for b in doc.blocks if isinstance(b, Table) and b.provenance.path == "exhibits")
    assert "EX-10.1" in [spans_text(c.spans) for c in exhibits.cells]
    assert doc.children == []


def test_index_url_fetches_primary_document() -> None:
    fake = FakeSec(_routes())
    doc = EdgarConverter(transport=fake).convert(_url_ref(INDEX_URL), _opts())
    assert [u for u, _ in fake.calls] == [INDEX_URL, DOC_URL]
    assert any(h.startswith("Item 5.02") for h in _headings(doc, 2))


def test_exhibits_option_converts_children() -> None:
    fake = FakeSec(_routes())
    doc = EdgarConverter(transport=fake).convert(_url_ref(DOC_URL), _opts(**{"specialized.edgar_exhibits": True}))
    assert f"{FOLDER}/offerletter.htm" in [u for u, _ in fake.calls]
    assert len(doc.children) == 1
    assert "Dear Mr. Skaggs" in doc.children[0].plain_text()


def test_company_lookup_by_ticker() -> None:
    routes = _routes()
    routes["https://www.sec.gov/files/company_tickers.json"] = json.dumps(
        {"0": {"cik_str": 1376986, "ticker": "TVE", "title": "Tennessee Valley Authority"}}
    ).encode()
    routes["https://data.sec.gov/submissions/CIK0001376986.json"] = json.dumps(
        {
            "filings": {
                "recent": {
                    "form": ["10-Q", "8-K"],
                    "accessionNumber": ["0001376986-26-000029", "0001376986-26-000026"],
                    "primaryDocument": ["tve-20260331.htm", "tve-20260424.htm"],
                    "reportDate": ["2026-03-31", "2026-04-24"],
                }
            }
        }
    ).encode()
    fake = FakeSec(routes)
    url = "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=TVE&type=8-K"
    doc = EdgarConverter(transport=fake).convert(_url_ref(url), _opts())
    assert [u for u, _ in fake.calls][-2:] == [INDEX_URL, DOC_URL]
    assert doc.metadata.extra["edgar.form"] == "8-K"


def test_company_lookup_missing_form_is_clear() -> None:
    routes: dict[str, bytes | int] = {
        "https://data.sec.gov/submissions/CIK0001376986.json": b'{"filings": {"recent": {"form": []}}}'
    }
    url = "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=1376986&type=10-K"
    with pytest.raises(ConversionError, match="no 10-K"):
        EdgarConverter(transport=FakeSec(routes)).convert(_url_ref(url), _opts())


@pytest.mark.parametrize("status", [403, 429])
def test_blocked_or_rate_limited_is_not_retried(status: int) -> None:
    fake = FakeSec({INDEX_URL: status})
    with pytest.raises(ConversionError) as e:
        EdgarConverter(transport=fake).convert(_url_ref(DOC_URL), _opts())
    assert len(fake.calls) == 1
    assert "rate_limited" in str(e.value)
    assert not e.value.retryable_with_fallback


def test_rate_limiter_spaces_requests() -> None:
    now = [100.0]
    slept: list[float] = []

    def sleep(s: float) -> None:
        slept.append(s)
        now[0] += s

    limiter = RateLimiter(5.0, clock=lambda: now[0], sleep=sleep)
    for _ in range(3):
        limiter.wait()
    assert slept == pytest.approx([0.2, 0.2])


def test_client_checks_deadline_before_each_request() -> None:
    opts = ConvertOptions(max_seconds=0.0)
    fake = FakeSec({})
    client = EdgarClient(identity=IDENTITY, options=opts, transport=fake, limiter=RateLimiter(1000.0))
    with pytest.raises(ConversionError) as e:
        client.get(DOC_URL)
    assert e.value.code == "timeout"
    assert fake.calls == []


def test_full_text_search_json_renders_table() -> None:
    payload = {
        "hits": {
            "hits": [
                {
                    "_id": "0001376986-26-000026:tve-20260424.htm",
                    "_source": {
                        "display_names": ["Tennessee Valley Authority (CIK 0001376986)"],
                        "form": "8-K",
                        "file_date": "2026-04-24",
                        "period_ending": "2026-04-24",
                        "adsh": "0001376986-26-000026",
                        "ciks": ["0001376986"],
                    },
                }
            ]
        }
    }
    url = "https://efts.sec.gov/LATEST/search-index?q=%22interim%20president%22"
    ref = InputRef.from_bytes(json.dumps(payload).encode(), filename="search.json", source_url=url)
    detect(ref)
    doc = EdgarConverter().convert(ref, ConvertOptions())
    table = next(b for b in doc.blocks if isinstance(b, Table))
    texts = [spans_text(c.spans) for c in table.cells]
    assert "0001376986-26-000026" in texts and "8-K" in texts
    assert any(c.spans and c.spans[0].href == DOC_URL for c in table.cells)


def test_empty_search_warns() -> None:
    url = "https://efts.sec.gov/LATEST/search-index?q=nothing"
    ref = InputRef.from_bytes(b'{"hits": {"hits": []}}', filename="s.json", source_url=url)
    detect(ref)
    doc = EdgarConverter().convert(ref, ConvertOptions())
    assert WarningKind.EXTRACTION_EMPTY in [w.kind for w in doc.warnings]


def test_complete_submission_text_file_uses_first_document() -> None:
    html = (FIX / "tva-8k" / "input.htm").read_text(encoding="utf-8")
    sub = (
        "<SEC-DOCUMENT>0001376986-26-000026.txt\n<SEC-HEADER>ACCESSION NUMBER: 0001376986-26-000026\n</SEC-HEADER>\n"
        "<DOCUMENT>\n<TYPE>8-K\n<SEQUENCE>1\n<FILENAME>tve-20260424.htm\n<TEXT>\n" + html + "\n</TEXT>\n</DOCUMENT>\n"
    )
    url = "https://www.sec.gov/Archives/edgar/data/1376986/0001376986-26-000026.txt"
    ref = InputRef.from_bytes(sub.encode(), filename="sub.txt", source_url=url)
    detect(ref)
    doc = EdgarConverter().convert(ref, ConvertOptions())
    assert any(h.startswith("Item 5.02") for h in _headings(doc, 2))


def test_oversized_body_is_refused() -> None:
    ref = InputRef.from_bytes(b"<html>" + b" " * 64 + b"</html>", filename="a.htm", source_url=DOC_URL)
    detect(ref)
    conv = EdgarConverter()
    opts = ConvertOptions()
    from intomd.context import Limits

    opts.ctx.limits = Limits(max_bytes=10)
    with pytest.raises(ConversionError, match="exceeds"):
        conv.convert(ref, opts)


def test_wingdings_box_inside_inline_xbrl_tag_is_mapped() -> None:
    ref = InputRef.from_path(FIX / "tva-8k" / "input.htm")
    ref.url = DOC_URL
    detect(ref)
    text = " ".join(EdgarConverter().convert(ref, ConvertOptions()).plain_text().split())
    assert "Emerging growth company " + chr(0x2610) in text
    assert "Emerging growth company o" not in text


def test_index_keeps_filer_role_addresses_and_ixbrl_marker() -> None:
    ref = InputRef.from_path(FIX / "tva-8k-index" / "input.html")
    ref.url = INDEX_URL
    detect(ref)
    doc = EdgarConverter().convert(ref, ConvertOptions())
    cells = [spans_text(c.spans) for b in doc.blocks if isinstance(b, Table) for c in b.cells]
    assert "Filer" in cells and "Tennessee Valley Authority (CIK 1376986)" in cells
    assert "400 WEST SUMMIT HILL DRIVE, KNOXVILLE TN 37902" in cells
    assert "400 WEST SUMMIT HILL DRIVE, KNOXVILLE TN 37902, 865-632-2101" in cells
    assert "tve-20260424.htm (iXBRL)" in cells


def test_conversion_without_edgar_url() -> None:
    ref = InputRef.from_path(FIX / "synthetic-10k" / "input.htm")
    detect(ref)
    conv = EdgarConverter()
    assert conv.can_handle(ref) == pytest.approx(0.95)  # claimed by its inline XBRL namespace
    doc = conv.convert(ref, ConvertOptions())
    assert "Item 8. Financial Statements and Supplementary Data" in _headings(doc, 2)
    assert "TABLE OF CONTENTS" in doc.plain_text()


def test_company_page_body_without_network_falls_back() -> None:
    url = "https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=TVE&type=8-K"
    ref = InputRef.from_bytes(b"<html><body>EDGAR company list</body></html>", filename="b.html", source_url=url)
    detect(ref)
    with pytest.raises(ConversionError) as e:
        EdgarConverter().convert(ref, ConvertOptions())
    assert e.value.retryable_with_fallback
