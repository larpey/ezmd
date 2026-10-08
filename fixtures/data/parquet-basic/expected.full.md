---
title: "input.parquet"
source: "input.parquet"
source_type: data
converter: data.parquet
converter_version: "0.1.0rc1"
ezmd_version: "0.1.0rc1"
schema_version: 1
profile: full
provenance: block
fetched_at: 2026-01-01T00:00:00Z
converted_at: 2026-01-01T00:00:00Z
word_count: 1223
tokens: {o200k_base: 5388, cl100k_base: 5438, claude_approx: 5819}
content_hash: "sha256:6be6121d191d7bdbe9496376278a23fccd205f2b3a490319bb28bbe72b419367"
source_hash: "sha256:a60ca6994e7020baa96306ac3ee27ceb60b7ea477eb8ccb867fd1f520850272e"
truncated: true
warnings: [rows_sampled]
injection_risk: none
exports: {tables: ["tables/table-03.csv"]}
extra: {columns: 6, created_by: "parquet-cpp-arrow version 25.0.1", format: Parquet, row_groups: 3, rows: 150}
---
> Sections: 1 Schema, 2 Statistics, 3 Sample rows. 3 tables.

## Contents

- [1 Schema](#sec-1)
- [2 Statistics](#sec-2)
- [3 Sample rows](#sec-3)

# input.parquet {#doc}

Parquet file with 150 rows, 6 columns and 3 row group(s); compression SNAPPY; written by parquet-cpp-arrow version 25.0.1.

## 1 Schema {#sec-1}

**Table 1**

| Column | Type | Nullable |
|---|---|---|
| id | int64 | yes |
| city | string | yes |
| amount | decimal128(10, 2) | yes |
| seen | timestamp[ms, tz=UTC] | yes |
| dims | struct<w: int64, h: int64> | yes |
| flag | bool | yes |

## 2 Statistics {#sec-2}

**Table 2**

| Column | Min | Max | Nulls |
|---|---|---|---:|
| id | 1 | 150 | 0 |
| city | Accra | Tromso | 0 |
| amount | 0.00 | 149.49 | 0 |
| seen | 2026-01-01T00:00:00Z | 2026-01-07T05:00:00Z | 0 |
| dims.w | 0 | 4 | 0 |
| dims.h | 0 | 2 | 0 |
| flag | false | true | 15 |

## 3 Sample rows {#sec-3}

**Table 3** (tables/table-03.csv)
Columns: id, city, amount, seen, dims, flag

| id | city | amount | seen | dims | flag |
|---:|---|---:|---|---|---|
| 1 | Lisbon | 0.00 | 2026-01-01T00:00:00Z | {"w": 0, "h": 0} | null |
| 2 | Oslo | 1.01 | 2026-01-01T01:00:00Z | {"w": 1, "h": 1} | false |
| 3 | Quito | 2.02 | 2026-01-01T02:00:00Z | {"w": 2, "h": 2} | true |
| 4 | Nairobi | 3.03 | 2026-01-01T03:00:00Z | {"w": 3, "h": 0} | false |
| 5 | Hanoi | 4.04 | 2026-01-01T04:00:00Z | {"w": 4, "h": 1} | true |
| 6 | Perth | 5.05 | 2026-01-01T05:00:00Z | {"w": 0, "h": 2} | false |
| 7 | Tromso | 6.06 | 2026-01-01T06:00:00Z | {"w": 1, "h": 0} | true |
| 8 | Cusco | 7.07 | 2026-01-01T07:00:00Z | {"w": 2, "h": 1} | false |
| 9 | Accra | 8.08 | 2026-01-01T08:00:00Z | {"w": 3, "h": 2} | true |
| 10 | Riga | 9.09 | 2026-01-01T09:00:00Z | {"w": 4, "h": 0} | false |
| 11 | Lisbon | 10.10 | 2026-01-01T10:00:00Z | {"w": 0, "h": 1} | null |
| 12 | Oslo | 11.11 | 2026-01-01T11:00:00Z | {"w": 1, "h": 2} | false |
| 13 | Quito | 12.12 | 2026-01-01T12:00:00Z | {"w": 2, "h": 0} | true |
| 14 | Nairobi | 13.13 | 2026-01-01T13:00:00Z | {"w": 3, "h": 1} | false |
| 15 | Hanoi | 14.14 | 2026-01-01T14:00:00Z | {"w": 4, "h": 2} | true |
| 16 | Perth | 15.15 | 2026-01-01T15:00:00Z | {"w": 0, "h": 0} | false |
| 17 | Tromso | 16.16 | 2026-01-01T16:00:00Z | {"w": 1, "h": 1} | true |
| 18 | Cusco | 17.17 | 2026-01-01T17:00:00Z | {"w": 2, "h": 2} | false |
| 19 | Accra | 18.18 | 2026-01-01T18:00:00Z | {"w": 3, "h": 0} | true |
| 20 | Riga | 19.19 | 2026-01-01T19:00:00Z | {"w": 4, "h": 1} | false |
| 21 | Lisbon | 20.20 | 2026-01-01T20:00:00Z | {"w": 0, "h": 2} | null |
| 22 | Oslo | 21.21 | 2026-01-01T21:00:00Z | {"w": 1, "h": 0} | false |
| 23 | Quito | 22.22 | 2026-01-01T22:00:00Z | {"w": 2, "h": 1} | true |
| 24 | Nairobi | 23.23 | 2026-01-01T23:00:00Z | {"w": 3, "h": 2} | false |
| 25 | Hanoi | 24.24 | 2026-01-02T00:00:00Z | {"w": 4, "h": 0} | true |
| 26 | Perth | 25.25 | 2026-01-02T01:00:00Z | {"w": 0, "h": 1} | false |
| 27 | Tromso | 26.26 | 2026-01-02T02:00:00Z | {"w": 1, "h": 2} | true |
| 28 | Cusco | 27.27 | 2026-01-02T03:00:00Z | {"w": 2, "h": 0} | false |
| 29 | Accra | 28.28 | 2026-01-02T04:00:00Z | {"w": 3, "h": 1} | true |
| 30 | Riga | 29.29 | 2026-01-02T05:00:00Z | {"w": 4, "h": 2} | false |
| 31 | Lisbon | 30.30 | 2026-01-02T06:00:00Z | {"w": 0, "h": 0} | null |
| 32 | Oslo | 31.31 | 2026-01-02T07:00:00Z | {"w": 1, "h": 1} | false |
| 33 | Quito | 32.32 | 2026-01-02T08:00:00Z | {"w": 2, "h": 2} | true |
| 34 | Nairobi | 33.33 | 2026-01-02T09:00:00Z | {"w": 3, "h": 0} | false |
| 35 | Hanoi | 34.34 | 2026-01-02T10:00:00Z | {"w": 4, "h": 1} | true |
| 36 | Perth | 35.35 | 2026-01-02T11:00:00Z | {"w": 0, "h": 2} | false |
| 37 | Tromso | 36.36 | 2026-01-02T12:00:00Z | {"w": 1, "h": 0} | true |
| 38 | Cusco | 37.37 | 2026-01-02T13:00:00Z | {"w": 2, "h": 1} | false |
| 39 | Accra | 38.38 | 2026-01-02T14:00:00Z | {"w": 3, "h": 2} | true |
| 40 | Riga | 39.39 | 2026-01-02T15:00:00Z | {"w": 4, "h": 0} | false |
| 41 | Lisbon | 40.40 | 2026-01-02T16:00:00Z | {"w": 0, "h": 1} | null |
| 42 | Oslo | 41.41 | 2026-01-02T17:00:00Z | {"w": 1, "h": 2} | false |
| 43 | Quito | 42.42 | 2026-01-02T18:00:00Z | {"w": 2, "h": 0} | true |
| 44 | Nairobi | 43.43 | 2026-01-02T19:00:00Z | {"w": 3, "h": 1} | false |
| 45 | Hanoi | 44.44 | 2026-01-02T20:00:00Z | {"w": 4, "h": 2} | true |
| 46 | Perth | 45.45 | 2026-01-02T21:00:00Z | {"w": 0, "h": 0} | false |
| 47 | Tromso | 46.46 | 2026-01-02T22:00:00Z | {"w": 1, "h": 1} | true |
| 48 | Cusco | 47.47 | 2026-01-02T23:00:00Z | {"w": 2, "h": 2} | false |
| 49 | Accra | 48.48 | 2026-01-03T00:00:00Z | {"w": 3, "h": 0} | true |
| 50 | Riga | 49.49 | 2026-01-03T01:00:00Z | {"w": 4, "h": 1} | false |
| 51 | Lisbon | 50.50 | 2026-01-03T02:00:00Z | {"w": 0, "h": 2} | null |
| 52 | Oslo | 51.51 | 2026-01-03T03:00:00Z | {"w": 1, "h": 0} | false |
| 53 | Quito | 52.52 | 2026-01-03T04:00:00Z | {"w": 2, "h": 1} | true |
| 54 | Nairobi | 53.53 | 2026-01-03T05:00:00Z | {"w": 3, "h": 2} | false |
| 55 | Hanoi | 54.54 | 2026-01-03T06:00:00Z | {"w": 4, "h": 0} | true |
| 56 | Perth | 55.55 | 2026-01-03T07:00:00Z | {"w": 0, "h": 1} | false |
| 57 | Tromso | 56.56 | 2026-01-03T08:00:00Z | {"w": 1, "h": 2} | true |
| 58 | Cusco | 57.57 | 2026-01-03T09:00:00Z | {"w": 2, "h": 0} | false |
| 59 | Accra | 58.58 | 2026-01-03T10:00:00Z | {"w": 3, "h": 1} | true |
| 60 | Riga | 59.59 | 2026-01-03T11:00:00Z | {"w": 4, "h": 2} | false |
| 61 | Lisbon | 60.60 | 2026-01-03T12:00:00Z | {"w": 0, "h": 0} | null |
| 62 | Oslo | 61.61 | 2026-01-03T13:00:00Z | {"w": 1, "h": 1} | false |
| 63 | Quito | 62.62 | 2026-01-03T14:00:00Z | {"w": 2, "h": 2} | true |
| 64 | Nairobi | 63.63 | 2026-01-03T15:00:00Z | {"w": 3, "h": 0} | false |
| 65 | Hanoi | 64.64 | 2026-01-03T16:00:00Z | {"w": 4, "h": 1} | true |
| 66 | Perth | 65.65 | 2026-01-03T17:00:00Z | {"w": 0, "h": 2} | false |
| 67 | Tromso | 66.66 | 2026-01-03T18:00:00Z | {"w": 1, "h": 0} | true |
| 68 | Cusco | 67.67 | 2026-01-03T19:00:00Z | {"w": 2, "h": 1} | false |
| 69 | Accra | 68.68 | 2026-01-03T20:00:00Z | {"w": 3, "h": 2} | true |
| 70 | Riga | 69.69 | 2026-01-03T21:00:00Z | {"w": 4, "h": 0} | false |
| 71 | Lisbon | 70.70 | 2026-01-03T22:00:00Z | {"w": 0, "h": 1} | null |
| 72 | Oslo | 71.71 | 2026-01-03T23:00:00Z | {"w": 1, "h": 2} | false |
| 73 | Quito | 72.72 | 2026-01-04T00:00:00Z | {"w": 2, "h": 0} | true |
| 74 | Nairobi | 73.73 | 2026-01-04T01:00:00Z | {"w": 3, "h": 1} | false |
| 75 | Hanoi | 74.74 | 2026-01-04T02:00:00Z | {"w": 4, "h": 2} | true |
| 76 | Perth | 75.75 | 2026-01-04T03:00:00Z | {"w": 0, "h": 0} | false |
| 77 | Tromso | 76.76 | 2026-01-04T04:00:00Z | {"w": 1, "h": 1} | true |
| 78 | Cusco | 77.77 | 2026-01-04T05:00:00Z | {"w": 2, "h": 2} | false |
| 79 | Accra | 78.78 | 2026-01-04T06:00:00Z | {"w": 3, "h": 0} | true |
| 80 | Riga | 79.79 | 2026-01-04T07:00:00Z | {"w": 4, "h": 1} | false |
| 81 | Lisbon | 80.80 | 2026-01-04T08:00:00Z | {"w": 0, "h": 2} | null |
| 82 | Oslo | 81.81 | 2026-01-04T09:00:00Z | {"w": 1, "h": 0} | false |
| 83 | Quito | 82.82 | 2026-01-04T10:00:00Z | {"w": 2, "h": 1} | true |
| 84 | Nairobi | 83.83 | 2026-01-04T11:00:00Z | {"w": 3, "h": 2} | false |
| 85 | Hanoi | 84.84 | 2026-01-04T12:00:00Z | {"w": 4, "h": 0} | true |
| 86 | Perth | 85.85 | 2026-01-04T13:00:00Z | {"w": 0, "h": 1} | false |
| 87 | Tromso | 86.86 | 2026-01-04T14:00:00Z | {"w": 1, "h": 2} | true |
| 88 | Cusco | 87.87 | 2026-01-04T15:00:00Z | {"w": 2, "h": 0} | false |
| 89 | Accra | 88.88 | 2026-01-04T16:00:00Z | {"w": 3, "h": 1} | true |
| 90 | Riga | 89.89 | 2026-01-04T17:00:00Z | {"w": 4, "h": 2} | false |
| 91 | Lisbon | 90.90 | 2026-01-04T18:00:00Z | {"w": 0, "h": 0} | null |
| 92 | Oslo | 91.91 | 2026-01-04T19:00:00Z | {"w": 1, "h": 1} | false |
| 93 | Quito | 92.92 | 2026-01-04T20:00:00Z | {"w": 2, "h": 2} | true |
| 94 | Nairobi | 93.93 | 2026-01-04T21:00:00Z | {"w": 3, "h": 0} | false |
| 95 | Hanoi | 94.94 | 2026-01-04T22:00:00Z | {"w": 4, "h": 1} | true |
| 96 | Perth | 95.95 | 2026-01-04T23:00:00Z | {"w": 0, "h": 2} | false |
| 97 | Tromso | 96.96 | 2026-01-05T00:00:00Z | {"w": 1, "h": 0} | true |
| 98 | Cusco | 97.97 | 2026-01-05T01:00:00Z | {"w": 2, "h": 1} | false |
| 99 | Accra | 98.98 | 2026-01-05T02:00:00Z | {"w": 3, "h": 2} | true |
| 100 | Riga | 99.99 | 2026-01-05T03:00:00Z | {"w": 4, "h": 0} | false |
| 131 | Lisbon | 130.30 | 2026-01-06T10:00:00Z | {"w": 0, "h": 1} | null |
| 132 | Oslo | 131.31 | 2026-01-06T11:00:00Z | {"w": 1, "h": 2} | false |
| 133 | Quito | 132.32 | 2026-01-06T12:00:00Z | {"w": 2, "h": 0} | true |
| 134 | Nairobi | 133.33 | 2026-01-06T13:00:00Z | {"w": 3, "h": 1} | false |
| 135 | Hanoi | 134.34 | 2026-01-06T14:00:00Z | {"w": 4, "h": 2} | true |
| 136 | Perth | 135.35 | 2026-01-06T15:00:00Z | {"w": 0, "h": 0} | false |
| 137 | Tromso | 136.36 | 2026-01-06T16:00:00Z | {"w": 1, "h": 1} | true |
| 138 | Cusco | 137.37 | 2026-01-06T17:00:00Z | {"w": 2, "h": 2} | false |
| 139 | Accra | 138.38 | 2026-01-06T18:00:00Z | {"w": 3, "h": 0} | true |
| 140 | Riga | 139.39 | 2026-01-06T19:00:00Z | {"w": 4, "h": 1} | false |
| 141 | Lisbon | 140.40 | 2026-01-06T20:00:00Z | {"w": 0, "h": 2} | null |
| 142 | Oslo | 141.41 | 2026-01-06T21:00:00Z | {"w": 1, "h": 0} | false |
| 143 | Quito | 142.42 | 2026-01-06T22:00:00Z | {"w": 2, "h": 1} | true |
| 144 | Nairobi | 143.43 | 2026-01-06T23:00:00Z | {"w": 3, "h": 2} | false |
| 145 | Hanoi | 144.44 | 2026-01-07T00:00:00Z | {"w": 4, "h": 0} | true |
| 146 | Perth | 145.45 | 2026-01-07T01:00:00Z | {"w": 0, "h": 1} | false |
| 147 | Tromso | 146.46 | 2026-01-07T02:00:00Z | {"w": 1, "h": 2} | true |
| 148 | Cusco | 147.47 | 2026-01-07T03:00:00Z | {"w": 2, "h": 0} | false |
| 149 | Accra | 148.48 | 2026-01-07T04:00:00Z | {"w": 3, "h": 1} | true |
| 150 | Riga | 149.49 | 2026-01-07T05:00:00Z | {"w": 4, "h": 2} | false |

(Sample: the first 100 and the last 20 of 150 rows; 30 rows omitted after row 100.)
