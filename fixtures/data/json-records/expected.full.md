---
title: "input.json"
source: "input.json"
source_type: data
converter: data.json
converter_version: "0.1.0rc1"
ezmd_version: "0.1.0rc1"
schema_version: 1
profile: full
provenance: block
fetched_at: 2026-01-01T00:00:00Z
converted_at: 2026-01-01T00:00:00Z
word_count: 157
tokens: {o200k_base: 474, cl100k_base: 475, claude_approx: 512}
content_hash: "sha256:2164d9cdde6274ef30ddfb3277d935597cb6e1d54924b1105a05a3424f00b99e"
source_hash: "sha256:9f5f875437d005132052be66d8f2d52108bcc02ee7970402470a1d3f331cf0c5"
truncated: false
warnings: []
injection_risk: none
exports: {tables: ["tables/table-02.csv"]}
extra: {depth: 3, encoding: utf-8, format: JSON}
---
# input.json {#doc}

JSON array of 3 records; nesting depth 3.

## 1 Schema {#sec-1}

**Table 1**
Columns: Path, Types, Count, Null %, Examples

| Path | Types | Count | Null % | Examples |
|---|---|---:|---:|---|
| / | array | 1 | 0 |  |
| /* | object | 3 | 0 |  |
| /*/id | integer | 3 | 0 | 1234567890123456789, 2, 3 |
| /*/name | string | 3 | 0 | Ada, Grace, Linus \| Jr |
| /*/score | number | 3 | 0 | 1.10, 2.50, 1e400 |
| /*/active | boolean, null | 3 | 33 | true, false |
| /*/address | object | 3 | 0 |  |
| /*/address/city | string | 3 | 0 | Lisbon, Oslo, Quito |
| /*/address/zip | string, null | 2 | 50 | 1100-001 |
| /*/tags | array | 2 | 0 |  |
| /\*/tags/\* | string | 2 | 0 | admin, ops |
| /*/note | string | 1 | 0 | only here |

## 2 Data {#sec-2}

**Table 2** (8 columns, 3 rows; full data: tables/table-02.csv)
Columns: id, name, score, active, address.city, address.zip, tags, note

- id: 1234567890123456789 | name: Ada | score: 1.10 | active: true | address.city: Lisbon | address.zip: 1100-001 | tags: ["admin", "ops"]
- id: 2 | name: Grace | score: 2.50 | active: false | address.city: Oslo | address.zip: null | tags: []
- id: 3 | name: Linus \| Jr | score: 1e400 | active: null | address.city: Quito | note: only here
