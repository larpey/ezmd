"""The real spawn-child sandbox path (docs/spec/part1.md section 8.1)."""

from __future__ import annotations

from pathlib import Path

import pytest

from ezmd_api.isolation import ChildRequest, run_isolated

BINARY = bytes([0, 1, 2, 255]) * 64


def _req(tmp_path: Path, data: bytes, name: str = "a.md") -> ChildRequest:
    body = tmp_path / "input"
    body.write_bytes(data)
    return ChildRequest(
        input_path=str(body),
        out_path=str(tmp_path / "result.json"),
        display=name,
        kind="bytes",
        url=None,
        declared_mime="text/markdown",
        convert_options={"max_pages": 10},
        converter_id=None,
        max_seconds=60,
        mem_mb=4096,
        max_bytes=1024 * 1024,
    )


@pytest.mark.real_sandbox
def test_spawn_child_converts(tmp_path: Path) -> None:
    from ezmd.ir import ConversionResult

    outcome = run_isolated(_req(tmp_path, b"# Hello" + bytes([10, 10]) + b"from a child process"))
    assert outcome.status == "ok", outcome
    result = ConversionResult.model_validate_json(outcome.result_json or "")
    assert result.converter_id == "text.markdown_passthrough"


@pytest.mark.real_sandbox
def test_spawn_child_reports_conversion_error(tmp_path: Path) -> None:
    # A damaged file of a supported type is conversion_failed; a type nothing converts carries core's
    # stable unsupported_media_type through the child (D-0065).
    broken = run_isolated(_req(tmp_path, b"%PDF-1.7\n" + b"\x00\x01garbage" * 64, "broken.pdf"))
    assert (broken.status, broken.code) == ("error", "conversion_failed")
    blob = run_isolated(_req(tmp_path, BINARY, "x.bin"))
    assert (blob.status, blob.code) == ("error", "unsupported_media_type")


@pytest.mark.real_sandbox
def test_spawn_child_killed_on_wall_clock(tmp_path: Path) -> None:
    outcome = run_isolated(_req(tmp_path, b"# slow"), kill_after=0.01)
    assert outcome.status == "timeout"
    assert outcome.code == "timeout"
