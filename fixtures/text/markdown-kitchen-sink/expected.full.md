---
title: "Kitchen Sink"
source: "input.md"
source_type: markdown
converter: text.markdown_passthrough
converter_version: "0.0.1"
intomd_version: "0.0.1"
schema_version: 1
profile: full
provenance: block
fetched_at: 2026-01-01T00:00:00Z
converted_at: 2026-01-01T00:00:00Z
author: "intomd fixtures"
word_count: 160
tokens: {o200k_base: 426, cl100k_base: 425, claude_approx: 460}
content_hash: "sha256:fd8be2c3ae23327454ad1d09e2fb30e74fff96d856fef1789a4545c1cea1bae4"
source_hash: "sha256:186a2ac6addb6269e4049da85f4f3cd2787039c3ffeaae465297cf0eb2de2559"
truncated: false
warnings: []
injection_risk: none
extra: {encoding: utf-8, front_matter: "title: Kitchen Sink\nauthor: intomd fixtures"}
---
> Sections: 1 Lists, 2 Code, 3 Quote, 4 Table, 5 Image, 6 Footnotes. 1 table, 1 figure.

## Contents

- [1 Lists](#sec-1)
- [2 Code](#sec-2)
- [3 Quote](#sec-3)
- [4 Table](#sec-4)
- [5 Image](#sec-5)
- [6 Footnotes](#sec-6)

# Kitchen Sink {#doc}

An opening paragraph with **bold**, *italic*, `inline code`, ~~struck~~ text and a [link](https://example.org/docs). It continues on a second line.

## 1 Lists {#sec-1}

- First item
- Second item
    - Nested item A
    - Nested item B
        1. Deep ordered one
        2. Deep ordered two
- Third item

3. Ordered starting at three
4. Ordered four

- [x] Done task
- [ ] Open task

## 2 Code {#sec-2}

```python
def greet(name: str) -> str:
    return f"Hello, {name}"
```

## 3 Quote {#sec-3}

> Simplicity is prerequisite for reliability.
>
> A second quoted paragraph.

## 4 Table {#sec-4}

**Table 1**

| Region | Q1 | Q2 |
|---|---:|---:|
| North | 120 | 135 |
| South | 98 | 101 |

## 5 Image {#sec-5}

![A small diagram](images/diagram.png "Figure 1")
<!-- image: images/diagram.png -->

## 6 Footnotes {#sec-6}

A claim that needs a source.[^1] And another one.[^2]

```html
<div class="aside">Raw HTML block.</div>
```

[^1]: The first footnote.
[^2]: A named footnote with *emphasis*.
