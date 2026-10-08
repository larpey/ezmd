"""ezmd_mcp.paging: token-budgeted pages over the renderer's opaque cursor.

The renderer already splits on section boundaries (never inside a table or code block) and marks a cut
page with `truncation.next_cursor` in the frontmatter. This module only:

- fits a page under the caller's `max_tokens` *including* the frontmatter on page 1 (it re-renders with a
  smaller body budget when the frontmatter pushes the page over), and
- wraps the renderer cursor in an MCP cursor that also binds the job id, the profile and the page number,
  so a cursor from another job or profile is rejected with a clear error.

Concatenating the bodies of every page (minus the continuation note) rebuilds the unpaged body.
"""

from __future__ import annotations

import base64
import json
import math
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from ezmd_mcp.errors import ToolFailure, suggestion_for

__all__ = [
    "CURSOR_VERSION",
    "DEFAULT_MAX_TOKENS",
    "MAX_MAX_TOKENS",
    "MIN_MAX_TOKENS",
    "McpCursor",
    "Outline",
    "RenderedPage",
    "build_page",
    "decode_cursor",
    "encode_cursor",
    "warning_dict",
]

CURSOR_VERSION = 1
DEFAULT_MAX_TOKENS = 8000
MAX_MAX_TOKENS = 50_000
MIN_MAX_TOKENS = 256
_FIT_ATTEMPTS = 4


@dataclass(frozen=True, slots=True)
class McpCursor:
    job_id: str
    profile: str
    page: int
    inner: str
    """The renderer's own opaque cursor (frontmatter `truncation.next_cursor`)."""


def encode_cursor(c: McpCursor) -> str:
    raw = json.dumps(
        {"v": CURSOR_VERSION, "job": c.job_id, "profile": c.profile, "page": c.page, "r": c.inner},
        separators=(",", ":"),
        sort_keys=True,
    )
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii").rstrip("=")


def decode_cursor(cursor: str) -> McpCursor | None:
    """The MCP cursor, or None when `cursor` is not one (it may be a bare renderer cursor)."""
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        data = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))
    except (ValueError, UnicodeError):
        return None
    if not isinstance(data, dict) or data.get("v") != CURSOR_VERSION or "job" not in data:
        return None
    job, profile, page, inner = data.get("job"), data.get("profile"), data.get("page"), data.get("r")
    if not (isinstance(job, str) and isinstance(profile, str) and isinstance(inner, str)):
        return None
    if not isinstance(page, int) or isinstance(page, bool) or page < 1:
        return None
    return McpCursor(job, profile, page, inner)


def check_max_tokens(value: int | None) -> int:
    if value is None:
        return DEFAULT_MAX_TOKENS
    if not MIN_MAX_TOKENS <= value <= MAX_MAX_TOKENS:
        raise ToolFailure("invalid_request", f"max_tokens must be between {MIN_MAX_TOKENS} and {MAX_MAX_TOKENS}.")
    return value


def warning_dict(w: dict[str, Any]) -> dict[str, Any]:
    """A warning as the tools report it: the renderer's fields verbatim, `kind` exposed as `code`, plus the
    shared suggested action."""
    out = {k: v for k, v in w.items() if v not in (None, {}, [])}
    code = str(out.pop("kind", out.get("code", "other")))
    return {"code": code, **out, "suggestion": suggestion_for(code)}


@dataclass(slots=True)
class RenderedPage:
    """One rendering from a backend: Markdown with frontmatter, the body alone, and the frontmatter map."""

    markdown: str
    body: str
    frontmatter: dict[str, Any]
    warnings: list[dict[str, Any]]
    over_budget: bool = False
    """Set by fit_page when even the smallest page the renderer produces exceeds max_tokens (page 1 of a
    document whose contents list alone is larger than the budget)."""

    @property
    def next_inner(self) -> str | None:
        trunc = self.frontmatter.get("truncation")
        if isinstance(trunc, dict):
            nxt = trunc.get("next_cursor")
            return nxt if isinstance(nxt, str) and nxt else None
        return None


@dataclass(slots=True)
class Outline:
    """Whole-document facts for page 1: the section list and the unpaged body token count."""

    sections: list[dict[str, Any]] = field(default_factory=list)
    tokens_total: int = 0


RenderFn = Callable[[str | None, int], Awaitable[RenderedPage]]
"""(renderer cursor or None, body token budget) -> page."""


def count_tokens(text: str) -> int:
    from ezmd.render.tokens import count_o200k

    return count_o200k(text)


async def fit_page(render: RenderFn, inner: str | None, max_tokens: int, *, with_frontmatter: bool) -> RenderedPage:
    """Render the page at `inner` so its returned text is at most `max_tokens` o200k tokens (or the smallest
    page the renderer can produce: it always keeps at least one unit)."""
    budget = max_tokens
    page = await render(inner, budget)
    for _ in range(_FIT_ATTEMPTS):
        used = count_tokens(page.markdown if with_frontmatter else page.body)
        if used <= max_tokens:
            return page
        if budget <= MIN_MAX_TOKENS // 4:
            break
        budget = max(MIN_MAX_TOKENS // 4, budget - (used - max_tokens) - 32)
        page = await render(inner, budget)
    page.over_budget = count_tokens(page.markdown if with_frontmatter else page.body) > max_tokens
    return page


def build_page(
    *,
    job_id: str,
    profile: str,
    page_no: int,
    page: RenderedPage,
    outline: Outline,
    max_tokens: int,
) -> dict[str, Any]:
    """The structured tool result for one page (docs/spec/part4.md 4.4.2)."""
    nxt = page.next_inner
    next_cursor = encode_cursor(McpCursor(job_id, profile, page_no + 1, nxt)) if nxt else None
    if next_cursor is None:
        pages_total, estimated = page_no, False
    else:
        pages_total = max(page_no + 1, math.ceil(outline.tokens_total / max(max_tokens, 1)))
        estimated = True
    fm = page.frontmatter
    out: dict[str, Any] = {
        "job_id": job_id,
        "status": "done",
        "title": fm.get("title"),
        "source": fm.get("source"),
        "profile": profile,
        "tokens_total": outline.tokens_total,
        "pages_total": pages_total,
        "pages_total_estimated": estimated,
        "page": page_no,
        "next_cursor": next_cursor,
        "warnings": page.warnings,
        "frontmatter": fm,
        "content": page.body,
    }
    if page.over_budget:
        out["over_budget"] = True
    if page_no == 1:
        out["sections"] = outline.sections
    return out


def page_text(result: dict[str, Any], markdown: str) -> str:
    """The text block shown to the model: page 1 carries the frontmatter; every page names the next cursor."""
    text = markdown if result["page"] == 1 else str(result["content"])
    nxt = result.get("next_cursor")
    footer = f"[page {result['page']} of ~{result['pages_total']}"
    if nxt:
        footer += f'; call get_job(job_id="{result["job_id"]}", cursor="{nxt}") for the next page]'
    else:
        footer += "; last page]"
    codes = sorted({str(w.get("code")) for w in result.get("warnings", [])})
    if codes:
        footer += " warnings: " + ", ".join(codes)
    return text.rstrip("\n") + "\n\n" + footer + "\n"


def sections_from_sidecar(sidecar: dict[str, Any] | None, body: str) -> list[dict[str, Any]]:
    """[{id, heading, level, tokens}] from the sidecar's section offsets (UTF-8 byte offsets into `body`)."""
    if not sidecar:
        return []
    raw = body.encode("utf-8")
    out: list[dict[str, Any]] = []
    for s in sidecar.get("sections", []) or []:
        if not isinstance(s, dict):
            continue
        start, end = s.get("offset_start"), s.get("offset_end")
        tokens = 0
        if isinstance(start, int) and isinstance(end, int) and 0 <= start <= end:
            tokens = count_tokens(raw[start:end].decode("utf-8", errors="ignore"))
        out.append({"id": s.get("id"), "heading": s.get("title"), "level": s.get("level"), "tokens": tokens})
    return out
