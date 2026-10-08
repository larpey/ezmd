"""EDGAR input recognition (docs/spec/part2.md 12a): Archives filing and index URLs, the inline XBRL viewer,
`browse-edgar` company pages, full-text search, and bare accession numbers.

Pure string work, no I/O, so `can_handle` stays cheap.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal
from urllib.parse import parse_qs, unquote, urlsplit

TargetKind = Literal["document", "index", "accession", "company", "search"]

ARCHIVES_BASE = "https://www.sec.gov/Archives/edgar/data"
_SEC_HOSTS = frozenset({"sec.gov", "www.sec.gov"})
_EFTS_HOST = "efts.sec.gov"
ACCESSION_RE = re.compile(r"^(\d{10})-(\d{2})-(\d{6})$")
_ACC18 = re.compile(r"^\d{18}$")
_ARCHIVES_PATH = re.compile(r"^/Archives/edgar/data/(\d{1,10})/(\d{18}|\d{10}-\d{2}-\d{6}(?:\.txt)?)(?:/(.*))?$", re.I)
_INDEX_FILE = re.compile(r"^(\d{10}-\d{2}-\d{6})-index(?:-headers)?\.html?$", re.I)
_CIK_RE = re.compile(r"^\d{1,10}$")
_TICKER_RE = re.compile(r"^[A-Za-z][A-Za-z0-9.\-]{0,9}$")
_FORM_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 /\-]{0,19}$")


@dataclass(frozen=True, slots=True)
class EdgarTarget:
    """What an input names. `cik` is unpadded digits; `accession` is the dashed form `0001234567-24-000123`."""

    kind: TargetKind
    url: str | None = None
    cik: str | None = None
    accession: str | None = None
    filename: str | None = None
    company: str | None = None
    """Ticker or CIK for `company` targets."""
    form: str | None = None
    query: str | None = None

    @property
    def folder_url(self) -> str | None:
        if self.cik is None or self.accession is None:
            return None
        return f"{ARCHIVES_BASE}/{self.cik}/{self.accession.replace('-', '')}"

    @property
    def index_url(self) -> str | None:
        folder = self.folder_url
        return f"{folder}/{self.accession}-index.html" if folder and self.accession else None

    @property
    def document_url(self) -> str | None:
        folder = self.folder_url
        return f"{folder}/{self.filename}" if folder and self.filename else None


def dashed(acc: str) -> str:
    """`000137698626000026` -> `0001376986-26-000026`; dashed input is returned unchanged."""
    if _ACC18.match(acc):
        return f"{acc[:10]}-{acc[10:12]}-{acc[12:]}"
    return acc


def is_accession(text: str) -> bool:
    return ACCESSION_RE.match(text.strip()) is not None


def _host(url: str) -> tuple[str, str, str]:
    parts = urlsplit(url)
    return (parts.hostname or "").lower(), parts.path, parts.query


def parse_target(text: str | None) -> EdgarTarget | None:
    """Recognize an EDGAR input, or None. Accepts http(s) URLs on sec.gov / efts.sec.gov and bare accessions."""
    if not text:
        return None
    text = text.strip()
    if is_accession(text):
        return EdgarTarget(kind="accession", accession=text, cik=str(int(text[:10])))
    if not text.lower().startswith(("http://", "https://")):
        return None
    host, path, query = _host(text)
    if host == _EFTS_HOST and path.lower().startswith("/latest/search-index"):
        q = parse_qs(query).get("q", [""])[0]
        return EdgarTarget(kind="search", url=text, query=q or None)
    if host not in _SEC_HOSTS:
        return None
    qs = parse_qs(query)
    if path.lower() in ("/ix", "/cgi-bin/viewer") and "doc" in qs:
        inner = unquote(qs["doc"][0])
        if inner.startswith("/"):
            return _archives(f"https://www.sec.gov{inner}", urlsplit(inner).path)
        return None
    if path.lower() == "/cgi-bin/browse-edgar":
        return _browse(text, qs)
    return _archives(text, path)


def _archives(url: str, path: str) -> EdgarTarget | None:
    m = _ARCHIVES_PATH.match(path)
    if m is None:
        return None
    cik = str(int(m.group(1)))
    acc_part, rest = m.group(2), (m.group(3) or "").strip("/")
    if acc_part.lower().endswith(".txt"):
        return EdgarTarget(kind="document", url=url, cik=cik, accession=acc_part[:-4], filename=acc_part)
    accession = dashed(acc_part)
    if not rest or rest.lower() in ("index.json", "index.html", "index.htm"):
        return EdgarTarget(kind="index", url=url, cik=cik, accession=accession)
    if "/" in rest:
        return None
    if _INDEX_FILE.match(rest):
        return EdgarTarget(kind="index", url=url, cik=cik, accession=accession)
    return EdgarTarget(kind="document", url=url, cik=cik, accession=accession, filename=rest)


def _browse(url: str, qs: dict[str, list[str]]) -> EdgarTarget | None:
    company = (qs.get("CIK") or qs.get("cik") or [""])[0].strip()
    form = (qs.get("type") or [""])[0].strip() or None
    if not company or not (_CIK_RE.match(company) or _TICKER_RE.match(company)):
        return None
    if form is not None and not _FORM_RE.match(form):
        form = None
    return EdgarTarget(kind="company", url=url, company=company, form=form)


def company_target(company: str, form: str | None) -> EdgarTarget | None:
    """A ticker or CIK plus a form type (`--form 10-K`, options `specialized.edgar_form`)."""
    company = company.strip()
    if not (_CIK_RE.match(company) or _TICKER_RE.match(company)):
        return None
    if form is not None and not _FORM_RE.match(form):
        return None
    return EdgarTarget(kind="company", company=company, form=form)
