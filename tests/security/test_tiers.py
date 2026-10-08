"""The fast tier really has no network (tests/security/conftest.py guard)."""

from __future__ import annotations

import socket

import pytest


def test_fast_tier_refuses_non_loopback_connects() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s, pytest.raises(AssertionError, match="mark it"):
        s.connect(("192.0.2.1", 80))  # TEST-NET-1: never routed, and the guard fires before any packet


def test_fast_tier_allows_loopback() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as srv:
        srv.bind(("127.0.0.1", 0))
        srv.listen(1)
        with socket.create_connection(srv.getsockname(), timeout=5):
            pass


def test_marker_applied(request: pytest.FixtureRequest) -> None:
    assert request.node.get_closest_marker("fast") is not None
