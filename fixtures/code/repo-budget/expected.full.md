---
title: "stockroom"
source: "input.repo.zip"
source_type: code
converter: code.repo_pack
converter_version: "0.1.0rc1"
ezmd_version: "0.1.0rc1"
schema_version: 1
profile: full
provenance: block
fetched_at: 2026-01-01T00:00:00Z
converted_at: 2026-01-01T00:00:00Z
word_count: 611
tokens: {o200k_base: 1807, cl100k_base: 1809, claude_approx: 1952}
content_hash: "sha256:3e48ef4c6e4ff3b166b8ee4040338ec07282bdb2b6f17d1192840b49b8a5d9c7"
source_hash: "sha256:6253e7ab6c47bab5c67d074fbb0a02e7e0094a9355279c35cbd43c8440cf1689"
truncated: true
warnings: [token_budget_applied, secret_file_excluded]
description: "Tiny inventory service (ezmd fixture)."
injection_risk: none
extra:
  budget_actions:
    "dropped 3 lockfile, generated, or minified file(s) | dropped 2 test file(s) | compressed 1 file(s) over 300 lines to signatures | truncated 2 file(s) to their first 40 lines | dropped 2 file(s) from the deepest directories"
  bytes: 11892
  excluded.binary: 1
  excluded.default_excluded: 3
  excluded.gitignored: 4
  excluded.minified: 1
  excluded.secret_file: 2
  files: 10
  languages: "python, javascript, typescript"
  license_file: LICENSE
  packed_bytes: 3001
  project: stockroom
  repo: stockroom
  tokens: 831
---
> Sections: 1 Directory tree, 2 Files.

## Contents

- [1 Directory tree](#sec-1)
- [2 Files](#sec-2)
    - [2.1 README.md](#sec-2-1)
    - [2.2 .gitignore](#sec-2-2)
    - [2.3 LICENSE](#sec-2-3)
    - [2.4 keep.log](#sec-2-4)
    - [2.5 pyproject.toml](#sec-2-5)
    - [2.6 web/greeter.ts](#sec-2-6)
    - [2.7 src/stockroom/\_\_init\_\_.py](#sec-2-7)
    - [2.8 src/stockroom/inventory.py](#sec-2-8)
    - [2.9 src/stockroom/scale.py (signatures only)](#sec-2-9)
    - [2.10 docs/notes_utf16.txt](#sec-2-10)

# stockroom {#doc}

10 files packed (11,892 source bytes, 831 tokens). Languages: python 68%, javascript 30%, typescript 2%. Not packed: 1 binary; 3 in default-excluded directories; 4 ignored by .gitignore/.ezmdignore; 1 minified or source maps; 2 credential files. 7 files left out to fit the token budget (still listed in the tree).

## 1 Directory tree {#sec-1}

```text
stockroom/
├── build/ (excluded, 1 file)
├── docs/
│   ├── deploy/
│   │   └── signing.pem (excluded: secret file)
│   └── notes_utf16.txt
├── node_modules/ (excluded, 2 files)
├── src/
│   └── stockroom/
│       ├── helpers/
│       │   ├── .gitignore (omitted: token budget)
│       │   └── units.py (omitted: token budget)
│       ├── proto/
│       │   └── item_pb2.py (omitted: token budget)
│       ├── __init__.py
│       ├── inventory.py
│       └── scale.py
├── tests/
│   ├── fixtures/
│   │   └── creds.txt (omitted: token budget)
│   └── test_inventory.py (omitted: token budget)
├── web/
│   ├── bundle.js (omitted: token budget)
│   ├── greeter.ts
│   ├── logo.png (excluded: binary)
│   └── vendor.min.js (excluded: minified)
├── .env (excluded: secret file)
├── .gitignore
├── LICENSE
├── README.md
├── keep.log
├── pyproject.toml
└── uv.lock (omitted: token budget)
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

### 2.4 keep.log {#sec-2-4}

File: `keep.log`

```text
2026-01-01 00:00:00 INFO kept by a !negation rule
```

### 2.5 pyproject.toml {#sec-2-5}

File: `pyproject.toml`

```toml
[project]
name = "stockroom"
version = "0.1.0"
description = "Tiny inventory service (ezmd fixture)."
requires-python = ">=3.12"
```

### 2.6 web/greeter.ts {#sec-2-6}

File: `web/greeter.ts`

```typescript
// greeter.ts: a tiny TypeScript module (ezmd fixture).
import { format } from "./format";

export interface Greeting {
  name: string;
  excited?: boolean;
}

export function greet(g: Greeting): string {
  const base = format(`Hello, ${g.name}`);
  return g.excited ? base + "!" : base;
}

export const DEFAULT_NAME = 'world';
```

### 2.7 src/stockroom/\_\_init\_\_.py {#sec-2-7}

File: `src/stockroom/__init__.py`

```python
"""stockroom package."""
```

### 2.8 src/stockroom/inventory.py {#sec-2-8}

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
... (truncated, 27 more lines)
```

### 2.9 src/stockroom/scale.py (signatures only) {#sec-2-9}

File: `src/stockroom/scale.py`

```python
"""Generated-looking helpers to make the repo exceed small token budgets."""

def helper_000(value: int, scale: int = 1) -> int:
    """Scale value by 1 and add a fixed offset."""
    ...

def helper_001(value: int, scale: int = 2) -> int:
    """Scale value by 2 and add a fixed offset."""
    ...

def helper_002(value: int, scale: int = 3) -> int:
    """Scale value by 3 and add a fixed offset."""
    ...

def helper_003(value: int, scale: int = 4) -> int:
    """Scale value by 4 and add a fixed offset."""
    ...

def helper_004(value: int, scale: int = 5) -> int:
    """Scale value by 5 and add a fixed offset."""
    ...

def helper_005(value: int, scale: int = 6) -> int:
    """Scale value by 6 and add a fixed offset."""
    ...

def helper_006(value: int, scale: int = 7) -> int:
    """Scale value by 7 and add a fixed offset."""
    ...

def helper_007(value: int, scale: int = 8) -> int:
    """Scale value by 8 and add a fixed offset."""
    ...

def helper_008(value: int, scale: int = 9) -> int:
    """Scale value by 9 and add a fixed offset."""
    ...

def helper_009(value: int, scale: int = 10) -> int:
    """Scale value by 10 and add a fixed offset."""
... (truncated, 121 more lines)
```

### 2.10 docs/notes_utf16.txt {#sec-2-10}

File: `docs/notes_utf16.txt`

```text
Notes in UTF-16: café, naïve, 日本語.
```
