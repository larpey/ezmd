"""The real console entry point over stdio: starts quickly and answers list_capabilities (4.4.6)."""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pytest
from mcp import Client, StdioServerParameters


@pytest.mark.slow
async def test_stdio_server_answers_list_capabilities(tmp_path: Path) -> None:
    params = StdioServerParameters(
        command=sys.executable, args=["-m", "ezmd_mcp.cli", "--allowed-dirs", str(tmp_path)], cwd=str(tmp_path)
    )
    start = time.monotonic()
    async with Client(params) as client:
        res = await client.call_tool("list_capabilities", {})
        elapsed = time.monotonic() - start
    assert not res.is_error
    assert res.structured_content["server"]["default_profile"] == "agent"
    # 2 s on a warm machine (the spec target); generous here because CI runners and Windows are slow.
    assert elapsed < 15, elapsed
