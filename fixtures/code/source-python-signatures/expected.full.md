---
title: "input.py (signatures only)"
source: "input.py"
source_type: code
converter: code.source_file
converter_version: "0.0.1"
intomd_version: "0.0.1"
schema_version: 1
profile: full
provenance: block
fetched_at: 2026-01-01T00:00:00Z
converted_at: 2026-01-01T00:00:00Z
word_count: 138
tokens: {o200k_base: 310, cl100k_base: 312, claude_approx: 335}
content_hash: "sha256:71c9ef5a145022a86a1f57fe8a0ad1bbcb34d0ec56345ab77a1b652e508e2a2c"
source_hash: "sha256:1152da8b3c3e5170b60e26fdaa7c8617e05ab2be323f443a546fc45ba0556374"
truncated: false
warnings: []
injection_risk: none
extra: {bytes: 1856, encoding: utf-8, language: python, lines: 67, shebang: python3, tokens: 289}
---
# input.py (signatures only) {#doc}

File: `input.py`

```python
#!/usr/bin/env python3
# inventory.py: a tiny stock ledger used as an intomd fixture.

"""Track stock levels per SKU and report items that need reordering."""

from __future__ import annotations
import json
from dataclasses import dataclass, field

REORDER_THRESHOLD = 5
Ledger = dict[str, int]

@dataclass
class Item:
    """One stock-keeping unit."""

    sku: str
    name: str
    quantity: int = 0
    tags: list[str] = field(default_factory=list)

    def needs_reorder(self, threshold: int = REORDER_THRESHOLD) -> bool:
        """True when the quantity is at or below the threshold."""
        ...

    def restock(self, amount: int) -> None:
        ...

class Inventory:
    """A collection of items keyed by SKU."""

    def __init__(self) -> None:
        ...

    def add(self, item: Item) -> None:
        ...

    def low_stock(self) -> list[Item]:
        """Items that need reordering, sorted by SKU."""
        ...

    def to_json(self) -> str:
        ...

async def sync_remote(inventory: Inventory, endpoint: str, *, retries: int = 3) -> int:
    """Push quantities to a remote endpoint; returns how many items were sent."""
    ...

def main() -> None:
    ...
```
