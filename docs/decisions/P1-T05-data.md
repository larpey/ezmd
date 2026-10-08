# P1-T05: data converters — decisions and approach notes

Date: 2026-10-08. Task: P1-T05. Branch: `task/P1-T05-data`. Spec: docs/spec/part2.md section 10 (and 2c
steps 35 to 37 for CSV), 13.4 caps, part1 8.2 input validation.

## Approach notes (part1 2.5)

### CSV/TSV (`data.csv`)
- Libraries: stdlib `csv` (PSF-2.0) with `csv.Sniffer`; charset-normalizer 3.5.2 (MIT, `LICENSE` in the
  wheel's `licenses/` read). Entry points: `csv.Sniffer().sniff(sample, delimiters=",;\t|")`,
  `csv.reader`, `charset_normalizer.from_bytes`.
- Known issues: `Sniffer` mis-detects on quoted fields containing the other candidate delimiters and on
  single-column files; `has_header` is unreliable on short or all-text files; charset-normalizer is
  ambiguous between single-byte code pages on short inputs (a 3-line Latin-1 file came back as cp1257).
- Mitigations: the sniffed delimiter is accepted only when at least 90% of sampled rows share a field
  count of 2 or more, else the most consistent candidate wins; `.tsv` forces tab. Header rule follows
  2c step 26 (string first row above typed data) with `has_header` only as a tie-breaker on 5+ rows.
  Among near-equal charset guesses (chaos within 0.1) cp1252, then Latin-1, then ISO-8859-15 is preferred.
- Fallback: none needed (stdlib). Fixtures: `csv-bom-semicolon`, `csv-wide`, `csv-long`, `tsv-basic`.

### JSON, JSON Lines (`data.json`), YAML (`data.yaml`), TOML (`data.toml`)
- Libraries: stdlib `json` and `tomllib` (PSF-2.0); PyYAML 6.0.3 (MIT, `licenses/LICENSE` read), already a
  core dependency, now also declared by ezmd-converters.
- Entry points: `json.loads(parse_int=RawNumber, parse_float=RawNumber, parse_constant=RawNumber)`;
  `tomllib.loads(parse_float=RawNumber)`; a `yaml.SafeLoader` subclass.
- YAML loader decision: the brief says `yaml.safe_load` only. We use a `SafeLoader` subclass (so the same
  safe constructor set) that changes three constructors: int/float keep the scalar text, timestamps stay
  strings, and the fallback constructor turns unknown tags into the inert string `!tag <value>` plus
  `yaml_unsafe_tags` (the spec's `yaml_tags="ignore"` default). Nothing outside SafeConstructor is
  reachable; `!!python/*` tags are never resolved to callables.
- Known issues: `json` and PyYAML recurse while parsing (depth ~1000 raises `RecursionError`); YAML
  aliases share objects, so a naive walk of an alias bomb is exponential and a self-referencing anchor is
  infinite; `tomllib` loses datetime spelling.
- Mitigations: `RecursionError` becomes a clean `ConversionError`; every parsed value goes through an
  iterative `clip()` copy with a depth cap (64, `depth_truncated`) and a node budget (200,000,
  `size_cap`), so rendering is bounded and cycles terminate. UTC datetimes render with `Z`.
- Layout decision (revised after Skeptic review): `## Schema` (generalized pointer, types, count, null %,
  examples) then `## Data` for JSON and YAML (10c steps 2 and 3). Members stay in source key order:
  consecutive scalars form one `Key | Value` table at their position; a run after a nested section gets
  its own heading at the nested members' level (the key for one member, `Other keys` for several), so
  section paths and RAG chunks never attribute it to the preceding section. Records follow 10c step 2 (shared keys over 60% of all keys). TOML keeps its tables as
  H2/H3 sections without a schema table (10c step 11 describes sections, not a schema).
- Sampling decision (revised after Skeptic review): tables never contain a marker row. Sampled tables hold
  only real rows, `Table.attrs` carry `rows_total`, `rows_omitted`, `omitted_after_row`, and a paragraph
  after the table states the gap. The renderer has no hook for these attrs today (core request), so the
  paragraph is the visible marker. Arrays over `max_rows` keep head 100 + tail 20 (no stratified middle
  sample yet: deviation from 10c step 5).
- Raw source: YAML, TOML and XML keep the raw (cleaned) source as a code block under `## Source` up to
  64 KB (10c steps 8, 9, 11); larger files get a one-line note instead. The converter cannot see the
  profile, so the block is present in every profile (deviation: spec says `full` only).
- Fixtures: `json-records`, `json-nested-config`, `jsonl-logs`, `yaml-anchors-unsafe`, `toml-config`.

### XML (`data.xml`)
- Library: defusedxml 0.7.1 (PSF-2.0, `LICENSE` in the dist-info read). Entry point
  `defusedxml.ElementTree.iterparse(events=("start-ns",))`, defaults `forbid_entities=True`,
  `forbid_external=True`. Open upstream issues are about Python 3.12 deprecations of
  `defusedxml.cElementTree`/`lxml` wrappers, not the ElementTree path used here.
- Decision: on `DefusedXmlException` (entity or DTD declarations) the DOCTYPE is removed, custom entity
  references are dropped, and the bytes are parsed again with `forbid_dtd=True`; `unsupported_feature`
  reports the count. Result: XXE and billion-laughs inputs convert with no entity content and no I/O.
  lxml (spec 10b) was not added: defusedxml satisfies part1 8.2 and ElementTree is stdlib.
- Structure: `## Structure` table (element path, count, attributes, text sample, up to 200 paths) per 10c
  step 9. Records threshold per the spec: an element repeated more than 5 times becomes a table; fewer
  repeats render one heading per element. The raw source is the sanitized copy when a DOCTYPE was removed,
  so the XXE payload text never reaches the output; it is not pretty-printed or sampled (deviation).
- Known gaps: no `sourceline`, no root dispatch to section 7/12 converters. Fixtures: `xml-namespaces`
  (six books, two suppliers), `xml-xxe`.

### SQLite (`data.sqlite`)
- Library: stdlib `sqlite3` (PSF-2.0; SQLite itself is public domain).
- Decision: copy to a private temp dir, open `file:<copy>?mode=ro&immutable=1` (URI), then
  `PRAGMA query_only=1`, `PRAGMA trusted_schema=OFF`, `SQLITE_DBCONFIG_DEFENSIVE` when available, and a
  progress handler that aborts any statement after 5 s or once the conversion deadline passes.
  Identifiers are double-quoted with `""` escaping; values are bound parameters.
- Detection: core detection maps Magika's `sqlite` label and `.sqlite`/`.db` to `application/vnd.sqlite3`
  (D-0026); `can_handle` keys on that mime, with 0.3 for `.sqlite`/`.db` octet-stream files (encrypted).
- Statistics: per table under `stats_max_rows`, one `SELECT` of `COUNT(*) - COUNT(c)`,
  `COUNT(DISTINCT c)`, `MIN(c)`, `MAX(c)` per sampled column (BLOB bounds left empty); size per table from
  `dbstat` when compiled in (the column is omitted otherwise, as on the stock Windows and Debian builds).
  Boolean schema columns (not null, primary key) use yes/no.
- Fixture: `sqlite-two-tables` (two tables, FK, index, view, NULLs, BLOBs, 130 rows sampled).

### Parquet (`data.parquet`)
- Library: pyarrow 25.0.1 (Apache-2.0; `LICENSE.txt` at github.com/apache/arrow read). Entry points
  `pyarrow.parquet.ParquetFile`, `.metadata`, `.schema_arrow`, `.iter_batches`, `.read_row_group`.
- Size decision: the cp312 wheels are 27 MB (Windows) to 50 MB (manylinux x86_64) compressed, well over
  100 MB installed, which alone breaks the `pip install ezmd` budget of under 120 MB (part4 4.3.3). So
  pyarrow lives in a new optional extra `data` on ezmd-converters, and without it the converter is an
  `Unavailable` entry naming the extra.
- Known issue: converting zone-aware timestamps needs a time zone database; Windows has none without
  `tzdata`, and pyarrow raises `ArrowInvalid`. Mitigation: zone-aware columns are cast to naive UTC
  before `to_pylist()`, statistics are rebuilt from the raw integers, and values render with `Z`.
- Fixture: `fixtures/data/parquet-basic` with `requires = ["data"]`: the harness skips it when pyarrow is
  missing (D-0026); `test_data_db.py::test_parquet_unavailable_or_fixture_matches` also runs it.

### Connection strings (`data.connection_string`)
- No library. URL inputs with a database scheme, and text bodies under 4 KB that are exactly one
  connection string, return a one-paragraph stub and `connection_string_refused`. The stub is a
  paragraph (not an empty document) because the golden harness rejects zero-block documents whose golden
  has content (the H1). Credentials are never echoed.

### CSV attachment check
- `expected.table-NN.csv` in `csv-wide`, `csv-long`, `json-records` and `sqlite-two-tables` are the
  byte-exact CSV attachments the renderer writes; `test_data_db.py::test_csv_attachments_match_expected`
  compares them.

## Thresholds
`fixtures/data/thresholds.toml` sets 1.0 for every data converter (ROADMAP P1-T05 "exact-match";
part2 10g asks for exact element counts and exact security fixtures).

## Dependencies
- `defusedxml>=0.7.1` (installed 0.7.1), PSF-2.0, ~25 KB, safe XML parsing (part1 8.2). Default.
- `pyyaml>=6.0` (installed 6.0.3), MIT, ~800 KB, YAML; already a core dependency, declared here because
  the converters import it. Default.
- `pyarrow>=17.0` (locked 25.0.1), Apache-2.0, 27 to 50 MB wheel, Parquet; optional extra `data`.
