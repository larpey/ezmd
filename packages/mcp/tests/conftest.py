"""Shared fixtures for the intomd MCP server tests: an in-memory client session over a local-mode server."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
from mcp import Client

from intomd_mcp.config import Settings
from intomd_mcp.local import LocalBackend
from intomd_mcp.paths import AllowedRoots
from intomd_mcp.server import build_server

NEXT_NOTE = re.compile(r'\n*<!-- intomd: (?:continued|truncated[^"]*); next_cursor="[A-Za-z0-9_-]+" -->\s*$')
FENCE_OPEN = re.compile(r"^<!-- intomd: The content between[^\n]*-->\n<untrusted_content [^\n]*>\n")
FENCE_CLOSE = re.compile(r"\n</untrusted_content>\n?$")


def unwrap(body: str) -> str:
    """A page body without the agent fence and without the trailing continuation note."""
    body = FENCE_OPEN.sub("", body, count=1)
    body = FENCE_CLOSE.sub("", body, count=1)
    body = NEXT_NOTE.sub("", body, count=1)
    return body.strip("\n")


def make_server(root: Path, **settings: Any) -> Any:
    s = Settings(allowed_dirs=AllowedRoots.from_strings([str(root)]), **settings)
    return build_server(s, LocalBackend())


@pytest.fixture
def root(tmp_path: Path) -> Path:
    d = tmp_path / "root"
    d.mkdir()
    return d.resolve()


async def call(client: Client, name: str, args: dict[str, Any] | None = None) -> Any:
    return await client.call_tool(name, args or {})


def text_of(result: Any) -> str:
    return "".join(getattr(c, "text", "") for c in result.content)
