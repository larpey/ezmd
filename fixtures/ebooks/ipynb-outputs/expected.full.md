---
title: "Rainfall Summary"
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
word_count: 58
tokens: {o200k_base: 201, cl100k_base: 201, claude_approx: 217}
content_hash: "sha256:c5bff97ea8ece4712804196129e1b95c9866ed94b01d9769d8ee35913afdb89c"
source_hash: "sha256:0e1cffa4a463a92ced9aad6e90e21655969aa19c21489bc20b95a0d3a38f368b"
truncated: false
warnings: []
injection_risk: none
extra: {kernel_language: r, nbformat: 4}
---
# Rainfall Summary {#doc}

Monthly totals for station **R-7**.

$$
\bar{x} = \frac{1}{n} \sum_i x_i
$$

**Table 1**

| Month | Rain (mm) |
|---|---:|
| May | 41 |
| June | 12 |

```r
rain <- c(41, 12)
cat('loaded', length(rain), 'months\n')
warning('June is provisional')
```

```output
loaded 2 months
```

```output
Warning message:
June is provisional
```

```r
IRdisplay::display_markdown('**Mean:** 26.5 mm')
```

**Mean:** 26.5 mm

```r
barplot(rain)
```

![plot without title](images/c3o0.svg)
<!-- image: images/c3o0.svg -->

```r
# not run yet
summary(rain)
```
