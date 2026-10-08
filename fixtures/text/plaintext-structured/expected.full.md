---
title: "Harbour Maintenance Manual"
source: "input.txt"
source_type: text
converter: text.plain
converter_version: "0.1.0rc1"
ezmd_version: "0.1.0rc1"
schema_version: 1
profile: full
provenance: block
fetched_at: 2026-01-01T00:00:00Z
converted_at: 2026-01-01T00:00:00Z
word_count: 188
tokens: {o200k_base: 296, cl100k_base: 299, claude_approx: 320}
content_hash: "sha256:c2b9858ac4577c5523eb4aa686714454e29fb10866f15147264fdf1a5c768d38"
source_hash: "sha256:dd3c4003b0b7e08bff3d2faf26115c639f3bbe9bee54e5530990933207834b94"
truncated: false
warnings: []
injection_risk: none
extra: {encoding: utf-8}
---
# Harbour Maintenance Manual {#doc}

This manual describes the routine upkeep of the small-boat harbour. It was written to be read on paper, so its paragraphs are hard-wrapped at about eighty columns and its sections are marked the way a typewriter would.

## 1 Daily Checks {#sec-1}

Walk the pontoons every morning before the first boat leaves.

1\. Check the mooring lines for chafe.\
2\. Test the shore power posts.\
2.1 Reset any tripped breaker once.\
2.2 Report a second trip to the harbour master.\
3\. Clear litter from the slipway.

## 2 SAFETY EQUIPMENT CHECKS {#sec-2}

Every pontoon carries a life ring, a throw line and a ladder. Replace a missing item the same day and note it in the log.

**Table 1**

| Item | Location | Checked |
|---|---|---|
| Life ring | Pontoon A head | daily |
| Throw line | Pontoon B head | daily |
| Ladder | Each finger | weekly |

## 3 WINTER LAY-UP {#sec-3}

Before the first frost, drain the fresh water lines with the following commands on the pump house controller:

```
valve close main
pump drain --all
valve open bleed
```

Leave the bleed valve open until spring.

END NOTE

Two capital words alone are not a heading.
