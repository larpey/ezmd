---
title: "Wading Bird Survey"
source: "input.ipynb"
source_type: notebook
converter: documents.ipynb
converter_version: "0.0.1"
intomd_version: "0.0.1"
schema_version: 1
profile: full
provenance: block
fetched_at: 2026-01-01T00:00:00Z
converted_at: 2026-01-01T00:00:00Z
word_count: 97
tokens: {o200k_base: 299, cl100k_base: 296, claude_approx: 323}
content_hash: "sha256:105cc16401bd1a1639482091cea47b6c978bf3bec7c9996db46b8c5200335793"
source_hash: "sha256:a0ab6f25447fc5e99ea81eaaac4d697c8add5bef0d2d5b7cb3c79657cdc42e8e"
truncated: false
warnings: []
injection_risk: none
extra: {kernel_language: python, nbformat: 4}
---
# Wading Bird Survey {#doc}

Counts from the **east marsh**, week 12.[^1] The rate is $r = n / d$.

- herons
- egrets

![Marsh sketch](images/cell0-sketch.png)
<!-- image: images/cell0-sketch.png -->

```python
import pandas as pd
df=pd.read_csv( 'counts.csv' )


print(len(df),'rows')   # count
```

```output
2 rows
```

```python
df
```

**Table 1**

| col_1 | species | count |
|---|---|---:|
| 0 | heron | 12 |
| 1 | egret | 7 |

[^1]: Counted at low tide.

## 1 Plot {#sec-1}

Counts by species, as a bar chart.

```python
df.plot.bar(x = 'species',y='count')
```

![Figure 2](images/c4o0.png)
<!-- image: images/c4o0.png -->

```python
total, days = 19, 0
rate = total / days
```

```output
---------------------------------------------------------------------------
ZeroDivisionError                         Traceback (most recent call last)
Cell In[3], line 1
----> 1 rate = total / days
ZeroDivisionError: division by zero
```

```rst
.. note:: raw rst
```
