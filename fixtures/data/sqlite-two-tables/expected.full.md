---
title: "input.sqlite"
source: "input.sqlite"
source_type: data
converter: data.sqlite
converter_version: "0.0.1"
intomd_version: "0.0.1"
schema_version: 1
profile: full
provenance: block
fetched_at: 2026-01-01T00:00:00Z
converted_at: 2026-01-01T00:00:00Z
word_count: 1174
tokens: {o200k_base: 3626, cl100k_base: 3630, claude_approx: 3916}
content_hash: "sha256:ccfaee7c58f7086427a17d65e19013c22eab8d950098625ba780724900c30ae5"
source_hash: "sha256:ac059b3b30c9d7d1cb9253dd4397d5cc839c94d88df00647b8275eec56f608e0"
truncated: true
warnings: [rows_sampled]
injection_risk: none
exports: {tables: ["tables/table-07.csv"]}
extra: {format: SQLite, tables: 2, views: 1}
---
> Sections: 1 Tables, 2 Views. 7 tables.

## Contents

- [1 Tables](#sec-1)
    - [1.1 customers](#sec-1-1)
        - [1.1.1 Statistics](#sec-1-1-1)
        - [1.1.2 Sample](#sec-1-1-2)
    - [1.2 orders](#sec-1-2)
        - [1.2.1 Statistics](#sec-1-2-1)
        - [1.2.2 Sample](#sec-1-2-2)
- [2 Views](#sec-2)
    - [2.1 big_orders](#sec-2-1)

# input.sqlite {#doc}

SQLite database with 2 table(s), 1 view(s), 1 index(es) and 0 trigger(s).

## 1 Tables {#sec-1}

**Table 1**

| Table | Rows | Columns |
|---|---:|---:|
| customers | 5 | 4 |
| orders | 130 | 5 |

### 1.1 customers {#sec-1-1}

**Table 2**
Columns: Column, Type, Not null, Default, Primary key, References

| Column | Type | Not null | Default | Primary key | References |
|---|---|---|---|---|---|
| id | INTEGER | no |  | yes |  |
| name | TEXT | yes |  | no |  |
| city | TEXT | no |  | no |  |
| joined | TEXT | no |  | no |  |

#### 1.1.1 Statistics {#sec-1-1-1}

**Table 3**
Columns: Column, Nulls, Distinct, Min, Max

| Column | Nulls | Distinct | Min | Max |
|---|---:|---:|---|---|
| id | 0 | 5 | 1 | 5 |
| name | 0 | 5 | Customer 1 | Customer 5 |
| city | 0 | 5 | Hanoi | Quito |
| joined | 0 | 5 | 2025-01-15 | 2025-05-15 |

#### 1.1.2 Sample {#sec-1-1-2}

**Table 4**

| id | name | city | joined |
|---:|---|---|---|
| 1 | Customer 1 | Oslo | 2025-01-15 |
| 2 | Customer 2 | Quito | 2025-02-15 |
| 3 | Customer 3 | Nairobi | 2025-03-15 |
| 4 | Customer 4 | Hanoi | 2025-04-15 |
| 5 | Customer 5 | Perth | 2025-05-15 |

### 1.2 orders {#sec-1-2}

**Table 5**
Columns: Column, Type, Not null, Default, Primary key, References

| Column | Type | Not null | Default | Primary key | References |
|---|---|---|---|---|---|
| id | INTEGER | no |  | yes |  |
| customer_id | INTEGER | yes |  | no | customers(id) |
| total | REAL | no |  | no |  |
| note | TEXT | no |  | no |  |
| receipt | BLOB | no |  | no |  |

- CREATE INDEX idx_orders_customer ON orders(customer_id)

#### 1.2.1 Statistics {#sec-1-2-1}

**Table 6**
Columns: Column, Nulls, Distinct, Min, Max

| Column | Nulls | Distinct | Min | Max |
|---|---:|---:|---|---|
| id | 0 | 130 | 1 | 130 |
| customer_id | 0 | 5 | 1 | 5 |
| total | 0 | 11 | 0.0 | 125.0 |
| note | 98 | 32 | note 100 | note 96 |
| receipt | 0 | 7 |  |  |

#### 1.2.2 Sample {#sec-1-2-2}

**Table 7** (tables/table-07.csv)
Columns: id, customer_id, total, note, receipt

| id | customer_id | total | note | receipt |
|---:|---:|---:|---|---|
| 1 | 2 | 12.5 | NULL | <blob 1 bytes> |
| 2 | 3 | 25.0 | NULL | <blob 2 bytes> |
| 3 | 4 | 37.5 | NULL | <blob 3 bytes> |
| 4 | 5 | 50.0 | note 4 | <blob 4 bytes> |
| 5 | 1 | 62.5 | NULL | <blob 5 bytes> |
| 6 | 2 | 75.0 | NULL | <blob 6 bytes> |
| 7 | 3 | 87.5 | NULL | <blob 0 bytes> |
| 8 | 4 | 100.0 | note 8 | <blob 1 bytes> |
| 9 | 5 | 112.5 | NULL | <blob 2 bytes> |
| 10 | 1 | 125.0 | NULL | <blob 3 bytes> |
| 11 | 2 | 0.0 | NULL | <blob 4 bytes> |
| 12 | 3 | 12.5 | note 12 | <blob 5 bytes> |
| 13 | 4 | 25.0 | NULL | <blob 6 bytes> |
| 14 | 5 | 37.5 | NULL | <blob 0 bytes> |
| 15 | 1 | 50.0 | NULL | <blob 1 bytes> |
| 16 | 2 | 62.5 | note 16 | <blob 2 bytes> |
| 17 | 3 | 75.0 | NULL | <blob 3 bytes> |
| 18 | 4 | 87.5 | NULL | <blob 4 bytes> |
| 19 | 5 | 100.0 | NULL | <blob 5 bytes> |
| 20 | 1 | 112.5 | note 20 | <blob 6 bytes> |
| 21 | 2 | 125.0 | NULL | <blob 0 bytes> |
| 22 | 3 | 0.0 | NULL | <blob 1 bytes> |
| 23 | 4 | 12.5 | NULL | <blob 2 bytes> |
| 24 | 5 | 25.0 | note 24 | <blob 3 bytes> |
| 25 | 1 | 37.5 | NULL | <blob 4 bytes> |
| 26 | 2 | 50.0 | NULL | <blob 5 bytes> |
| 27 | 3 | 62.5 | NULL | <blob 6 bytes> |
| 28 | 4 | 75.0 | note 28 | <blob 0 bytes> |
| 29 | 5 | 87.5 | NULL | <blob 1 bytes> |
| 30 | 1 | 100.0 | NULL | <blob 2 bytes> |
| 31 | 2 | 112.5 | NULL | <blob 3 bytes> |
| 32 | 3 | 125.0 | note 32 | <blob 4 bytes> |
| 33 | 4 | 0.0 | NULL | <blob 5 bytes> |
| 34 | 5 | 12.5 | NULL | <blob 6 bytes> |
| 35 | 1 | 25.0 | NULL | <blob 0 bytes> |
| 36 | 2 | 37.5 | note 36 | <blob 1 bytes> |
| 37 | 3 | 50.0 | NULL | <blob 2 bytes> |
| 38 | 4 | 62.5 | NULL | <blob 3 bytes> |
| 39 | 5 | 75.0 | NULL | <blob 4 bytes> |
| 40 | 1 | 87.5 | note 40 | <blob 5 bytes> |
| 41 | 2 | 100.0 | NULL | <blob 6 bytes> |
| 42 | 3 | 112.5 | NULL | <blob 0 bytes> |
| 43 | 4 | 125.0 | NULL | <blob 1 bytes> |
| 44 | 5 | 0.0 | note 44 | <blob 2 bytes> |
| 45 | 1 | 12.5 | NULL | <blob 3 bytes> |
| 46 | 2 | 25.0 | NULL | <blob 4 bytes> |
| 47 | 3 | 37.5 | NULL | <blob 5 bytes> |
| 48 | 4 | 50.0 | note 48 | <blob 6 bytes> |
| 49 | 5 | 62.5 | NULL | <blob 0 bytes> |
| 50 | 1 | 75.0 | NULL | <blob 1 bytes> |
| 51 | 2 | 87.5 | NULL | <blob 2 bytes> |
| 52 | 3 | 100.0 | note 52 | <blob 3 bytes> |
| 53 | 4 | 112.5 | NULL | <blob 4 bytes> |
| 54 | 5 | 125.0 | NULL | <blob 5 bytes> |
| 55 | 1 | 0.0 | NULL | <blob 6 bytes> |
| 56 | 2 | 12.5 | note 56 | <blob 0 bytes> |
| 57 | 3 | 25.0 | NULL | <blob 1 bytes> |
| 58 | 4 | 37.5 | NULL | <blob 2 bytes> |
| 59 | 5 | 50.0 | NULL | <blob 3 bytes> |
| 60 | 1 | 62.5 | note 60 | <blob 4 bytes> |
| 61 | 2 | 75.0 | NULL | <blob 5 bytes> |
| 62 | 3 | 87.5 | NULL | <blob 6 bytes> |
| 63 | 4 | 100.0 | NULL | <blob 0 bytes> |
| 64 | 5 | 112.5 | note 64 | <blob 1 bytes> |
| 65 | 1 | 125.0 | NULL | <blob 2 bytes> |
| 66 | 2 | 0.0 | NULL | <blob 3 bytes> |
| 67 | 3 | 12.5 | NULL | <blob 4 bytes> |
| 68 | 4 | 25.0 | note 68 | <blob 5 bytes> |
| 69 | 5 | 37.5 | NULL | <blob 6 bytes> |
| 70 | 1 | 50.0 | NULL | <blob 0 bytes> |
| 71 | 2 | 62.5 | NULL | <blob 1 bytes> |
| 72 | 3 | 75.0 | note 72 | <blob 2 bytes> |
| 73 | 4 | 87.5 | NULL | <blob 3 bytes> |
| 74 | 5 | 100.0 | NULL | <blob 4 bytes> |
| 75 | 1 | 112.5 | NULL | <blob 5 bytes> |
| 76 | 2 | 125.0 | note 76 | <blob 6 bytes> |
| 77 | 3 | 0.0 | NULL | <blob 0 bytes> |
| 78 | 4 | 12.5 | NULL | <blob 1 bytes> |
| 79 | 5 | 25.0 | NULL | <blob 2 bytes> |
| 80 | 1 | 37.5 | note 80 | <blob 3 bytes> |
| 81 | 2 | 50.0 | NULL | <blob 4 bytes> |
| 82 | 3 | 62.5 | NULL | <blob 5 bytes> |
| 83 | 4 | 75.0 | NULL | <blob 6 bytes> |
| 84 | 5 | 87.5 | note 84 | <blob 0 bytes> |
| 85 | 1 | 100.0 | NULL | <blob 1 bytes> |
| 86 | 2 | 112.5 | NULL | <blob 2 bytes> |
| 87 | 3 | 125.0 | NULL | <blob 3 bytes> |
| 88 | 4 | 0.0 | note 88 | <blob 4 bytes> |
| 89 | 5 | 12.5 | NULL | <blob 5 bytes> |
| 90 | 1 | 25.0 | NULL | <blob 6 bytes> |
| 91 | 2 | 37.5 | NULL | <blob 0 bytes> |
| 92 | 3 | 50.0 | note 92 | <blob 1 bytes> |
| 93 | 4 | 62.5 | NULL | <blob 2 bytes> |
| 94 | 5 | 75.0 | NULL | <blob 3 bytes> |
| 95 | 1 | 87.5 | NULL | <blob 4 bytes> |
| 96 | 2 | 100.0 | note 96 | <blob 5 bytes> |
| 97 | 3 | 112.5 | NULL | <blob 6 bytes> |
| 98 | 4 | 125.0 | NULL | <blob 0 bytes> |
| 99 | 5 | 0.0 | NULL | <blob 1 bytes> |
| 100 | 1 | 12.5 | note 100 | <blob 2 bytes> |
| 111 | 2 | 12.5 | NULL | <blob 6 bytes> |
| 112 | 3 | 25.0 | note 112 | <blob 0 bytes> |
| 113 | 4 | 37.5 | NULL | <blob 1 bytes> |
| 114 | 5 | 50.0 | NULL | <blob 2 bytes> |
| 115 | 1 | 62.5 | NULL | <blob 3 bytes> |
| 116 | 2 | 75.0 | note 116 | <blob 4 bytes> |
| 117 | 3 | 87.5 | NULL | <blob 5 bytes> |
| 118 | 4 | 100.0 | NULL | <blob 6 bytes> |
| 119 | 5 | 112.5 | NULL | <blob 0 bytes> |
| 120 | 1 | 125.0 | note 120 | <blob 1 bytes> |
| 121 | 2 | 0.0 | NULL | <blob 2 bytes> |
| 122 | 3 | 12.5 | NULL | <blob 3 bytes> |
| 123 | 4 | 25.0 | NULL | <blob 4 bytes> |
| 124 | 5 | 37.5 | note 124 | <blob 5 bytes> |
| 125 | 1 | 50.0 | NULL | <blob 6 bytes> |
| 126 | 2 | 62.5 | NULL | <blob 0 bytes> |
| 127 | 3 | 75.0 | NULL | <blob 1 bytes> |
| 128 | 4 | 87.5 | note 128 | <blob 2 bytes> |
| 129 | 5 | 100.0 | NULL | <blob 3 bytes> |
| 130 | 1 | 112.5 | NULL | <blob 4 bytes> |

(Sample: the first 100 and the last 20 of 130 rows; 10 rows omitted after row 100.)

## 2 Views {#sec-2}

### 2.1 big_orders {#sec-2-1}

```sql
CREATE VIEW big_orders AS SELECT * FROM orders WHERE total > 100
```
