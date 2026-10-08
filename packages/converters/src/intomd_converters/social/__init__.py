"""Social and forum family, Phase 1 stub (docs/spec/part2.md section 7; ROADMAP P1-T07, full adapters P3-T02).

Behind the family flag `INTOMD_ENABLE_SOCIAL` (off by default). Off: the Reddit and Hacker News converters are
registered as `Unavailable`, so capabilities list them with the reason and their URLs fall through to the
web family. On (self-host testing only): experimental stub converters claim thread URLs, ask the pipeline
for the sanctioned JSON API response with `FetchRequired`, and render it through the shared thread model.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from intomd.registry import Converter, Unavailable

CHAINS: dict[str, list[str]] = {}
FLAG_ENV = "INTOMD_ENABLE_SOCIAL"
IDS = {"reddit": "web.social_reddit", "hackernews": "web.social_hn"}


def enabled(env: dict[str, str] | None = None) -> bool:
    return (env if env is not None else os.environ).get(FLAG_ENV, "").strip().lower() in ("1", "true", "yes", "on")


def converters(env: dict[str, str] | None = None) -> list[Converter | Unavailable]:
    from intomd.registry import Unavailable
    from intomd_converters.social.adapters import ADAPTERS
    from intomd_converters.social.converter import SocialStubConverter

    if enabled(env):
        return [SocialStubConverter(a, IDS[a.name]) for a in ADAPTERS]
    reason = (
        f"the social family is disabled (set {FLAG_ENV}=1 to try the Phase 1 stubs); "
        "full Reddit and Hacker News adapters ship in Phase 3"
    )
    return [Unavailable(id=IDS[a.name], family="web", reason=reason) for a in ADAPTERS]
