"""tools/bench/qa.py: questions per segment of the text layer, whole outputs sent to the answering model, and the
scorer's second-half view of the results. No model needed."""

from __future__ import annotations

import json
import re
import sys
from itertools import pairwise
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))  # tools/ is not an installed package

from tools.bench import qa  # noqa: E402
from tools.bench.schema import DocResult, append_result  # noqa: E402
from tools.bench.scoring import arxiv  # noqa: E402

LINES = [f"Line {i}: the depot moved {i * 3} pallets on day {i} of the trial." for i in range(120)]
TEXT = "\n".join(LINES)


def test_segments_cut_at_line_ends_and_record_contiguous_offsets() -> None:
    segs = qa.segments(TEXT, size=200)
    assert len(segs) > 3
    assert "\n".join(s.text for s in segs) == TEXT
    assert segs[0].start == 0
    for a, b in pairwise(segs):
        assert a.end == b.start
    for s in segs[:-1]:
        assert arxiv.count_tokens(s.text) <= 200
    total = segs[-1].end
    assert abs(total - arxiv.count_tokens(TEXT)) <= len(segs) + 1  # per-line counts add a newline each
    assert segs[1].where(total) == {"from": segs[1].start, "to": segs[1].end, "of": total}


def test_segments_join_a_short_tail_and_split_an_oversize_line() -> None:
    # 200-token pieces of a text whose last lines fall well short of a quarter of a piece: the tail joins the
    # piece before it rather than being asked about alone.
    segs = qa.segments("\n".join(LINES[:28]), size=200)
    assert len(segs) >= 2 and arxiv.count_tokens(segs[-1].text) >= 50
    assert all(arxiv.count_tokens(s.text) >= 50 for s in segs)
    long_line = " ".join(f"word{i}" for i in range(600))
    pieces = qa.segments(long_line, size=100)
    assert len(pieces) > 3 and "".join(p.text for p in pieces) == long_line
    assert qa.segments("", size=100) == [qa.Segment(0, 0, "")]


class _Writer:
    """A question writer that quotes the first line of whatever part it is shown."""

    model = "fake"
    base_url = "http://x"

    def __init__(self) -> None:
        self.parts: list[tuple[int, int]] = []

    def chat(self, prompt: str, **_: object) -> str:
        m = re.search(r"PART (\d+) OF (\d+):\n(.*)", prompt, re.S)
        assert m
        self.parts.append((int(m.group(1)), int(m.group(2))))
        first = m.group(3).split("\n")[0]
        number = re.search(r"moved (\d+) pallets", first)
        assert number
        grounded = {"question": f"How many pallets moved on {first[:7]}?", "answer": number.group(1), "quote": first}
        invented = {"question": "Invented?", "answer": "zebra", "quote": "A sentence that is in no part."}
        return json.dumps([grounded, invented])


def test_generate_questions_asks_every_segment_and_records_where_the_evidence_is(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(qa, "SEGMENT_TOKENS", 200)
    writer = _Writer()
    questions, parts = qa.generate_questions(writer, TEXT)  # type: ignore[arg-type]
    assert parts == len(qa.segments(TEXT, 200)) and parts > 3
    assert writer.parts == [(i + 1, parts) for i in range(parts)]
    assert len(questions) == parts  # one grounded pair per part; the invented one is dropped every time
    total = questions[0]["segment"]["of"]
    assert [q["segment"]["from"] for q in questions] == sorted(q["segment"]["from"] for q in questions)
    assert questions[-1]["segment"]["to"] == total and questions[0]["segment"]["from"] == 0
    assert all(q["segment"]["of"] == total for q in questions)
    assert sum(1 for q in questions if arxiv.in_second_half(q)) >= 1


def test_question_files_from_an_older_scheme_are_generated_again(tmp_path: Path) -> None:
    path = tmp_path / "q.json"
    path.write_text(json.dumps({"questions": [{"question": "q"}] * 5}), encoding="utf-8")  # no scheme
    assert qa.cached_questions(path) is None
    path.write_text(json.dumps({"scheme": qa.SCHEME, "segments": 4, "questions": [{"question": "q"}] * 3}))
    assert qa.cached_questions(path) is None  # fewer than one per segment
    path.write_text(json.dumps({"scheme": qa.SCHEME, "segments": 4, "questions": [{"question": "q"}] * 4}))
    assert qa.cached_questions(path) == 4
    assert qa.cached_questions(tmp_path / "missing.json") is None


class _Reader:
    """An answerer that remembers the document it was shown."""

    model = "fake"
    base_url = "http://x"

    def __init__(self) -> None:
        self.seen: list[str] = []

    def chat(self, prompt: str, **_: object) -> str:
        self.seen.append(prompt.split("DOCUMENT:\n", 1)[1])
        return json.dumps(["14"])


def _run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, md: str) -> Path:
    monkeypatch.setenv("EZMD_BENCH_CACHE", str(tmp_path / "cache"))
    run = tmp_path / "run"
    (run / "ezmd-main").mkdir(parents=True)
    (run / "ezmd-main" / "2601_00001.md").write_text(md, encoding="utf-8")
    (run / "docs.json").write_text(json.dumps({"documents": [{"id": "2601_00001"}]}), encoding="utf-8")
    append_result(
        run / "results.jsonl",
        DocResult("arxiv", "2601_00001", "c", "ezmd-main", "1", "ok", output="ezmd-main/2601_00001.md"),
    )
    qa.qa_dir().mkdir(parents=True, exist_ok=True)
    (qa.qa_dir() / "2601_00001.json").write_text(
        json.dumps(
            {
                "scheme": qa.SCHEME,
                "segments": 1,
                "questions": [
                    {
                        "question": "How many?",
                        "answer": "14",
                        "quote": "moved 14 pallets",
                        "segment": {"from": 0, "to": 400, "of": 400},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return run


def test_answer_sends_the_whole_output_and_marks_a_cut(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    run = _run(tmp_path, monkeypatch, TEXT)
    reader = _Reader()
    qa.answer(reader, run, None, 1, context=qa.PROMPT_RESERVE + 10_000)  # type: ignore[arg-type]
    record = json.loads((run / "qa" / "ezmd-main" / "2601_00001.json").read_text(encoding="utf-8"))
    assert record["cut"] is False and record["context"] == qa.PROMPT_RESERVE + 10_000
    assert reader.seen[-1] == TEXT
    assert record["items"][0]["segment"] == {"from": 0, "to": 400, "of": 400}
    (run / "qa" / "ezmd-main" / "2601_00001.json").unlink()
    qa.answer(reader, run, None, 1, context=qa.PROMPT_RESERVE + 300)  # type: ignore[arg-type]
    record = json.loads((run / "qa" / "ezmd-main" / "2601_00001.json").read_text(encoding="utf-8"))
    assert record["cut"] is True
    assert TEXT.startswith(reader.seen[-1]) and arxiv.count_tokens(reader.seen[-1]) <= 300
    assert qa.document_text("short", 50_000) == ("short", False)


def test_a_long_run_of_one_character_is_squeezed_before_the_text_is_sent() -> None:
    """MinerU read a table's rules as 764 of one CJK character and the server's tokenizer refused the text."""
    rules = "二" * 764
    assert qa.squeeze_runs(f"| a | {rules} |\n") == f"| a | {'二' * qa.RUN_CAP} |\n"
    assert qa.squeeze_runs("二" * qa.RUN_CAP) == "二" * qa.RUN_CAP  # at the cap: untouched
    assert qa.squeeze_runs("-" * 500 + " ab") == "-" * 500 + " ab"  # ASCII rules are the model's to read
    text, cut = qa.document_text(f"Intro.\n{rules}\nEnd.", 50_000)
    assert text == f"Intro.\n{'二' * qa.RUN_CAP}\nEnd." and cut is False


def test_scorer_splits_accuracy_by_where_the_evidence_lies() -> None:
    items = [
        {"correct": True, "segment": {"from": 0, "to": 8000, "of": 40000}},
        {"correct": True, "segment": {"from": 8000, "to": 16000, "of": 40000}},
        {"correct": False, "segment": {"from": 16000, "to": 24000, "of": 40000}},  # midpoint 20000: second half
        {"correct": False, "segment": {"from": 32000, "to": 40000, "of": 40000}},
        {"correct": True, "segment": {"from": 24000, "to": 32000, "of": 40000}},
        {"correct": True},  # an older question without a segment: counted, placed nowhere
    ]
    assert [arxiv.in_second_half(it) for it in items] == [False, False, True, True, True, None]
    per_doc = {
        "d1": {"qa_asked": 6.0, "qa_correct": 4.0, "qa_tail_asked": 3.0, "qa_tail_correct": 1.0, "qa_cut": 1.0},
        "d2": {"qa_asked": 4.0, "qa_correct": 4.0, "qa_tail_asked": 2.0, "qa_tail_correct": 2.0, "qa_cut": 0.0},
        "d3": {"qa_asked": None},
    }
    pooled = arxiv._qa_pooled(per_doc)
    assert pooled["qa_questions"] == {"value": 10, "n": 2}
    assert pooled["qa_pooled_accuracy"] == {"value": 0.8, "n": 10}
    assert pooled["qa_second_half"] == {"value": 0.6, "n": 5}
    assert pooled["qa_first_half"] == {"value": 1.0, "n": 5}
    assert pooled["qa_outputs_cut"] == {"value": 1, "n": 2}


def test_qa_scores_read_the_segments_and_the_cut_flag(tmp_path: Path) -> None:
    run = tmp_path / "run"
    (run / "qa" / "ezmd-main").mkdir(parents=True)
    record = {
        "cut": True,
        "items": [
            {"correct": True, "segment": {"from": 0, "to": 100, "of": 1000}},
            {"correct": False, "segment": {"from": 900, "to": 1000, "of": 1000}},
            {"correct": True, "segment": {"from": 600, "to": 700, "of": 1000}},
            {"answer_given": "x"},  # not graded yet
        ],
    }
    (run / "qa" / "ezmd-main" / "2601_00001.json").write_text(json.dumps(record), encoding="utf-8")
    result = DocResult("arxiv", "2601_00001", "c", "ezmd-main", "1", "ok", output="ezmd-main/2601_00001.md")
    score = arxiv.qa_scores(result, run)
    assert score == arxiv.QaScore(correct=2, asked=3, tail_correct=1, tail_asked=2, cut=True)
    assert score.accuracy == pytest.approx(2 / 3) and score.tail_accuracy == pytest.approx(0.5)
    other = DocResult("arxiv", "2601_00002", "c", "ezmd-main", "1", "ok", output="ezmd-main/2601_00002.md")
    assert arxiv.qa_scores(other, run) is None
