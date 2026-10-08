"""Profiles and overrides, frontmatter order and quoting, token counting, budgets and cursors."""

from __future__ import annotations

import base64
import json
import re
from datetime import UTC, datetime

import pytest
from render_builders import CONVERTED_AT, harbor_lane, heading, make_result, para

from intomd.ir import ConversionResult, Warning, WarningKind
from intomd.profiles import AGENT, COMPACT, FULL, PROFILES, RAG, Profile, get_profile
from intomd.render import count_tokens, render
from intomd.render import tokens as tokmod
from intomd.render.assemble import decode_cursor, encode_cursor
from intomd.render.frontmatter import COMPACT_KEYS, KEY_ORDER, dump_yaml


def test_profiles_registry_and_distinctive_defaults() -> None:
    assert set(PROFILES) == {"full", "compact", "rag", "agent"}
    assert PROFILES["full"] is FULL and isinstance(FULL, Profile)
    assert not COMPACT.number_headings and not COMPACT.anchors and not COMPACT.page_markers
    assert COMPACT.links == "numbered_list" and COMPACT.max_tokens == 16_000 and not COMPACT.sidecar
    assert RAG.chunks.enabled and RAG.links == "text_only" and RAG.footnotes == "inline" and not RAG.image_comments
    assert AGENT.untrusted_fence and AGENT.tables.csv_sidecar and AGENT.agent_salt == "deterministic"
    assert FULL.transcript.non_speech_italic and not AGENT.transcript.non_speech_italic


def test_get_profile_overrides_and_coercion() -> None:
    p = get_profile("rag", **{"chunks.chunk_tokens": "512", "number_headings": "false", "max_tokens": "none"})
    assert p.chunks.chunk_tokens == 512 and p.number_headings is False and p.max_tokens is None
    assert get_profile("compact", max_tokens="2000").max_tokens == 2000
    assert get_profile("full", numbered_headings="0", tables_csv="yes").tables.csv_sidecar is True
    assert get_profile("full", **{"transcript.paragraph_gap_seconds": "2.5"}).transcript.paragraph_gap_seconds == 2.5
    assert get_profile("full") is FULL
    with pytest.raises(ValueError, match="unknown profile option"):
        get_profile("full", bogus=1)
    with pytest.raises(ValueError, match="unknown profile option"):
        get_profile("full", **{"chunks.nope": 1})
    with pytest.raises(ValueError, match="expected one of"):
        get_profile("full", links="sometimes")
    with pytest.raises(ValueError, match="invalid integer"):
        get_profile("full", max_tokens="lots")
    with pytest.raises(ValueError, match="unknown profile"):
        get_profile("nope")
    with pytest.raises(ValueError):
        get_profile("full", name="rag")


def test_render_accepts_profile_object_and_overrides() -> None:
    out = render(harbor_lane(), FULL, anchors="false", converted_at="2026-10-08T15:02:13Z")
    assert "{#" not in out.body
    assert out.frontmatter["converted_at"] == "2026-10-08T15:02:13Z"
    with pytest.raises(ValueError):
        render(harbor_lane(), "full", converted_at="yesterday")


def test_frontmatter_key_order_and_compact_minimal_set() -> None:
    for profile in ("full", "rag", "agent"):
        keys = list(render(harbor_lane(), profile, converted_at=CONVERTED_AT).frontmatter)
        assert keys == [k for k in KEY_ORDER if k in keys]
    compact = list(render(harbor_lane(), "compact", converted_at=CONVERTED_AT).frontmatter)
    assert compact == [
        "title",
        "source",
        "source_type",
        "language",
        "word_count",
        "tokens",
        "content_hash",
        "warnings",
        "injection_risk",
        "profile",
    ]
    assert set(compact) <= set(COMPACT_KEYS)


def test_converted_at_defaults_to_now_utc_seconds() -> None:
    fm = render(harbor_lane(), "full").frontmatter
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", str(fm["converted_at"]))
    assert fm["fetched_at"] == "2026-10-08T15:02:11Z"


def test_yaml_quoting_and_styles() -> None:
    text = dump_yaml(
        {
            "title": "Plain",
            "source": "a: b",
            "source_type": "web",
            "language": "pt-BR",
            "author": ["Zoë", "B # c"],
            "warnings": [],
            "tags": ["x" * 50, "y" * 50, "z" * 50, "w" * 50],
            "truncated": False,
            "pages": 3,
            "duration_seconds": 2832.4,
            "extra": {"k": "yes", "n": 1},
            "tokens": {"o200k_base": 1},
        }
    )
    assert text.startswith('---\ntitle: "Plain"\nsource: "a: b"\nsource_type: web\nlanguage: pt-BR\n')
    assert 'author: ["Zoë", "B # c"]' in text
    assert "warnings: []" in text and "truncated: false" in text and "pages: 3" in text
    assert "duration_seconds: 2832.4" in text
    assert 'tags:\n  - "' in text
    assert 'extra: {k: "yes", "n": 1}' in text  # bare n would read as a YAML 1.1 boolean
    assert text.endswith("tokens: {o200k_base: 1}\n---\n")


def test_warning_codes_deduplicated_and_info_omitted_in_compact() -> None:
    res = harbor_lane()
    res.warnings.extend(
        [
            Warning(kind=WarningKind.CHAPTERS_GENERATED, message="a"),
            Warning(kind=WarningKind.CHAPTERS_GENERATED, message="b"),
            Warning(kind=WarningKind.OCR_CONFIDENCE_LOW, message="c"),
        ]
    )
    full = render(res, "full").frontmatter["warnings"]
    assert full == ["chapters_generated", "ocr_confidence_low"]
    compact = render(res, "compact").frontmatter["warnings"]
    assert compact == ["ocr_confidence_low"]


def test_count_tokens_map_and_offline_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    counts = count_tokens("Hello world, this is a test.")
    assert set(counts) == {"o200k_base", "cl100k_base", "claude_approx"}
    assert counts["claude_approx"] == round(counts["o200k_base"] * 1.08)
    monkeypatch.setattr(tokmod, "_ENCODINGS", {"o200k_base": None, "cl100k_base": None})
    est = count_tokens("a" * 38)
    assert est == {"o200k_base": 10, "cl100k_base": 10, "claude_approx": 11}
    assert tokmod.tokens_estimated()
    assert count_tokens("漢字" * 8)["o200k_base"] == 10


def test_rendered_output_tokens_is_cl100k_of_markdown() -> None:
    out = render(harbor_lane(), "full")
    assert out.tokens == tokmod.TiktokenCounter("cl100k_base").count(out.markdown)


def test_compact_budget_truncates_at_section_boundary() -> None:
    blocks = []
    for i in range(6):
        blocks += [heading(f"Part {i}", 1), para("Some words in a sentence. " * 40)]
    res = make_result(blocks)
    out = render(res, "compact", max_tokens="700")
    assert out.truncated and out.frontmatter["truncated"] is True
    assert "truncated" in out.frontmatter["warnings"]  # type: ignore[operator]
    assert any(w.kind == "truncated" and w.detail.get("reason") == "max_tokens" for w in out.warnings)
    note = '<!-- intomd: truncated at max_tokens=700; [0-9]+ blocks omitted; next_cursor="[A-Za-z0-9_-]+" -->'
    assert re.search(note + "$", out.body.rstrip("\n"))
    assert out.body.rsplit("\n\n", 2)[-2].startswith("Some words")  # cut before a heading, not mid-section
    full = render(res, "full")
    assert not full.truncated and "truncation" not in full.frontmatter


_NEXT = re.compile('next_cursor="([A-Za-z0-9_-]+)" -->$')


def _walk(res: ConversionResult, profile: str, budget: int) -> list[str]:
    """Render every page by following next_cursor; return each page body without its continuation note."""
    pages: list[str] = []
    cursor: str | None = None
    for _ in range(500):
        kw: dict[str, object] = {"max_tokens": budget}
        if cursor:
            kw["cursor"] = cursor
        body = render(res, profile, **kw).body.rstrip("\n")
        m = _NEXT.search(body)
        if m is None:
            pages.append(body)
            return pages
        cursor = m.group(1)
        pages.append(body[: m.start()].rsplit("\n\n", 1)[0])
    raise AssertionError("cursor walk did not terminate")


def test_cursor_walk_rebuilds_multi_section_body() -> None:
    blocks = []
    for i in range(6):
        blocks += [heading(f"Part {i}", 1), para("Some words in a sentence. " * 40), para("More text. " * 30)]
    res = make_result(blocks)
    pages = _walk(res, "full", 300)
    assert len(pages) > 3
    assert "\n\n".join(pages) + "\n" == render(res, "full", max_tokens="none").body


def test_cursor_walk_splits_inside_long_headingless_body() -> None:
    res = make_result([para(f"Paragraph {i} has a few words in it. " * 8) for i in range(60)])
    pages = _walk(res, "full", 250)
    assert len(pages) > 5
    assert "\n\n".join(pages) + "\n" == render(res, "full", max_tokens="none").body


def test_cursor_is_opaque_and_profile_bound() -> None:
    cursor = encode_cursor("agent", 3)
    assert decode_cursor(cursor) == ("agent", 3)
    assert json.loads(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))) == {
        "profile": "agent",
        "unit": 3,
        "v": 1,
    }
    assert decode_cursor("sec-4") is None


def test_agent_cursor_paging() -> None:
    blocks = []
    for i in range(6):
        blocks += [heading(f"Part {i}", 1), para("Some words in a sentence. " * 40)]
    res = make_result(blocks)
    first = render(res, "agent", max_tokens=700)
    m = re.search('<!-- intomd: continued; next_cursor="([A-Za-z0-9_-]+)" -->', first.body)
    assert m and first.frontmatter["truncation"]["reason"] == "max_tokens"  # type: ignore[index]
    assert first.frontmatter["truncation"]["next_cursor"] == m.group(1)  # type: ignore[index]
    nxt = render(res, "agent", max_tokens=700, cursor=m.group(1))
    assert "## 1 Part 0" not in nxt.body and "## 3 Part 2" in nxt.body
    # A heading anchor is still accepted (the Part 3 example cursor).
    assert "Part 2" in render(res, "agent", max_tokens=700, cursor="sec-3").body
    with pytest.raises(ValueError, match="unknown cursor"):
        render(res, "agent", cursor="sec-99")
    with pytest.raises(ValueError, match="unknown cursor"):
        render(res, "agent", cursor=encode_cursor("agent", 10_000))
    with pytest.raises(ValueError, match="profile"):
        render(res, "full", cursor=m.group(1))


def test_sidecar_shape() -> None:
    out = render(harbor_lane(), "full", converted_at=datetime(2026, 10, 8, tzinfo=UTC))
    sc = out.sidecar
    assert sc is not None and sc["schema"] == "intomd.sidecar/1" and sc["frontmatter"] == out.frontmatter
    for key in (
        "sections",
        "tables",
        "figures",
        "links",
        "speakers",
        "segments",
        "warnings",
        "provenance",
        "injection_findings",
        "counts",
        "document",
    ):
        assert key in sc
    assert "chunks" not in sc
    assert render(harbor_lane(), "compact").sidecar is None
