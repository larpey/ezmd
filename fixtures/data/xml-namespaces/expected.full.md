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
word_count: 289
tokens: {o200k_base: 1181, cl100k_base: 1175, claude_approx: 1275}
content_hash: "sha256:74a68f5c02760e7169782503dabe5c03a6988b5dbe58f0a6bfd285b5fc1a6a23"
source_hash: "sha256:92f640fa7bd1415edd5b4ec8aec4f317b306badc83a873d25a4c094f35815617"
truncated: false
warnings: []
injection_risk: none
extra: {elements: 29, format: XML, root: catalog}
---
> Sections: 1 Structure, 2 Data, 3 Source. 7 tables.

## Contents

- [1 Structure](#sec-1)
- [2 Data](#sec-2)
    - [2.1 book](#sec-2-1)
    - [2.2 supplier](#sec-2-2)
        - [2.2.1 supplier 1](#sec-2-2-1)
        - [2.2.2 supplier 2](#sec-2-2-2)
    - [2.3 notes](#sec-2-3)
- [3 Source](#sec-3)

# input.xml {#doc}

XML document with root element catalog and 29 elements; 2 namespace(s).

**Table 1**

| Prefix | Namespace URI |
|---|---|
| (default) | urn:example:catalog |
| dc | http://purl.org/dc/elements/1.1/ |

## 1 Structure {#sec-1}

**Table 2**

| Element path | Count | Attributes | Text sample |
|---|---:|---|---|
| /catalog | 1 | @version |  |
| /catalog/dc:title | 1 |  | Spring parts catalog |
| /catalog/book | 6 | @id @lang |  |
| /catalog/book/dc:creator | 6 |  | R. Field |
| /catalog/book/price | 6 | @currency | 12.50 |
| /catalog/supplier | 2 | @code |  |
| /catalog/supplier/name | 2 |  | North Mill |
| /catalog/supplier/city | 2 |  | Oslo |
| /catalog/notes | 1 |  |  |
| /catalog/notes/note | 2 |  | Prices exclude VAT. |

## 2 Data {#sec-2}

**Table 3**

| Key | Value |
|---|---|
| @version | 2 |
| dc:title | Spring parts catalog |

### 2.1 book {#sec-2-1}

**Table 4**
Columns: @id, @lang, dc:creator, price.@currency, price.#text

| @id | @lang | dc:creator | price.@currency | price.#text |
|---|---|---|---|---:|
| b1 | en | R. Field | EUR | 12.50 |
| b2 | pt | M. Costa | EUR | 9.00 |
| b3 | no | K. Berg | NOK | 110 |
| b4 | en | A. Moss | GBP | 7.25 |
| b5 | es | L. Vega | EUR | 15.00 |
| b6 | lv | I. Ozola | EUR | 11.40 |

### 2.2 supplier {#sec-2-2}

#### 2.2.1 supplier 1 {#sec-2-2-1}

**Table 5**

| Key | Value |
|---|---|
| @code | S1 |
| name | North Mill |
| city | Oslo |

#### 2.2.2 supplier 2 {#sec-2-2-2}

**Table 6**

| Key | Value |
|---|---|
| @code | S2 |
| name | Harbor Works |
| city | Lisbon |

### 2.3 notes {#sec-2-3}

**Table 7**

| Key | Value |
|---|---|
| note | ["Prices exclude VAT.", "Stock is updated nightly."] |

## 3 Source {#sec-3}

```xml
<?xml version="1.0" encoding="UTF-8"?>
<catalog xmlns="urn:example:catalog" xmlns:dc="http://purl.org/dc/elements/1.1/" version="2">
  <dc:title>Spring parts catalog</dc:title>
  <book id="b1" lang="en">
    <dc:creator>R. Field</dc:creator>
    <price currency="EUR">12.50</price>
  </book>
  <book id="b2" lang="pt">
    <dc:creator>M. Costa</dc:creator>
    <price currency="EUR">9.00</price>
  </book>
  <book id="b3" lang="no">
    <dc:creator>K. Berg</dc:creator>
    <price currency="NOK">110</price>
  </book>
  <book id="b4" lang="en">
    <dc:creator>A. Moss</dc:creator>
    <price currency="GBP">7.25</price>
  </book>
  <book id="b5" lang="es">
    <dc:creator>L. Vega</dc:creator>
    <price currency="EUR">15.00</price>
  </book>
  <book id="b6" lang="lv">
    <dc:creator>I. Ozola</dc:creator>
    <price currency="EUR">11.40</price>
  </book>
  <supplier code="S1"><name>North Mill</name><city>Oslo</city></supplier>
  <supplier code="S2"><name>Harbor Works</name><city>Lisbon</city></supplier>
  <notes>
    <note>Prices exclude VAT.</note>
    <note>Stock is updated nightly.</note>
  </notes>
</catalog>
```
