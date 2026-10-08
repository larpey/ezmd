"""intomd_api.ircache: the fingerprint that decides whether a finished job's cached IR may be served
again (dedup, docs/spec/part1.md 7.1; DECISIONS.md D-0017 item 6).

The key covers the IR `schema_version`, the converter id and the version of the package that ships
it, and the intomd core version, so an upgrade never serves IR produced by older code.
"""

from __future__ import annotations

import importlib.metadata
import sys
from functools import lru_cache

from intomd_api.db import JobRow
from intomd_api.util import canonical_json, sha256_hex


def current_schema_version() -> str:
    from intomd.ir import Document

    return str(Document.model_fields["schema_version"].default)


def _package_version(module_name: str) -> str:
    root = module_name.split(".", 1)[0]
    module = sys.modules.get(root)
    version = getattr(module, "__version__", None)
    if isinstance(version, str) and version:
        return version
    try:
        return importlib.metadata.version(root.replace("_", "-"))
    except importlib.metadata.PackageNotFoundError:
        return "0"


@lru_cache(maxsize=256)
def converter_version(converter_id: str) -> str:
    """`Converter.version` when a converter declares one, else its distribution's version."""
    try:
        from intomd.registry import default_registry

        conv = default_registry().get(converter_id)
    except Exception:
        return "unknown"
    declared = getattr(conv, "version", None)
    if isinstance(declared, str) and declared:
        return declared
    return _package_version(type(conv).__module__)


def engine_version() -> str:
    import intomd

    return str(getattr(intomd, "__version__", "0"))


def ir_cache_key(schema_version: str, converter_id: str) -> str:
    payload = {
        "schema_version": schema_version,
        "converter_id": converter_id,
        "converter_version": converter_version(converter_id),
        "intomd": engine_version(),
    }
    return sha256_hex(canonical_json(payload))


def is_fresh(row: JobRow) -> bool:
    """True when `row`'s cached IR was produced by the schema, converter, and engine running now."""
    if not row.ir_cache_key or not row.converter_id:
        return False
    return row.ir_cache_key == ir_cache_key(current_schema_version(), row.converter_id)
