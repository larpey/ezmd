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
word_count: 224
tokens: {o200k_base: 655, cl100k_base: 660, claude_approx: 707}
content_hash: "sha256:cfce8a46e6507b801420b2fc06c3ffc5c824f2cd96c71baa67d665817c9f60fb"
source_hash: "sha256:c9019be121afd433f5985d257e04855262f99417cc0bf50512cf3160c694f8e4"
truncated: false
warnings: []
injection_risk: none
exports: {tables: ["tables/table-01.csv"]}
extra: {bom: false, columns: 12, delimiter: comma, dialect_sniffed: true, encoding: utf-8, format: CSV, header_row: true, rows: 8}
---
# input.csv {#doc}

**Table 1** (12 columns, 8 rows; full data: tables/table-01.csv)
Columns: sku, name, city, qty, price, weight_kg, color, supplier, lead_days, in_stock, rating, updated

- sku: SKU-1000 | name: bolts | city: Lisbon | qty: 10 | price: 3.00 | weight_kg: 0.5 | color: red | supplier: Supplier A | lead_days: 7 | in_stock: true | rating: 4.0 | updated: 2026-01-10
- sku: SKU-1001 | name: washers | city: Oslo | qty: 20 | price: 4.25 | weight_kg: 0.6 | color: blue | supplier: Supplier B | lead_days: 8 | in_stock: false | rating: 4.5 | updated: 2026-02-11
- sku: SKU-1002 | name: hinges | city: Quito | qty: 30 | price: 5.50 | weight_kg: 0.7 | color: green | supplier: Supplier C | lead_days: 9 | in_stock: true | rating: 4.0 | updated: 2026-03-12
- sku: SKU-1003 | name: brackets | city: Nairobi | qty: 40 | price: 6.75 | weight_kg: 0.8 | color: red | supplier: Supplier D | lead_days: 10 | in_stock: false | rating: 4.5 | updated: 2026-04-13
- sku: SKU-1004 | name: rivets | city: Hanoi | qty: 50 | price: 8.00 | weight_kg: 0.9 | color: blue | supplier: Supplier E | lead_days: 11 | in_stock: true | rating: 4.0 | updated: 2026-05-14
- sku: SKU-1005 | name: springs | city: Perth | qty: 60 | price: 9.25 | weight_kg: 1.0 | color: green | supplier: Supplier F | lead_days: 12 | in_stock: false | rating: 4.5 | updated: 2026-06-15
- sku: SKU-1006 | name: gaskets | city: Tromso | qty: 70 | price: 10.50 | weight_kg: 1.1 | color: red | supplier: Supplier G | lead_days: 13 | in_stock: true | rating: 4.0 | updated: 2026-07-16
- sku: SKU-1007 | name: clamps | city: Cusco | qty: 80 | price: 11.75 | weight_kg: 1.2 | color: blue | supplier: Supplier H | lead_days: 14 | in_stock: false | rating: 4.5 | updated: 2026-08-17
