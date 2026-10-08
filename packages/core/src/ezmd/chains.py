"""ezmd.chains: default fallback chains per mime type (docs/spec/part1.md section 5.3).

Exact keys are matched before wildcard keys (`audio/*`). Each converter family declares the chains for
the mimes it owns in `ezmd_converters.<family>.CHAINS` (D-0020); `DEFAULT_CHAINS` holds only chains
that span families or exist without ezmd-converters installed.
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)

DEFAULT_CHAINS: dict[str, list[str]] = {}


def default_chains() -> dict[str, list[str]]:
    chains = dict(DEFAULT_CHAINS)
    try:
        from ezmd_converters import builtin_chains
    except ImportError:
        return chains
    for mime, ids in builtin_chains().items():
        if mime in chains:
            log.warning("family chain for %s overrides the core default", mime)
        chains[mime] = ids
    return chains
