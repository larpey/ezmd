"""ezmd_api.fetchpolicy: platform policy lookups shared by job creation, the worker, and the
fetch-node claim (docs/spec/part1.md 8.3, DECISIONS.md D-0017 items 4 and 6).

Residential routing is decided here and only here: a host whose policy is `residential_only`, or a
keyed caller whose key has the residential permission and who asked for it. Nothing a converter
child reports (its `residential` flag) and nothing an anonymous caller sends (`prefer_residential`)
can route a job to the home fetch node.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ezmd_api.settings import Settings

if TYPE_CHECKING:
    from ezmd.core.netguard import PlatformPolicy

DISABLED = "disabled"
RESIDENTIAL_ONLY = "residential_only"


def load_policy(settings: Settings) -> PlatformPolicy | None:
    if not settings.platforms_file:
        return None
    from ezmd.core.netguard import PlatformPolicy

    return PlatformPolicy.load(settings.platforms_file)


def policy_state(settings: Settings, host: str) -> str:
    policy = load_policy(settings)
    return policy.state(host) if policy is not None else "default"


def platform_for(settings: Settings, host: str) -> str | None:
    """The most specific policy entry matching `host` (for example `youtube.com`), or None."""
    policy = load_policy(settings)
    if policy is None:
        return None
    h = host.lower().rstrip(".")
    best: str | None = None
    for key in policy.hosts:
        if (h == key or h.endswith("." + key)) and (best is None or len(key) > len(best)):
            best = key
    return best


def wants_residential(state: str, *, prefer_residential: bool, keyed: bool, key_residential_allowed: bool) -> bool:
    """D-0017 item 6: anonymous `prefer_residential` is ignored."""
    if state == RESIDENTIAL_ONLY:
        return True
    return prefer_residential and keyed and key_residential_allowed
