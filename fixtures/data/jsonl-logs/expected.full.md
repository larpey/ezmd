---
title: "input.jsonl"
source: "input.jsonl"
source_type: data
converter: data.json
converter_version: "0.1.0rc1"
ezmd_version: "0.1.0rc1"
schema_version: 1
profile: full
provenance: block
fetched_at: 2026-01-01T00:00:00Z
converted_at: 2026-01-01T00:00:00Z
word_count: 148
tokens: {o200k_base: 572, cl100k_base: 573, claude_approx: 618}
content_hash: "sha256:b214a46a3aef6f784ed237149e786bfae21da6da26649b02616488555e1b94c5"
source_hash: "sha256:cd5e4749447205e4b1ff765d22e85d5415d9b78a648a20d8e67a6f2b38678af8"
truncated: false
warnings: [markup_partial]
injection_risk: none
extra: {depth: 2, encoding: utf-8, format: "JSON Lines"}
---
# input.jsonl {#doc}

JSON Lines array of 12 records; nesting depth 2.

## 1 Schema {#sec-1}

**Table 1**
Columns: Path, Types, Count, Null %, Examples

| Path | Types | Count | Null % | Examples |
|---|---|---:|---:|---|
| / | array | 1 | 0 |  |
| /* | object | 12 | 0 |  |
| /*/ts | string | 12 | 0 | 2026-05-01T10:00:00Z, 2026-05-01T10:01:00Z, 2026-05-01T10:02:00Z |
| /*/level | string | 12 | 0 | INFO, WARN, ERROR |
| /*/msg | string | 12 | 0 | request 0 handled, request 1 handled, request 2 handled |
| /*/ms | integer | 12 | 0 | 10, 13, 16 |

## 2 Data {#sec-2}

**Table 2**

| ts | level | msg | ms |
|---|---|---|---:|
| 2026-05-01T10:00:00Z | INFO | request 0 handled | 10 |
| 2026-05-01T10:01:00Z | WARN | request 1 handled | 13 |
| 2026-05-01T10:02:00Z | ERROR | request 2 handled | 16 |
| 2026-05-01T10:03:00Z | INFO | request 3 handled | 19 |
| 2026-05-01T10:04:00Z | WARN | request 4 handled | 22 |
| 2026-05-01T10:05:00Z | ERROR | request 5 handled | 25 |
| 2026-05-01T10:06:00Z | INFO | request 6 handled | 28 |
| 2026-05-01T10:07:00Z | WARN | request 7 handled | 31 |
| 2026-05-01T10:08:00Z | ERROR | request 8 handled | 34 |
| 2026-05-01T10:09:00Z | INFO | request 9 handled | 37 |
| 2026-05-01T10:10:00Z | WARN | request 10 handled | 40 |
| 2026-05-01T10:11:00Z | ERROR | request 11 handled | 43 |
