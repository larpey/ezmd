"""Web family: static HTML pages (docs/spec/part2.md section 5, web/pages). Site crawling (section 6) and JS
rendering are Phase 3."""

from __future__ import annotations

import importlib.util
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from intomd.registry import Converter, Unavailable

CHAINS: dict[str, list[str]] = {
    "text/html": ["web.trafilatura", "web.rules", "web.html_raw"],
    "application/xhtml+xml": ["web.trafilatura", "web.rules", "web.html_raw"],
}


def converters() -> list[Converter | Unavailable]:
    from intomd.registry import Unavailable
    from intomd_converters.web.engines import FullBodyConverter, RulesConverter, TrafilaturaConverter

    out: list[Converter | Unavailable] = [RulesConverter(), FullBodyConverter()]
    if importlib.util.find_spec("trafilatura") is None:
        out.insert(
            0,
            Unavailable(
                id="web.trafilatura",
                family="web",
                reason="trafilatura is not installed",
                mimes=("text/html", "application/xhtml+xml"),
            ),
        )
    else:
        out.insert(0, TrafilaturaConverter())
    return out
