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
word_count: 27
tokens: {o200k_base: 98, cl100k_base: 99, claude_approx: 106}
content_hash: "sha256:ba6fab0a24d271130790153078edf431b26bff2a047045f5348283becc37b137"
source_hash: "sha256:e39020bb15ee3b8c0f77881db82cc8c70d73e2a5f3f26c65e8e8443fcafc119f"
truncated: false
warnings: []
injection_risk: none
extra: {bom: true, columns: 4, delimiter: semicolon, dialect_sniffed: true, encoding: utf-8-sig, format: CSV, header_row: true, rows: 4}
---
# input.csv {#doc}

**Table 1**

| id | name | amount | note |
|---:|---|---:|---|
| 1 | Müller, Anna | 1234,50 | first line<br>second line |
| 2 | Søren | 99,00 | plain |
| 3 | O"Brien | 0,75 | has ; semicolon |
| 4 | Zoe | -12,30 |  |
