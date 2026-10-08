"""Pagination acceptance (docs/spec/part4.md 4.4.6): page 1 fits max_tokens, and walking every cursor
rebuilds the full body byte for byte."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import tiktoken
from conftest import call, make_server, text_of, unwrap
from mcp import Client

import intomd


def long_document(sections: int = 300) -> str:
    """A 300-section report (one section per 'page' of a long PDF) with tables and code blocks."""
    parts = ["# Annual operations report", ""]
    for i in range(1, sections + 1):
        parts += [f"## Section {i}: depot {i % 17} review", ""]
        parts += [
            f"Paragraph {i} reports throughput, staffing and incidents for the period. "
            "Volumes rose while dwell time fell, and the night shift absorbed most of the overtime. " * 3,
            "",
        ]
        if i % 5 == 0:
            parts += ["| week | pallets | dwell |", "|---|---|---|"]
            parts += [f"| {w} | {100 + w * i} | {w + 0.5} |" for w in range(1, 9)]
            parts.append("")
        if i % 7 == 0:
            parts += ["```python", f"def total_{i}(rows):", "    return sum(r.pallets for r in rows)", "```", ""]
    return "\n".join(parts)


def _tokens(text: str) -> int:
    try:
        enc = tiktoken.get_encoding("o200k_base")
    except Exception:  # offline without a cached encoding: the renderer's own counter
        from intomd.render.tokens import count_o200k

        return count_o200k(text)
    return len(enc.encode(text, disallowed_special=()))


async def _walk(client: Client, first: Any, max_tokens: int, **extra: Any) -> list[dict[str, Any]]:
    pages = [first.structured_content]
    texts = [text_of(first)]
    for _ in range(500):
        nxt = pages[-1]["next_cursor"]
        if nxt is None:
            break
        res = await call(
            client, "get_job", {"job_id": pages[-1]["job_id"], "cursor": nxt, "max_tokens": max_tokens, **extra}
        )
        assert not res.is_error, text_of(res)
        pages.append(res.structured_content)
        texts.append(text_of(res))
    else:
        raise AssertionError("cursor walk did not terminate")
    for p, t in zip(pages, texts, strict=True):
        p["_text"] = t
    return pages


@pytest.mark.slow
async def test_long_file_pages_fit_budget_and_rebuild_body(root: Path) -> None:
    src = root / "report.md"
    src.write_text(long_document(), encoding="utf-8", newline="\n")
    async with Client(make_server(root)) as client:
        first = await call(client, "convert_file", {"path": str(src), "max_tokens": 8000})
        assert "over_budget" not in first.structured_content
        assert not first.is_error, text_of(first)
        page1 = first.structured_content
        assert page1["page"] == 1 and page1["next_cursor"]
        assert len(page1["sections"]) == 300
        assert page1["tokens_total"] > 8000
        pages = await _walk(client, first, 8000)
    assert len(pages) > 3
    assert [p["page"] for p in pages] == list(range(1, len(pages) + 1))
    assert pages[-1]["pages_total"] == len(pages) and pages[-1]["pages_total_estimated"] is False
    for p in pages:
        assert _tokens(p["_text"]) <= 8000, (p["page"], _tokens(p["_text"]))
        body = unwrap(p["content"])
        assert body.count("```") % 2 == 0, "a page split inside a code block"
        last = body.rstrip().split("\n")[-1]
        assert not (last.startswith("|") and p["next_cursor"] and body.endswith("|---|")), "split in a table"
    expected = intomd.convert(src, profile="agent").render("agent", max_tokens="none").body
    rebuilt = "\n\n".join(unwrap(p["content"]) for p in pages)
    assert rebuilt == unwrap(expected)


async def test_full_profile_walk_rebuilds_body(root: Path) -> None:
    src = root / "short.md"
    src.write_text(long_document(40), encoding="utf-8", newline="\n")
    async with Client(make_server(root)) as client:
        first = await call(client, "convert_file", {"path": str(src), "max_tokens": 2500, "profile": "full"})
        assert not first.is_error, text_of(first)
        pages = await _walk(client, first, 2500)
        # A cursor stays bound to its profile.
        wrong = await call(
            client,
            "get_job",
            {"job_id": pages[0]["job_id"], "cursor": pages[0]["next_cursor"], "profile": "agent"},
        )
        assert wrong.is_error and wrong.structured_content["error"]["code"] == "cursor_invalid"
    assert len(pages) >= 3
    for p in pages:
        assert _tokens(p["_text"]) <= 2500 and "over_budget" not in p
    expected = intomd.convert(src, profile="full").render("full", max_tokens="none").body
    assert "\n\n".join(unwrap(p["content"]) for p in pages) + "\n" == expected
    assert all("sections" not in p for p in pages[1:])


async def test_page_over_budget_is_flagged(root: Path) -> None:
    """The renderer keeps the head (orientation, contents) whole on page 1; when that alone exceeds the
    budget the page says so instead of silently overshooting."""
    src = root / "toc.md"
    src.write_bytes(long_document(60).encode("utf-8"))
    async with Client(make_server(root)) as client:
        res = await call(client, "convert_file", {"path": str(src), "max_tokens": 400, "profile": "full"})
    assert not res.is_error
    assert res.structured_content["over_budget"] is True
    assert res.structured_content["next_cursor"]
