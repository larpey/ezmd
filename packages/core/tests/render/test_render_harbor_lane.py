"""The Part 3 section 17 worked example (Harbor Lane), rendered in all four profiles and compared with the
expected outputs taken verbatim from docs/spec/part3.md. Placeholder lines (hashes, token counts, word counts,
the intomd version, the fence id and chunk doc ids) are normalized on both sides, as the spec prescribes."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from render_builders import CONVERTED_AT, harbor_lane

from intomd.render import render

SPEC = Path(__file__).resolve().parents[4] / "docs" / "spec" / "part3.md"
SIDECAR = "harbor-lane-depot-report.intomd.json"

_NORMALIZE = [
    (re.compile(r'^content_hash: "sha256:[0-9a-f]{64}"$', re.M), 'content_hash: "sha256:HASH"'),
    (re.compile(r"^tokens: \{[^}]*\}$", re.M), "tokens: TOKENS"),
    (re.compile(r"^word_count: \d+$", re.M), "word_count: N"),
    (re.compile(r'^intomd_version: "[^"]+"$', re.M), 'intomd_version: "V"'),
    (re.compile(r'^untrusted_content_id: "[0-9a-f]{16}"$', re.M), 'untrusted_content_id: "FID"'),
    (re.compile(r'<untrusted_content id="[0-9a-f]{16}"'), '<untrusted_content id="FID"'),
    (re.compile(r'chunk id="[0-9a-f]{12}#'), 'chunk id="DOCID#'),
    (re.compile(r' tokens="\d+"'), ' tokens="N"'),
]


def _normalize(text: str) -> str:
    for pattern, repl in _NORMALIZE:
        text = pattern.sub(repl, text)
    return text


def _expected(profile: str) -> str:
    if not SPEC.exists():
        pytest.skip("spec not available")
    spec = SPEC.read_text(encoding="utf-8")
    start = spec.index(f"**`{profile}`")
    block = spec.index("```markdown\n", start) + len("```markdown\n")
    end = spec.index("\n```\n", block)
    return spec[block:end] + "\n"


@pytest.mark.parametrize("profile", ["full", "compact", "rag", "agent"])
def test_harbor_lane_matches_spec(profile: str) -> None:
    # compact writes no sidecar, so the caller passes no sidecar path (the spec example has none)
    options = {} if profile == "compact" else {"sidecar_path": SIDECAR}
    out = render(harbor_lane(), profile, converted_at=CONVERTED_AT, **options)
    assert _normalize(out.markdown) == _normalize(_expected(profile))


@pytest.mark.parametrize("profile", ["full", "compact", "rag", "agent"])
def test_harbor_lane_body_is_deterministic(profile: str) -> None:
    a = render(harbor_lane(), profile, converted_at=CONVERTED_AT)
    b = render(harbor_lane(), profile)
    assert a.body == b.body
    assert a.frontmatter["content_hash"] == b.frontmatter["content_hash"]


def test_harbor_lane_content_hash_is_body_hash() -> None:
    import hashlib

    out = render(harbor_lane(), "full", converted_at=CONVERTED_AT)
    assert out.markdown.endswith(out.body)
    assert out.frontmatter["content_hash"] == "sha256:" + hashlib.sha256(out.body.encode()).hexdigest()


def test_harbor_lane_rag_chunks() -> None:
    out = render(harbor_lane(), "rag", converted_at=CONVERTED_AT)
    assert len(out.chunks) == 2
    first, second = out.chunks
    assert first.section_id == "sec-1" and first.merged_preamble
    assert second.time_start == pytest.approx(3.2) and second.time_end == pytest.approx(45.3)
    assert second.breadcrumb == "Harbor Lane depot report > 2 Interview with the shift lead [00:00:03 - 00:00:45]"
    assert out.frontmatter["chunks"] == 2 and out.frontmatter["chunk_tokens"] == 400
    assert out.sidecar is not None and len(out.sidecar["chunks"]) == 2  # type: ignore[arg-type]


def test_harbor_lane_agent_attachment_and_offsets() -> None:
    out = render(harbor_lane(), "agent", converted_at=CONVERTED_AT)
    assert [a.path for a in out.attachments] == ["tables/table-01.csv"]
    csv = out.attachments[0].data.decode()
    assert csv.splitlines()[0] == "Week,Pallets,Dock doors,Overtime hours"
    assert '"1,105"' in csv
    assert out.sidecar is not None
    sections = out.sidecar["sections"]
    assert isinstance(sections, list)
    body = out.body.encode()
    for sec in sections:
        start = sec["offset_start"]
        assert body[start:].startswith(b"## ")
