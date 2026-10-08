---
title: "Configuration reference"
source: "https://docs.example.test/quayside/reference/config.html"
source_type: web
converter: web.trafilatura
converter_version: "0.0.1"
intomd_version: "0.0.1"
schema_version: 1
profile: full
provenance: block
fetched_at: 2026-01-01T00:00:00Z
converted_at: 2026-01-01T00:00:00Z
language: en
word_count: 149
tokens: {o200k_base: 454, cl100k_base: 453, claude_approx: 490}
content_hash: "sha256:5bd451958f8b75432c841c552b7d1b21058ac4f969fed6d00eb715d6cdd37b94"
source_hash: "sha256:4288e080820428ccf73942e63542177912d7038a553113563ea23d4ab02ca58f"
truncated: false
warnings: []
description: "Reference for the quayside.toml configuration file."
injection_risk: none
extra: {encoding: utf-8, readability_ratio: 0.99}
---
> Sections: 1 Keys, 2 Example, 3 Fee formula, 4 Terms. 1 table.

## Contents

- [1 Keys](#sec-1)
- [2 Example](#sec-2)
- [3 Fee formula](#sec-3)
- [4 Terms](#sec-4)
    - [4.1 Migration from version 1](#sec-4-1)

# Configuration reference {#doc}

Quayside reads `quayside.toml` from the working directory. Every key is optional; the defaults are listed below.[^1]

[^1]: Paths are resolved relative to the file.

## 1 Keys {#sec-1}

**Table 1: Top-level keys**

<table>
<thead>
<tr><th>Key</th><th>Type</th><th>Default</th></tr>
</thead>
<tbody>
<tr><td>berths</td><td>integer</td><td>12</td></tr>
<tr><td>tide_source</td><td>string</td><td>"local"</td></tr>
<tr><td colspan="3">Keys below are experimental.</td></tr>
<tr><td>forecast_days</td><td>integer</td><td>3</td></tr>
</tbody>
</table>

## 2 Example {#sec-2}

```toml
[harbor]
berths = 24
tide_source = "noaa"
```

Load it from Python:

```python
import tomllib

with open("quayside.toml", "rb") as f:
    config = tomllib.load(f)
print(config["harbor"]["berths"])
```

## 3 Fee formula {#sec-3}

The nightly fee scales with length: $f = b + r L$ where L is the boat length in meters.

## 4 Terms {#sec-4}

**Berth**
    A numbered mooring place.

**Slack water**
    The short period with no tidal stream.

### 4.1 Migration from version 1 {#sec-4-1}

Rename `slips` to `berths`.
