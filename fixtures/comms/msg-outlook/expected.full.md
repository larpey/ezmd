---
title: "Quarterly plan"
source: "input.msg"
source_type: email
converter: comms.msg
converter_version: "0.0.1"
intomd_version: "0.0.1"
schema_version: 1
profile: full
provenance: block
created_at: 2024-10-01T09:00:00Z
fetched_at: 2026-01-01T00:00:00Z
converted_at: 2026-01-01T00:00:00Z
author: "Ann Reed"
word_count: 123
tokens: {o200k_base: 384, cl100k_base: 384, claude_approx: 415}
content_hash: "sha256:1cd10bcb04ec1387d9ef6244a18c433e122fbf880728c3a0ce3011fe7dbbc636"
source_hash: "sha256:9445b531fc79fd7938996c02bac0d332c69454157d44be14a62b369606e45266"
truncated: false
warnings: []
injection_risk: none
extra: {attachments: 3, body_alternatives: false, body_source: html, encoding: utf-8, engine: "olefile 0.47", message_id: "<plan-1@example.org>"}
---
# Quarterly plan {#doc}

**Table 1: Message headers**

| Header | Value |
|---|---|
| From | Ann Reed \<ann@example.org> |
| To | Bob Stone \<bob@example.org> |
| Cc | Field Office \<office@example.org> |
| Date | 2024-10-01T09:00:00+00:00 |
| Subject | Quarterly plan |
| Message-ID | \<plan-1@example.org> |
| List-Id | Survey plans <plans.example.org> |

Hello Bob,

The **quarterly plan** is attached.

- Count herons in March
- Count egrets in June

## 1 Attachments {#sec-1}

**Table 2**

| Name | Type | Size | Status |
|---|---|---|---|
| plan.csv | text/csv | 26 B | converted (data.csv) |
| notes.txt | text/plain | 32 B | converted (text.plain) |
| Boat schedule.msg | application/vnd.ms-outlook | 214 B | converted (comms.msg) |

## 2 attachments/plan.csv {#sec-2}

**Table 3**

| site | count |
|---|---:|
| east | 14 |
| west | 3 |

## 3 attachments/notes.txt {#sec-3}

Bring waders.\
Meet at the dock.

## 4 attachments/Boat schedule.msg: Boat schedule {#sec-4}

**Table 4: Message headers**

| Header | Value |
|---|---|
| From | Dock Office \<dock@example.org> |
| To | Ann Reed \<ann@example.org> |
| Date | 2024-09-30T16:00:00+00:00 |
| Subject | Boat schedule |

Boat at 7am.
