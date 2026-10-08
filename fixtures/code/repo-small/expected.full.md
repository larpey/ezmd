---
title: "stockroom"
source: "input.repo.zip"
source_type: code
converter: code.repo_pack
converter_version: "0.0.1"
intomd_version: "0.0.1"
schema_version: 1
profile: full
provenance: block
fetched_at: 2026-01-01T00:00:00Z
converted_at: 2026-01-01T00:00:00Z
word_count: 2077
tokens: {o200k_base: 8507, cl100k_base: 8499, claude_approx: 9188}
content_hash: "sha256:ccaa7563e5dc3c4be5fd0f4d56be15820d2bd5af5f50e4ddc45d4fb6fed7ebd6"
source_hash: "sha256:1d0348c51a02da7d5104f42734724bf50e822557104da86ac491a500d4e6ff5e"
truncated: false
warnings: [secret_file_excluded, secret_redacted, archive_entry_skipped]
description: "Tiny inventory service (intomd fixture)."
injection_risk: none
extra:
  bytes: 25316
  excluded.binary: 1
  excluded.default_excluded: 3
  excluded.gitignored: 4
  excluded.minified: 1
  excluded.secret_file: 2
  files: 17
  languages: "python, javascript, typescript"
  license_file: LICENSE
  packed_bytes: 19285
  project: stockroom
  repo: stockroom
  tokens: 7208
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
    - [2.6 uv.lock](#sec-2-6)
    - [2.7 web/bundle.js](#sec-2-7)
    - [2.8 web/greeter.ts](#sec-2-8)
    - [2.9 src/stockroom/\_\_init\_\_.py](#sec-2-9)
    - [2.10 src/stockroom/inventory.py](#sec-2-10)
    - [2.11 src/stockroom/scale.py](#sec-2-11)
    - [2.12 src/stockroom/helpers/.gitignore](#sec-2-12)
    - [2.13 src/stockroom/helpers/units.py](#sec-2-13)
    - [2.14 src/stockroom/proto/item_pb2.py](#sec-2-14)
    - [2.15 docs/notes_utf16.txt](#sec-2-15)
    - [2.16 tests/test_inventory.py](#sec-2-16)
    - [2.17 tests/fixtures/creds.txt](#sec-2-17)

# stockroom {#doc}

17 files packed (25,316 source bytes, 7,208 tokens). Languages: python 68%, javascript 30%, typescript 2%. Not packed: 1 binary; 3 in default-excluded directories; 4 ignored by .gitignore/.intomdignore; 1 minified or source maps; 2 credential files.

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
│       │   ├── .gitignore
│       │   └── units.py
│       ├── proto/
│       │   └── item_pb2.py
│       ├── __init__.py
│       ├── inventory.py
│       └── scale.py
├── tests/
│   ├── fixtures/
│   │   └── creds.txt
│   └── test_inventory.py
├── web/
│   ├── bundle.js
│   ├── greeter.ts
│   ├── logo.png (excluded: binary)
│   └── vendor.min.js (excluded: minified)
├── .env (excluded: secret file)
├── .gitignore
├── LICENSE
├── README.md
├── keep.log
├── pyproject.toml
└── uv.lock
```

## 2 Files {#sec-2}

### 2.1 README.md {#sec-2-1}

File: `README.md`

```markdown
# stockroom

A small inventory service used as an intomd repo-pack fixture.

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
description = "Tiny inventory service (intomd fixture)."
requires-python = ">=3.12"
```

### 2.6 uv.lock {#sec-2-6}

File: `uv.lock`

```text
package-000==1.0.0 --hash=sha256:250a6728a4773d005822ae1bd6f1967b7107d692e8197e1502d9659017b278c4
package-001==1.1.0 --hash=sha256:3634c0e5a62cc707990c82dc542ddd601ef8b3e922d0f954067b3c605ca33f73
package-002==1.2.0 --hash=sha256:0f89a1134b81894b74e4f36c5446fe657a0dda8a5f70dfca3218aef79baad576
package-003==1.3.0 --hash=sha256:a8f39ace60c2712c62f4ef4109aa1797a3ab490f8a8258c51ec5454489eb4a2e
package-004==1.4.0 --hash=sha256:6c1aa1c6fc8b2d9b2dd5a17773ec8c7d9385c18021d06c626ee85572baa58725
package-005==1.5.0 --hash=sha256:a6809728f2d3b196e8f742e1e3ddae6c623071229a0e9f5385cb455fe5799c14
package-006==1.6.0 --hash=sha256:116fc250919cf1defc4c00acd652cae2c82638af5d55ac90736fbce0426e04c4
package-007==1.7.0 --hash=sha256:334ca2826616d498e9e24bf6a061623560cfa0bbfdce68f1f5709d0a8b2d3dc0
package-008==1.8.0 --hash=sha256:09bab8f8dc2c41f48d44eec90826d8eb1df65091b6693460a1a446758e4a000b
package-009==1.9.0 --hash=sha256:3d2024cada10b07249e560a3ba263d06785833e6dd90ed3dc157cf7e7847d77b
package-010==1.10.0 --hash=sha256:d076f85118186aa719e5fd6de92807e4b1e9b3997b64bf33ea016245e5f09649
package-011==1.11.0 --hash=sha256:96d361920ed212d32c5e2a069dc0f257668937f1fe032af2ce2ca2ef836199d3
package-012==1.12.0 --hash=sha256:dd50b461c567d5d93b0b68e87afb68639c7e8637e33197d9c783d8d556674d4a
package-013==1.13.0 --hash=sha256:c2a322ff54db0ab9c676a196f8f1403c94315e6bfafc9581524f97a3a0e3fe83
package-014==1.14.0 --hash=sha256:6cf389abd87e8c9b0c4e6aacc26ea7da346508560a9176480f9088b1b5827a76
package-015==1.15.0 --hash=sha256:ca065b1e2d82afda5e2ddb07ded93a1e7b71aac764ab8eb1d53ba8fd343bc4a6
package-016==1.16.0 --hash=sha256:6be685096bcd1103bcc5bc580918d3634b7945cf859301b673eb31d8bcf7631b
package-017==1.17.0 --hash=sha256:15fd70346e1397dfb5aa402f5261bfe521b580ecaf6422be4c40dabd7188a6fc
package-018==1.18.0 --hash=sha256:b6f038e622242643bd4f432a55ed5f32171d35194cda4c265288772e35b27248
package-019==1.19.0 --hash=sha256:814420cf741df90f967f52a017fe5ff52fd47a9a39da65c1ea8ae7b0d081af55
package-020==1.20.0 --hash=sha256:e5df16e469c09a8a22f429cacf535aa52885fd935a55ba2623ad5c4899f80ccb
package-021==1.21.0 --hash=sha256:c149c2429585aa6a2406bfc8171803e1e53aa6d44033963f7e7ed64dfb65a23a
package-022==1.22.0 --hash=sha256:3cb43ad1c8b2a9a998c0f96c9cd4d3fddfbbd2b03fd1cd35bc436e0bbb92611a
package-023==1.23.0 --hash=sha256:7c089557d89057c8e0ac9b3629035585415e8d6d105e9f3bfdd7abc64f0c917e
package-024==1.24.0 --hash=sha256:817c663b13646fe5dea07947c87849cf928fc24665d75b731a2b361cbe224743
package-025==1.25.0 --hash=sha256:e2dd213a2b4a302c46b8c34d3a92a893e7f1ba1f83be7433bebae4a950f4aaac
package-026==1.26.0 --hash=sha256:f53bc6d661a27da3de840c9a7caa174e76d87ea8f6e0ad39cb1709fe9b1a398b
package-027==1.27.0 --hash=sha256:2328ed0068f9f7c5ddb56055aac802a002ba1a0b299aa6f06c21affa34ae0767
package-028==1.28.0 --hash=sha256:46fc2e2a90ea212a9fb2fedbb354a3159d91b15cacb00ffee3f9c1856fb8038b
package-029==1.29.0 --hash=sha256:8da9c6ec6268c31bb0c0424f414080efb0027c4347ecb7be2f9bb65da24b5cea
package-030==1.30.0 --hash=sha256:f788c6874ef23b6742a656e18eedc8c29133a6d83dd8aeed958398a61079e695
package-031==1.31.0 --hash=sha256:148601b1025d7e471c876101678b2090946b055dc1e6958393f5493b2d891c4f
package-032==1.32.0 --hash=sha256:0b359e1f7f578129edc5db839000361f0b7a2beaa17e03d60c77769bde8b1296
package-033==1.33.0 --hash=sha256:7db62ae06baa1d8ef099e1ff2d9621568de7e56100b1987800e47daa18c6458a
package-034==1.34.0 --hash=sha256:2c9cae5d7f268e73794266f8e98f0d1d711f1799ae9bc184dcdec86e8ed129e2
package-035==1.35.0 --hash=sha256:cca21c5c3ed1b74171d6209ea243b2877b8ef358160ec7ada893548453fdf60d
package-036==1.36.0 --hash=sha256:270170dc62d17edac18ef7715cd68ccb7f0831635764d3f41e5cd7a995754c31
package-037==1.37.0 --hash=sha256:d2bbcc5465c9e527255a58ebc96c69a187e01723226651ba21f5ea53335ddc43
package-038==1.38.0 --hash=sha256:c9b7e12890c548734fbb2bb2c87f74ee6ced9176e6961a06f226199930f33999
package-039==1.39.0 --hash=sha256:12f2ce9075f78827e5cf78568fc3edd35e60d22c5e616656f933107a67d11f98
package-040==1.40.0 --hash=sha256:7b30987814e77084457c23ea97cb2f0e9d3bcfd3d32ecd9d11bff08b4fed47a4
package-041==1.41.0 --hash=sha256:79c7de7356cd22f8759c28df8832bac402f33a0223d4efe1933babdc3e847418
package-042==1.42.0 --hash=sha256:4dfa48f8615da30bc47c2f5e61a62c5ef697d382db04683b4e6b2ea5482e1a8d
package-043==1.43.0 --hash=sha256:3408182845d3c7ad68e28cc09701b1f9263091ea4d7ed696682b3114e94cf7d9
package-044==1.44.0 --hash=sha256:115fec9f920d09b5fcc945b950e80607f5b05433bf3ca478cd71d159e756cc58
package-045==1.45.0 --hash=sha256:9ccaa935e88588ba6df1fe4a29ca5fe09d4395968487881a5723e0d0ebfed55e
package-046==1.46.0 --hash=sha256:5fb4b2bdc237783e96d6aa827f864fe6cdfa8f4b15a4eaf139f723e3ce4e983b
package-047==1.47.0 --hash=sha256:da25524c329a1bb3c88ef1e0000102ccbf592c64c53feab6554133cb66c875ba
package-048==1.48.0 --hash=sha256:65c7b0bb3edf7515fde23bc6929d31737e75860e395659325685049297b5c3de
package-049==1.49.0 --hash=sha256:40eb85ccb1b015f1bcab47dc0c1351916a912c1c73c6cf95652bc73511150148
... (lockfile truncated, 30 more lines)
```

### 2.7 web/bundle.js {#sec-2-7}

File: `web/bundle.js`

```javascript
!function(){var a0=0;var a1=1;var a2=2;var a3=3;var a4=4;var a5=5;var a6=6;var a7=7;var a8=8;var a9=9;var a10=10;var a11=11;var a12=12;var a13=13;var a14=14;var a15=15;var a16=16;var a17=17;var a18=18;var a19=19;var a20=20;var a21=21;var a22=22;var a23=23;var a24=24;var a25=25;var a26=26;var a27=27;var a28=28;var a29=29;var a30=30;var a31=31;var a32=32;var a33=33;var a34=34;var a35=35;var a36=36;var a37=37;var a38=38;var a39=39;var a40=40;var a41=41;var a42=42;var a43=43;var a44=44;var a45=45;var a46=46;var a47=47;var a48=48;var a49=49;var a50=50;var a51=51;var a52=52;var a53=53;var a54=54;var a55=55;var a56=56;var a57=57;var a58=58;var a59=59;var a60=60;var a61=61;var a62=62;var a63=63;var a64=64;var a65=65;var a66=66;var a67=67;var a68=68;var a69=69;var a70=70;var a71=71;var a72=72;var a73=73;var a74=74;var a75=75;var a76=76;var a77=77;var a78=78;var a79=79;var a80=80;var a81=81;var a82=82;var a83=83;var a84=84;var a85=85;var a86=86;var a87=87;var a88=88;var a89=89;var a90=90;var a91=91;var a92=92;var a93=93;var a94=94;var a95=95;var a96=96;var a97=97;var a98=98;var a99=99;var a100=100;var a101=101;var a102=102;var a103=103;var a104=104;var a105=105;var a106=106;var a107=107;var a108=108;var a109=109;var a110=110;var a111=111;var a112=112;var a113=113;var a114=114;var a115=115;var a116=116;var a117=117;var a118=118;var a119=119;var a120=120;var a121=121;var a122=122;var a123=123;var a124=124;var a125=125;var a126=126;var a127=127;var a128=128;var a129=129;var a130=130;var a131=131;var a132=132;var a133=133;var a134=134;var a135=135;var a136=136;var a137=137;var a138=138;var a139=139;var a140=140;var a141=141;var a142=142;var a143=143;var a144=144;var a145=145;var a146=146;var a147=147;var a148=148;var a149=149;var a150=150;var a151=151;var a152=152;var a153=153;var a154=154;var a155=155;var a156=156;var a157=157;var a158=158;var a159=159;var a160=160;var a161=161;var a162=162;var a163=163;var a164=164;var a165=165;var a166=166;var a167=167;var a168=168;var a169=16
... (minified, truncated, 2,996 more characters)
```

### 2.8 web/greeter.ts {#sec-2-8}

File: `web/greeter.ts`

```typescript
// greeter.ts: a tiny TypeScript module (intomd fixture).
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

### 2.9 src/stockroom/\_\_init\_\_.py {#sec-2-9}

File: `src/stockroom/__init__.py`

```python
"""stockroom package."""
```

### 2.10 src/stockroom/inventory.py {#sec-2-10}

File: `src/stockroom/inventory.py`

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

### 2.11 src/stockroom/scale.py {#sec-2-11}

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

### 2.12 src/stockroom/helpers/.gitignore {#sec-2-12}

File: `src/stockroom/helpers/.gitignore`

```gitignore
scratch/
*.tmp
```

### 2.13 src/stockroom/helpers/units.py {#sec-2-13}

File: `src/stockroom/helpers/units.py`

```python
CM_PER_INCH = 2.54
GRAMS_PER_OUNCE = 28.35
```

### 2.14 src/stockroom/proto/item_pb2.py {#sec-2-14}

File: `src/stockroom/proto/item_pb2.py`

```python
# Generated by the protocol buffer compiler.  DO NOT EDIT!
ITEM = 1
```

### 2.15 docs/notes_utf16.txt {#sec-2-15}

File: `docs/notes_utf16.txt`

```text
Notes in UTF-16: café, naïve, 日本語.
```

### 2.16 tests/test_inventory.py {#sec-2-16}

File: `tests/test_inventory.py`

```python
from stockroom.inventory import Inventory, Item


def test_low_stock() -> None:
    inv = Inventory()
    inv.add(Item("A-1", "Widget", 1))
    assert [i.sku for i in inv.low_stock()] == ['A-1']
```

### 2.17 tests/fixtures/creds.txt {#sec-2-17}

File: `tests/fixtures/creds.txt`

```text
# Test credentials accidentally committed (fake values, intomd fixture).
aws_secret_access_key = [REDACTED:aws_secret_access_key]
auth_token: '[REDACTED:generic_secret]'
```
