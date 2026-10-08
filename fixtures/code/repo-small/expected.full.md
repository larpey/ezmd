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
word_count: 2077
tokens: {o200k_base: 8501, cl100k_base: 8489, claude_approx: 9181}
content_hash: "sha256:6bc1c7bd7acbbac05995f0636ff960079cb91d687ec8c7d95c837513f2057f28"
source_hash: "sha256:d5cb67b3cb91d8b18f097242d579ec82dfd0422b3fe457d302f497546239efe9"
truncated: false
warnings: [secret_file_excluded, secret_redacted, archive_entry_skipped]
description: "Tiny inventory service (ezmd fixture)."
injection_risk: none
extra:
  bytes: 25306
  excluded.binary: 1
  excluded.default_excluded: 3
  excluded.gitignored: 4
  excluded.minified: 1
  excluded.secret_file: 2
  files: 17
  languages: "python, javascript, typescript"
  license_file: LICENSE
  packed_bytes: 19275
  project: stockroom
  repo: stockroom
  tokens: 7199
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

17 files packed (25,306 source bytes, 7,199 tokens). Languages: python 68%, javascript 30%, typescript 2%. Not packed: 1 binary; 3 in default-excluded directories; 4 ignored by .gitignore/.ezmdignore; 1 minified or source maps; 2 credential files.

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

### 2.6 uv.lock {#sec-2-6}

File: `uv.lock`

```text
package-000==1.0.0 --hash=sha256:a76a5c8b7e5bd2f0fb24edec7e60f3538d0e8dbd9f3fd53dfb22e571fe5cfa9a
package-001==1.1.0 --hash=sha256:af17dcff995e3eb0d7ab88fa06c86f574d385fafc3e1523911b49a7c9abe2132
package-002==1.2.0 --hash=sha256:2f2c57de7be0ac79ae0e0c62434f4db86018a3dc40c2348804e5b34f991907f8
package-003==1.3.0 --hash=sha256:88ce3b4398872482ac505ae51016af9bcf9233c1b266477ea55470f525543a22
package-004==1.4.0 --hash=sha256:9ac02017315f29273c0900fb49d1b97a9c92c5eb2a4ddc67ce281c1d24df3756
package-005==1.5.0 --hash=sha256:cecd219bb550231193d5ab5f88c05a224ef0e05999ca9641a72765537a4a5110
package-006==1.6.0 --hash=sha256:4026d1b0c0494cef3d638f0163e508b1853d65a2a460cea770a2e7fc6d0e2a81
package-007==1.7.0 --hash=sha256:c98dc8c2dc75e2a4a48326aed460926adb32a32acd8654bea5d270d2449dcdc0
package-008==1.8.0 --hash=sha256:95de0cc0f72ae9fcfff8f31d64ed1ec1632d6586e1904c841ee55c22a768561b
package-009==1.9.0 --hash=sha256:213e8ae63da0dcd800f7e086feb53aca4bb46e32b9468e009b126b4b39eadc7a
package-010==1.10.0 --hash=sha256:c3f060bdebda9a3d53b1b1a5a19279188fe511f4f0eda7b68a785ef7523070d9
package-011==1.11.0 --hash=sha256:e009a4641b6d02e6c22d336263a637c8fd840444cb8623d74a8a7c033c5828d6
package-012==1.12.0 --hash=sha256:6a38c87a412155a5faec791b3ae3b598fd30da77651094625972e0e1e50af5df
package-013==1.13.0 --hash=sha256:91f42d275eb779ca7c16fc2426d6a2b589d6de4a2873e398c2f7807c4e99e7ee
package-014==1.14.0 --hash=sha256:ecfd1d5b14e2a0b1ecfc56a21f078e7a12d0e4d27b234de52fe8490467fcaeac
package-015==1.15.0 --hash=sha256:a69b6fc5378b5ea158c7994c51cbe1d119a5fb4fc1c0680dcda3a20f74394ca3
package-016==1.16.0 --hash=sha256:b7ec6af4e39cd515b50806f562030b2ce0ad079693d69b4c544bf92afa85d083
package-017==1.17.0 --hash=sha256:3d81d6aa20ce52f36582877c2d1d22cabbc884ea98285dbd63be3eb846e41ff3
package-018==1.18.0 --hash=sha256:3de5673df7fa4eaaee392bc8baa196574b4f7d305a391ecafc0f96855bd97fdb
package-019==1.19.0 --hash=sha256:9aae1c398ed197bdf47b863721bcdcbcb3322df09da310ef1d9384bdce999932
package-020==1.20.0 --hash=sha256:9188ee31575f1b9ab807cad2303c16d3f52673e0de82043daa30a6bc314b617a
package-021==1.21.0 --hash=sha256:bfe56c4c756cf46b5a1ab1a04f6476c692d8353d5007451949510c73a431c371
package-022==1.22.0 --hash=sha256:1c5d9d39b933534e0bd6ed184cb201e94842b14ed9e2cf29a381c2a2558d0de4
package-023==1.23.0 --hash=sha256:c03c28a3cd64587f47331e55c4cf8244ea65cc7ae02a1b2c56ea72b536fcbc15
package-024==1.24.0 --hash=sha256:29684c9a7c187bcbf9607a9636a942866ce7da603674cc6138c290994bfecb65
package-025==1.25.0 --hash=sha256:a60f77600dcb387fa66fc195c06f2a5c895d154239b6fb3ff4c820f2fb3aeb12
package-026==1.26.0 --hash=sha256:07d1d404a284730ccdddeea0195d62988310c486e54a461d758514bf1c408b24
package-027==1.27.0 --hash=sha256:ea51d8d69eccdef3c6932eaac06bdc17806cad41b41063d02b68ce5f2e9aefe1
package-028==1.28.0 --hash=sha256:b48f9281bf99eb5a28fef513106b59efa598be5587adb4592bc2118dd29960b4
package-029==1.29.0 --hash=sha256:061bdeff7effca83b0f1ad36e239ac131f3bc70797209ac2605be922afc9eae0
package-030==1.30.0 --hash=sha256:36199357412e83f2b5dcc66b79e0697c34b7c1581ce6d236f94b3d25ad929f86
package-031==1.31.0 --hash=sha256:e4941f158221b8f640ad3b6127a17d5accbec1fb831d20aa5ab46c04f8f33df7
package-032==1.32.0 --hash=sha256:f922473f589d9aa9a6347dfa43c202021fe712c62d2c068f8ceaccca5d5e48f2
package-033==1.33.0 --hash=sha256:8d4afaefdd72232dea1ca54084ff9773e5d8fe866b3acce0e0b135b4166a6955
package-034==1.34.0 --hash=sha256:849efe9ae25c7a0679a917c1a3c516150bf16b80f9b64a02c5068686f3510076
package-035==1.35.0 --hash=sha256:74bd922ffdcc0811f27a7484e59d733ad7037b7bd332eee4b65605eaaf364ce0
package-036==1.36.0 --hash=sha256:8f79157e8adeb41a650c6e223a27f000dd9b9af3a44904ed22097e62126e67cc
package-037==1.37.0 --hash=sha256:4a532b70434d0dfd0e51a6cb1a45d7279549d4277edc96751fc335700e5a7af1
package-038==1.38.0 --hash=sha256:0aef8b8b17fc2d0fce92c688450171109d3825a446242e678edbf6e835a268bd
package-039==1.39.0 --hash=sha256:040178e7141870955b0bf681b925e87441dbd908fdcc4cbea3a5d1a8d8f3aa5e
package-040==1.40.0 --hash=sha256:d6e658d6ddb379bdf0ff5ad6844ed303a86020c7c92c294524e4b8115496bac3
package-041==1.41.0 --hash=sha256:62e06921e4b5d6cfcaf07b471e55458c88862589672fe66cf609e3fa8a125e21
package-042==1.42.0 --hash=sha256:316684cba58a89a22e6a322479a6707c20fd4f5237621cc8a41083cb6d2c475a
package-043==1.43.0 --hash=sha256:595e04c6e2e9516d18094000cef496cebbeec5536507f1907287eb03352aa09b
package-044==1.44.0 --hash=sha256:752fc289c6bfad823a5aeb4e1a6d764ef366f1d4548dddf678174fa36f383f53
package-045==1.45.0 --hash=sha256:ab42cc9046242565f74bb4533e53df67318b288a9b8a17a806e924878860e0af
package-046==1.46.0 --hash=sha256:019e5d59b018d3425594ee4854f1fab59e503419ff3c62e0163ebc60f80c923c
package-047==1.47.0 --hash=sha256:7cd1eb01f99e8827eff9a4498212bfd7612fb61f1875da38e5e99f9efbae1c13
package-048==1.48.0 --hash=sha256:f6f30a8416177b22ebb24b1e061d37d4e3f638eb85137aa31a282f6edb26b200
package-049==1.49.0 --hash=sha256:24f5ebc8ff29da060891601a1464d45a356fb4d0a0e77232773c450ea24dad53
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

### 2.9 src/stockroom/\_\_init\_\_.py {#sec-2-9}

File: `src/stockroom/__init__.py`

```python
"""stockroom package."""
```

### 2.10 src/stockroom/inventory.py {#sec-2-10}

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
# Test credentials accidentally committed (fake values, ezmd fixture).
aws_secret_access_key = [REDACTED:aws_secret_access_key]
auth_token: '[REDACTED:generic_secret]'
```
