"""SEC EDGAR family (docs/spec/part2.md section 12, EdgarConverter): filings, filing indexes, company and
accession lookups, and full-text search. Implemented directly against the documented EDGAR endpoints;
`edgartools` is not used because it hard-depends on Unidecode (GPL-2.0+), see docs/decisions/P1-T07.md.

The converter claims inputs by URL and pattern (sec.gov Archives, browse-edgar, efts.sec.gov, accession
numbers) and, for uploads without a URL, by the inline XBRL namespace, so it owns no mime chain: the
registry's specialist rule puts it ahead of the text/html and XML chains.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from intomd.registry import Converter, Unavailable

CHAINS: dict[str, list[str]] = {}


def converters() -> list[Converter | Unavailable]:
    from intomd_converters.edgar.converter import EdgarConverter

    return [EdgarConverter()]
