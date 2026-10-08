---
title: "acme/stockroom at main"
source: "https://codeload.github.com/acme/stockroom/tar.gz/main"
source_type: code
converter: code.repo_pack
converter_version: "0.1.0rc1"
ezmd_version: "0.1.0rc1"
schema_version: 1
profile: full
provenance: block
fetched_at: 2026-01-01T00:00:00Z
converted_at: 2026-01-01T00:00:00Z
word_count: 1559
tokens: {o200k_base: 3803, cl100k_base: 3804, claude_approx: 4107}
content_hash: "sha256:880fc324dac02a239b3400468257117c17f5d03f7c97ff8e871c66a013c77fb5"
source_hash: "sha256:a41064f88fcc703ec81ad0800b0678561321e9146a4b68903f573493392fc886"
truncated: false
warnings: []
description: "Tiny inventory service (ezmd fixture)."
injection_risk: none
extra:
  bytes: 11442
  commit: "0e76f7757c5d6830073b0d1c0d4c407d365cd410"
  files: 7
  languages: python
  license_file: LICENSE
  packed_bytes: 11434
  project: stockroom
  ref: main
  repo: "acme/stockroom"
  tokens: 3273
---
> Sections: 1 Directory tree, 2 Files.

## Contents

- [1 Directory tree](#sec-1)
- [2 Files](#sec-2)
    - [2.1 README.md](#sec-2-1)
    - [2.2 .gitignore](#sec-2-2)
    - [2.3 LICENSE](#sec-2-3)
    - [2.4 pyproject.toml](#sec-2-4)
    - [2.5 src/stockroom/\_\_init\_\_.py](#sec-2-5)
    - [2.6 src/stockroom/inventory.py](#sec-2-6)
    - [2.7 src/stockroom/scale.py](#sec-2-7)

# acme/stockroom at main {#doc}

7 files packed (11,442 source bytes, 3,273 tokens). Languages: python 100%. Commit 0e76f7757c5d.

## 1 Directory tree {#sec-1}

```text
stockroom/
├── src/
│   └── stockroom/
│       ├── __init__.py
│       ├── inventory.py
│       └── scale.py
├── .gitignore
├── LICENSE
├── README.md
└── pyproject.toml
```

## 2 Files {#sec-2}

### 2.1 README.md {#sec-2-1}

File: `README.md`

```markdown
# stockroom

A small inventory service used as an ezmd repo-pack fixture.

Run `python -m stockroom` to print items that need reordering.
```

### 2.2 .gitignore {#sec-2-2}

File: `.gitignore`

```gitignore
*.log
!keep.log
build/
local_settings.py
__pycache__/
```

### 2.3 LICENSE {#sec-2-3}

File: `LICENSE`

```text
CC0 1.0 Universal (fixture placeholder license text).
```

### 2.4 pyproject.toml {#sec-2-4}

File: `pyproject.toml`

```toml
[project]
name = "stockroom"
version = "0.1.0"
description = "Tiny inventory service (ezmd fixture)."
requires-python = ">=3.12"
```

### 2.5 src/stockroom/\_\_init\_\_.py {#sec-2-5}

File: `src/stockroom/__init__.py`

```python
"""stockroom package."""
```

### 2.6 src/stockroom/inventory.py {#sec-2-6}

File: `src/stockroom/inventory.py`

```python
#!/usr/bin/env python3
# inventory.py: a tiny stock ledger used as an ezmd fixture.
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
        return self.quantity <= threshold

    def restock(self, amount: int) -> None:
        if amount <= 0:
            raise ValueError("amount must be positive")
        self.quantity += amount


class Inventory:
    """A collection of items keyed by SKU."""

    def __init__(self) -> None:
        self._items: dict[str, Item] = {}

    def add(self, item: Item) -> None:
        self._items[item.sku] = item

    def low_stock(self) -> list[Item]:
        """Items that need reordering, sorted by SKU."""
        return sorted((i for i in self._items.values() if i.needs_reorder()), key=lambda i: i.sku)

    def to_json(self) -> str:
        return json.dumps({sku: item.quantity for sku, item in self._items.items()}, indent=2)


async def sync_remote(inventory: Inventory, endpoint: str, *, retries: int = 3) -> int:
    """Push quantities to a remote endpoint; returns how many items were sent."""
    sent = 0
    for _attempt in range(retries):
        sent = len(inventory.low_stock())
    return sent


def main() -> None:
    inv = Inventory()
    inv.add(Item("A-1", "Widget", 3))
    inv.add(Item("B-2", "Gadget", 40))
    for item in inv.low_stock():
        print(f"reorder {item.sku}: {item.name}")


if __name__ == "__main__":
    main()
```

### 2.7 src/stockroom/scale.py {#sec-2-7}

File: `src/stockroom/scale.py`

```python
"""Generated-looking helpers to make the repo exceed small token budgets."""

def helper_000(value: int, scale: int = 1) -> int:
    """Scale value by 1 and add a fixed offset."""
    offset = 0
    result = value * scale
    if result > 1000:
        result = result % 1000
    return result + offset


def helper_001(value: int, scale: int = 2) -> int:
    """Scale value by 2 and add a fixed offset."""
    offset = 7
    result = value * scale
    if result > 1000:
        result = result % 1000
    return result + offset


def helper_002(value: int, scale: int = 3) -> int:
    """Scale value by 3 and add a fixed offset."""
    offset = 1
    result = value * scale
    if result > 1000:
        result = result % 1000
    return result + offset


def helper_003(value: int, scale: int = 4) -> int:
    """Scale value by 4 and add a fixed offset."""
    offset = 8
    result = value * scale
    if result > 1000:
        result = result % 1000
    return result + offset


def helper_004(value: int, scale: int = 5) -> int:
    """Scale value by 5 and add a fixed offset."""
    offset = 2
    result = value * scale
    if result > 1000:
        result = result % 1000
    return result + offset


def helper_005(value: int, scale: int = 6) -> int:
    """Scale value by 6 and add a fixed offset."""
    offset = 9
    result = value * scale
    if result > 1000:
        result = result % 1000
    return result + offset


def helper_006(value: int, scale: int = 7) -> int:
    """Scale value by 7 and add a fixed offset."""
    offset = 3
    result = value * scale
    if result > 1000:
        result = result % 1000
    return result + offset


def helper_007(value: int, scale: int = 8) -> int:
    """Scale value by 8 and add a fixed offset."""
    offset = 10
    result = value * scale
    if result > 1000:
        result = result % 1000
    return result + offset


def helper_008(value: int, scale: int = 9) -> int:
    """Scale value by 9 and add a fixed offset."""
    offset = 4
    result = value * scale
    if result > 1000:
        result = result % 1000
    return result + offset


def helper_009(value: int, scale: int = 10) -> int:
    """Scale value by 10 and add a fixed offset."""
    offset = 11
    result = value * scale
    if result > 1000:
        result = result % 1000
    return result + offset


def helper_010(value: int, scale: int = 11) -> int:
    """Scale value by 11 and add a fixed offset."""
    offset = 5
    result = value * scale
    if result > 1000:
        result = result % 1000
    return result + offset


def helper_011(value: int, scale: int = 12) -> int:
    """Scale value by 12 and add a fixed offset."""
    offset = 12
    result = value * scale
    if result > 1000:
        result = result % 1000
    return result + offset


def helper_012(value: int, scale: int = 13) -> int:
    """Scale value by 13 and add a fixed offset."""
    offset = 6
    result = value * scale
    if result > 1000:
        result = result % 1000
    return result + offset


def helper_013(value: int, scale: int = 14) -> int:
    """Scale value by 14 and add a fixed offset."""
    offset = 0
    result = value * scale
    if result > 1000:
        result = result % 1000
    return result + offset


def helper_014(value: int, scale: int = 15) -> int:
    """Scale value by 15 and add a fixed offset."""
    offset = 7
    result = value * scale
    if result > 1000:
        result = result % 1000
    return result + offset


def helper_015(value: int, scale: int = 16) -> int:
    """Scale value by 16 and add a fixed offset."""
    offset = 1
    result = value * scale
    if result > 1000:
        result = result % 1000
    return result + offset


def helper_016(value: int, scale: int = 17) -> int:
    """Scale value by 17 and add a fixed offset."""
    offset = 8
    result = value * scale
    if result > 1000:
        result = result % 1000
    return result + offset


def helper_017(value: int, scale: int = 18) -> int:
    """Scale value by 18 and add a fixed offset."""
    offset = 2
    result = value * scale
    if result > 1000:
        result = result % 1000
    return result + offset


def helper_018(value: int, scale: int = 19) -> int:
    """Scale value by 19 and add a fixed offset."""
    offset = 9
    result = value * scale
    if result > 1000:
        result = result % 1000
    return result + offset


def helper_019(value: int, scale: int = 20) -> int:
    """Scale value by 20 and add a fixed offset."""
    offset = 3
    result = value * scale
    if result > 1000:
        result = result % 1000
    return result + offset


def helper_020(value: int, scale: int = 21) -> int:
    """Scale value by 21 and add a fixed offset."""
    offset = 10
    result = value * scale
    if result > 1000:
        result = result % 1000
    return result + offset


def helper_021(value: int, scale: int = 22) -> int:
    """Scale value by 22 and add a fixed offset."""
    offset = 4
    result = value * scale
    if result > 1000:
        result = result % 1000
    return result + offset


def helper_022(value: int, scale: int = 23) -> int:
    """Scale value by 23 and add a fixed offset."""
    offset = 11
    result = value * scale
    if result > 1000:
        result = result % 1000
    return result + offset


def helper_023(value: int, scale: int = 24) -> int:
    """Scale value by 24 and add a fixed offset."""
    offset = 5
    result = value * scale
    if result > 1000:
        result = result % 1000
    return result + offset


def helper_024(value: int, scale: int = 25) -> int:
    """Scale value by 25 and add a fixed offset."""
    offset = 12
    result = value * scale
    if result > 1000:
        result = result % 1000
    return result + offset


def helper_025(value: int, scale: int = 26) -> int:
    """Scale value by 26 and add a fixed offset."""
    offset = 6
    result = value * scale
    if result > 1000:
        result = result % 1000
    return result + offset


def helper_026(value: int, scale: int = 27) -> int:
    """Scale value by 27 and add a fixed offset."""
    offset = 0
    result = value * scale
    if result > 1000:
        result = result % 1000
    return result + offset


def helper_027(value: int, scale: int = 28) -> int:
    """Scale value by 28 and add a fixed offset."""
    offset = 7
    result = value * scale
    if result > 1000:
        result = result % 1000
    return result + offset


def helper_028(value: int, scale: int = 29) -> int:
    """Scale value by 29 and add a fixed offset."""
    offset = 1
    result = value * scale
    if result > 1000:
        result = result % 1000
    return result + offset


def helper_029(value: int, scale: int = 30) -> int:
    """Scale value by 30 and add a fixed offset."""
    offset = 8
    result = value * scale
    if result > 1000:
        result = result % 1000
    return result + offset


def helper_030(value: int, scale: int = 31) -> int:
    """Scale value by 31 and add a fixed offset."""
    offset = 2
    result = value * scale
    if result > 1000:
        result = result % 1000
    return result + offset


def helper_031(value: int, scale: int = 32) -> int:
    """Scale value by 32 and add a fixed offset."""
    offset = 9
    result = value * scale
    if result > 1000:
        result = result % 1000
    return result + offset


def helper_032(value: int, scale: int = 33) -> int:
    """Scale value by 33 and add a fixed offset."""
    offset = 3
    result = value * scale
    if result > 1000:
        result = result % 1000
    return result + offset


def helper_033(value: int, scale: int = 34) -> int:
    """Scale value by 34 and add a fixed offset."""
    offset = 10
    result = value * scale
    if result > 1000:
        result = result % 1000
    return result + offset


def helper_034(value: int, scale: int = 35) -> int:
    """Scale value by 35 and add a fixed offset."""
    offset = 4
    result = value * scale
    if result > 1000:
        result = result % 1000
    return result + offset


def helper_035(value: int, scale: int = 36) -> int:
    """Scale value by 36 and add a fixed offset."""
    offset = 11
    result = value * scale
    if result > 1000:
        result = result % 1000
    return result + offset


def helper_036(value: int, scale: int = 37) -> int:
    """Scale value by 37 and add a fixed offset."""
    offset = 5
    result = value * scale
    if result > 1000:
        result = result % 1000
    return result + offset


def helper_037(value: int, scale: int = 38) -> int:
    """Scale value by 38 and add a fixed offset."""
    offset = 12
    result = value * scale
    if result > 1000:
        result = result % 1000
    return result + offset


def helper_038(value: int, scale: int = 39) -> int:
    """Scale value by 39 and add a fixed offset."""
    offset = 6
    result = value * scale
    if result > 1000:
        result = result % 1000
    return result + offset


def helper_039(value: int, scale: int = 40) -> int:
    """Scale value by 40 and add a fixed offset."""
    offset = 0
    result = value * scale
    if result > 1000:
        result = result % 1000
    return result + offset
```
