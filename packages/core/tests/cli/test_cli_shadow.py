"""`ezmd shadow-run`: engine discovery, comparison against the reference engine, output, exit codes."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from typer.testing import CliRunner

from ezmd.cli import app
from ezmd.cli.shadow import EngineRun, FileReport, discover, select_engines, shadow_file, summarize
from ezmd.inputs import InputRef
from ezmd.ir import Document
from ezmd.registry import ConversionError, ConvertOptions, default_registry, reset_default_registry

runner = CliRunner()
ROOT = Path(__file__).resolve().parents[4]
TEXT_FIXTURES = ROOT / "fixtures" / "text"
KITCHEN_SINK = TEXT_FIXTURES / "markdown-kitchen-sink" / "input.md"
# The text fixture corpus grows (P1-T19); derive the expected discovery from it instead of hard-coding counts.
TEXT_INPUTS = sorted(TEXT_FIXTURES.glob("*/input.*"))


def _json(args: list[str]) -> dict[str, object]:
    res = runner.invoke(app, ["shadow-run", *args, "--json"])
    assert res.exit_code == 0, res.output
    data = json.loads(res.stdout)
    assert isinstance(data, dict)
    return data


def test_table_on_fixture_subset() -> None:
    res = runner.invoke(app, ["shadow-run", str(TEXT_FIXTURES)], env={"COLUMNS": "140"})
    assert res.exit_code == 0, res.output
    out = res.stdout
    assert "text.markdown_passthrough *" in out
    assert "text.plain" in out
    multi = sum(1 for p in TEXT_INPUTS if p.suffix == ".md")  # Markdown has two engines, plain text one
    assert f"summary: {len(TEXT_INPUTS)} files, {multi} with 2+ engines" in out
    for col in ("engine", "time s", "blocks", "headings", "tables", "warnings", "text", "structure"):
        assert col in out


def test_json_compares_every_engine_against_the_reference() -> None:
    data = _json([str(KITCHEN_SINK)])
    files = data["files"]
    assert isinstance(files, list) and len(files) == 1
    rep = files[0]
    assert rep["mime"] == "text/markdown"
    assert rep["reference"] == "text.markdown_passthrough"
    engines = {e["engine"]: e for e in rep["engines"]}
    assert set(engines) == {"text.markdown_passthrough", "text.plain"}
    ref = engines["text.markdown_passthrough"]
    assert ref["status"] == "ok" and ref["text_similarity"] == 1.0 and ref["structure_similarity"] == 1.0
    assert ref["headings"] > 0 and ref["tables"] > 0 and ref["blocks"] > 0
    plain = engines["text.plain"]
    assert plain["headings"] == 0 and plain["text_similarity"] < 1.0
    assert rep["pairs"] and rep["pairs"][0]["a"] == "text.markdown_passthrough"
    assert {"text", "structure", "overall"} <= set(rep["pairs"][0])
    summary = data["summary"]
    assert isinstance(summary, dict) and summary["files"] == 1 and summary["files_compared"] == 1


def test_engines_filter_and_profile() -> None:
    data = _json([str(KITCHEN_SINK), "--engines", "plain", "--profile", "compact"])
    assert data["profile"] == "compact"
    rep = data["files"][0]  # type: ignore[index]
    assert [e["engine"] for e in rep["engines"]] == ["text.plain"]
    assert rep["reference"] == "text.plain"


def test_glob_and_fixture_aware_directory_discovery(tmp_path: Path) -> None:
    found = discover([str(TEXT_FIXTURES)])
    assert [p.name for p in found] == [p.name for p in TEXT_INPUTS]
    assert len(found) >= 4
    (tmp_path / "a.txt").write_text("hello", encoding="utf-8")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "b.md").write_text("# b", encoding="utf-8")
    (tmp_path / ".hidden").write_text("x", encoding="utf-8")
    assert [p.name for p in discover([str(tmp_path)])] == ["a.txt", "b.md"]
    assert [p.name for p in discover([str(tmp_path / "*.txt"), str(tmp_path / "a.txt")])] == ["a.txt"]


@pytest.mark.parametrize(
    ("args", "needle"),
    [
        (["does-not-exist.txt"], "no such file"),
        ([str(KITCHEN_SINK), "--engines", "nope"], "no converter matches"),
        ([str(KITCHEN_SINK), "--profile", "bogus"], "unknown profile"),
        ([str(KITCHEN_SINK), "--timeout", "0"], "--timeout"),
    ],
)
def test_usage_errors_exit_2(args: list[str], needle: str) -> None:
    res = runner.invoke(app, ["shadow-run", *args])
    assert res.exit_code == 2
    assert needle in res.output


def test_select_engines() -> None:
    known = ["text.plain", "web.rules", "documents.docx"]
    assert select_engines(None, known) is None
    assert select_engines("plain, documents.docx", known) == frozenset({"text.plain", "documents.docx"})
    with pytest.raises(ValueError):
        select_engines(" , ", known)


class _Crashes:
    id = "testing.crashes"
    family = "text"
    priority = 100
    experimental = False
    requires_extras: tuple[str, ...] = ()
    mimes: tuple[str, ...] = ("text/markdown",)

    def can_handle(self, ref: InputRef) -> float:
        return 1.0 if ref.detected is not None and ref.detected.mime == "text/markdown" else 0.0

    def convert(self, ref: InputRef, options: ConvertOptions) -> Document:
        raise ConversionError("boom", user_message="The test engine failed.")


@pytest.fixture
def crashing_engine() -> Iterator[None]:
    reset_default_registry()
    default_registry().register(_Crashes(), source="test")
    yield
    reset_default_registry()


@pytest.mark.usefixtures("crashing_engine")
def test_failing_engine_is_reported_and_reference_falls_through() -> None:
    rep = shadow_file(KITCHEN_SINK)
    first = rep.runs[0]
    assert first.engine == "testing.crashes" and first.status == "failed" and first.error
    assert rep.reference == "text.markdown_passthrough"
    res = runner.invoke(app, ["shadow-run", str(KITCHEN_SINK)], env={"COLUMNS": "140"})
    assert res.exit_code == 0
    assert "testing.crashes failed" in res.stdout


def test_summary_leaves_the_reference_out_of_mean_similarity() -> None:
    runs = (
        EngineRun(engine="a", status="ok", seconds=1.0, text_similarity=1.0, structure_similarity=1.0),
        EngineRun(engine="b", status="ok", seconds=3.0, text_similarity=0.5, structure_similarity=0.25),
        EngineRun(engine="c", status="failed", seconds=0.5, error="x"),
    )
    summary = summarize([FileReport(path="f", mime="text/plain", reference="a", runs=runs)])
    rows = {r["engine"]: r for r in summary["engines"]}  # type: ignore[union-attr]
    assert rows["a"]["reference"] == 1 and rows["a"]["mean_text_similarity"] is None
    assert rows["b"]["mean_text_similarity"] == 0.5 and rows["b"]["mean_structure_similarity"] == 0.25
    assert rows["c"]["failed"] == 1
    assert summary["files_compared"] == 1
