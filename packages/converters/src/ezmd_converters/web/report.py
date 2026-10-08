"""Warnings for a converted web page (part2 5c steps 8, 9, 12, 16 and 5e; part3 section 18 phase 1)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ezmd.ir import Metadata, Warning, WarningKind
from ezmd_converters.web import signals
from ezmd_converters.web.build import Builder

if TYPE_CHECKING:
    from ezmd_converters.web.pipeline import Page

PAYWALL_MAX_CHARS = 600


def _hidden_warnings(page: Page) -> list[Warning]:
    out: list[Warning] = []
    h = page.hygiene
    if h.elements:
        detail: dict[str, str | int | float] = {f"type.{k}": v for k, v in sorted(h.by_type.items())}
        detail["elements"] = h.elements
        detail["hidden_text"] = h.hidden_joined()
        kinds = ", ".join(sorted(h.by_type))
        out.append(
            Warning(
                kind=WarningKind.REMOVED_HIDDEN_ELEMENTS,
                message=f"Removed {h.elements} hidden elements ({kinds}); their text is in the sidecar.",
                count=h.elements,
                detail=detail,
            )
        )
    if h.chars.total:
        out.append(
            Warning(
                kind=WarningKind.REMOVED_HIDDEN_ELEMENTS,
                message=f"Removed {h.chars.total} zero-width, bidi-control, or control characters.",
                count=h.chars.total,
                detail={"invisible_chars": h.chars.invisible, "control_chars": h.chars.control},
            )
        )
    return out


def page_warnings(page: Page, b: Builder, extracted: int, metadata: Metadata) -> list[Warning]:
    out = _hidden_warnings(page)
    if page.truncated:
        out.append(
            Warning(
                kind=WarningKind.SIZE_CAP,
                message="The page exceeded the HTML size cap; only the beginning was converted.",
                detail={"how_to_raise": "raise the web converter's max_bytes limit (self-host)"},
            )
        )
    if signals.is_js_shell(page.sig, page.clean_chars) and extracted < signals.SHELL_TEXT_CHARS:
        out.append(
            Warning(
                kind=WarningKind.EMPTY_BODY_JS_REQUIRED,
                message="The page has no content without JavaScript; it needs browser rendering.",
                detail={"script_bytes": page.sig.script_bytes, "root": page.sig.spa_root or ""},
            )
        )
    triggers: list[str] = []
    if page.meta.jsonld_paywalled:
        triggers.append("jsonld_isAccessibleForFree")
    if page.sig.paywall_markers:
        triggers.append("selector:" + page.sig.paywall_markers[0])
    if signals.wall_phrase(page.full_text):
        triggers.append("wall_phrase")
    if triggers and extracted < PAYWALL_MAX_CHARS:
        out.append(
            Warning(
                kind=WarningKind.PAYWALL_DETECTED,
                message="This page appears to be paywalled; only the free preview was captured.",
                detail={"triggers": ", ".join(triggers), "wall_prompts_removed": page.walls_removed},
            )
        )
    label = signals.multipage_label(page.full_text)
    if page.meta.next_page or label:
        if page.meta.next_page:
            metadata.extra["next_page"] = page.meta.next_page
        out.append(
            Warning(
                kind=WarningKind.MULTIPAGE_ARTICLE,
                message="The article continues on another page, which was not fetched.",
                detail={"next_page": page.meta.next_page or "", "label": label or ""},
            )
        )
    if b.lazy_images or page.sig.infinite_scroll:
        out.append(
            Warning(
                kind=WarningKind.LAZY_CONTENT_POSSIBLE,
                message="The page loads some content lazily; images or sections may be missing without rendering.",
                detail={"lazy_images": b.lazy_images, "infinite_scroll": int(page.sig.infinite_scroll)},
            )
        )
    if b.images_without_alt:
        out.append(
            Warning(
                kind=WarningKind.IMAGES_WITHOUT_ALT,
                message=f"{b.images_without_alt} images have no alt text or caption; they are labeled 'image'.",
                count=b.images_without_alt,
            )
        )
    if not b.blocks and not any(w.kind == WarningKind.EMPTY_BODY_JS_REQUIRED for w in out):
        out.append(Warning(kind=WarningKind.EXTRACTION_EMPTY, message="No text could be extracted from the page."))
    return out
