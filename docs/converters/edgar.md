# SEC EDGAR

Package `intomd_converters.edgar`, converter `specialized.edgar`, family `specialized` (spec: docs/spec/part2.md
section 12, EdgarConverter; ROADMAP P1-T07). Implemented directly against the documented EDGAR endpoints;
`edgartools` is not used (it hard-depends on Unidecode, GPL-2.0+; see docs/decisions/P1-T07.md). No new
dependencies.

| Input | Example | What happens |
|---|---|---|
| Filing document URL | `https://www.sec.gov/Archives/edgar/data/1376986/000137698626000026/tve-20260424.htm` | the filing converted to Markdown |
| Inline XBRL viewer URL | `https://www.sec.gov/ix?doc=/Archives/edgar/data/.../tve-20260424.htm` | same as the document URL |
| Filing folder or index page | `.../000137698626000026/`, `.../0001376986-26-000026-index.html` | with network: the primary document plus an Exhibits table; offline (index page body): the filing facts, items list, and document tables |
| Complete submission text file | `.../data/1376986/0001376986-26-000026.txt` | the first document of the submission |
| Accession number | `0001376986-26-000026` | network only: resolved through the index under the accession's filer CIK |
| Company page | `https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=AAPL&type=10-K` | network only: ticker to CIK (`company_tickers.json`), latest filing of that form (`data.sec.gov/submissions`) |
| Ticker or CIK with a form | display `AAPL` with `extra.specialized.edgar_form=10-K` | as the company page (needs `--converter specialized.edgar`) |
| Full-text search | `https://efts.sec.gov/LATEST/search-index?q=...` | a table of matching filings (not converted) |

The converter claims inputs by URL (confidence 0.95), so a sec.gov filing goes to it rather than to the
generic web chain. An uploaded or saved inline XBRL filing (the `http://www.xbrl.org/2013/inlineXBRL`
namespace in the first 64 KiB of an HTML/XHTML/XML body) is claimed at the same confidence without a URL, ahead
of `data.xml` and the web chain. A plain HTML file without an EDGAR URL or inline XBRL is not claimed, but a
saved older (non-iXBRL) filing converts with `--converter specialized.edgar`. A company page (`browse-edgar`) body without network access is handed back
to the web chain.

## Network, identity, and rate limit

- Offline first. When the input already has a body (an upload, a file with `[input] url`, or a body the
  pipeline fetched) nothing is requested.
- Without a body and with `allow_network` off, Archives and search URLs raise `FetchRequired` so the
  pipeline fetches them; accession and company lookups fail with a message asking for network access or the
  Archives URL.
- With `allow_network` on, every request carries the declared identity as the User-Agent. The identity comes
  from `extra.specialized.edgar_identity`, else `INTOMD_EDGAR_IDENTITY`, and must contain a contact email
  (`"Name you@example.com"`). Without it the conversion fails immediately (`edgar_identity_missing`), before
  any request.
- Requests are spaced to 5 per second per process (the SEC limit is 10). HTTP 403 or 429 fails at once with
  a `rate_limited` message; it is never retried in a loop. Every request goes through
  `intomd.core.netguard.fetch` (SSRF guard, redirect re-validation, byte cap 25 MB) and checks the deadline.

## Output

1. H1 `<company> <form> <period>` from the inline XBRL cover facts (`dei:EntityRegistrantName`,
   `dei:DocumentType`, `dei:DocumentPeriodEndDate`), falling back to the index page.
2. A cover table: form, period, CIK, ticker, exchange, commission file number, filer status, fiscal year
   end, shares outstanding, public float, fiscal focus, amendment flag, filing date (when the index is known),
   accession.
3. `Cover page`: the cover text in document order (check boxes rendered as ballot boxes).
4. One H2 per `PART`, `Item` (`Item 1A. Risk Factors`, `Item 5.02 ...`), and `SIGNATURES`, with the heading
   text exactly as filed. Table-of-contents duplicates are dropped (the last bold occurrence of each item wins);
   10-Q items are keyed by part (`item/II-1`). A sentence that merely begins with "Item 7" stays text.
5. Sub-headings: real HTML headings become H3 or lower; with `edgar_infer_headings` (default true) a short
   all-bold line becomes H3 and a short all-italic line H4 (`heading_inferred_from_formatting`).
6. Tables through the web family's HTML table path, then cleaned: empty spacer rows and columns removed, `$`
   folded into the number on its right and `)`/`%` into the number on its left (`$(1,204)` stays one exact
   string), leading all-bold rows marked as header rows.
7. `Exhibits`: the EX- documents from the filing index (network flows). With `edgar_exhibits=true` each
   convertible exhibit (at most 10) is converted as a child Document through the registry.

Page numbers and repeated "Table of Contents" links at page breaks are removed
(`removed_running_header_footer`). The hidden `ix:header` is dropped.

Provenance: `path` = `cover`, `part/<n>`, `item/<id>`, `signatures`, `exhibits`, or `index/...`;
`source_id` = the accession number on every block. Metadata `extra`: `edgar.cik`, `edgar.company`,
`edgar.form`, `edgar.filed`, `edgar.period`, `edgar.accession`, `edgar.url`; `published` = filing date.

## Options (`ConvertOptions.extra`)

| Key | Default | Meaning |
|---|---|---|
| `specialized.edgar_identity` | `INTOMD_EDGAR_IDENTITY` | declared SEC identity (`Name email`) |
| `specialized.edgar_form` | `10-K` | form for ticker/CIK lookups |
| `specialized.edgar_year` | none | restrict ticker/CIK lookups to a report year |
| `specialized.edgar_exhibits` | `false` | convert exhibits as child documents (network) |
| `specialized.edgar_infer_headings` | `true` | infer sub-headings from bold and italic lines |

## Warnings

`unsupported_feature` (a 10-K/10-Q/8-K/20-F/S-1/DEF 14A with no recognizable item headings),
`attachment_unconverted` (Item 8 incorporates Exhibit 13 by reference), `removed_running_header_footer`,
`heading_inferred_from_formatting`, `removed_hidden_elements`, `extraction_empty`, `attachment_failed`,
`attachment_skipped` (more than 10 exhibits).

## Fixtures

| Fixture | Input | Threshold |
|---|---|---|
| `edgar/tva-8k` | recorded Form 8-K (TVA, a U.S. federal corporation; public domain), items 5.02 and 9.01 | 0.95 |
| `edgar/tva-8k-index` | recorded SEC filing index page | 0.95 |
| `edgar/synthetic-10k` | self-generated Workiva-style 10-K: TOC, parts, items, sub-headings, financial table | 0.95 |

## Known limitations

- XBRL financial statements (part2 12c step 4: statement tables, facts table, `compare_context`) are not
  built; the statements appear as the HTML tables of Item 8. This belongs with the XbrlConverter.
- Accession-only lookups assume the accession's filer prefix is the company CIK (true for self-filed
  filings); filings by an agent need the Archives URL.
- `Item 8` pointing to `EX-13` is detected and warned about, but the exhibit is followed only with
  `edgar_exhibits=true`.
- Table captions from the preceding bold line are emitted as an H3 sub-heading, not as `Table.caption`.
- The PDF-rendering classifier (`UNITED STATES SECURITIES AND EXCHANGE COMMISSION` on page 1) is not
  implemented.
- The CLI has no `--form`/`--year` flags yet; use the `browse-edgar` URL
  (`...?action=getcompany&CIK=<ticker or CIK>&type=10-K`); a bare ticker works only through the library with
  `converter="specialized.edgar"` and `extra.specialized.edgar_form`.
