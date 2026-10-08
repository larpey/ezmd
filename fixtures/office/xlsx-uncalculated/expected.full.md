---
title: "Fuel Budget"
source: "input.xlsx"
source_type: xlsx
converter: documents.xlsx
converter_version: "0.0.1"
intomd_version: "0.0.1"
schema_version: 1
profile: full
provenance: block
fetched_at: 2026-01-01T00:00:00Z
converted_at: 2026-01-01T00:00:00Z
author: "Transit Desk"
sheets: ["Budget", "Check"]
word_count: 37
tokens: {o200k_base: 183, cl100k_base: 183, claude_approx: 198}
content_hash: "sha256:19cd8cc9b011f434244e183e6946b85d7169b835bfef688ce697042384d4d9af"
source_hash: "sha256:9889cbb504266939eaea65f92691cc7dc1facfa4f7d08ea087eb10a2eac7b43a"
truncated: false
warnings: [formula_uncalculated, formulas_present]
injection_risk: none
---
# Fuel Budget {#doc}

<!-- sheet "Budget" -->
## 1 Budget {#sec-1}

**Table 1**

| Month | Litres | Price | Cost |
|---|---:|---:|---|
| January | 12000 | 1.42 | =B2*C2 |
| February | 11000 | 1.45 | =B3*C3 |
| March | 12500 | 1.39 | =B4*C4 |
| Total | =SUM(B2:B4) |  | =SUM(D2:D4) |

<!-- sheet "Check" -->
## 2 Check {#sec-2}

**Table 2**
<!-- intomd: header synthesized -->

| col_1 | col_2 |
|---|---|
| Average price | =AVERAGE(Budget!C2:C4) |
