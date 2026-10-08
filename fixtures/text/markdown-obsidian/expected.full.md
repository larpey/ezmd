---
title: "Tide Station Notes"
source: "input.md"
source_type: markdown
converter: text.markdown_passthrough
converter_version: "0.1.0rc1"
ezmd_version: "0.1.0rc1"
schema_version: 1
profile: full
provenance: block
fetched_at: 2026-01-01T00:00:00Z
converted_at: 2026-01-01T00:00:00Z
word_count: 113
tokens: {o200k_base: 284, cl100k_base: 286, claude_approx: 307}
content_hash: "sha256:09ee2c34968ef56a4845196f15f0a00fc1eb8d257570162dd7d1ab579e10e2c4"
source_hash: "sha256:73da6e4b1197cb2249b09b4a492f30d2d65287ad1f063f1b7543e794f938229e"
truncated: false
warnings: []
injection_risk: none
extra: {encoding: utf-8, front_matter: "title: Tide Station Notes\ntags: [harbour, tides]\naliases:\n  - tide notes\ncreated: 2024-05-02"}
---
# Tide Station Notes {#doc}

Readings are copied from [[Tide Log 2024]] and the [[Station Map|map of the stations]].

![[station-photo.png]]

> **Warning:** Calibration due
>
> The north gauge drifts by 2 cm a month. See [[Calibration#Procedure]].

> **Note:** Folded note
>
> Folded callouts start collapsed in Obsidian.

## 1 Tasks {#sec-1}

- [x] Replace the gauge battery
- [ ] Re-level the staff board
    - [ ] Borrow the dumpy level

## 2 Readings {#sec-2}

**Table 1**

| Station | High (m) | Low (m) |
|---|---:|---:|
| North | 4.2 | 0.6 |
| South | 3.9 | 0.8 |

The south gauge sits in a sheltered inlet.[^1]

```python
def range_m(high, low):
    return round(high - low, 2)
```

```html
<details>
<summary>Raw export</summary>
```

north,4.2,0.6

```html
</details>
```

Tagged #tides and #harbour/maintenance.

[^1]: The inlet halves the wave height compared with the open shore.
