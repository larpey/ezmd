"""GET /v1/warnings and JobOut.warnings (deferred by D-0017, built in P1-T10)."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from ezmd.ir import Warning
from ezmd.warnings.codes import ALIASES, CODES, WarningKind
from ezmd_api.testing import upload, wait_for_state


async def test_registry_lists_every_code_with_aliases(client: httpx.AsyncClient) -> None:
    r = await client.get("/v1/warnings")
    assert r.status_code == 200
    assert "max-age" in r.headers["cache-control"]
    rows = r.json()["warnings"]
    by_code = {row["code"]: row for row in rows}
    assert set(by_code) == {k.value for k in CODES}
    assert [row["code"] for row in rows] == sorted(by_code)
    for alias, kind in ALIASES.items():
        assert alias in by_code[kind.value]["aliases"]
    truncated = by_code[WarningKind.TRUNCATED.value]
    assert truncated["truncates"] is True
    for row in rows:
        assert row["severity"] in ("info", "warning", "error")
        assert row["description"] and row["suggestion"]


@pytest.fixture
def emit_warnings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Append warnings (one duplicated, one via a retired alias) to every real conversion result."""
    import ezmd.pipeline as pipeline

    real = pipeline.convert_ref

    def wrapped(*args: Any, **kwargs: Any) -> Any:
        result = real(*args, **kwargs)
        result.warnings.extend(
            [
                Warning(kind=WarningKind.ENCODING_UNCERTAIN, message="low confidence"),
                Warning(kind="encoding_guessed", message="alias spelling"),  # type: ignore[arg-type]
                Warning(kind=WarningKind.TRUNCATED, message="cut"),
            ]
        )
        return result

    monkeypatch.setattr(pipeline, "convert_ref", wrapped)


@pytest.mark.usefixtures("emit_warnings")
async def test_job_out_lists_canonical_codes_once(client: httpx.AsyncClient) -> None:
    created = await upload(client, b"hello warnings\n", "w.txt")
    assert created.json()["job"]["warnings"] == []
    job = await wait_for_state(client, created.json()["job"]["id"])
    assert job["state"] == "done", job
    assert job["warnings"] == ["encoding_uncertain", "truncated"]
    assert job["warnings_count"] == 3
    registry = {row["code"] for row in (await client.get("/v1/warnings")).json()["warnings"]}
    assert set(job["warnings"]) <= registry


def test_warning_codes_tolerates_bad_rows() -> None:
    from ezmd_api.db import JobRow
    from ezmd_api.schemas import warning_codes_of

    assert warning_codes_of(JobRow(warning_codes="not json")) == []
    assert warning_codes_of(JobRow(warning_codes=json.dumps({"a": 1}))) == []
    assert warning_codes_of(JobRow(warning_codes='["a", 2]')) == ["a", "2"]
