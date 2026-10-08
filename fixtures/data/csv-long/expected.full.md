---
title: "input.csv"
source: "input.csv"
source_type: data
converter: data.csv
converter_version: "0.0.1"
intomd_version: "0.0.1"
schema_version: 1
profile: full
provenance: block
fetched_at: 2026-01-01T00:00:00Z
converted_at: 2026-01-01T00:00:00Z
word_count: 233
tokens: {o200k_base: 598, cl100k_base: 614, claude_approx: 646}
content_hash: "sha256:f364a424383b64d515d6bb86a6716dab68b931ec7cf2ded4615208adca6c1ffc"
source_hash: "sha256:25d3a1fc41337238c32af92de23eb6be180ccbefc463eb6c919991debfed8ce0"
truncated: true
warnings: [table_sampled]
injection_risk: none
exports: {tables: ["tables/table-01.csv"]}
extra: {bom: false, columns: 4, delimiter: comma, dialect_sniffed: true, encoding: utf-8, format: CSV, header_row: true, rows: 1200}
---
# input.csv {#doc}

**Table 1** (4 columns, 1,200 rows; full data: tables/table-01.csv)
Columns: row, city, item, qty

- row: 1 | city: Oslo | item: clamps | qty: 37
- row: 2 | city: Quito | item: gaskets | qty: 74
- row: 3 | city: Nairobi | item: springs | qty: 111
- row: 4 | city: Hanoi | item: rivets | qty: 148
- row: 5 | city: Perth | item: brackets | qty: 185
- row: 6 | city: Tromso | item: hinges | qty: 222
- row: 7 | city: Cusco | item: washers | qty: 259
- row: 8 | city: Accra | item: bolts | qty: 296
- row: 9 | city: Riga | item: clamps | qty: 333
- row: 10 | city: Lisbon | item: gaskets | qty: 370
- row: 11 | city: Oslo | item: springs | qty: 407
- row: 12 | city: Quito | item: rivets | qty: 444
- row: 13 | city: Nairobi | item: brackets | qty: 481
- row: 14 | city: Hanoi | item: hinges | qty: 18
- row: 15 | city: Perth | item: washers | qty: 55
- row: 16 | city: Tromso | item: bolts | qty: 92
- row: 17 | city: Cusco | item: clamps | qty: 129
- row: 18 | city: Accra | item: gaskets | qty: 166
- row: 19 | city: Riga | item: springs | qty: 203
- row: 20 | city: Lisbon | item: rivets | qty: 240
<!-- intomd: 1,175 rows omitted; full data in tables/table-01.csv -->
- row: 1196 | city: Tromso | item: rivets | qty: 252
- row: 1197 | city: Cusco | item: brackets | qty: 289
- row: 1198 | city: Accra | item: hinges | qty: 326
- row: 1199 | city: Riga | item: washers | qty: 363
- row: 1200 | city: Lisbon | item: bolts | qty: 400

Summary: 1,200 rows; row min 1, max 1,200, sum 720,600; qty min 0, max 499, sum 300,200
