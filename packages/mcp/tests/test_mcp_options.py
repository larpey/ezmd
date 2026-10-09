"""Tool callers (an LLM) may not raise conversion limits or pick engines: only an allowlist of output
options is settable, and the operator's limits (ezmd-mcp flags) are ceilings."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from conftest import call, make_server
from mcp import Client

from ezmd_mcp.cli import parse_args
from ezmd_mcp.config import Settings
from ezmd_mcp.errors import ToolFailure
from ezmd_mcp.local import LocalBackend
from ezmd_mcp.options import OperatorLimits


@pytest.mark.parametrize(
    "options",
    [
        {"extra": {"specialized.archive_max_total": 10**12}},
        {"converter": "text.plain"},
        {"experimental": True},
        {"max_bytes": 10**12},
        {"max_seconds": 10**6},
        {"max_pages": 10**6},
        {"max_pages": None},
        {"max_duration_seconds": None},
    ],
)
def test_limit_raising_and_engine_keys_are_refused(options: dict[str, Any]) -> None:
    with pytest.raises(ToolFailure) as info:
        LocalBackend()._options(options)
    assert info.value.code == "invalid_request"
    assert next(iter(options)) in info.value.message


def test_harmless_options_and_lower_limits_are_allowed() -> None:
    opts = LocalBackend()._options(
        {"ocr": False, "languages": ["en"], "max_pages": 5, "max_bytes": 1000, "render": {"chunks.chunk_tokens": 256}}
    )
    assert opts.ocr is False and opts.max_pages == 5 and opts.max_bytes == 1000
    assert opts.render == {"chunks.chunk_tokens": 256}


def test_operator_limits_apply_when_the_caller_sets_none() -> None:
    limits = OperatorLimits(max_bytes=2048, max_seconds=30.0, max_pages=7, max_duration_seconds=60.0)
    opts = LocalBackend(limits=limits)._options({})
    assert (opts.max_bytes, opts.max_seconds, opts.max_pages, opts.max_duration_seconds) == (2048, 30.0, 7, 60.0)
    with pytest.raises(ToolFailure, match="max_pages"):
        LocalBackend(limits=limits)._options({"max_pages": 8})


def test_cli_flags_set_the_operator_limits() -> None:
    args = parse_args(["--max-bytes", "4096", "--max-seconds", "15", "--max-pages", "3", "--max-duration-seconds", "9"])
    settings = Settings.from_env(
        {},
        max_bytes=args.max_bytes,
        max_seconds=args.max_seconds,
        max_pages=args.max_pages,
        max_duration_seconds=args.max_duration_seconds,
    )
    assert settings.limits == OperatorLimits(max_bytes=4096, max_seconds=15.0, max_pages=3, max_duration_seconds=9.0)


async def test_tool_call_cannot_raise_archive_cap(root: Path) -> None:
    async with Client(make_server(root)) as client:
        res = await call(
            client,
            "convert_text",
            {"text": "hello"},
        )
        assert not res.is_error
        res = await call(
            client,
            "convert_url",
            {"url": "https://example.com/", "options": {"extra": {"specialized.archive_max_total": 10**12}}},
        )
        assert res.is_error and res.structured_content["error"]["code"] == "invalid_request"
        assert "extra" in res.structured_content["error"]["message"]


async def test_capabilities_report_operator_limits(root: Path) -> None:
    async with Client(make_server(root)) as client:
        caps = (await call(client, "list_capabilities")).structured_content
        assert caps["limits"]["max_bytes"] == OperatorLimits().max_bytes
        assert "ocr" in caps["tool_options"] and "extra" not in caps["tool_options"]


def test_every_library_option_is_classified() -> None:
    """A new `ezmd.library.Options` field must be placed in exactly one list before tools can set it."""
    from ezmd.library import Options
    from ezmd_mcp.options import LIMIT_FIELDS, SERVER_FIELDS, TOOL_FIELDS

    groups = [set(TOOL_FIELDS), set(LIMIT_FIELDS), set(SERVER_FIELDS)]
    assert set().union(*groups) == set(Options.model_fields)
    assert sum(len(g) for g in groups) == len(Options.model_fields)
    defaults = Options()
    assert OperatorLimits().as_dict() == {k: getattr(defaults, k) for k in LIMIT_FIELDS}
