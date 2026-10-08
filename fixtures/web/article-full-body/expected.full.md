---
title: "Tide Tables for Small Harbors"
source: "https://harbor.example.test/posts/tide-tables"
source_type: web
converter: web.html_raw
converter_version: "0.1.0rc1"
ezmd_version: "0.1.0rc1"
schema_version: 1
profile: full
provenance: block
created_at: 2026-03-14T08:00:00Z
modified_at: 2026-03-15T10:30:00Z
fetched_at: 2026-01-01T00:00:00Z
converted_at: 2026-01-01T00:00:00Z
author: "Mara Quill"
language: en
word_count: 293
tokens: {o200k_base: 506, cl100k_base: 509, claude_approx: 546}
content_hash: "sha256:54f89c2cd1acad6f16e87ab36b0fcbd6fcbaae6c52d3aa4b93da6dabd44300f9"
source_hash: "sha256:27137cccb340e1134acb0b2c44d07eee4d29406a89dd595b1e9c83a23945a05b"
truncated: false
warnings: [readability_fallback_full_body]
description: "How to read a tide table and plan a launch around slack water."
tags: ["tides", "boating", "planning"]
injection_risk: none
extra: {encoding: utf-8, readability_ratio: 1.0}
---
# Tide Tables for Small Harbors {#doc}

By Mara Quill, March 14, 2026

A tide table tells you when the water is high, when it is low, and how far it will rise or fall. For a small harbor with a shallow entrance, those numbers decide whether you can launch at all. This guide walks through reading a table and turning it into a launch window.

## 1 Reading the columns {#sec-1}

Most tables list the date, the time of each high and low, and the height relative to [chart datum](https://harbor.example.test/glossary#chart-datum). Heights can be negative when the water drops below the datum, which matters on *spring tides* after a full or new moon.

- Time of high and low water, in local time
- Height in meters above chart datum
    - Positive values: above datum
    - Negative values: below datum
- Tidal range, the difference between consecutive high and low

## 2 Planning a launch {#sec-2}

The rule of twelfths estimates how much the water moves in each hour of a six-hour tide. In the first hour it moves one twelfth of the range, then two, three, three, two, and one.

1. Find the low water time before your planned launch.
2. Compute the range from the neighbouring high water.
3. Add the twelfths hour by hour until the depth clears your keel.

```python
def depth_after(hours, low, rng):
    twelfths = [1, 2, 3, 3, 2, 1]
    return low + rng * sum(twelfths[:hours]) / 12
```

![A tide curve over twelve hours](https://harbor.example.test/img/tide-curve.png)
Figure 1: Water height over one tidal cycle.
<!-- image: https://harbor.example.test/img/tide-curve.png -->

> Slack water is short. Be ready before it arrives.

Check the harbor notice board for local corrections, and read our [guide to entrance bars](https://harbor.example.test/posts/entrance-bars) before your first season.

## 3 Comments {#sec-3}

Great guide, the twelfths table saved my morning.

Could you cover tidal streams next?

[Share](https://share.example.test/?u=1) [Post](https://social.example.test/)
