---
title: "Survey files"
source: "input.eml"
source_type: email
converter: comms.eml
converter_version: "0.1.0rc1"
ezmd_version: "0.1.0rc1"
schema_version: 1
profile: full
provenance: block
created_at: 2024-10-03T09:00:00Z
fetched_at: 2026-01-01T00:00:00Z
converted_at: 2026-01-01T00:00:00Z
author: "Ann Reed"
word_count: 330
tokens: {o200k_base: 1037, cl100k_base: 1044, claude_approx: 1120}
content_hash: "sha256:6f85b5e85f3d763b7e82873ea2d303afec16b260a5216ee90fefb189bbca0cd9"
source_hash: "sha256:b8b344c56e820cc1f28d18f4208485e9a113977db08f00fd0fe9b6ce781f0747"
truncated: false
warnings: [attachment_unconverted, tnef_unparsed, engine_fallback, removed_hidden_elements, textbox_content_relocated, heading_inferred_from_formatting]
injection_risk: none
extra: {attachments: 5, body_alternatives: false, body_source: text, encoding: utf-8, message_id: "<att-1@example.org>"}
---
> Sections: 1 Attachments, 2 attachments/report.pdf: Quarterly cargo throughput, 3 attachments/method.docx: Field Guide to Ponds, 4 attachments/tally.csv. 5 tables.

## Contents

- [1 Attachments](#sec-1)
- [2 attachments/report.pdf: Quarterly cargo throughput](#sec-2)
- [3 attachments/method.docx: Field Guide to Ponds](#sec-3)
    - [3.1 Introduction](#sec-3-1)
    - [3.2 Habitats](#sec-3-2)
        - [3.2.1 Plants](#sec-3-2-1)
            - [3.2.1.1 Survey method](#sec-3-2-1-1)
                - [3.2.1.1.1 Appendix](#sec-3-2-1-1-1)
- [4 attachments/tally.csv](#sec-4)

# Survey files {#doc}

**Table 1: Message headers**

| Header | Value |
|---|---|
| From | Ann Reed \<ann@example.org> |
| To | Bob Stone \<bob@example.org> |
| Date | 2024-10-03T09:00:00+00:00 |
| Subject | Survey files |
| Message-ID | \<att-1@example.org> |

Attached are the survey files: the report, the tally, and the raw sheet.

## 1 Attachments {#sec-1}

**Table 2**

| Name | Type | Size | Status |
|---|---|---|---|
| report.pdf | application/pdf | 1.7 KB | converted (documents.pdfium_text) |
| method.docx | application/vnd.openxmlformats-officedocument.wordprocessingml.document | 5.5 KB | converted (documents.docx) |
| tally.csv | text/csv | 26 B | converted (data.csv) |
| raw.bin | application/octet-stream | 1.0 KB | not converted (unsupported type) |
| winmail.dat | application/ms-tnef | 64 B | not converted (TNEF) |

## 2 attachments/report.pdf: Quarterly cargo throughput {#sec-2}

<!-- page 1 -->

The table lists cargo handled per quarter, in thousand tonnes, by terminal.

**Table 3**

| Terminal | Q1 | Q2 | Q3 |
|---|---:|---:|---:|
| East quay | 120 | 135 | 98 |
| West quay | 88 | 91 | 77 |
| Container yard | 301 | 322 | 290 |
| Bulk berth | 45 | 52 | 49 |

Totals are reported separately in the annual statement.

## 3 attachments/method.docx: Field Guide to Ponds {#sec-3}

### 3.1 Introduction {#sec-3-1}

Ponds are small bodies of still water. The [pond survey portal](https://example.org/ponds) collects records[^1] from volunteers[^2].

**Safety first**

Never sample alone after dark.

Visible text continues here.

[^1]: Records are checked by a county recorder.
[^2]: Volunteers are trained each April.

### 3.2 Habitats {#sec-3-2}

Most ponds have a shallow margin and a deeper centre.

#### 3.2.1 Plants {#sec-3-2-1}

- Reeds
    1. Common reed
    2. Bulrush
- Lilies
    1. White lily
        - Fragrant water lily

##### 3.2.1.1 Survey method {#sec-3-2-1-1}

1. Observe the margin
2. Record each species
3. Report within a week

**Table 4: Reed counts by zone**

<table>
<thead>
<tr><th>Species</th><th>Zone</th><th>Count</th></tr>
</thead>
<tbody>
<tr><td rowspan="2">Common reed</td><td>Shallow margin</td><td>40</td></tr>
<tr><td>Deep margin</td><td>12</td></tr>
<tr><td colspan="2">Both zones combined</td><td>52</td></tr>
</tbody>
</table>

> *A pond is a garden for things that swim.*

Area ratio: $\frac{a}{b}+{x}^{2}$

```
count = sum(zone_counts)
print(count)
```

###### 3.2.1.1.1 Appendix {#sec-3-2-1-1-1}

Data were collected in spring 2025.

## 4 attachments/tally.csv {#sec-4}

**Table 5**

| site | count |
|---|---:|
| east | 14 |
| west | 3 |
