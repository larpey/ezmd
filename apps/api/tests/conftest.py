from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from ezmd_api.settings import Settings
from ezmd_api.testing import api_client, make_settings, use_in_process_isolation


@pytest.fixture(autouse=True)
def _fast_isolation(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    if "real_sandbox" not in request.keywords:
        use_in_process_isolation(monkeypatch)


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests never touch the network; tests that exercise fetching patch netguard.fetch themselves."""
    from ezmd.core import netguard

    def offline(url: str, **kwargs: Any) -> Any:
        raise netguard.FetchFailed("network disabled in tests", url=url)

    monkeypatch.setattr(netguard, "fetch", offline)


@pytest.fixture
def settings_factory(tmp_path: Path) -> Callable[..., Settings]:
    def factory(**overrides: Any) -> Settings:
        return make_settings(tmp_path / "data", **overrides)

    return factory


@pytest.fixture
async def client(settings_factory: Callable[..., Settings]) -> AsyncIterator[httpx.AsyncClient]:
    async with api_client(settings_factory()) as (c, _app):
        yield c


@pytest.fixture
async def client_app(settings_factory: Callable[..., Settings]) -> AsyncIterator[tuple[httpx.AsyncClient, FastAPI]]:
    async with api_client(settings_factory()) as pair:
        yield pair


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "real_sandbox: run conversions in the real spawn child")
