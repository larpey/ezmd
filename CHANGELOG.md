# Changelog

All notable changes are generated from Conventional Commits. This project uses semantic versioning.

## [Unreleased]

### Added
- Benchmark harness (`tools/bench`): an `arxiv` corpus of 109 whole CC BY papers that measures what a downstream
  model gets rather than a page's edit distance: text recall against the PDF's own text layer, silent loss (over
  5% of the words gone with no warning raised), outline recall against the PDF's bookmarks, o200k tokens per page
  and answer accuracy, where a local model (`tools/bench/qa.py`, LM Studio) writes grounded questions from the
  text layer, answers them from each tool's output and grades them. `ezmd-main`, `ezmd-main-compact` and
  `ezmd-main-rag` rows run the checkout's code under three profiles; the ezmd adapter records each document's
  warnings so declared loss can be told from silent loss. Two witnesses keep the numbers honest: each paper's LaTeX
  source (`fetch --only arxiv-source`, `tools/bench/scoring/latex.py`), which no converter's extractor produced,
  and an `arxiv-damaged` corpus (`tools/bench/damage.py`: scanned, partly scanned and truncated copies of ten
  papers) that checks whether a tool says what it lost and which pages. The damaged set found ezmd's first
  silent loss, a repaired truncated file (#23). First results in `bench/results/2026-10-24/` and
  `docs/benchmarks.md`. `run --corpus arxiv-damaged --split heldout` damages the 79 held-out papers the same
  way; the #23 fix is confirmed there (`bench/results/2026-10-24-heldout/`: 0 of 237 silent, 0.1.0 1 of 237).
  The QA questions are written per 8,000-token segment of the text layer (two each) and record where their
  evidence lies, and the answering model reads each tool's whole output in a 131k context, so a converter that
  cuts a paper's tail is measured; the first version wrote five questions from the first 24,000 tokens, which
  145 of 148 times fell inside what the `compact` profile kept. The scorer adds `arxiv-qa-second-half`
  (accuracy on questions whose evidence is in the paper's second half) and pooled first-half/second-half
  accuracy as secondary statistics. Result (`bench/results/2026-10-24-whole/`): the compact profile's cut costs
  0.22 of answer accuracy over the whole paper (0.564 against 0.780 for the full profile) and 0.26 on second-half
  questions; the full profile ties MarkItDown, Docling and MinerU. Harness fixes on the way: a server error ends
  the pass cleanly and the caches resume it; runs of one non-ASCII character are squeezed before an output is
  sent (a 764-character run broke the server's tokenizer); a correctly escaped `\\` in a reply is kept; the
  score summary names each tool's own primary metric.
- Benchmark harness: a `govdocs1-held` corpus, twenty of the thousand Govdocs1 archives drawn once by seed minus
  every file that is in a thread (about 19,500 files), for confirming a batch of fixes on files that were never
  looked at while the threads' bugs were fixed. `fetch --only govdocs1-held` extracts them from a local copy of
  the archives or downloads them. First results in `bench/results/2026-10-27-confirm/`.
- Benchmark harness: a `govdocs1` corpus, the ten official Govdocs1 threads (about 9,900 everyday files from
  .gov servers across some twenty formats), scored on outcome because no ground truth exists: an output, a
  declared refusal, or a bug (an undeclared exception, a timeout, a worker crash). `score` writes the clean rate
  and `clusters.md`, the bugs grouped by exception class and the frame that raised (a new `where` field in
  results.jsonl, filled by the worker from the traceback) with sample files. `run --workers N` converts N shards
  at once. The first pass over the pilot is where the everyday-documents coverage work (#28 to #33) starts:
  `bench/results/2026-10-26-pilot/`, clean rate 0.9941 over 9,875 files, 58 bugs from one defect and seven
  more in the declared refusals. `score` also runs a structural smell scorer over every output (empty, control
  characters, lone bullets, bullet headings, truncated-then-repeated headings, replacement characters,
  mojibake, repeated lines, character runs, mostly-empty tables, shrunk text, injection flags) and writes
  `smells.md`. Two more corpora cover what Govdocs1 cannot: `ccgov`, modern files of every document type from
  Common Crawl's .gov, .mil and .edu hosts (`tools/bench/cc.py`), and `media`, images, audio, video and EPUB
  from Wikimedia Commons, Project Gutenberg, LibriVox and NASA (`tools/bench/media.py`). First results over the
  whole `media` corpus in `bench/results/2026-10-27-media-c/` (20,348 files): every raster image, audio and video
  file a declared refusal, 998 of 998 EPUBs converted, and SVG falling through to the plain-text reader (#55).
- `ezmd convert --image-dir DIR` and `ezmd batch --image-dir DIR` extract embedded images, and the library's
  `Options.image_dir` does the same for code. Pictures are written to `DIR/images/<name>` (in `batch`, under one
  folder per input, `DIR/<its path>/images/`, so two documents' `image1.png` cannot overwrite each other) and
  the Markdown links are made relative to the written `.md`, or to the working directory when the Markdown
  goes to stdout, so they resolve where the file lands. `Result.save()` rebases the links the same way and
  `Result.relocate_images(base)` does it without writing. The REST API and the MCP server refuse the field,
  as they do `converter` and `experimental`: it names a path on the server's disk (#32).

### Changed
- Container images apply Debian's security updates at build time (`apt-get upgrade` in the runtime stage):
  the base image is pinned by digest and rebuilt upstream on its own schedule, so a fixed CVE in a system
  library (openssl, this week) no longer ships in every image and fails the scan until the next digest bump.
- LibreOffice conversions initialise a user profile once per process and copy it for every later file,
  instead of initialising a throwaway profile from scratch each time. Each file still gets its own writable,
  disposable copy with macros, active content and link updates disabled. A legacy `.doc`, `.xls` or `.ppt`
  cost about 13 seconds on the 2026-10-26 Govdocs1 pilot (86% of the run's time); after the first file it is
  the conversion itself plus the copy.
- `rag` chunk markers carry the chunk number only (`<!-- chunk id="c0001" section="1" page="1" -->`); the
  content-hash prefix and the `tokens` attribute moved out of the body and stay in the sidecar's `chunks`
  (D-0073). On 30 arXiv papers the old markers were 9.5% of the rag output. A consumer that read the hash from
  the marker reads it from the frontmatter `content_hash` or the sidecar.

### Fixed
- PPTX pictures reach the user. The converter returned every picture as a link to its path inside the package
  (`ppt/media/image3.png`) and never wrote the bytes, so a deck's images were all broken links; with
  `image_dir` set it now writes them like the DOCX converter does. DOCX joins the convention the EPUB, notebook
  and email converters already follow (`<image_dir>/images/<name>`, link `images/<name>`) instead of writing
  into `image_dir` itself with an absolute path in the link (#31).
- The sidecar's byte-offset table is linear in the body. `locate_units` re-encoded the whole body prefix for
  every unit, so a 32 MB log with a unit per line spent minutes there after a conversion of seconds; the two
  timeouts of the held-out Govdocs1 run (`bench/results/2026-10-27-confirm/`, a 32 MB log and a 25 MB
  PostScript file in a gzip) now convert in under 50 seconds (#56).
- The injection scanner no longer marks one ordinary document in thirty as `high`. The 2026-10-26 corpus
  sweep (D-0075) found 3.2% of Govdocs1 and 3.5% of modern government files at `high` with no injection in
  them: "act as a buffer" in prose, `rm -rf` in build logs, KML's `<Document>` root, "run the command" in
  software documentation, "forward the data to" in contracts, a sentence starting "System:", and long tables
  or manuals accumulating low-severity heuristics. The model-directed patterns now need the model as addressee
  (`you must act as`, `act as an unrestricted assistant`, `call your tools`, `please run rm -rf`), a quoted
  shell command or fetch on its own is a low `shell_mention`, the delimiter family matches ezmd's own fence and
  the chat-template tags only, the bare `System:` line is low while `[system]:` stays high, and the
  accumulation heuristics together reach `medium` at most. Attacks (override, role hijack with the model
  named, exfiltration of the conversation, fence and tag spoofing, hidden text) still score `high`.
- Running headers that sit below the margin zone are removed. The PDF path only looked in the top and bottom
  8% of the page, so a court opinion's case name 17% below the top edge stayed in the body 73 times in the
  Govdocs1 pilot (2026-10-26). A line that repeats at the same position on most pages within the top or
  bottom quarter is furniture now; the same text once in the body (a quotation) stays. A further copy of a
  known running text inside a margin zone, however rare (#29's footer sentence at the top of one page), is
  removed too.
- XML dialects convert as XML and XHTML converts as a web page. Any `+xml` type without a converter of its
  own (RDF, GPX, KML, Atom, RSS, MathML, ISO 19115, SMIL, ...), property lists and DTDs now take the XML
  converter's chain instead of "no converter"; an XML document with an `<html` root, an XHTML doctype, an HTML
  extension or Magika's `html` label is `application/xhtml+xml` and goes to the web converters instead of
  failing in the XML parser. 37 RDF files and 3 XHTML pages in the Govdocs1 pilot and thousands of feed and
  KML files in the modern corpus (2026-10-26).
- Legacy and modern Office containers are typed by their strongest evidence. For an OLE2 file, libmagic's
  stream-name verdict (`application/msword`, `vnd.ms-excel`, ...) now beats a Magika guess, and a generic
  `application/cdfv2` or `vnd.ms-office` verdict resolves from the extension (`.doc`, `.ppt`, `.msg`, `.vsd`)
  or Magika's label instead of leaving the file with "no converter" or sending LibreOffice the wrong target.
  An Excel binary workbook (`.xlsb`, a package with `xl/workbook.bin`) is recognised as such and goes to
  LibreOffice instead of failing in openpyxl. 29 refused Office files, 7 wrong targets and 25 `.xlsb`
  failures in the 2026-10-26 corpus runs.
- Readable text is never refused as "no converter" or "binary". Three rules: a type verdict of
  `application/octet-stream` on bytes that read as text (a Magika label with no MIME type, such as a Protein
  Data Bank file) becomes `text/plain`; when no converter claims a type whose bytes read as text (SQL scripts,
  property lists, DTDs, Mathematica notebooks), the registry reads the file as plain text and says so with the
  new `unknown_type_read_as_text` warning; and every text-based data chain (CSV, JSON, YAML, TOML, XML) ends in
  plain text, so a YAML or XML look-alike that does not parse comes through as text with `engine_fallback`
  instead of failing. Usenet articles (`message/news`) go to the email converter. About 600 files of the
  2026-10-26 corpus runs.
- A scanned page whose only text is its printer's stamp or footer is reported as a page without text. The
  running-header pass removed the stamp and the page counted as text-bearing because the raw text layer was
  not empty, so two Govdocs1 pilot files (2026-10-26) came out with no body and no `pages_without_text`
  warning. The scan classifier now counts a page's text after the running lines are taken out.
- A huge single paragraph no longer stalls the renderer: `escape_inline` runs markdown-it's inline parser
  only on spans up to 64,000 characters and the regex check beyond that. A 4 MB ASCII grid file spent 150 of
  its 160 seconds in that parser in the 2026-10-26 Govdocs1 pilot and timed out at the 120-second limit.
- The OOXML package guard no longer rejects real documents as zip bombs: the per-member compression limit is
  1000:1 instead of 100:1. Deflate tops out near 1032:1, so a run of one byte is still refused, while
  generated slide and sheet XML (100:1 to 300:1) and EMF vector images (up to 730:1) pass; the total
  uncompressed cap and the declared-size check still bound every package. Six Govdocs1 files converted
  through LibreOffice and six native `.docx`/`.pptx` files in the modern corpus were refused with
  `package rejected ... compression ratio` on 2026-10-26.
- A heading level above 6 no longer fails the conversion: Word's Heading 7 to 9 (and an outline level that
  deep) and a tagged PDF's `H7` become level 6, as Markdown has six levels. Before, the IR refused the level
  and the document did not convert at all: 58 of 9,875 Govdocs1 files and 21 of 3,295 modern `.docx` files in
  the corpus runs of 2026-10-26.
- Detection: libmagic's `application/x-mimearchive` (a message whose first line is a MIME header) is an email,
  so such an `.eml` reaches the email converter instead of "no converter"; the libmagic answer outranks the
  extension, which is why newer libmagic builds on CI made `test_html_only_body_and_inline_cid_image` fail.
- Tables without a header row render an empty header (`|  |  |`) instead of `| col_1 | col_2 |`, with no
  `<!-- ezmd: header synthesized -->` comment and no `Columns: col_1, ...` line; the sidecar still counts
  synthesized headers, and the key-value and sampled representations keep `col_N` as keys. On 30 arXiv papers
  the generated names and markers were 17,000 of the words ezmd emitted and Docling did not.
- PDF (text-layer engine): paragraphs in double-spaced manuscripts are no longer one line each. The assembler
  measures the page's own line spacing and continues a paragraph within it, and treats a first-line indent
  after a short line as the start of a new paragraph (a hanging indent after a full line still continues). On
  a double-spaced arXiv paper this turns 1,404 one-line "paragraphs" into 1,031 real ones; the leftovers are
  display equations.
- PDF: a damaged file that qpdf repairs on open (truncated, or a broken cross-reference table) now carries a
  `file_repaired` warning with qpdf's messages, so the content lost past the damage is declared rather than
  silent (#23, found by the damaged-paper benchmark: 9% of a truncated paper's words gone with no sign). The
  warning now says where, as far as the file's object graph allows (`ezmd_converters/pdf/repair.py`): the pages
  whose content stream is gone or cut (`detail.pages_content_damaged`, also the warning's `page`), the pages
  that draw an image or form that is gone (`pages_figures_missing`), and a count of fonts that lost part of
  their definition (`fonts_damaged`), with the message saying that text set in them may be incomplete on pages
  that cannot be pinpointed. Font damage is counted rather than placed because it does not map to pages: on 51
  repaired arXiv papers the pages with a damaged font and the pages that lost words barely overlap.
- PDF (text-layer engine): rotated margin text such as an arXiv stamp is no longer taken as the title or a
  heading, and a notice set in heading-sized type is a paragraph, not three headings.
- PDF (text-layer engine): the lettering of a figure (axis ticks, legend entries, panel labels) no longer comes
  out as tables and stray paragraphs. A figure included as a form XObject keeps its text objects together with
  its paths, so the engine reads each such form (three or more paths or images, short lines) as one figure and
  emits its lettering as a single paragraph where the figure sits, tagged `attrs.pdf_figure_text` with the line
  count; the lines take no part in table detection, heading planning or the title. On a plot-heavy arXiv paper
  this turns 103 tables into 18, the real ones. Figures drawn straight onto the page (TikZ) are unchanged.
  Image boxes of images nested in forms are now placed on the page correctly (they were in the form's own
  coordinates).
- PDF: outline bookmarks match numbered headings ("3.1 Encoder" for the bookmark "Encoder"), each bookmark is
  used once, and figure labels that repeat a section title stay labels. Without an outline, bold numbered
  lines such as "3.1 Encoder and Decoder Stacks" become headings at their numbering depth.
- PDF: superscripts and subscripts are kept as such, including exponents set as separate text objects, so
  `1.0 · 10^20` no longer reads `1020`. Without extended Markdown, digit scripts render as `10²⁰` (D-0072).
- PDF tables: a header cell centred over a two-line header joins the header row, header cells that span
  two columns no longer merge the columns below them, and a typeset formula is no longer emitted as a table.
- PDF: math letters set outside Unicode's basic plane (TeX's math italic 𝑥, 𝐷) were decoded as two
  replacement characters each and every variable in a formula was lost; they now read as plain `x`, `D`.
- PDF: bold section headings only slightly larger than the body (ACL-style 12 pt over 11 pt) are headings,
  and the title page's author and affiliation lines above "Abstract" are not.
- PDF titles: junk metadata titles (a lone private-use glyph from Word, "Microsoft Word - x.docx", file
  names) are ignored, and without a metadata title the title is the first page's largest text, or its
  centred capitals at body size (AMS), instead of the first heading ("1. Introduction").
- PDF: accents TeX draws as separate glyphs (`´` over `A`) compose into the letter (`Á`), and math italic
  folds to plain letters while bold, script and double-struck math letters keep their style.
- PDF headings: bookmarks match headings numbered in any style (`2.1.`, IEEE `II.` and `A.`, appendix `B.1`),
  REVTeX small-capital headings, headings that wrap onto a second line, and run-in headings
  ("2.1. Metric graph theory. For a graph G, ..."), which are split from their paragraph. A printed table
  of contents, with or without page numbers, no longer takes the bookmarks of the headings it lists.
- PDF: a glyph whose font maps it to its text twice (`ψψ` for one `ψ`) is one character; glyphs with no
  text mapping stay visible as U+FFFD and raise the new `unmapped_glyphs` warning naming their pages.
- PDF: display equations (a fraction's rows, an equation number at the right, dense math symbols) are no
  longer emitted as tables.
- PDF titles: a title set at body size under "Draft version" notes (AASTeX) is found in the top of the first
  page, and a title split across objects ("Eagle" and ": Ethical Dataset ...") joins without a gap.
  Contents entries with dot leaders and lines over 150 characters are never headings.

### Documentation
- The README is rewritten for a first-time reader: what you get (a real paper's header and outline), how to
  use it from each surface, what it converts, where it stands, and why. It says what is true today: ezmd
  reports what it couldn't convert, and no comparison with other tools appears until the benchmark is
  published.
- Benchmarks (`docs/benchmarks.md`): ezmd against MinerU, Marker, Docling, pymupdf4llm, Unstructured, MarkItDown and
  Trafilatura on olmOCR-Bench, OmniDocBench and an article-extraction benchmark. The harness (`tools/bench`), the
  pins and the raw results are in the repository, so the numbers can be rerun.

## [0.1.1] - 2026-10-23

A security release. No code changes; it rebuilds the packages and Docker images on fixed dependencies.

### Security
- Pillow 12.3.0 -> 13.0.0: 35 advisories, four of them critical in the image scan. Docling moves with it
  (docling-slim 2.135.0 -> 2.142.1), because Docling 2.142 is the first that accepts Pillow 13.
- certifi 2026.7.22 -> 2026.10.23: GHSA-6q48-6c7w-9gw2 (critical), emSign root certificates with compromised keys.
- DOMPurify 3.4.16 -> 3.4.17 in the web app: GHSA-cg2g-xh64-v4q7 (critical), GHSA-mrv2-3pqr-j5jr (high) and a
  low-severity advisory.

pip installs of 0.1.0 already resolve the fixed Pillow and certifi, since neither is pinned; the 0.1.0 Docker
images ship the old versions, so self-hosted deployments should move to 0.1.1.

### Documentation
- The README opens with a banner.

## [0.1.0] - 2026-10-15

The first stable release. The code is the same as 0.1.0-rc5; see the release candidates below for everything in
0.1.0.

### Packaging
- `@ezmd/sdk` 0.1.0 is published to npm, and `ezmd-mcp` is listed in the MCP registry.

### Documentation
- The README and docs no longer describe release candidates.

## [0.1.0-rc5] - 2026-10-14

Fixes from the pre-0.1.0 test pass on rc4: install tests, a self-hosted stack test, a red team and a competitive
benchmark (D-0044 to D-0071). The npm SDK stays at 0.1.0-rc.3 (unchanged).

### Security
- Anonymous jobs are never deduplicated across client IPs; before, a second caller submitting the same file or
  URL got the first caller's job id and filename, and could delete the job (D-0061).
- LibreOffice no longer fetches linked content (images, OLE/DDE links, fields, recalculation), and servers can
  require it to run under bubblewrap (`EZMD_REQUIRE_SANDBOX`, on in the worker; `sandbox_unavailable` 422 when it
  cannot). The worker image ships bubblewrap; an opt-in seccomp profile lets it run (D-0056, D-0064, D-0066).
- Admission is atomic: parallel requests can no longer exceed a caller's concurrency limit; anonymous traffic
  gets a share of the global cap so keyed callers keep headroom; one upload is read per caller at a time
  (D-0062).
- IPv6 clients are counted per /64 for rate limits, quotas and Turnstile binding (D-0063).
- Job, result, attachment and convert responses send `Cache-Control: no-store, private` and `Vary: X-API-Key`.
- Caddy's access log redacts job ids and token/key query values.
- The prompt-injection scan covers DOCX hidden text and spoofed `<!-- ezmd: -->` markers; marker comments cannot
  be closed early; links are emitted only for http(s), relative and fragment targets (D-0059).
- Archives charge every decompressed byte and bound zip directories before parsing (D-0057); executables in
  Magika's executable group are refused, Magika's archive labels need the archive's signature, and Magika uses
  `EZMD_MAGIKA_THREADS` threads (default 1) (D-0058); overlong hostnames are refused as `url_blocked`.
- The API refuses to start with a Turnstile setup that cannot work (no JWT secret, no Turnstile secret).

### Fixed
- PDF text layer: lines are grouped by baseline with the effective font size, so real PDFs no longer split into
  one line per glyph (51.7% to 0.5% broken words on a 101-page benchmark sample; olmOCR-Bench 0.277 to 0.335; see `bench/results/rc5`)
  (D-0050).
- Turnstile verifies through an internal Caddy relay instead of failing (the API has no egress); no verdict is
  `503 turnstile_unavailable` (D-0044).
- `/readyz` stays 200 while workers are idle and recovers after a Redis restart (D-0045).
- Anonymous uploads up to the tier cap no longer return 500; larger ones get 413. Unsupported and executable
  inputs get 415 before a job exists (D-0048).
- Plain text and Markdown truncate at 50 MB with a `size_cap` warning, and long wrapped runs convert in linear
  time; a 150 MB text upload no longer kills the worker (D-0071).
- The reaper requeues jobs Redis lost and fails jobs whose worker died within about a minute (D-0046).
- External tools and the conversion child use the container's pids limit instead of `RLIMIT_NPROC` 64, which
  broke Magika, LibreOffice, bubblewrap and pandoc (D-0047).
- Docling is skipped up front when its models are missing, and `ezmd doctor` checks them (D-0052).
- Wikipedia titles, footnote references and infobox cells (D-0053, D-0070).
- Missing extras exit 2 with `extra_required`; unsupported types carry `unsupported_media_type` (D-0054); `batch`
  stops at the first failure; `-q` silences model loading bars; non-http URLs are refused as a scheme; `-f zip` explains what to use instead (D-0055).
- `ezmd doctor` no longer reports ffmpeg as missing while the `media` extra is unreleased, and `--quiet` prints
  only problems.
- Trailing-dot hosts (`https://example.com./`) are fetched.
- Wrong HTTP methods get 405; `Retry-After` is exact; rejected creations refund their rate-limit hits (D-0049).
- The API reports its real version; the plain-HTTP port binds to loopback by default; `upgrade.sh` prunes only
  ezmd images; status probes work under Git Bash.
- The first `docker compose up` on a new install no longer fails intermittently with `mkdir .../cache: file
  exists`: the workers start after the API, so only one container populates the new `state` volume.
- `@ezmd/sdk` resolves its types under node10 module resolution and lists the new error codes.

### Packaging
- `defusedxml` is capped below 0.8 and `openpyxl` below 3.2 so `pip install --pre` does not pull pre-releases.

### Documentation
- Linux `ezmd[docs]` documents the CPU-only torch install (about 6 GB of CUDA torch and NVIDIA wheels
  otherwise, D-0051); install docs no longer pin a release candidate; the self-hosting guide covers the
  Turnstile relay, 413/415 and dedup rules, readiness, key restrictions, LibreOffice sandboxing and Git Bash.
- The build specification, decision log, status and roadmap trackers and agent instructions (now
  `AGENTS.md`) moved to `docs/internal/` and are no longer published on the docs site, which gets a short
  public roadmap instead. `ezmd` and `ezmd-converters` have real PyPI descriptions. Security reports go
  through GitHub private vulnerability reporting; the placeholder email addresses are gone.

## [0.1.0-rc4] - 2026-10-13

Release candidate for the pre-0.1.0 test pass. The npm SDK stays at 0.1.0-rc.3 (unchanged).

### Added
- `ezmd --version` (and `-V`) prints the same line as `ezmd version`.

### Security
- API-key `allowed_sources` / `disabled_sources` now hold across redirects and converter-requested
  fetches; before, an open redirect on an allowed site could reach any public host (D-0043).
- A Turnstile challenge JWT covers at most 5 URL jobs, counted per nonce, instead of any number until it
  expired (docs/spec/part4.md 4.11.2; D-0043).

### Fixed
- The fetch worker finds `keys.json` keys: a file key with `residential_allowed` is no longer failed
  when a redirect lands on a residential-only host.

## [0.1.0-rc3] - 2026-10-09

Fixes from the pre-release audit (D-0039 to D-0042).

### Security
- Client-IP spoofing behind proxies is fixed: uvicorn no longer rewrites the peer from `X-Forwarded-For`;
  the API trusts only Caddy's `X-Real-IP` from the internal network (`EZMD_TRUST_PROXY_HEADER`,
  `EZMD_TRUSTED_PROXIES`), so a client can no longer pick the address that rate limits, quotas, Turnstile and
  API-key IP pinning use.
- Brotli-encoded responses are decompressed with a cap, like gzip and deflate (decompression bomb).
- MCP tool calls may set only whitelisted conversion options and may lower, never raise, the operator's
  limits (new `ezmd-mcp --max-*` flags).
- Pillow's pixel cap is set to 50 megapixels.

### Packaging
- `httpx` is capped below 1.0 and `httpcore` is declared, so `pip install --pre ezmd` no longer pulls an
  httpx pre-release that breaks URL conversion; `lxml` is capped below 7 for the same reason.
- LICENSE and NOTICE are included in every wheel and sdist.
- The `mcp` and `all` extras pin `ezmd-mcp` to the exact matching version.
- The license gate covers every extra except `nonfree`; NVIDIA's CUDA runtime wheels, pulled by torch on Linux
  through the `docs` extra, are a named, reviewed exception.

### Tests
- Golden checks add hard structural invariants (math, blockquotes, list nesting, table spans, links, exact
  numbers, key frontmatter fields) and per-fixture `must_contain`/`must_not_contain`; sidecar goldens are
  compared. CI gains an `extras` job that runs the 7z and data converters.

### Fixed
- `.mbox` detection no longer depends on the host's `mime.types` (a spurious `misnamed_file` warning on
  Ubuntu and macOS); SQLite's `dbstat` size column can be turned off with `data.sqlite_sizes = false`.
- `ezmd doctor` lists the published extras (`7z`, `data`, `docs`, `mcp`, `nonfree`) from the package metadata,
  detects them by their real requirements, and shows spec extras that are not published yet as coming in a
  later release instead of printing a pip command that fails.
- `ezmd serve` without the API no longer suggests `pip install ezmd-api` (not on PyPI); it points at Docker
  Compose self-hosting.
- `--engine pdf=docling` resolves to `documents.docling_pdf`; naming a converter whose extra is missing (with
  `--engine` or `--converter`) says which extra to install instead of `Unknown converter`.
- The Parquet "needs pyarrow" error no longer repeats its install hint; the 7z placeholder names
  `pip install 'ezmd[7z]'` without escaped brackets.
- Release notes come from the exact `## [<version>]` changelog heading (or `## [Unreleased]`); the release fails
  instead of publishing another version's notes.
- `packages/mcp/server.json` no longer advertises a hosted `/mcp` endpoint the API does not serve yet.

### Documentation
- README and docs describe what is published (PyPI pre-release, GHCR images; npm with 0.1.0) and recommend an
  exact version pin for the release candidate.
- Email (EML, MBOX, MSG) is listed as supported; repository packing is documented as `--converter
  code.repo_pack` or a GitHub URL (local `*.repo.zip` names are not picked automatically, directories are not
  an input).
- Converter options are documented with the working `--opt extra.pdf.<name>=...` form; the install guide has
  the Docling model download step (`docling-tools models download layout tableformer -o DIR`,
  `EZMD_DOCLING_ARTIFACTS=DIR`).

## [0.1.0-rc2] - 2026-10-08

Second release candidate. Published to PyPI as a pre-release.

### Fixed
- On Windows, `ezmd convert` crashed with `UnicodeEncodeError` when its output was piped or redirected
  (the stream used the legacy cp1252 code page). The CLI now writes UTF-8 to stdout and stderr.
- Parquet column statistics render zone-aware timestamps the same way on every pyarrow version.

### Changed
- Renamed from intomd to ezmd before the first release (D-0037).

## [0.1.0-rc1] - 2026-10-08

First release candidate (Phase 1). Published to PyPI as a pre-release.

### Added
- Converters: PDF (pypdfium2 text with structure-tree headings; Docling layout engine in the `docs` extra),
  DOCX with tracked changes and comments, PPTX with notes, XLSX with formulas and every sheet, ODF, RTF,
  EPUB, Jupyter notebooks, archives (zip, tar, 7z in the `7z` extra) with bomb limits, web pages
  (Trafilatura with hidden-content stripping), source files and repositories with secret redaction,
  CSV/TSV/JSON/YAML/TOML/XML/SQLite (Parquet in the `data` extra), email (EML, MBOX, native Outlook MSG),
  and SEC EDGAR filings.
- Interfaces: `ezmd` CLI (`convert`, `batch`, `doctor`, ~~`config`, `remote`~~, `shadow-run`; correction: the
  `config` and `remote` commands are not implemented yet: config is read from the config file and remote use is
  the `--remote` option), the Python library
  (`ezmd.convert`, `convert_async`, `convert_many`), the MCP server `ezmd-mcp` (stdio and streamable HTTP),
  the HTTP API with SSE progress, the web UI, and the `@ezmd/sdk` TypeScript client.
- Self-hosting: Docker Compose stack with bootstrap, backup, restore and upgrade scripts; images scanned with
  Trivy, shipped with SPDX SBOMs and signed with cosign.
- 94 golden fixtures with provenance checks, a nightly scorecard, integration tests on the compose stack, and a
  Playwright suite with accessibility checks.

### Security
- SSRF guard on every fetch (blocked ranges, IPv4-mapped addresses, internal service ports, per-hop checks),
  sandboxed external tools, hidden-text and prompt-injection scanning in the renderer.

## [0.0.1] - 2026-10-08

### Added
- Phase 0 foundation: IR, detection, converter registry with fallback chains, sandbox, SSRF guard,
  plain text and Markdown converters, renderer profiles, fixture scorer, CLI, API, web UI, Docker Compose, CI.
