"""Built-in converters for intomd.

Each converter family is a subpackage (`intomd_converters.<family>`) that exposes:

- `converters() -> list[Converter | Unavailable]`: instances to register. A converter whose optional
  engine is not installed is returned as `intomd.registry.Unavailable(...)` so capabilities can list it
  with the reason and the extra that provides it (docs/spec/part4.md 4.3.3).
- `CHAINS: dict[str, list[str]]`: fallback chains for the mimes the family owns (docs/spec/part1.md 5.3).

Families are discovered automatically, so adding a family never edits a shared list (D-0020). One family
failing to import never takes down the others; the failure is recorded as an unavailable entry.
"""

from __future__ import annotations

import importlib
import logging
import pkgutil
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from intomd.registry import Converter, Unavailable

log = logging.getLogger(__name__)


def family_names() -> list[str]:
    return sorted(m.name for m in pkgutil.iter_modules(__path__) if m.ispkg and not m.name.startswith("_"))


def builtin_converters() -> list[Converter | Unavailable]:
    from intomd.registry import Unavailable

    out: list[Converter | Unavailable] = []
    for name in family_names():
        try:
            mod = importlib.import_module(f"{__name__}.{name}")
            out.extend(mod.converters())
        except Exception as e:
            log.warning("converter family %s failed to load: %s", name, e)
            out.append(Unavailable(id=f"{name}.family", family=name, reason=f"family failed to load: {e}"))
    return out


def builtin_chains() -> dict[str, list[str]]:
    chains: dict[str, list[str]] = {}
    for name in family_names():
        try:
            mod = importlib.import_module(f"{__name__}.{name}")
        except Exception:
            continue
        for mime, ids in getattr(mod, "CHAINS", {}).items():
            if mime in chains:
                raise ValueError(f"mime {mime} has a chain in two families ({name} and another)")
            chains[mime] = list(ids)
    return chains
