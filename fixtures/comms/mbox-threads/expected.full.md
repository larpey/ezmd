---
title: "input.mbox"
source: "input.mbox"
source_type: email
converter: comms.mbox
converter_version: "0.1.0rc1"
ezmd_version: "0.1.0rc1"
schema_version: 1
profile: full
provenance: block
fetched_at: 2026-01-01T00:00:00Z
converted_at: 2026-01-01T00:00:00Z
word_count: 246
tokens: {o200k_base: 975, cl100k_base: 975, claude_approx: 1053}
content_hash: "sha256:172275ec36aa401a209e31aa16bbbff9e736917e3e48d15917c42ee7540719ca"
source_hash: "sha256:fa255135b298483277b57793afb9741fe8f4f3f7a14f91f3ae6ea4ffdccba426"
truncated: false
warnings: []
injection_risk: none
extra: {merged_splits: 0, messages: 5, threads: 2}
---
> Sections: 1 Field trip, 2 Gear list. 5 tables.

## Contents

- [1 Field trip](#sec-1)
    - [1.1 Ann Reed \<ann@example.org> · 2024-10-07T09:00:00+00:00](#sec-1-1)
    - [1.2 Bob Stone \<bob@example.org> · 2024-10-07T10:00:00+00:00](#sec-1-2)
    - [1.3 Ann Reed \<ann@example.org> · 2024-10-07T11:00:00+00:00](#sec-1-3)
- [2 Gear list](#sec-2)
    - [2.1 Carol Diaz \<carol@example.org> · 2024-10-08T09:00:00+00:00](#sec-2-1)
    - [2.2 Ann Reed \<ann@example.org> · 2024-10-08T12:00:00+00:00](#sec-2-2)

# input.mbox {#doc}

## 1 Field trip {#sec-1}

### 1.1 Ann Reed \<ann@example.org> · 2024-10-07T09:00:00+00:00 {#sec-1-1}

**Table 1: Message headers**

| Header | Value |
|---|---|
| From | Ann Reed \<ann@example.org> |
| To | Bob Stone \<bob@example.org> |
| Date | 2024-10-07T09:00:00+00:00 |
| Subject | Field trip |
| Message-ID | \<t1@example.org> |
| Labels | Inbox, Survey |

Shall we go on Friday?

From the dock, we can reach the east marsh in an hour.

### 1.2 Bob Stone \<bob@example.org> · 2024-10-07T10:00:00+00:00 {#sec-1-2}

**Table 2: Message headers**

| Header | Value |
|---|---|
| From | Bob Stone \<bob@example.org> |
| To | Ann Reed \<ann@example.org> |
| Date | 2024-10-07T10:00:00+00:00 |
| Subject | Re: Field trip |
| Message-ID | \<t2@example.org> |
| In-Reply-To | \<t1@example.org> |
| References | \<t1@example.org> |

Friday works.

> Shall we go on Friday?

### 1.3 Ann Reed \<ann@example.org> · 2024-10-07T11:00:00+00:00 {#sec-1-3}

**Table 3: Message headers**

| Header | Value |
|---|---|
| From | Ann Reed \<ann@example.org> |
| To | Bob Stone \<bob@example.org> |
| Date | 2024-10-07T11:00:00+00:00 |
| Subject | Re: Field trip |
| Message-ID | \<t3@example.org> |
| In-Reply-To | \<t2@example.org> |
| References | \<t1@example.org> \<t2@example.org> |

Great, see you at the dock.

## 2 Gear list {#sec-2}

### 2.1 Carol Diaz \<carol@example.org> · 2024-10-08T09:00:00+00:00 {#sec-2-1}

**Table 4: Message headers**

| Header | Value |
|---|---|
| From | Carol Diaz \<carol@example.org> |
| To | Ann Reed \<ann@example.org> |
| Date | 2024-10-08T09:00:00+00:00 |
| Subject | Gear list |
| Message-ID | \<g1@example.org> |

Bring waders and the spotting scope.

### 2.2 Ann Reed \<ann@example.org> · 2024-10-08T12:00:00+00:00 {#sec-2-2}

**Table 5: Message headers**

| Header | Value |
|---|---|
| From | Ann Reed \<ann@example.org> |
| To | Carol Diaz \<carol@example.org> |
| Date | 2024-10-08T12:00:00+00:00 |
| Subject | Re: Gear list |
| Message-ID | \<g2@example.org> |

Will do. I lost the original thread headers, sorry.
