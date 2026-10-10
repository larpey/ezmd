# Data converters

The `data` family turns structured files into Markdown that keeps every value exactly as the source wrote
it. Numbers are never rounded or reformatted (`1.10` stays `1.10`, a 19-digit id stays exact), and long
cells are cut for display only, with the full value kept in the sidecar. Tables are emitted whole; the
renderer then applies the table rules (pipe table up to six columns, key:value records beyond that,
sampling past 1,000 rows) and writes the CSV attachment `tables/table-NN.csv` for wide, long or sampled
tables.

| Converter | Formats (detected mime) | Engine | Install |
|---|---|---|---|
| `data.csv` | CSV, TSV (`text/csv`, `text/tab-separated-values`) | stdlib `csv`, charset-normalizer | default |
| `data.json` | JSON, JSON Lines (`application/json`, `application/jsonl`, `application/x-ndjson`) | stdlib `json` | default |
| `data.yaml` | YAML, multi-document streams (`application/yaml`) | PyYAML `SafeLoader` subclass | default |
| `data.toml` | TOML (`application/toml`) | stdlib `tomllib` | default |
| `data.xml` | generic XML (`application/xml`) | defusedxml ElementTree | default |
| `data.sqlite` | SQLite 3 databases (Magika `sqlite`, `application/vnd.sqlite3`) | stdlib `sqlite3`, read-only | default |
| `data.parquet` | Apache Parquet (`application/vnd.apache.parquet`) | pyarrow | `pip install 'ezmd[data]'` |
| `data.connection_string` | `postgres://`, `mysql://`, `mongodb+srv://`, `jdbc:`, `Server=...;Database=...` | none | default; always refuses |

Without pyarrow, `data.parquet` is listed by `ezmd capabilities` as unavailable with the extra to install.

## What each converter produces

Every document starts with an H1 of the file name and, for nested formats, a one-line summary (top-level
type, record count, nesting depth). Every block carries `provenance.path`: a cell range for CSV
(`A1:L9`), a JSON pointer for JSON, YAML and TOML (the root is shown as `/`), an XPath for XML
(`/catalog/book`), and the table name (`orders`, `orders/sample`) for SQLite.

- **CSV/TSV**: one `Table` with `header_rows=1` and `column_types` from a 500-row sample (`int`, `float`,
  `percent`, `date`, `bool`, `text`; `1234,50` counts as a float in semicolon files). The delimiter is
  sniffed over `, ; tab |` and checked for a consistent field count; `.tsv` files always use tabs. A BOM
  is stripped and recorded (`extra.bom`). When the first row is data, a synthetic `A, B, C` header row is
  added and `attrs.header_synthesized` is set. Quoted newlines stay inside the cell (rendered as `<br>`).
- **JSON and YAML** start with `## Schema`: one row per generalized JSON pointer (`*` stands for every
  array index) with the types seen, count, null percentage and up to three examples (at most 200 paths,
  10,000 values per path). `## Data` follows.
- **JSON, YAML, TOML** share one data layout, in source key order: each run of consecutive scalar members
  (and short lists of scalars) is a `Key | Value` table at its position; a run that follows a nested
  section gets its own heading at that section's level (the key name for one member, `Other keys` for
  several), so it is never filed under the section above it; each nested member becomes a heading one level down; an array of
  objects whose shared keys make up over 60% of all keys becomes a records table with nested objects
  flattened by dot path (`address.city`) up to three levels and deeper values as compact JSON; other
  arrays of objects list each item under its own heading (`hooks 1`, `hooks 2`); an array of scalars is a
  bullet list; anything else is pretty-printed JSON in a code block. Below H6 the rest of the subtree is a
  JSON code block, so nothing is dropped. `null` is shown as `null`; a key missing from one record is an
  empty cell.
- **Sampling** never adds marker rows to a table. A sampled table holds only real rows; its `attrs` carry
  `rows_total`, `rows_omitted` and `omitted_after_row`, and a paragraph right after it says
  `(Sample: the first 100 and the last 20 of 1,500 rows; 1,380 rows omitted after row 100.)`.
- **JSON Lines**: one records table; malformed lines (typically a truncated last line) are skipped and
  listed in a `markup_partial` warning. A `.json` file that is really JSON Lines is detected.
- **API responses**: when a JSON object has a non-empty `error` or `errors` member, it is rendered
  first and `api_error_payload` is raised.
- **YAML**: anchors and merge keys are expanded (`extra.anchors_expanded`), each document of a stream
  gets an H3 `Document N` under `## Data`, timestamps stay as written, and the raw source (comments are
  often the documentation) is kept as a `yaml` code block under `## Source` (files up to 64 KB). Tags PyYAML's safe loader does not know
  (`!!python/object/apply:...`, `!Ref`) are never constructed: they appear as the text `!tag value` with
  `yaml_unsafe_tags`.
- **TOML**: tables become headings by dotted path, arrays of tables become records tables, floats keep
  their spelling, datetimes are ISO 8601 (`Z` for UTC); the raw file follows as a `toml` code block under
  `## Source`.
- **XML**: a `Prefix | Namespace URI` table, `## Structure` (element path, count, attributes, text
  sample, up to 200 paths), `## Data`, and `## Source` (the raw XML, after DOCTYPE removal when that
  happened). In the data, attributes are `@name` columns, text next to child elements is `#text`, an element
  repeated more than 5 times forms a records table (fewer repeats are listed one by one as `book 1`,
  `book 2`), namespaces use the document's own prefixes, and string values are typed like CSV cells. DTDs and entities are never processed: a file
  that declares them is re-parsed without its DOCTYPE, its custom entity references are dropped and
  `unsupported_feature` names how many. No file or network access happens (XXE and billion-laughs safe).
- **SQLite**: a summary table (table, rows, columns, and size in bytes when SQLite has `dbstat`), then per
  table its columns (type, not null and primary key as yes/no, default, foreign key target), its indexes,
  `Statistics` (nulls, distinct values, min and max per column, for tables under 1,000,000 rows) and a
  `Sample` of the first 100 and last 20 rows (`rows_sampled`). Views and triggers are shown as SQL.
  BLOBs render as `<blob N bytes>`, NULL as `NULL`. The database is opened from a private copy with
  `mode=ro&immutable=1`, `query_only`, `trusted_schema=OFF` and the defensive flag, and every statement
  has a 5 second budget (`COUNT(*)` falls back to `>= max(rowid) (estimated)`).
- **Parquet**: summary (rows, columns, row groups, compression, writer), a schema table with Arrow types
  (zone and precision included), a statistics table from row-group metadata (min, max, nulls) and sample
  rows (first 100, last 20) reading only the row groups needed and at most 50 columns. Structs and lists
  render as compact JSON, decimals verbatim, zone-aware timestamps as UTC with `Z`.
- **Connection strings** are refused: the output is a one-paragraph stub and a `connection_string_refused`
  error. Credentials never appear in the output, the sidecar or the logs (a URL input's `source` is
  reduced to scheme, host and database).

## Options

Set through `ConvertOptions.extra` as `data.<name>`; from the CLI, `--opt extra.data.<name>=<value>` (for
example `ezmd convert big.json --opt extra.data.max_rows=200`):

| Option | Default | Meaning |
|---|---|---|
| `data.max_bytes` | 50 MB | refuse JSON/YAML/TOML/XML inputs above this size |
| `data.max_rows` | 1000 | arrays longer than this are sampled to head + tail |
| `data.schema_sample` / `data.schema_max_paths` | 10,000 / 200 | schema and structure table limits |
| `data.stats_max_rows` | 1,000,000 | SQLite tables above this get no statistics |
| `data.sqlite_sizes` | true | SQLite size column from `dbstat` (only in SQLite builds that include it, e.g. Linux CPython, not Windows); `false` leaves it out everywhere |
| `data.head_rows` / `data.tail_rows` | 100 / 20 | sample sizes for arrays, SQLite tables and Parquet |
| `data.max_cols` | 50 | columns kept in records, SQLite and Parquet samples |
| `data.schema_depth` | 3 | dot-path flattening depth inside records |
| `data.max_depth` | 64 | deeper values are replaced with `…` |
| `data.max_nodes` | 200,000 | values converted per document (bounds YAML alias bombs) |
| `data.csv_max_rows` / `data.csv_max_cols` | 10,000 / 256 | CSV caps |
| `data.sqlite_max_bytes` | 2 GB | refuse larger SQLite files |
| `data.statement_timeout_s` | 5 | per-statement SQLite budget |

## Warnings

| Code | When |
|---|---|
| `ragged_rows` | CSV rows with too few fields (padded) or too many (joined into the last column) |
| `row_cap_reached` | CSV longer than `csv_max_rows`; the rest is not converted |
| `rows_sampled` | an array, SQLite table or Parquet file was cut to head + tail rows |
| `columns_truncated` | more columns than `max_cols` / `csv_max_cols` |
| `depth_truncated` | values nested deeper than `max_depth` |
| `size_cap` | more values than `max_nodes` |
| `markup_partial` | malformed JSON Lines lines skipped, YAML stream or CSV parsing stopped early |
| `yaml_unsafe_tags` | YAML tags rendered as inert text |
| `api_error_payload` | the JSON carries an error envelope |
| `unsupported_feature` | XML DTD/entities ignored |
| `sqlite_encrypted` | the file lacks the SQLite header (SQLCipher or not a database) |
| `connection_string_refused` | the input is a database connection string |
| `encoding_uncertain`, `removed_hidden_elements` | as for text inputs |

## Known limitations

- CSV: surveys (Typeform, Google Forms, Qualtrics), UTF-16 files without a BOM, and HTML saved as `.csv`
  are not special-cased. Short single-byte files are ambiguous; near-equal guesses prefer cp1252.
- JSON: no JSON5, comments, repair (`json_repaired`) or streaming; files above `max_bytes` are refused
  rather than sampled. Arrays are sampled head + tail, without the stratified middle sample. A one-line
  `.jsonl` file is read as plain JSON.
- YAML: Kubernetes header tables are not built. Merge keys and anchors are expanded silently.
- TOML: comments are only kept through the raw source block; no schema table (tables map directly to
  sections). INI, `.properties` and `.env` files are
  not handled by this family yet (they fall back to plain text).
- XML: no root-element dispatch to RSS/Atom, SVG, plist, XBRL, JATS or DocBook converters; no source line
  numbers; the order of interleaved different child elements is not preserved (children are grouped by
  name); the raw source is shown as written, not pretty-printed or sampled.
- SQLite: uncheckpointed WAL content is not read (the copy is opened immutable); no `options.data.tables`
  filter or user SQL; statistics cover the sampled columns (`max_cols`).
- Parquet: single files only (no partitioned datasets); Arrow IPC/Feather and ORC are not handled; zone
  names other than UTC are shown in the schema but sample values are converted to UTC.
- Connection strings in a `.txt` file are only refused when the text family's `text/plain` chain tries
  `data.connection_string` first (URL inputs are always refused).
