---
title: "input.json"
source: "input.json"
source_type: data
converter: data.json
converter_version: "0.0.1"
intomd_version: "0.0.1"
schema_version: 1
profile: full
provenance: block
fetched_at: 2026-01-01T00:00:00Z
converted_at: 2026-01-01T00:00:00Z
word_count: 374
tokens: {o200k_base: 1759, cl100k_base: 1775, claude_approx: 1900}
content_hash: "sha256:2b1f16af4ad367a66b0528a9ddb09cd2d84ca57c03ca280276c48bb9cbb03da7"
source_hash: "sha256:3e5a7d4f8681a0eb6c46ec670ac1c47346e5adda4b63732e7713bbf54be89bbe"
truncated: true
warnings: [depth_truncated, rows_sampled]
injection_risk: none
extra: {depth: 17, depth_cap: 12, encoding: utf-8, format: JSON}
---
> Sections: 1 Schema, 2 Data. 5 tables.

## Contents

- [1 Schema](#sec-1)
- [2 Data](#sec-2)
    - [2.1 unicode_keys](#sec-2-1)
    - [2.2 Other keys](#sec-2-2)
    - [2.3 chain](#sec-2-3)
        - [2.3.1 n15](#sec-2-3-1)
            - [2.3.1.1 n14](#sec-2-3-1-1)
                - [2.3.1.1.1 n13](#sec-2-3-1-1-1)
    - [2.4 rows](#sec-2-4)

# input.json {#doc}

JSON object with 6 keys; nesting depth 17 (shown to 12 levels).

## 1 Schema {#sec-1}

**Table 1**
Columns: Path, Types, Count, Null %, Examples

| Path | Types | Count | Null % | Examples |
|---|---|---:|---:|---|
| / | object | 1 | 0 |  |
| /title | string | 1 | 0 | Precision and depth |
| /unicode_keys | object | 1 | 0 |  |
| /unicode_keys/café | integer | 1 | 0 | 1 |
| /unicode_keys/東京 | integer | 1 | 0 | 2 |
| /unicode_keys/naïve | integer | 1 | 0 | 3 |
| /unicode_keys/🚀launch | integer | 1 | 0 | 4 |
| /big | integer | 1 | 0 | 123456789012345678901234567890 |
| /ratio | number | 1 | 0 | 1.10 |
| /chain | object | 1 | 0 |  |
| /chain/n15 | object | 1 | 0 |  |
| /chain/n15/n14 | object | 1 | 0 |  |
| /chain/n15/n14/n13 | object | 1 | 0 |  |
| /chain/n15/n14/n13/n12 | object | 1 | 0 |  |
| /chain/n15/n14/n13/n12/n11 | object | 1 | 0 |  |
| /chain/n15/n14/n13/n12/n11/n10 | object | 1 | 0 |  |
| /chain/n15/n14/n13/n12/n11/n10/n9 | object | 1 | 0 |  |
| /chain/n15/n14/n13/n12/n11/n10/n9/n8 | object | 1 | 0 |  |
| /chain/n15/n14/n13/n12/n11/n10/n9/n8/n7 | object | 1 | 0 |  |
| /chain/n15/n14/n13/n12/n11/n10/n9/n8/n7/n6 | object | 1 | 0 |  |
| /chain/n15/n14/n13/n12/n11/n10/n9/n8/n7/n6/n5 | object (truncated) | 1 | 0 | … |
| /rows | array | 1 | 0 |  |
| /rows/* | object | 60 | 0 |  |
| /rows/*/seq | integer | 60 | 0 | 98765432109876543210, 98765432109876543211, 98765432109876543212 |
| /rows/*/label | string | 60 | 0 | café 0, 東京 1, naïve 2 |
| /rows/*/price | number | 60 | 0 | 0.10, 1.10, 2.10 |
| /rows/*/tiny | number | 60 | 0 | 0.1e-7 |
| /rows/*/neg_zero | number | 60 | 0 | -0.0 |

## 2 Data {#sec-2}

**Table 2**

| Key | Value |
|---|---|
| title | Precision and depth |

### 2.1 unicode_keys {#sec-2-1}

**Table 3**

| Key | Value |
|---|---|
| café | 1 |
| 東京 | 2 |
| naïve | 3 |
| 🚀launch | 4 |

### 2.2 Other keys {#sec-2-2}

**Table 4**

| Key | Value |
|---|---|
| big | 123456789012345678901234567890 |
| ratio | 1.10 |

### 2.3 chain {#sec-2-3}

#### 2.3.1 n15 {#sec-2-3-1}

##### 2.3.1.1 n14 {#sec-2-3-1-1}

###### 2.3.1.1.1 n13 {#sec-2-3-1-1-1}

```json
{
  "n12": {
    "n11": {
      "n10": {
        "n9": {
          "n8": {
            "n7": {
              "n6": {
                "n5": "…"
              }
            }
          }
        }
      }
    }
  }
}
```

### 2.4 rows {#sec-2-4}

**Table 5**
Columns: seq, label, price, tiny, neg_zero

| seq | label | price | tiny | neg_zero |
|---:|---|---:|---:|---:|
| 98765432109876543210 | café 0 | 0.10 | 0.1e-7 | -0.0 |
| 98765432109876543211 | 東京 1 | 1.10 | 0.1e-7 | -0.0 |
| 98765432109876543212 | naïve 2 | 2.10 | 0.1e-7 | -0.0 |
| 98765432109876543213 | 🚀launch 3 | 3.10 | 0.1e-7 | -0.0 |
| 98765432109876543214 | café 4 | 4.10 | 0.1e-7 | -0.0 |
| 98765432109876543215 | 東京 5 | 5.10 | 0.1e-7 | -0.0 |
| 98765432109876543216 | naïve 6 | 6.10 | 0.1e-7 | -0.0 |
| 98765432109876543217 | 🚀launch 7 | 0.10 | 0.1e-7 | -0.0 |
| 98765432109876543218 | café 8 | 1.10 | 0.1e-7 | -0.0 |
| 98765432109876543219 | 東京 9 | 2.10 | 0.1e-7 | -0.0 |
| 98765432109876543265 | 🚀launch 55 | 6.10 | 0.1e-7 | -0.0 |
| 98765432109876543266 | café 56 | 0.10 | 0.1e-7 | -0.0 |
| 98765432109876543267 | 東京 57 | 1.10 | 0.1e-7 | -0.0 |
| 98765432109876543268 | naïve 58 | 2.10 | 0.1e-7 | -0.0 |
| 98765432109876543269 | 🚀launch 59 | 3.10 | 0.1e-7 | -0.0 |

(Sample: the first 10 and the last 5 of 60 rows; 45 rows omitted after row 10.)
