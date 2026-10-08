"""Page-level signals measured on the raw tree before hygiene: JavaScript-only shells, paywall markers, lazy
or infinite-scroll content (part2 5b step 5, 5c step 9, 5e items 4 to 8)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from intomd_converters.web.dom import HtmlElement, collapse, is_element

_ROOT_IDS = frozenset({"root", "app", "__next", "___gatsby", "__nuxt", "svelte"})
_PAYWALL_CLASS = re.compile(
    r"(^|[\s_-])(paywall|meteredcontent|metered-content|tp-modal|piano|subscriber-only|premium-content|regwall)"
    r"([\s_-]|$)",
    re.I,
)
_PAYWALL_ID = re.compile(r"^(piano-|paywall|regwall)", re.I)
_WALL_PHRASE = re.compile(
    r"\b(subscribe|subscription|sign in|log in|continue reading|already a subscriber|members only)\b", re.I
)
_INFINITE = re.compile(r"infinite[-_]?scroll|load[-_]?more|endless", re.I)
SCRIPT_BYTES_JS_SHELL = 50 * 1024
SHELL_TEXT_CHARS = 300


@dataclass(slots=True)
class Signals:
    script_bytes: int = 0
    script_count: int = 0
    spa_root: str | None = None
    paywall_markers: list[str] = field(default_factory=list)
    infinite_scroll: bool = False


def measure(root: HtmlElement) -> Signals:
    sig = Signals()
    for sc in root.iter("script"):
        typ = (sc.get("type") or "").lower()
        if typ in ("application/ld+json", "application/json") or typ.startswith("math/"):
            continue
        sig.script_count += 1
        sig.script_bytes += len(sc.text or "")
    body = root.find("body")
    scope = body if body is not None else root
    for el in scope.iter():
        if not is_element(el):
            continue
        el_id = (el.get("id") or "").strip()
        if sig.spa_root is None and (el_id in _ROOT_IDS or el.get("data-reactroot") is not None):
            sig.spa_root = f"#{el_id}" if el_id else "[data-reactroot]"
        classes = el.get("class") or ""
        if _PAYWALL_CLASS.search(classes) or _PAYWALL_ID.match(el_id) or el.get("data-paywall") is not None:
            sig.paywall_markers.append(classes.split()[0] if classes.split() else el_id or "data-paywall")
        if _INFINITE.search(classes) or _INFINITE.search(el_id) or el.get("data-infinite-scroll") is not None:
            sig.infinite_scroll = True
    return sig


def remove_walls(body: HtmlElement) -> int:
    """Remove paywall and registration-wall prompts (a paywall-marked element with under 400 characters of
    subscribe or sign-in text) so the prompt is not converted as article text. Marked containers that hold
    real content are left alone. Returns how many were removed."""
    removed = 0
    for el in list(body.iter()):
        if not is_element(el) or el.getparent() is None:
            continue
        el_id = (el.get("id") or "").strip()
        marked = _PAYWALL_CLASS.search(el.get("class") or "") or _PAYWALL_ID.match(el_id)
        if not marked and el.get("data-paywall") is None:
            continue
        if wall_phrase(visible_text(el)):
            el.drop_tree()
            removed += 1
    return removed


def is_js_shell(sig: Signals, visible_chars: int) -> bool:
    """Static HTML that needs JavaScript to show content (part2 5b step 5 trigger, without rendering)."""
    if visible_chars >= SHELL_TEXT_CHARS:
        return False
    return (
        sig.script_bytes > SCRIPT_BYTES_JS_SHELL
        or sig.spa_root is not None
        or (visible_chars < 40 and sig.script_count > 0)
    )


def wall_phrase(text: str) -> bool:
    return len(text) < 400 and bool(_WALL_PHRASE.search(text))


def multipage_label(body_text: str) -> str | None:
    m = re.search(r"\bpage\s+(\d{1,3})\s+of\s+(\d{1,3})\b", body_text, re.I)
    return m.group(0) if m else None


def visible_text(el: HtmlElement) -> str:
    return collapse(el.text_content() or "")
