"""Integration tier: tests against a running compose stack (docs/spec/part4.md 4.14.3).

Every test here is marked `integration` and skips unless EZMD_BASE_URL points at a stack
(`tests/integration/stack.sh up`, then `stack.sh env`). Owner-key calls read the key from
EZMD_API_KEY or EZMD_API_KEY_FILE. Tests marked `private_fetch` need the stack restarted with
EZMD_ALLOW_PRIVATE_NETWORKS=true (`stack.sh private`) and skip unless EZMD_PRIVATE_FETCH=1.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from stackclient import Stack

HERE = Path(__file__).resolve().parent


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "integration: needs a running compose stack (EZMD_BASE_URL)")
    config.addinivalue_line("markers", "private_fetch: needs EZMD_ALLOW_PRIVATE_NETWORKS=true on the stack")
    config.addinivalue_line("markers", "ratelimit: consumes the anonymous creation budget; run last")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    for item in items:
        if HERE in Path(str(item.path)).resolve().parents:
            item.add_marker(pytest.mark.integration)


@pytest.fixture(autouse=True)
def _require_stack(request: pytest.FixtureRequest) -> None:
    if not os.environ.get("EZMD_BASE_URL"):
        pytest.skip("no stack: set EZMD_BASE_URL (tests/integration/stack.sh up && stack.sh env)")
    if request.node.get_closest_marker("private_fetch") and os.environ.get("EZMD_PRIVATE_FETCH") != "1":
        pytest.skip("needs EZMD_PRIVATE_FETCH=1 and a stack started with `stack.sh private`")


@pytest.fixture(scope="session")
def stack() -> Iterator[Stack]:
    # Session-scoped fixtures are set up before the per-test autouse check, so skip here as well.
    if not os.environ.get("EZMD_BASE_URL"):
        pytest.skip("no stack: set EZMD_BASE_URL (tests/integration/stack.sh up && stack.sh env)")
    s = Stack.from_env()
    try:
        yield s
    finally:
        s.close()


@pytest.fixture
def owner(stack: Stack) -> httpx.Client:
    return stack.owner


@pytest.fixture
def anon(stack: Stack) -> httpx.Client:
    return stack.anon
