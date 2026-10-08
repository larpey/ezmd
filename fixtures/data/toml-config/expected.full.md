---
title: "input.toml"
source: "input.toml"
source_type: data
converter: data.toml
converter_version: "0.1.0rc1"
ezmd_version: "0.1.0rc1"
schema_version: 1
profile: full
provenance: block
fetched_at: 2026-01-01T00:00:00Z
converted_at: 2026-01-01T00:00:00Z
word_count: 120
tokens: {o200k_base: 413, cl100k_base: 413, claude_approx: 446}
content_hash: "sha256:23a8f66815f5995f6de9cc8b4a01fc7291df8b00c0018b18a86f924713073ca4"
source_hash: "sha256:bedd90a56b47d88b14c75b0299a201116733a895461a88e56de6f5feadbecf86"
truncated: false
warnings: []
injection_risk: none
extra: {depth: 4, encoding: utf-8, format: TOML}
---
> Sections: 1 owner, 2 sync, 3 targets, 4 Source. 4 tables.

## Contents

- [1 owner](#sec-1)
- [2 sync](#sec-2)
    - [2.1 schedule](#sec-2-1)
- [3 targets](#sec-3)
- [4 Source](#sec-4)

# input.toml {#doc}

TOML object with 8 keys; nesting depth 4.

**Table 1**

| Key | Value |
|---|---|
| title | Warehouse sync |
| version | 3 |
| ratio | 1.10 |
| enabled | true |
| started | 2026-02-03T04:05:06Z |

## 1 owner {#sec-1}

**Table 2**

| Key | Value |
|---|---|
| name | Operations |
| email | ops@example.invalid |

## 2 sync {#sec-2}

### 2.1 schedule {#sec-2-1}

**Table 3**

| Key | Value |
|---|---|
| cron | */15 * * * * |
| zones | ["eu", "us"] |

## 3 targets {#sec-3}

**Table 4**

| name | weight |
|---|---:|
| primary | 70 |
| backup | 30 |

## 4 Source {#sec-4}

```toml
title = "Warehouse sync"
version = 3
ratio = 1.10
enabled = true
started = 2026-02-03T04:05:06Z

[owner]
name = "Operations"
email = "ops@example.invalid"

[sync.schedule]
cron = "*/15 * * * *"
zones = ["eu", "us"]

[[targets]]
name = "primary"
weight = 70

[[targets]]
name = "backup"
weight = 30
```
