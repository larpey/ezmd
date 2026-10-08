---
title: "input.json"
source: "input.json"
source_type: data
converter: data.json
converter_version: "0.1.0rc1"
ezmd_version: "0.1.0rc1"
schema_version: 1
profile: full
provenance: block
fetched_at: 2026-01-01T00:00:00Z
converted_at: 2026-01-01T00:00:00Z
word_count: 351
tokens: {o200k_base: 1564, cl100k_base: 1561, claude_approx: 1689}
content_hash: "sha256:3d9b78b7be0540d8f3c32de98480376af3515111a9dc5c73fc8eda754f01a6b7"
source_hash: "sha256:2cd25834f234c1e732dc6af67224bc83632d650316511a5fbedc6da6a2320789"
truncated: false
warnings: []
injection_risk: none
extra: {depth: 7, encoding: utf-8, format: JSON}
---
> Sections: 1 Schema, 2 Data. 9 tables.

## Contents

- [1 Schema](#sec-1)
- [2 Data](#sec-2)
    - [2.1 service](#sec-2-1)
    - [2.2 server](#sec-2-2)
        - [2.2.1 tls](#sec-2-2-1)
    - [2.3 database](#sec-2-3)
        - [2.3.1 primary](#sec-2-3-1)
            - [2.3.1.1 pool](#sec-2-3-1-1)
        - [2.3.2 replicas](#sec-2-3-2)
    - [2.4 features](#sec-2-4)
    - [2.5 limits](#sec-2-5)
        - [2.5.1 a](#sec-2-5-1)
            - [2.5.1.1 b](#sec-2-5-1-1)
                - [2.5.1.1.1 c](#sec-2-5-1-1-1)
    - [2.6 matrix](#sec-2-6)
    - [2.7 empty](#sec-2-7)

# input.json {#doc}

JSON object with 7 keys; nesting depth 7.

## 1 Schema {#sec-1}

**Table 1**
Columns: Path, Types, Count, Null %, Examples

| Path | Types | Count | Null % | Examples |
|---|---|---:|---:|---|
| / | object | 1 | 0 |  |
| /service | object | 1 | 0 |  |
| /service/name | string | 1 | 0 | inventory-api |
| /service/version | string | 1 | 0 | 2.4.1 |
| /service/debug | boolean | 1 | 0 | false |
| /server | object | 1 | 0 |  |
| /server/host | string | 1 | 0 | 0.0.0.0 |
| /server/port | integer | 1 | 0 | 8080 |
| /server/tls | object | 1 | 0 |  |
| /server/tls/enabled | boolean | 1 | 0 | true |
| /server/tls/cert | string | 1 | 0 | /etc/certs/api.pem |
| /server/tls/ciphers | array | 1 | 0 |  |
| /server/tls/ciphers/* | string | 1 | 0 | TLS_AES_128_GCM_SHA256 |
| /database | object | 1 | 0 |  |
| /database/primary | object | 1 | 0 |  |
| /database/primary/url | string | 1 | 0 | file:inventory.db |
| /database/primary/pool | object | 1 | 0 |  |
| /database/primary/pool/min | integer | 1 | 0 | 1 |
| /database/primary/pool/max | integer | 1 | 0 | 8 |
| /database/replicas | array | 1 | 0 |  |
| /database/replicas/* | object | 2 | 0 |  |
| /database/replicas/*/region | string | 2 | 0 | eu-west, us-east |
| /database/replicas/*/lag_ms | integer | 2 | 0 | 120, 340 |
| /features | array | 1 | 0 |  |
| /features/* | string | 3 | 0 | search, export, audit |
| /limits | object | 1 | 0 |  |
| /limits/a | object | 1 | 0 |  |
| /limits/a/b | object | 1 | 0 |  |
| /limits/a/b/c | object | 1 | 0 |  |
| /limits/a/b/c/d | object | 1 | 0 |  |
| /limits/a/b/c/d/e | object | 1 | 0 |  |
| /limits/a/b/c/d/e/f | string | 1 | 0 | deep value |
| /matrix | array | 1 | 0 |  |
| /matrix/* | array | 2 | 0 |  |
| /matrix/\*/\* | integer | 4 | 0 | 1, 2, 3 |
| /empty | object | 1 | 0 |  |

## 2 Data {#sec-2}

### 2.1 service {#sec-2-1}

**Table 2**

| Key | Value |
|---|---|
| name | inventory-api |
| version | 2.4.1 |
| debug | false |

### 2.2 server {#sec-2-2}

**Table 3**

| Key | Value |
|---|---|
| host | 0.0.0.0 |
| port | 8080 |

#### 2.2.1 tls {#sec-2-2-1}

**Table 4**

| Key | Value |
|---|---|
| enabled | true |
| cert | /etc/certs/api.pem |
| ciphers | ["TLS_AES_128_GCM_SHA256"] |

### 2.3 database {#sec-2-3}

#### 2.3.1 primary {#sec-2-3-1}

**Table 5**

| Key | Value |
|---|---|
| url | file:inventory.db |

##### 2.3.1.1 pool {#sec-2-3-1-1}

**Table 6**

| Key | Value |
|---|---|
| min | 1 |
| max | 8 |

#### 2.3.2 replicas {#sec-2-3-2}

**Table 7**

| region | lag_ms |
|---|---:|
| eu-west | 120 |
| us-east | 340 |

### 2.4 features {#sec-2-4}

**Table 8**

| Key | Value |
|---|---|
| features | ["search", "export", "audit"] |

### 2.5 limits {#sec-2-5}

#### 2.5.1 a {#sec-2-5-1}

##### 2.5.1.1 b {#sec-2-5-1-1}

###### 2.5.1.1.1 c {#sec-2-5-1-1-1}

```json
{
  "d": {
    "e": {
      "f": "deep value"
    }
  }
}
```

### 2.6 matrix {#sec-2-6}

```json
[
  [
    1,
    2
  ],
  [
    3,
    4
  ]
]
```

### 2.7 empty {#sec-2-7}

**Table 9**

| Key | Value |
|---|---|
| empty | {} |
