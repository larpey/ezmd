"""keys.json bootstrap keys (docs/spec/part4.md 4.11.1, P1-T10): hashed storage, per-key limits, client
restrictions, expiry, reload, and fail-fast on a malformed file."""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from ezmd_api.keys import KeysFileError, KeyStore, file_key_id, hash_api_key
from ezmd_api.settings import Settings
from ezmd_api.testing import api_client, make_settings, upload, use_in_process_isolation

PEPPER = "p" * 40
KEY = "ak_test_FileKeyForTheTestSuite01"


@pytest.fixture(autouse=True)
def _isolated(monkeypatch: pytest.MonkeyPatch) -> None:
    use_in_process_isolation(monkeypatch)


def _write(path: Path, entries: list[dict[str, Any]]) -> Path:
    path.write_text(json.dumps(entries), encoding="utf-8", newline="\n")
    return path


@pytest.fixture
def settings_for(tmp_path: Path) -> Callable[..., Settings]:
    def factory(entries: list[dict[str, Any]], **overrides: Any) -> Settings:
        keys = _write(tmp_path / "keys.json", entries)
        return make_settings(tmp_path / "data", keys_file=keys, key_pepper=PEPPER, **overrides)

    return factory


def _hashed(settings: Settings, **entry: Any) -> dict[str, Any]:
    return {"key_hash": hash_api_key(settings, KEY), "name": "ci", **entry}


def _base() -> Settings:
    return Settings(key_pepper=PEPPER)


async def test_hashed_file_key_authenticates_and_jobs_carry_its_id(settings_for: Callable[..., Settings]) -> None:
    settings = settings_for([_hashed(_base())])
    async with api_client(settings) as (client, app):
        r = await upload(client, b"hello\n", headers={"X-API-Key": KEY})
        assert r.status_code == 202, r.text
        row = app.state.services.jobs.require(r.json()["job"]["id"])
        assert row.api_key_id == file_key_id(hash_api_key(settings, KEY))
        bad = await upload(client, b"hello\n", headers={"X-API-Key": KEY + "x"})
        assert bad.status_code == 401


async def test_plaintext_file_key_is_hashed_at_load(settings_for: Callable[..., Settings]) -> None:
    settings = settings_for([{"key": KEY, "name": "legacy"}])
    async with api_client(settings) as (client, app):
        store = app.state.services.keys
        assert store is not None
        assert all(KEY not in repr(r) for r in store.records())
        assert (await upload(client, b"x\n", headers={"X-API-Key": KEY})).status_code == 202


async def test_per_key_window_limit(settings_for: Callable[..., Settings]) -> None:
    entry = _hashed(_base(), limits={"requests_per_window": 2, "window_s": 3600, "concurrency": 50})
    async with api_client(settings_for([entry])) as (client, _app):
        codes = [(await upload(client, f"{i}\n".encode(), headers={"X-API-Key": KEY})).status_code for i in range(3)]
        assert codes == [202, 202, 429]


async def test_key_upload_cap_and_page_cap(settings_for: Callable[..., Settings]) -> None:
    entry = _hashed(_base(), limits={"max_upload_mb": 1, "max_pages": 7})
    async with api_client(settings_for([entry], anon_max_upload_mb=50)) as (client, app):
        big = await upload(client, b"a" * (2 * 1024 * 1024), headers={"X-API-Key": KEY})
        assert big.status_code == 413
        ok = await upload(client, b"b\n", headers={"X-API-Key": KEY}, options={"max_pages": 500})
        row = app.state.services.jobs.require(ok.json()["job"]["id"])
        assert json.loads(row.options_json)["convert"]["max_pages"] == 7


async def test_ip_and_user_agent_allowlists(settings_for: Callable[..., Settings]) -> None:
    entry = _hashed(_base(), ips=["10.0.0.0/8"], user_agents=["ezmd-obsidian/*"])
    settings = settings_for([entry])
    async with api_client(settings, client_addr=("10.1.2.3", 4000)) as (client, _app):
        good = {"X-API-Key": KEY, "User-Agent": "ezmd-obsidian/1.2"}
        assert (await upload(client, b"1\n", headers=good)).status_code == 202
        wrong_ua = {"X-API-Key": KEY, "User-Agent": "curl/8"}
        assert (await upload(client, b"2\n", headers=wrong_ua)).status_code == 403
    async with api_client(settings, client_addr=("192.0.2.9", 4000)) as (client, _app):
        r = await upload(client, b"3\n", headers={"X-API-Key": KEY, "User-Agent": "ezmd-obsidian/1.2"})
        assert r.status_code == 403
        assert r.json()["error"]["code"] == "forbidden"


async def test_expired_file_key_is_rejected(settings_for: Callable[..., Settings]) -> None:
    entry = _hashed(_base(), expires="2020-01-01T00:00:00Z")
    async with api_client(settings_for([entry])) as (client, _app):
        assert (await upload(client, b"x\n", headers={"X-API-Key": KEY})).status_code == 401


@pytest.mark.parametrize(
    "content",
    [
        "{not json",
        json.dumps({"key": KEY}),
        json.dumps([{"name": "no key"}]),
        json.dumps([{"key": KEY, "key_hash": "0" * 64, "name": "both"}]),
        json.dumps([{"key_hash": "zz", "name": "bad hash"}]),
        json.dumps([{"key": KEY, "name": "typo", "limts": {}}]),
        json.dumps([{"key": KEY, "name": "a"}, {"key": KEY, "name": "dup"}]),
        json.dumps([{"key": KEY, "name": "cidr", "ips": ["not-a-cidr"]}]),
    ],
)
def test_malformed_keys_file_stops_startup_without_leaking_keys(tmp_path: Path, content: str) -> None:
    from ezmd_api.main import create_app

    path = tmp_path / "keys.json"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(KeysFileError) as info:
        create_app(make_settings(tmp_path / "data", keys_file=path, key_pepper=PEPPER))
    assert KEY not in str(info.value)


def test_reload_on_change_and_keep_previous_on_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import ezmd_api.keys as keys_mod

    monkeypatch.setattr(keys_mod, "RELOAD_CHECK_SECONDS", 0.0)
    settings = Settings(key_pepper=PEPPER, keys_file=tmp_path / "keys.json")
    digest = hash_api_key(settings, KEY)
    path = _write(tmp_path / "keys.json", [])
    store = KeyStore(settings)
    assert store.load() == 0
    assert store.get(digest) is None
    _write(path, [{"key_hash": digest, "name": "new"}])
    os.utime(path, (time.time() + 5, time.time() + 5))
    assert store.get(digest) is not None
    path.write_text("[broken", encoding="utf-8")
    os.utime(path, (time.time() + 10, time.time() + 10))
    assert store.get(digest) is not None, "a broken reload keeps the previous keys"


async def test_unlimited_file_key_skips_rate_limits(settings_for: Callable[..., Settings]) -> None:
    entry = _hashed(_base(), unlimited=True, tier="sponsor", limits={"requests_per_window": 1})
    async with api_client(settings_for([entry])) as (client, _app):
        codes = [(await upload(client, f"{i}\n".encode(), headers={"X-API-Key": KEY})).status_code for i in range(3)]
        assert codes == [202, 202, 202]


async def test_key_source_allow_and_deny_lists(
    settings_for: Callable[..., Settings], monkeypatch: pytest.MonkeyPatch
) -> None:
    from ezmd.core import netguard

    def offline(url: str, **kwargs: Any) -> Any:
        raise netguard.FetchFailed("network disabled in tests", url=url)

    monkeypatch.setattr(netguard, "fetch", offline)
    entry = _hashed(_base(), allowed_sources=["*.example.com"], disabled_sources=["private.example.com"])
    async with api_client(settings_for([entry])) as (client, _app):

        async def post(url: str) -> int:
            r = await client.post("/v1/convert", json={"url": url}, headers={"X-API-Key": KEY})
            return r.status_code

        assert await post("https://docs.example.com/a.html") == 202
        assert await post("https://private.example.com/a.html") == 403
        assert await post("https://example.org/a.html") == 403
