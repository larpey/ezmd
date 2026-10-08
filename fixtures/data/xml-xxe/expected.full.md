---
title: "input.xml"
source: "input.xml"
source_type: data
converter: data.xml
converter_version: "0.0.1"
intomd_version: "0.0.1"
schema_version: 1
profile: full
provenance: block
fetched_at: 2026-01-01T00:00:00Z
converted_at: 2026-01-01T00:00:00Z
word_count: 61
tokens: {o200k_base: 225, cl100k_base: 225, claude_approx: 243}
content_hash: "sha256:36a6fc18b5179e5abc59cfe01abe02726a442e3e9123553dfa41f4303932f173"
source_hash: "sha256:1ae28eb7eef1935d9ca74a6f4b029145b7005e372fa90f5fd329f7112488191a"
truncated: false
warnings: [unsupported_feature]
injection_risk: none
extra: {elements: 5, format: XML, root: order}
---
# input.xml {#doc}

XML document with root element order and 5 elements.

## 1 Structure {#sec-1}

**Table 1**

| Element path | Count | Attributes | Text sample |
|---|---:|---|---|
| /order | 1 |  |  |
| /order/customer | 1 |  |  |
| /order/ref | 1 |  |  |
| /order/memo | 1 |  | & more |
| /order/total | 1 |  | 42 |

## 2 Data {#sec-2}

**Table 2**

| Key | Value |
|---|---|
| customer |  |
| ref |  |
| memo | & more |
| total | 42 |

## 3 Source {#sec-3}

```xml
<?xml version="1.0"?>

<order>
  <customer></customer>
  <ref></ref>
  <memo> &amp; more</memo>
  <total>42</total>
</order>
```
