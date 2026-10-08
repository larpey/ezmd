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
