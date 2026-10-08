"""Social family Phase 1 stubs: the family flag, URL recognition, API URLs, minimal parsing, rendering."""

from __future__ import annotations

import json

import pytest

from intomd.detect import detect
from intomd.inputs import FetchRequired, InputRef
from intomd.ir import Comment, Heading, Link, WarningKind, spans_text
from intomd.registry import ConversionError, ConvertOptions, Unavailable, default_registry
from intomd_converters.social import FLAG_ENV, converters
from intomd_converters.social.adapters import AdapterError, HackerNewsAdapter, RedditAdapter
from intomd_converters.social.converter import SocialStubConverter

REDDIT_URL = "https://www.reddit.com/r/AskHistorians/comments/abc123/why_lighthouses/"
HN_URL = "https://news.ycombinator.com/item?id=4242"


def _reddit_payload() -> bytes:
    def t1(cid: str, author: str, body: str, replies: object = "") -> dict[str, object]:
        return {
            "kind": "t1",
            "data": {
                "id": cid,
                "author": author,
                "body": body,
                "created_utc": 1767225600,
                "score": 3,
                "replies": replies,
            },
        }

    child = t1("c2", "op_user", "Thanks, that helps.")
    forest = [
        t1("c1", "keeper", "Because ships need a fixed light.", {"kind": "Listing", "data": {"children": [child]}}),
        t1("c3", "[deleted]", "[deleted]"),
        {"kind": "more", "data": {"count": 7, "children": ["x", "y"]}},
    ]
    post = {
        "id": "abc123",
        "title": "Why were lighthouses painted?",
        "selftext": "Asking for a model.",
        "author": "op_user",
        "created_utc": 1767225000,
        "score": 41,
        "is_self": True,
        "subreddit": "AskHistorians",
        "permalink": "/r/AskHistorians/comments/abc123/why_lighthouses/",
    }
    return json.dumps(
        [
            {"kind": "Listing", "data": {"children": [{"kind": "t3", "data": post}]}},
            {"kind": "Listing", "data": {"children": forest}},
        ]
    ).encode()


def _hn_payload() -> bytes:
    return json.dumps(
        {
            "id": 4242,
            "type": "story",
            "title": "Show HN: a tide clock",
            "author": "maker",
            "created_at_i": 1767225600,
            "points": 120,
            "url": "https://tides.example.test/",
            "text": None,
            "children": [
                {
                    "id": 4243,
                    "author": "reader",
                    "created_at_i": 1767225700,
                    "text": "<p>Nice.</p><p>Does it handle <i>neap</i> tides?</p>",
                    "children": [
                        {"id": 4244, "author": "maker", "created_at_i": 1767225800, "text": "Yes.", "children": []}
                    ],
                },
                {"id": 4245, "author": None, "text": None, "children": []},
            ],
        }
    ).encode()


def test_family_disabled_by_default_registers_unavailable() -> None:
    convs = converters({})
    assert [c.id for c in convs] == ["web.social_reddit", "web.social_hn"]
    assert all(isinstance(c, Unavailable) and FLAG_ENV in c.reason for c in convs)
    ids = {r.converter.id: r.import_error for r in default_registry().registrations()}
    assert ids.get("web.social_reddit") is not None


def test_flag_enables_experimental_stubs() -> None:
    convs = converters({FLAG_ENV: "1"})
    assert all(isinstance(c, SocialStubConverter) and c.experimental and c.family == "web" for c in convs)


@pytest.mark.parametrize(
    ("url", "tid"),
    [
        (REDDIT_URL, "abc123"),
        ("https://old.reddit.com/r/AskHistorians/comments/abc123/", "abc123"),
        ("https://redd.it/abc123", "abc123"),
        ("https://www.reddit.com/comments/abc123.json?raw_json=1", "abc123"),
        ("https://www.reddit.com/r/AskHistorians/", None),
        ("https://evil.example/r/x/comments/abc123/", None),
    ],
)
def test_reddit_thread_ids(url: str, tid: str | None) -> None:
    assert RedditAdapter().thread_id(url) == tid


def test_reddit_api_url_normalizes_and_sanitizes_sort() -> None:
    a = RedditAdapter()
    assert a.api_url(REDDIT_URL) == "https://www.reddit.com/comments/abc123.json?raw_json=1&limit=500&sort=confidence"
    assert a.api_url(REDDIT_URL, sort="top&x=1").endswith("sort=confidence")
    assert a.api_url(REDDIT_URL, sort="new").endswith("sort=new")


@pytest.mark.parametrize(
    ("url", "tid"),
    [
        (HN_URL, "4242"),
        ("https://hn.algolia.com/api/v1/items/4242", "4242"),
        ("https://news.ycombinator.com/item?id=x", None),
    ],
)
def test_hn_ids(url: str, tid: str | None) -> None:
    assert HackerNewsAdapter().thread_id(url) == tid


def test_hn_api_url() -> None:
    assert HackerNewsAdapter().api_url(HN_URL) == "https://hn.algolia.com/api/v1/items/4242"


def test_reddit_parse_tree_flags_and_collapsed() -> None:
    thread = RedditAdapter().parse(_reddit_payload(), REDDIT_URL)
    nodes = thread.walk()
    assert [n.id for n in nodes] == ["c1", "c2", "c3"]
    assert [n.depth for n in nodes] == [0, 1, 0]
    assert nodes[1].parent_id == "t1_c1" and "op" in nodes[1].flags
    assert nodes[2].author is None and "deleted" in nodes[2].flags
    assert thread.collapsed == 7


def test_html_instead_of_json_is_an_adapter_error() -> None:
    with pytest.raises(AdapterError):
        RedditAdapter().parse(b"<html>blocked</html>", REDDIT_URL)


def _converter(name: str) -> SocialStubConverter:
    conv = {c.id: c for c in converters({FLAG_ENV: "1"})}[name]
    assert isinstance(conv, SocialStubConverter)
    return conv


def test_stub_requests_api_fetch_without_body() -> None:
    ref = InputRef.from_url(REDDIT_URL)
    detect(ref)
    conv = _converter("web.social_reddit")
    assert conv.can_handle(ref) == pytest.approx(0.9)
    with pytest.raises(FetchRequired) as e:
        conv.convert(ref, ConvertOptions())
    assert e.value.url.startswith("https://www.reddit.com/comments/abc123.json")


def test_stub_renders_reddit_thread() -> None:
    ref = InputRef.from_bytes(_reddit_payload(), filename="t.json", source_url=REDDIT_URL)
    detect(ref)
    doc = _converter("web.social_reddit").convert(ref, ConvertOptions())
    heads = [spans_text(b.spans) for b in doc.blocks if isinstance(b, Heading)]
    assert heads == ["Why were lighthouses painted?", "Comments (3)"]
    comments = [b for b in doc.blocks if isinstance(b, Comment)]
    assert [c.attrs["depth"] for c in comments] == ["0", "1", "0"]
    assert spans_text(comments[2].spans) == "[deleted]"
    assert all(c.provenance.source_id and c.provenance.path == f"comments/{c.provenance.source_id}" for c in comments)
    assert all(c.created is not None for c in comments)
    assert WarningKind.COMMENTS_COLLAPSED in [w.kind for w in doc.warnings]


def test_stub_renders_hn_with_dead_placeholder_and_cap() -> None:
    ref = InputRef.from_bytes(_hn_payload(), filename="i.json", source_url=HN_URL)
    detect(ref)
    opts = ConvertOptions(extra={"social.max_comments": 2})
    doc = _converter("web.social_hn").convert(ref, opts)
    assert isinstance(doc.blocks[1], Link) and doc.blocks[1].href == "https://tides.example.test/"
    comments = [b for b in doc.blocks if isinstance(b, Comment)]
    assert len(comments) == 2
    assert "neap" in spans_text(comments[0].spans) and "<i>" not in spans_text(comments[0].spans)
    assert WarningKind.COMMENTS_TRUNCATED in [w.kind for w in doc.warnings]
    full = _converter("web.social_hn").convert(ref, ConvertOptions())
    assert spans_text([b for b in full.blocks if isinstance(b, Comment)][-1].spans) == "[dead]"


def test_stub_bad_payload_raises_conversion_error() -> None:
    ref = InputRef.from_bytes(b'{"nope": 1}', filename="i.json", source_url=HN_URL)
    detect(ref)
    with pytest.raises(ConversionError):
        _converter("web.social_hn").convert(ref, ConvertOptions())
