---
title: "Depot Shifts"
source: "input.xlsx"
source_type: xlsx
converter: documents.xlsx
converter_version: "0.1.0rc1"
ezmd_version: "0.1.0rc1"
schema_version: 1
profile: full
provenance: block
fetched_at: 2026-01-01T00:00:00Z
converted_at: 2026-01-01T00:00:00Z
author: "Transit Desk"
sheets: ["Shifts", "Ratios"]
word_count: 52
tokens: {o200k_base: 318, cl100k_base: 321, claude_approx: 343}
content_hash: "sha256:2f5823c716c8f32d49612e319bb99dcc3f31cfa645a56395948c469502374528"
source_hash: "sha256:689ba8963d052598863106684ee0d6b3c356b79956adb9128d84bb1305acfb9d"
truncated: false
warnings: [formulas_present]
injection_risk: none
---
# Depot Shifts {#doc}

<!-- sheet "Shifts" -->
## 1 Shifts {#sec-1}

**Table 1: Region 1 (A1:D7)**

<table>
<thead>
<tr><th colspan="4">Depot shift plan</th></tr>
<tr><th>Depot</th><th>Shift</th><th>Drivers</th><th>Buses</th></tr>
</thead>
<tbody>
<tr><td rowspan="2">North</td><td>Early</td><td>12</td><td>10</td></tr>
<tr><td>Late</td><td>9</td><td>8</td></tr>
<tr><td rowspan="2">South</td><td>Early</td><td>7</td><td>6</td></tr>
<tr><td>Late</td><td>5</td><td>5</td></tr>
<tr><td>Total</td><td></td><td>33</td><td>29</td></tr>
</tbody>
</table>

**Table 2: Region 2 (A10:B12)**

| Spare buses | Count |
|---|---:|
| North | 2 |
| South | 1 |

<!-- sheet "Ratios" -->
## 2 Ratios {#sec-2}

**Table 3**

| Measure | Value |
|---|---:|
| Drivers per bus | 1.1379310344827587 |
