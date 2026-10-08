---
title: "Pond Survey Workbook"
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
author: "Field Team"
sheets: ["Visits", "Summary", "Lookup"]
word_count: 102
tokens: {o200k_base: 452, cl100k_base: 455, claude_approx: 488}
content_hash: "sha256:611fb3d696490ea73d112c5bae83bfb7989c4dcf855775f831623689f36222d6"
source_hash: "sha256:474334c052229c81c56a228906796e62477cbdfa7e7e99d88f9cddae49652fc3"
truncated: false
warnings: [hidden_sheets_included, cell_errors, comments_present, formulas_present]
injection_risk: none
---
# Pond Survey Workbook {#doc}

<!-- sheet "Visits" -->
## 1 Visits {#sec-1}

**Table 1: Region 1 (A1:E5)**
Columns: Site, Visit date, Species, Share, Cost

| Site | Visit date | Species | Share | Cost |
|---|---|---:|---:|---:|
| North pond | 2025-04-03 | 14 | 25.0% | $120.50 |
| South pond | 2025-04-10 | 9 | 12.5% | $80.00 |
| East pond | 2025-05-02 | 11 | 50.0% | $95.25 |
| Total |  | 34 |  | $295.75 |

**Table 2: Region 2 (A8:B9)**
<!-- intomd: header synthesized -->

| col_1 | col_2 |
|---|---|
| Notes |  |
| Rain on 10 April | #REF! |

<!-- sheet "Summary" -->
## 2 Summary {#sec-2}

**Table 3**

<table>
<thead>
<tr><th colspan="3">Season totals</th></tr>
<tr><th>Season</th><th>Plants</th><th>Animals</th></tr>
</thead>
<tbody>
<tr><td>Spring</td><td>12</td><td>7</td></tr>
<tr><td>Summer</td><td>18</td><td>11</td></tr>
<tr><td>All</td><td>30</td><td>18</td></tr>
</tbody>
</table>

<!-- sheet "Lookup" -->
## 3 Lookup (hidden) {#sec-3}

**Table 4**

| Code | Meaning |
|---|---|
| NP | North pond |
| SP | South pond |

## 4 Named ranges {#sec-4}

**Table 5**

| Name | Refers to |
|---|---|
| SiteCodes | Lookup!\$A\$2:\$B\$3 |
