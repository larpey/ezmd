"""The media corpus: resume log, document ids and extension choice."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))  # tools/ is not an installed package

from tools.bench import media  # noqa: E402


def test_doc_ids_are_unique_when_titles_collide_after_sanitizing() -> None:
    a = media.doc_id("commons", "A" * 90 + " (1).webp")
    b = media.doc_id("commons", "A" * 90 + " (2).webp")
    assert a != b and a.startswith("commons__") and "/" not in a and " " not in a
    assert media.doc_id("commons", "x.webp") == media.doc_id("commons", "x.webp")


def test_extension_from_url_then_mime() -> None:
    assert media._ext("https://upload.wikimedia.org/a/b/Photo.WEBP?x=1", "image/webp") == "webp"
    assert media._ext("https://archive.org/download/item/chapter01", "audio/mpeg") == "mpeg"
    assert media._ext("https://x/y.tar.gz", "application/gzip") == "gz"


def test_log_records_and_counts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EZMD_MEDIA", str(tmp_path))
    log = media.Log(tmp_path)
    dest = log.save("gutenberg", "123", "https://g/pg123.epub", "application/epub+zip", b"PK", "epub")
    assert dest.is_file() and dest.name == "123.epub" and dest.parent.name == "epub"
    assert log.has("gutenberg", "123") and log.count("gutenberg") == 1 and log.count("gutenberg", "x") == 0
    again = media.Log(tmp_path)
    assert again.has("gutenberg", "123") and again.records[("gutenberg", "123")]["bytes"] == 2
    docs = media.media()
    assert len(docs) == 1 and docs[0].category == "gutenberg-application-epub+zip" and docs[0].input == dest
