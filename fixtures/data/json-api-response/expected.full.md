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
word_count: 468
tokens: {o200k_base: 1496, cl100k_base: 1491, claude_approx: 1616}
content_hash: "sha256:64913b6608d7b1590c3c8ac496fc2783f0325ddcb6f1fdffc1220979f1a8b270"
source_hash: "sha256:b9595442dafc3a27c03e238f838d475fd0744260e46a4c4b3eeaf859864b5aea"
truncated: false
warnings: []
injection_risk: none
exports: {tables: ["tables/table-02.csv"]}
extra: {depth: 5, encoding: utf-8, format: JSON}
---
> Sections: 1 Schema, 2 Data. 4 tables.

## Contents

- [1 Schema](#sec-1)
- [2 Data](#sec-2)
    - [2.1 data](#sec-2-1)
    - [2.2 meta](#sec-2-2)
    - [2.3 links](#sec-2-3)

# input.json {#doc}

JSON object with 3 keys; nesting depth 5.

## 1 Schema {#sec-1}

**Table 1**
Columns: Path, Types, Count, Null %, Examples

| Path | Types | Count | Null % | Examples |
|---|---|---:|---:|---|
| / | object | 1 | 0 |  |
| /data | array | 1 | 0 |  |
| /data/* | object | 12 | 0 |  |
| /data/*/id | integer | 12 | 0 | 5000, 5001, 5002 |
| /data/*/name | string | 12 | 0 | Customer A, Customer B, Customer C |
| /data/*/email | string | 12 | 0 | customer0@example.invalid, customer1@example.invalid, customer2@example.invalid |
| /data/*/address | object | 12 | 0 |  |
| /data/*/address/street | string | 12 | 0 | 10 Harbour Road, 11 Harbour Road, 12 Harbour Road |
| /data/*/address/city | string | 12 | 0 | Lisbon, Oslo, Quito |
| /data/*/address/geo | object | 12 | 0 |  |
| /data/*/address/geo/lat | number | 12 | 0 | 38.7, 38.95, 39.2 |
| /data/*/address/geo/lng | number | 12 | 0 | -9.1, -8.6, -8.1 |
| /data/*/orders | integer | 12 | 0 | 0, 1, 2 |
| /data/*/vip | boolean | 12 | 0 | true, false |
| /meta | object | 1 | 0 |  |
| /meta/page | integer | 1 | 0 | 2 |
| /meta/per_page | integer | 1 | 0 | 12 |
| /meta/total | integer | 1 | 0 | 61 |
| /meta/next | string | 1 | 0 | https://api.example.invalid/v1/customer… |
| /links | object | 1 | 0 |  |
| /links/self | string | 1 | 0 | https://api.example.invalid/v1/customer… |

## 2 Data {#sec-2}

### 2.1 data {#sec-2-1}

**Table 2** (9 columns, 12 rows; full data: tables/table-02.csv)
Columns: id, name, email, address.street, address.city, address.geo.lat, address.geo.lng, orders, vip

- id: 5000 | name: Customer A | email: customer0@example.invalid | address.street: 10 Harbour Road | address.city: Lisbon | address.geo.lat: 38.7 | address.geo.lng: -9.1 | orders: 0 | vip: true
- id: 5001 | name: Customer B | email: customer1@example.invalid | address.street: 11 Harbour Road | address.city: Oslo | address.geo.lat: 38.95 | address.geo.lng: -8.6 | orders: 1 | vip: false
- id: 5002 | name: Customer C | email: customer2@example.invalid | address.street: 12 Harbour Road | address.city: Quito | address.geo.lat: 39.2 | address.geo.lng: -8.1 | orders: 2 | vip: false
- id: 5003 | name: Customer D | email: customer3@example.invalid | address.street: 13 Harbour Road | address.city: Nairobi | address.geo.lat: 39.45 | address.geo.lng: -7.6 | orders: 3 | vip: false
- id: 5004 | name: Customer E | email: customer4@example.invalid | address.street: 14 Harbour Road | address.city: Hanoi | address.geo.lat: 39.7 | address.geo.lng: -7.1 | orders: 0 | vip: false
- id: 5005 | name: Customer F | email: customer5@example.invalid | address.street: 15 Harbour Road | address.city: Perth | address.geo.lat: 39.95 | address.geo.lng: -6.6 | orders: 1 | vip: true
- id: 5006 | name: Customer G | email: customer6@example.invalid | address.street: 16 Harbour Road | address.city: Tromso | address.geo.lat: 40.2 | address.geo.lng: -6.1 | orders: 2 | vip: false
- id: 5007 | name: Customer H | email: customer7@example.invalid | address.street: 17 Harbour Road | address.city: Cusco | address.geo.lat: 40.45 | address.geo.lng: -5.6 | orders: 3 | vip: false
- id: 5008 | name: Customer I | email: customer8@example.invalid | address.street: 18 Harbour Road | address.city: Accra | address.geo.lat: 40.7 | address.geo.lng: -5.1 | orders: 0 | vip: false
- id: 5009 | name: Customer J | email: customer9@example.invalid | address.street: 19 Harbour Road | address.city: Riga | address.geo.lat: 40.95 | address.geo.lng: -4.6 | orders: 1 | vip: false
- id: 5010 | name: Customer K | email: customer10@example.invalid | address.street: 20 Harbour Road | address.city: Lisbon | address.geo.lat: 41.2 | address.geo.lng: -4.1 | orders: 2 | vip: true
- id: 5011 | name: Customer L | email: customer11@example.invalid | address.street: 21 Harbour Road | address.city: Oslo | address.geo.lat: 41.45 | address.geo.lng: -3.6 | orders: 3 | vip: false

### 2.2 meta {#sec-2-2}

**Table 3**

| Key | Value |
|---|---|
| page | 2 |
| per_page | 12 |
| total | 61 |
| next | https://api.example.invalid/v1/customers?page=3 |

### 2.3 links {#sec-2-3}

**Table 4**

| Key | Value |
|---|---|
| self | https://api.example.invalid/v1/customers?page=2 |
