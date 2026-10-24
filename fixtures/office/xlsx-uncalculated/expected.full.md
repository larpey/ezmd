---
title: "Fuel Budget"
source: "input.xlsx"
source_type: xlsx
converter: documents.xlsx
converter_version: "0.1.1"
ezmd_version: "0.1.1"
schema_version: 1
profile: full
provenance: block
fetched_at: 2026-01-01T00:00:00Z
converted_at: 2026-01-01T00:00:00Z
author: "Transit Desk"
sheets: ["Budget", "Check"]
word_count: 35
tokens: {o200k_base: 171, cl100k_base: 171, claude_approx: 185}
content_hash: "sha256:ad6f2798420adac5457346b205a55007cefbaded708bc9ba8c48b723f4728e36"
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

|  |  |
|---|---|
| Average price | =AVERAGE(Budget!C2:C4) |
