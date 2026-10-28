"""`locate_units`: byte offsets of each unit in the body, linear in the body's size (#56)."""

from __future__ import annotations

import time

from ezmd.render.context import Unit
from ezmd.render.ledger import locate_units


def _units(lines: list[str]) -> list[Unit]:
    return [Unit(text=line, kind="paragraph") for line in lines]


def test_offsets_are_byte_offsets_and_skip_missing_units() -> None:
    lines = ["héllo", "wörld", "absent", "日本語", "last"]
    body = "héllo\n\nwörld\n\n日本語\n\nlast\n"
    out = locate_units(body, _units(lines))
    assert 2 not in out, "a unit not in the body gets no offset"
    assert 0 not in locate_units(body, _units([""])), "an empty unit gets no offset"
    assert out[0] == (0, len("héllo".encode()))
    start_w = len("héllo\n\n".encode())
    assert out[1] == (start_w, start_w + len("wörld".encode()))
    start_j = len("héllo\n\nwörld\n\n".encode())
    assert out[3] == (start_j, start_j + len("日本語".encode()))
    start_l = len("héllo\n\nwörld\n\n日本語\n\n".encode())
    assert out[4] == (start_l, start_l + 4)
    for i, (start, end) in out.items():
        assert body.encode()[start:end].decode() == lines[i]


def test_repeated_text_resolves_in_order() -> None:
    body = "same\n\nsame\n\nsame\n"
    out = locate_units(body, _units(["same", "same", "same"]))
    assert [out[i] for i in range(3)] == [(0, 4), (6, 10), (12, 16)]


def test_large_body_with_a_unit_per_line_is_linear() -> None:
    # 60,000 lines of 25 bytes: the old prefix re-encode per unit was 60,000 encodes of a 1.5 MB body.
    lines = [f"line {i:06d} of the log ü" for i in range(60_000)]
    body = "\n".join(lines) + "\n"
    t = time.perf_counter()
    out = locate_units(body, _units(lines))
    elapsed = time.perf_counter() - t
    assert len(out) == 60_000
    raw = body.encode()
    for i in (0, 1, 30_000, 59_999):
        start, end = out[i]
        assert raw[start:end].decode() == lines[i]
    assert elapsed < 10, f"locate_units took {elapsed:.1f} s on a 1.5 MB body"


def _split_in_body(text: str, n: int) -> str:
    """What the rag chunker leaves in the body for a prose unit over the budget: the sentences in `n` pieces,
    each inside its own chunk markers, so the unit's whole text is no longer in the body."""
    sentences = text.split(" ")
    size = max(1, len(sentences) // n)
    pieces = [" ".join(sentences[k : k + size]) for k in range(0, len(sentences), size)]
    marked = (f'<!-- chunk id="c{k:04d}" part="{k}/{n}" -->\n{p}\n<!-- /chunk -->' for k, p in enumerate(pieces, 1))
    return "\n\n".join(marked)


def test_split_units_get_no_offset_and_later_units_still_resolve() -> None:
    long = " ".join(f"Sentence {k} of a paragraph the chunker splits because it is over the budget." for k in range(40))
    units = ["Intro.", long, "Middle ü.", long, "Last."]
    body = "\n\n".join(["Intro.", _split_in_body(long, 3), "Middle ü.", _split_in_body(long, 3), "Last."]) + "\n"
    out = locate_units(body, _units(units))
    assert sorted(out) == [0, 2, 4], "the split units get no offset; the whole ones before, between and after do"
    raw = body.encode()
    for i in (0, 2, 4):
        start, end = out[i]
        assert raw[start:end].decode() == units[i]


def test_a_whole_unit_that_starts_like_a_split_one_is_still_found() -> None:
    # The second unit begins with the first unit's text. The first is split, so its head is in the body but
    # its whole text is not; the second must not stop at the first's pieces.
    first = " ".join(f"Sentence {k} of a paragraph the chunker splits because it is over the budget." for k in range(8))
    second = first + " And a second unit that goes on from there."
    units = [first, second, "Last."]
    body = "\n\n".join([_split_in_body(first, 2), second, "Last."]) + "\n"
    out = locate_units(body, _units(units))
    assert sorted(out) == [1, 2]
    raw = body.encode()
    for i in (1, 2):
        start, end = out[i]
        assert raw[start:end].decode() == units[i]


def test_a_head_that_matches_inside_a_later_unit_does_not_move_the_search() -> None:
    # The first unit is not in the body at all, but a later unit starts with its first 250 characters. The
    # units between keep their offsets, and the later unit its own.
    absent = " ".join(f"Sentence {k} of a paragraph that was dropped from the body." for k in range(8))
    later = absent[:250] + " but then it goes somewhere else entirely."
    units = [absent, "Between ü.", later, "Last."]
    body = "\n\n".join(["Between ü.", later, "Last."]) + "\n"
    out = locate_units(body, _units(units))
    assert sorted(out) == [1, 2, 3]
    raw = body.encode()
    for i in (1, 2, 3):
        start, end = out[i]
        assert raw[start:end].decode() == units[i]


def test_a_unit_whose_trailing_whitespace_was_stripped_keeps_later_units_in_order() -> None:
    # The renderer strips trailing whitespace from lines, so a unit with a padded line is in the body with its
    # whitespace changed: no offset for it, and the units after it are searched from where it is.
    padded = " ".join(f"Sentence {k} of a long paragraph with a padded line." for k in range(6)) + "   \nand more."
    units = [padded, "Next ü.", "Last."]
    body = "\n\n".join([padded.replace("   \n", "\n"), "Next ü.", "Last."]) + "\n"
    out = locate_units(body, _units(units))
    assert sorted(out) == [1, 2]
    raw = body.encode()
    for i in (1, 2):
        start, end = out[i]
        assert raw[start:end].decode() == units[i]


def test_probe_ends_at_the_first_sentence_or_line() -> None:
    from ezmd.render.ledger import PROBE_CHARS, PROBE_MIN, _probe

    long = " ".join(f"Sentence {k} of a paragraph." for k in range(40))
    first = "Sentence 0 of a paragraph long enough to stand alone."
    assert _probe(first + "\n" + long) == first
    assert _probe(first + "  " + long) == first
    assert _probe("Yes. " + long) == ("Yes. " + long)[:PROBE_MIN], "a short first sentence takes the next's start"
    header = "| column alpha | column beta | column gamma |"
    assert _probe(header + "\n|---|---|---|\n| 1 | 2 | 3 |") == header
    assert _probe("| a | b |\n|---|---|\n| 1 | 2 |") == "| a | b |\n|---|---|\n| 1 | 2 |"[:PROBE_MIN]
    assert _probe("x" * 500) == "x" * PROBE_CHARS
    assert _probe("short") == "short"


def _cut_after_first_sentence(text: str) -> tuple[str, str]:
    first, _, rest = text.partition(". ")
    return first + ".", rest


def test_a_split_unit_whose_first_piece_is_one_sentence_is_found_by_it() -> None:
    # The chunker packs an oversized unit into a partly filled chunk, so its first piece can be one sentence.
    unit = " ".join(f"Sentence {k} of a paragraph that the chunker cut after its first one." for k in range(30))
    first, rest = _cut_after_first_sentence(unit)
    body = (
        f'<!-- chunk id="c0001" -->\n**Doc**\n\nBefore ü.\n\n{first}\n<!-- /chunk -->\n\n'
        f'<!-- chunk id="c0002" part="2/2" -->\n**Doc**\n\n{rest}\n<!-- /chunk -->\n\nAfter.\n'
    )
    units = ["Before ü.", unit, "After."]
    out = locate_units(body, _units(units))
    assert sorted(out) == [0, 2]
    raw = body.encode()
    for i in (0, 2):
        start, end = out[i]
        assert raw[start:end].decode() == units[i]


def test_many_split_units_with_one_sentence_first_pieces_do_not_rescan_the_body() -> None:
    # 12,000 split units whose first piece is one sentence: a 200-character probe was found nowhere and scanned
    # the rest of the 12 MB body for each, about 20 seconds; a probe that ends at the sentence is found at once.
    unit = " ".join(f"Sentence {k} of a paragraph that the chunker cut after its first one." for k in range(12))
    first, rest = _cut_after_first_sentence(unit)
    parts: list[str] = []
    units: list[str] = []
    for i in range(12_000):
        units.extend([f"Whole paragraph {i} ü.", unit])
        parts.append(
            f'<!-- chunk id="c{i:05d}" -->\nWhole paragraph {i} ü.\n\n{first}\n<!-- /chunk -->\n\n'
            f'<!-- chunk id="d{i:05d}" part="2/2" -->\n{rest}\n<!-- /chunk -->'
        )
    body = "\n\n".join(parts) + "\n"
    t = time.perf_counter()
    out = locate_units(body, _units(units))
    elapsed = time.perf_counter() - t
    assert sorted(out) == list(range(0, 24_000, 2))
    raw = body.encode()
    for i in (0, 12_000, 23_998):
        start, end = out[i]
        assert raw[start:end].decode() == units[i]
    assert elapsed < 10, f"locate_units took {elapsed:.1f} s with 12,000 one-sentence first pieces"


def test_many_split_units_do_not_rescan_the_body() -> None:
    # 4,000 paragraphs the chunker split: each used to scan the rest of the body for a text that is not there,
    # 4,000 scans of a 4 MB body. Units longer than the probe keep their head in the body, which is enough.
    long = " ".join(f"Sentence {k} of a paragraph the chunker splits because it is over the budget." for k in range(12))
    units: list[str] = []
    parts: list[str] = []
    for i in range(4_000):
        units.extend([f"Whole paragraph {i} ü.", long])
        parts.extend([f"Whole paragraph {i} ü.", _split_in_body(long, 2)])
    body = "\n\n".join(parts) + "\n"
    t = time.perf_counter()
    out = locate_units(body, _units(units))
    elapsed = time.perf_counter() - t
    assert sorted(out) == list(range(0, 8_000, 2))
    raw = body.encode()
    for i in (0, 4_000, 7_998):
        start, end = out[i]
        assert raw[start:end].decode() == units[i]
    assert elapsed < 10, f"locate_units took {elapsed:.1f} s with 4,000 split units in a {len(body) / 1e6:.1f} MB body"
