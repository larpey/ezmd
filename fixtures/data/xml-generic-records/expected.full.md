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
word_count: 217
tokens: {o200k_base: 935, cl100k_base: 944, claude_approx: 1010}
content_hash: "sha256:89bc4e5659caccec3250b07236bc8cd8a7dda47e93fe610537a7938e8e0ede3e"
source_hash: "sha256:05906e3ec9dffb2907b7612e6040ae215f967faa13202ca4eb3712fb0b6987de"
truncated: false
warnings: []
injection_risk: none
extra: {elements: 42, format: XML, root: people}
---
# input.xml {#doc}

XML document with root element people and 42 elements.

## 1 Structure {#sec-1}

**Table 1**

| Element path | Count | Attributes | Text sample |
|---|---:|---|---|
| /people | 1 | @source @count |  |
| /people/person | 8 | @id |  |
| /people/person/name | 8 |  | Ada Lovelace |
| /people/person/born | 8 |  | 1815-12-10 |
| /people/person/city | 8 |  | London |
| /people/person/field | 8 |  | mathematics |
| /people/person/note | 1 |  | Founded modern nursing statistics & the… |

## 2 Data {#sec-2}

**Table 2**

| Key | Value |
|---|---|
| @source | self-generated |
| @count | 8 |

### 2.1 person {#sec-2-1}

**Table 3**
Columns: @id, name, born, city, field, note

| @id | name | born | city | field | note |
|---|---|---|---|---|---|
| p1 | Ada Lovelace | 1815-12-10 | London | mathematics |  |
| p2 | Mary Somerville | 1780-12-26 | Jedburgh | astronomy |  |
| p3 | Sofia Kovalevskaya | 1850-01-15 | Moscow | analysis |  |
| p4 | Emmy Noether | 1882-03-23 | Erlangen | algebra |  |
| p5 | Hypatia |  | Alexandria | geometry |  |
| p6 | Caroline Herschel | 1750-03-16 | Hanover | astronomy |  |
| p7 | Grace Chisholm Young | 1868-03-15 | Haslemere | analysis |  |
| p8 | Florence Nightingale | 1820-05-12 | Florence | statistics | Founded modern nursing statistics & the polar area chart. |

## 3 Source {#sec-3}

```xml
<?xml version="1.0" encoding="UTF-8"?>
<people source="self-generated" count="8">
  <person id="p1">
    <name>Ada Lovelace</name>
    <born>1815-12-10</born>
    <city>London</city>
    <field>mathematics</field>
  </person>
  <person id="p2">
    <name>Mary Somerville</name>
    <born>1780-12-26</born>
    <city>Jedburgh</city>
    <field>astronomy</field>
  </person>
  <person id="p3">
    <name>Sofia Kovalevskaya</name>
    <born>1850-01-15</born>
    <city>Moscow</city>
    <field>analysis</field>
  </person>
  <person id="p4">
    <name>Emmy Noether</name>
    <born>1882-03-23</born>
    <city>Erlangen</city>
    <field>algebra</field>
  </person>
  <person id="p5">
    <name>Hypatia</name>
    <born/>
    <city>Alexandria</city>
    <field>geometry</field>
  </person>
  <person id="p6">
    <name>Caroline Herschel</name>
    <born>1750-03-16</born>
    <city>Hanover</city>
    <field>astronomy</field>
  </person>
  <person id="p7">
    <name>Grace Chisholm Young</name>
    <born>1868-03-15</born>
    <city>Haslemere</city>
    <field>analysis</field>
  </person>
  <person id="p8">
    <name>Florence Nightingale</name>
    <born>1820-05-12</born>
    <city>Florence</city>
    <field>statistics</field>
    <note>Founded modern nursing statistics &amp; the polar area chart.</note>
  </person>
</people>
```
