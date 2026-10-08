---
title: "Connection string refused"
source: "input.txt"
source_type: data
converter: data.connection_string
converter_version: "0.1.0rc1"
ezmd_version: "0.1.0rc1"
schema_version: 1
profile: full
provenance: block
fetched_at: 2026-01-01T00:00:00Z
converted_at: 2026-01-01T00:00:00Z
word_count: 36
tokens: {o200k_base: 48, cl100k_base: 48, claude_approx: 52}
content_hash: "sha256:197d79977f49182178b7766692aa161f570fed9582c5743f120b36726500b989"
source_hash: "sha256:adf93cfdb7ac124d2a247e513e6bd8481df2a19da8e5bffe41c294dad721d133"
truncated: false
warnings: [connection_string_refused]
injection_risk: none
---
# Connection string refused {#doc}

This input is a database URL connection string. ezmd does not connect to live databases, so nothing was converted. Export the data to CSV, Parquet, or SQLite and convert that file instead.
