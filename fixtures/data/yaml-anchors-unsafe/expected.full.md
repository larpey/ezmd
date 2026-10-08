---
title: "input.yaml"
source: "input.yaml"
source_type: data
converter: data.yaml
converter_version: "0.1.0rc1"
ezmd_version: "0.1.0rc1"
schema_version: 1
profile: full
provenance: block
fetched_at: 2026-01-01T00:00:00Z
converted_at: 2026-01-01T00:00:00Z
word_count: 279
tokens: {o200k_base: 1022, cl100k_base: 1021, claude_approx: 1104}
content_hash: "sha256:4ddc50e9c34d7e87389a4fdbc72f5765b39d96b4555cb42a0a6cc1abe43fc347"
source_hash: "sha256:b665cc722c0a83f8a441484598256590d0487c316b9b1de52e216f5cbaacfab9"
truncated: false
warnings: [yaml_unsafe_tags]
injection_risk: none
extra: {anchors_expanded: true, documents: 1, encoding: utf-8, format: YAML}
---
> Sections: 1 Schema, 2 Data, 3 Source. 6 tables.

## Contents

- [1 Schema](#sec-1)
- [2 Data](#sec-2)
    - [2.1 defaults](#sec-2-1)
    - [2.2 staging](#sec-2-2)
    - [2.3 production](#sec-2-3)
    - [2.4 hooks](#sec-2-4)
    - [2.5 Other keys](#sec-2-5)
- [3 Source](#sec-3)

# input.yaml {#doc}

YAML object with 6 keys; nesting depth 3.

## 1 Schema {#sec-1}

**Table 1**
Columns: Path, Types, Count, Null %, Examples

| Path | Types | Count | Null % | Examples |
|---|---|---:|---:|---|
| / | object | 1 | 0 |  |
| /defaults | object | 1 | 0 |  |
| /defaults/retries | integer | 1 | 0 | 3 |
| /defaults/timeout_s | number | 1 | 0 | 1.50 |
| /defaults/region | string | 1 | 0 | eu-west |
| /staging | object | 1 | 0 |  |
| /staging/retries | integer | 1 | 0 | 3 |
| /staging/timeout_s | number | 1 | 0 | 1.50 |
| /staging/region | string | 1 | 0 | eu-west |
| /staging/replicas | integer | 1 | 0 | 2 |
| /production | object | 1 | 0 |  |
| /production/retries | integer | 1 | 0 | 3 |
| /production/timeout_s | number | 1 | 0 | 1.50 |
| /production/region | string | 1 | 0 | us-east |
| /production/replicas | integer | 1 | 0 | 6 |
| /hooks | array | 1 | 0 |  |
| /hooks/* | object | 2 | 0 |  |
| /hooks/*/name | string | 2 | 0 | notify, audit |
| /hooks/*/url | string | 2 | 0 | https://hooks.example.invalid/notify, https://hooks.example.invalid/audit |
| /payload | string | 1 | 0 | !!python/object/apply:os.system ["echo … |
| /released | string | 1 | 0 | 2026-04-01 |

## 2 Data {#sec-2}

### 2.1 defaults {#sec-2-1}

**Table 2**

| Key | Value |
|---|---|
| retries | 3 |
| timeout_s | 1.50 |
| region | eu-west |

### 2.2 staging {#sec-2-2}

**Table 3**

| Key | Value |
|---|---|
| retries | 3 |
| timeout_s | 1.50 |
| region | eu-west |
| replicas | 2 |

### 2.3 production {#sec-2-3}

**Table 4**

| Key | Value |
|---|---|
| retries | 3 |
| timeout_s | 1.50 |
| region | us-east |
| replicas | 6 |

### 2.4 hooks {#sec-2-4}

**Table 5**

| name | url |
|---|---|
| notify | https://hooks.example.invalid/notify |
| audit | https://hooks.example.invalid/audit |

### 2.5 Other keys {#sec-2-5}

**Table 6**

| Key | Value |
|---|---|
| payload | !!python/object/apply:os.system ["echo pwned"] |
| released | 2026-04-01 |

## 3 Source {#sec-3}

```yaml
# Deployment settings for the demo service.
defaults: &defaults
  retries: 3
  timeout_s: 1.50
  region: eu-west
staging:
  <<: *defaults
  replicas: 2
production:
  <<: *defaults
  replicas: 6
  region: us-east
hooks:
  - name: notify
    url: https://hooks.example.invalid/notify
  - name: audit
    url: https://hooks.example.invalid/audit
# The next value must never be constructed as a Python object.
payload: !!python/object/apply:os.system ["echo pwned"]
released: 2026-04-01
```
