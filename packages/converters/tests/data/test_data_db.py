"""SQLite, Parquet, connection strings, and family wiring (registration, chains, detection, rendering)."""

from __future__ import annotations

import hashlib
import importlib.util
import sqlite3
from collections.abc import Callable
from pathlib import Path

import pytest

from ezmd.detect import detect
from ezmd.inputs import Detected, InputRef
from ezmd.ir import CodeBlock, Document, Heading, ListBlock, Table, WarningKind
from ezmd.pipeline import convert_ref
from ezmd.registry import ConvertOptions, Unavailable
from ezmd_converters import data as family
from ezmd_converters.data.connstr import ConnectionStringConverter, looks_like_connection_string, redacted
from ezmd_converters.data.sqlite_conv import SqliteConverter

Convert = Callable[..., Document]
FIXTURES = Path(__file__).resolve().parents[4] / "fixtures"


def _tables(doc: Document) -> list[Table]:
    return [b for b in doc.blocks if isinstance(b, Table)]


def _cells(t: Table) -> list[list[str]]:
    return [["".join(s.text for s in c.spans) if c else "" for c in row] for row in t.grid()]


def _db(path: Path, script: str, rows: int = 0) -> Path:
    con = sqlite3.connect(path)
    con.executescript(script)
    for i in range(rows):
        con.execute('INSERT INTO "we""ird" VALUES (?, ?)', (i, f"v{i}"))
    con.commit()
    con.close()
    return path


# ---------------------------------------------------------------- SQLite


def test_sqlite_quoted_names_sampling_and_read_only(tmp_path: Path, convert: Convert) -> None:
    db = _db(
        tmp_path / "a.sqlite",
        'CREATE TABLE "we""ird" (id INTEGER PRIMARY KEY, "na me" TEXT);'
        "CREATE TABLE kv (k TEXT PRIMARY KEY, v BLOB) WITHOUT ROWID;"
        "INSERT INTO kv VALUES ('a', x'0102'), ('b', NULL);"
        "CREATE TRIGGER t AFTER INSERT ON kv BEGIN SELECT 1; END;",
        rows=150,
    )
    before = hashlib.sha256(db.read_bytes()).hexdigest()
    doc = convert(SqliteConverter(), db.read_bytes(), "a.sqlite")
    assert hashlib.sha256(db.read_bytes()).hexdigest() == before
    summary, weird_cols, weird_stats, weird_sample, _kv_cols, kv_stats, kv_sample = _tables(doc)
    assert [r[:3] for r in _cells(summary)[1:]] == [['we"ird', "150", "2"], ["kv", "2", "2"]]
    assert summary.column_types[:3] == ["text", "int", "int"]
    assert _cells(weird_cols)[1] == ["id", "INTEGER", "no", "", "yes", ""]
    assert _cells(weird_stats)[1:] == [["id", "0", "150", "0", "149"], ["na me", "0", "150", "v0", "v99"]]
    assert _cells(kv_stats)[2] == ["v", "1", "1", "", ""]
    assert weird_sample.n_rows == 1 + 100 + 20
    assert _cells(weird_sample)[100] == ["99", "v99"] and _cells(weird_sample)[101] == ["130", "v130"]
    assert _cells(weird_sample)[-1] == ["149", "v149"]
    assert weird_sample.attrs["rows_omitted"] == "30" and weird_sample.attrs["omitted_after_row"] == "100"
    assert _cells(kv_sample)[1:] == [["a", "<blob 2 bytes>"], ["b", "NULL"]]
    assert weird_sample.provenance.path == 'we"ird/sample'
    assert any(isinstance(b, CodeBlock) and b.language == "sql" and "TRIGGER" in b.code for b in doc.blocks)
    assert [w.kind for w in doc.warnings] == [WarningKind.ROWS_SAMPLED]
    assert doc.truncated is False  # rows_sampled truncates via the registry (code spec)


def test_sqlite_foreign_keys_and_indexes(convert: Convert) -> None:
    raw = (FIXTURES / "data" / "sqlite-two-tables" / "input.sqlite").read_bytes()
    doc = convert(SqliteConverter(), raw, "shop.db")
    cols = _tables(doc)[4]
    assert ["customer_id", "INTEGER", "yes", "", "no", "customers(id)"] in _cells(cols)
    assert any(isinstance(b, ListBlock) for b in doc.blocks)
    assert [(b.level, b.spans[0].text) for b in doc.blocks if isinstance(b, Heading)][:3] == [
        (1, "shop.db"),
        (2, "Tables"),
        (3, "customers"),
    ]


def test_sqlite_encrypted_header(convert: Convert) -> None:
    doc = convert(SqliteConverter(), bytes(range(256)) * 16, "secret.db")
    assert doc.blocks == []
    assert doc.warnings[0].kind == WarningKind.SQLITE_ENCRYPTED and doc.warnings[0].severity == "error"


def test_sqlite_corrupt_raises(convert: Convert) -> None:
    from ezmd.registry import ConversionError

    bad = b"SQLite format 3" + bytes([0]) + bytes([0xFF]) * 4000
    with pytest.raises(ConversionError):
        convert(SqliteConverter(), bad, "bad.sqlite")


def test_sqlite_can_handle() -> None:
    ref = InputRef.from_bytes(b"x", filename="a.db")
    ref.detected = Detected(mime="application/vnd.sqlite3", extension=".db", confidence=1.0)
    assert SqliteConverter().can_handle(ref) == 1.0
    ref.detected = Detected(mime="application/octet-stream", extension=".db", confidence=0.0)
    assert SqliteConverter().can_handle(ref) == 0.3
    ref.detected = Detected(mime="text/plain", extension=".txt", confidence=1.0)
    assert SqliteConverter().can_handle(ref) == 0.0


# ---------------------------------------------------------------- Parquet


def test_parquet_unavailable_or_fixture_matches() -> None:
    convs = {c.id: c for c in family.converters()}
    if importlib.util.find_spec("pyarrow") is None:
        conv = convs["data.parquet"]
        assert isinstance(conv, Unavailable) and conv.requires_extras == ("data",)
        return
    from ezmd.testing.fixtures import Fixture, load_meta, run_fixture

    case = FIXTURES / "data" / "parquet-basic"
    run = run_fixture(Fixture(path=case, meta=load_meta(case)), FIXTURES)
    assert not run.hard_failures and run.score is not None and run.score.overall >= 1.0


# ---------------------------------------------------------------- connection strings


@pytest.mark.parametrize(
    "text",
    [
        "postgres://u:p@h:5432/db",
        "postgresql+psycopg://h/db",
        "mongodb+srv://u:p@cluster.example/x?retryWrites=true",
        "jdbc:mysql://h:3306/db",
        "Server=tcp:h,1433;Database=db;User Id=u;Password=p;",
    ],
)
def test_connection_strings_detected(text: str) -> None:
    assert looks_like_connection_string(text)


def test_connection_string_not_detected_for_prose() -> None:
    assert not looks_like_connection_string("see postgres://h/db for details")
    assert not looks_like_connection_string("https://example.com/x")


def test_redaction_drops_credentials() -> None:
    assert redacted("postgres://user:secret@db.example:5432/sales?sslmode=x") == "postgres://db.example/sales"


def test_connection_string_url_input_refused() -> None:
    ref = InputRef.from_url("postgres://user:secret@db.example/sales")
    conv = ConnectionStringConverter()
    assert conv.can_handle(ref) == 1.0
    doc = conv.convert(ref, ConvertOptions())
    assert len(doc.blocks) == 1 and doc.warnings[0].kind == WarningKind.CONNECTION_STRING_REFUSED
    assert "secret" not in doc.model_dump_json() and doc.metadata.source == "postgres://db.example/sales"


def test_connection_string_text_body() -> None:
    ref = InputRef.from_bytes(b"mysql://root:pw@localhost/app\n", filename="c.txt")
    detect(ref)
    conv = ConnectionStringConverter()
    assert conv.can_handle(ref) == 1.0
    assert "pw" not in conv.convert(ref, ConvertOptions()).model_dump_json()
    plain = InputRef.from_bytes(b"just words here\n", filename="c.txt")
    detect(plain)
    assert conv.can_handle(plain) == 0.0


# ---------------------------------------------------------------- family wiring


def test_family_registration_and_chains() -> None:
    ids = {c.id for c in family.converters()}
    assert {"data.csv", "data.json", "data.yaml", "data.toml", "data.xml", "data.sqlite", "data.parquet"} <= ids
    assert set(family.CHAINS["text/csv"]) == {"data.csv"}
    for chain in family.CHAINS.values():
        assert set(chain) <= ids


@pytest.mark.parametrize(
    ("case", "converter"),
    [
        ("csv-bom-semicolon", "data.csv"),
        ("tsv-basic", "data.csv"),
        ("json-records", "data.json"),
        ("jsonl-logs", "data.json"),
        ("yaml-anchors-unsafe", "data.yaml"),
        ("toml-config", "data.toml"),
        ("xml-namespaces", "data.xml"),
        ("sqlite-two-tables", "data.sqlite"),
    ],
)
def test_detection_routes_fixtures(case: str, converter: str) -> None:
    path = next((FIXTURES / "data" / case).glob("input.*"))
    ref = InputRef.from_path(path)
    try:
        result = convert_ref(ref, ConvertOptions())
    finally:
        ref.cleanup()
    assert result.converter_id == converter


def test_wide_and_long_tables_render_with_csv_attachment() -> None:
    from ezmd.render import render

    for case in ("csv-wide", "csv-long"):
        ref = InputRef.from_path(FIXTURES / "data" / case / "input.csv")
        try:
            out = render(convert_ref(ref, ConvertOptions()), "full", "md")
        finally:
            ref.cleanup()
        attachments = {a.path: a for a in out.attachments}
        assert "tables/table-01.csv" in attachments, case
        body = attachments["tables/table-01.csv"].data.decode("utf-8")
        assert body.count(chr(10)) == {"csv-wide": 9, "csv-long": 1201}[case]
        assert "- sku: SKU-1000" in out.markdown or "- row: 1 |" in out.markdown


@pytest.mark.parametrize("case", ["csv-wide", "csv-long", "json-records", "sqlite-two-tables"])
def test_csv_attachments_match_expected(case: str) -> None:
    """The CSV attachments the renderer writes (six-column and fifty-row rules) are byte-exact against
    `expected.table-NN.csv` in the fixture directory."""
    from ezmd.render import render
    from ezmd.testing.fixtures import PINNED_TIME

    d = FIXTURES / "data" / case
    path = next(d.glob("input.*"))
    ref = InputRef.from_path(path)
    ref.display = path.name
    try:
        out = render(convert_ref(ref, ConvertOptions()), "full", "md", converted_at=PINNED_TIME, fetched_at=PINNED_TIME)
    finally:
        ref.cleanup()
    got = {"expected." + a.path.split("/", 1)[1]: a.data for a in out.attachments if a.path.startswith("tables/")}
    want = {f.name: f.read_bytes() for f in d.glob("expected.table-*.csv")}
    assert want and got == want


def test_parquet_statistic_timestamps_render_the_same_for_naive_and_aware_utc() -> None:
    """Older pyarrow yields zone-aware statistics as naive UTC, newer as aware datetimes: same text either way."""
    import datetime as dt

    from ezmd_converters.data.parquet_conv import _stat_text

    naive = dt.datetime(2026, 1, 7, 5, 0)
    assert _stat_text(naive) == "2026-01-07T05:00:00Z"
    assert _stat_text(naive.replace(tzinfo=dt.UTC)) == "2026-01-07T05:00:00Z"
    plus_two = dt.timezone(dt.timedelta(hours=2))
    assert _stat_text(dt.datetime(2026, 1, 7, 7, 0, tzinfo=plus_two)) == "2026-01-07T05:00:00Z"


def _has_dbstat() -> bool:
    con = sqlite3.connect(":memory:")
    try:
        con.execute("SELECT * FROM dbstat LIMIT 1")
    except sqlite3.OperationalError:
        return False
    finally:
        con.close()
    return True


@pytest.mark.parametrize("sizes", [True, False])
def test_sqlite_size_column_follows_dbstat_and_option(tmp_path: Path, convert: Convert, sizes: bool) -> None:
    db = _db(tmp_path / "s.sqlite", 'CREATE TABLE "we""ird" (id INTEGER PRIMARY KEY, v TEXT);', rows=20)
    doc = convert(SqliteConverter(), db.read_bytes(), "s.sqlite", sqlite_sizes=sizes)
    header = _cells(_tables(doc)[0])[0]
    assert ("Size (bytes)" in header) == (sizes and _has_dbstat())
