---
title: "Tide harmonics"
source: "https://docs.example.test/quayside/theory/harmonics.html"
source_type: web
converter: web.trafilatura
converter_version: "0.1.0rc1"
ezmd_version: "0.1.0rc1"
schema_version: 1
profile: full
provenance: block
fetched_at: 2026-01-01T00:00:00Z
converted_at: 2026-01-01T00:00:00Z
language: en
word_count: 137
tokens: {o200k_base: 417, cl100k_base: 417, claude_approx: 450}
content_hash: "sha256:f2dd7a56df7be508a8b7da6cb503c2f07d9492133a1d6a03b14bc7d2c8352d50"
source_hash: "sha256:fa1793d815520c77678ba39b55fa52f87bfb93e23c752f57f09d41618d69bef7"
truncated: false
warnings: []
description: "How Quayside predicts tides from harmonic constituents."
injection_risk: none
extra: {encoding: utf-8, readability_ratio: 0.98}
---
# Tide harmonics {#doc}

Quayside models the water level as a sum of cosine constituents.[^1] The height at time $t$ is

$$
h(t) = H_0 + \sum_{i=1}^{n} A_i \cos(\omega_i t + \phi_i)
$$

where each amplitude $A_i$ comes from the station file.[^2]

[^1]: This is the classical harmonic method.
[^2]: Station files list up to 37 constituents.

## 1 Constituents {#sec-1}

**Table 1: Principal constituents**

<table>
<thead>
<tr><th rowspan="2">Name</th><th colspan="2">Period</th></tr>
<tr><th>hours</th><th>days</th></tr>
</thead>
<tbody>
<tr><td>M2</td><td>12.42</td><td>0.52</td></tr>
<tr><td>S2</td><td>12.00</td><td>0.50</td></tr>
<tr><td>K1</td><td>23.93</td><td>1.00</td></tr>
</tbody>
</table>

## 2 Mean level {#sec-2}

Over a full cycle the cosine terms cancel:

$$
\frac{1}{T}\int_0^T h(t)\,dt = H_0
$$

## 3 Computing a prediction {#sec-3}

```python
from quayside import harmonics

levels = harmonics.predict(station="harbor-01", hours=48)
print(max(levels))
```

From the shell:

```bash
quayside predict --station harbor-01 --hours 48
```

Note

Predictions ignore weather surge.

### 3.1 Why cosines? {#sec-3-1}

Each constituent is a periodic astronomical forcing, so a cosine with a fixed angular speed fits it exactly.
