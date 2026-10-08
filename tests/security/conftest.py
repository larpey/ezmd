"""Security test tiers (docs/spec/part4.md 4.14.5).

fast     every test here not marked `network`. Runs on every PR (`pytest tests/security -m fast`, or as
         part of the plain `pytest tests` run). A guard refuses any socket connect outside loopback, so
         a fast test that reaches the network fails instead of passing on a networked runner.
network  marked `network`; runs in the integration workflow against the compose stack and skips unless
         EZMD_NETWORK_TESTS=1 and EZMD_BASE_URL are set (`tests/integration/stack.sh env`).
"""

from __future__ import annotations

import ipaddress
import os
import socket
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

HERE = Path(__file__).resolve().parent
_LOOPBACK_NAMES = frozenset({"localhost", "localhost.", ""})


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "fast: security test without network access (runs on every PR)")


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    for item in items:
        if HERE in Path(str(item.path)).resolve().parents and not item.get_closest_marker("network"):
            item.add_marker(pytest.mark.fast)


def _is_local(address: Any) -> bool:
    if not isinstance(address, tuple):
        return True  # AF_UNIX path or abstract socket
    host = str(address[0]).split("%", 1)[0]
    if host.lower() in _LOOPBACK_NAMES:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False  # a host name: resolving and connecting to it is network access


@pytest.fixture(autouse=True)
def _security_tier(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    if request.node.get_closest_marker("network"):
        if os.environ.get("EZMD_NETWORK_TESTS") != "1" or not os.environ.get("EZMD_BASE_URL"):
            pytest.skip("network tier: set EZMD_NETWORK_TESTS=1 and EZMD_BASE_URL (tests/integration/stack.sh)")
        yield
        return

    real_connect = socket.socket.connect
    real_connect_ex = socket.socket.connect_ex

    def guarded_connect(self: socket.socket, address: Any) -> None:
        if not _is_local(address):
            raise AssertionError(f"fast-tier security test tried to connect to {address!r}; mark it `network`")
        real_connect(self, address)

    def guarded_connect_ex(self: socket.socket, address: Any) -> int:
        if not _is_local(address):
            raise AssertionError(f"fast-tier security test tried to connect to {address!r}; mark it `network`")
        return real_connect_ex(self, address)

    monkeypatch.setattr(socket.socket, "connect", guarded_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", guarded_connect_ex)
    yield
