"""Size caps, rate limits, admission control."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from ezmd_api.settings import Settings
from ezmd_api.testing import api_client, upload, wait_for_state


async def test_413_over_cap_streaming(settings_factory: Callable[..., Settings]) -> None:
    async with api_client(settings_factory(anon_max_upload_mb=1)) as (client, _):
        limit = 1024 * 1024
        r = await upload(client, b"a" * (limit + 1), "big.txt")
        assert r.status_code == 413
        err = r.json()["error"]
        assert err["code"] == "input_too_large"
        assert err["detail"]["limit_bytes"] == limit
        assert err["detail"]["received_bytes"] > limit
        # Real text: Magika calls a megabyte of one repeated byte an ISO image, which nothing converts (415).
        ok = await upload(client, (b"a line of plain text\n" * (limit // 21 + 1))[:limit], "edge.txt")
        assert ok.status_code == 202, ok.text


async def test_413_on_declared_content_length(settings_factory: Callable[..., Settings]) -> None:
    async with api_client(settings_factory(anon_max_upload_mb=1)) as (client, _):
        r = await client.post(
            "/v1/convert",
            content=b"--x--\r\n",
            headers={"content-type": "multipart/form-data; boundary=x", "content-length": str(50 * 1024 * 1024)},
        )
        assert r.status_code == 413


async def test_429_with_headers(settings_factory: Callable[..., Settings]) -> None:
    async with api_client(settings_factory(anon_ratelimit_max=2, anon_ratelimit_window_s=60)) as (client, _):
        first = await upload(client, b"one\n", "1.txt")
        assert first.status_code == 202
        assert first.headers["x-ratelimit-limit"] == "2"
        assert first.headers["x-ratelimit-remaining"] == "1"
        assert int(first.headers["x-ratelimit-reset"]) > 0
        await upload(client, b"two\n", "2.txt")
        third = await upload(client, b"three\n", "3.txt")
        assert third.status_code == 429
        assert third.json()["error"]["code"] == "rate_limited"
        assert third.headers["x-ratelimit-remaining"] == "0"
        assert int(third.headers["retry-after"]) >= 1


async def test_rate_limit_is_per_client_ip(settings_factory: Callable[..., Settings]) -> None:
    settings = settings_factory(anon_ratelimit_max=1)
    async with api_client(settings, client_addr=("203.0.113.5", 1)) as (a, _):
        assert (await upload(a, b"x\n", "a.txt")).status_code == 202
        assert (await upload(a, b"y\n", "b.txt")).status_code == 429
    async with api_client(settings, client_addr=("203.0.113.6", 1)) as (b, _):
        assert (await upload(b, b"z\n", "c.txt")).status_code == 202


async def test_result_fetch_rate_limited(settings_factory: Callable[..., Settings]) -> None:
    async with api_client(settings_factory(anon_result_ratelimit_max=1)) as (client, _):
        r = await upload(client, b"hello\n", "a.txt")
        job_id = r.json()["job"]["id"]
        await wait_for_state(client, job_id)
        assert (await client.get(f"/v1/jobs/{job_id}/result")).status_code == 200
        limited = await client.get(f"/v1/jobs/{job_id}/result")
        assert limited.status_code == 429
        assert "retry-after" in limited.headers


async def test_concurrency_admission(settings_factory: Callable[..., Settings]) -> None:
    async with api_client(settings_factory(anon_concurrency=1)) as (client, app):
        services = app.state.services
        r = await upload(client, b"first\n", "a.txt")
        job_id = r.json()["job"]["id"]
        await wait_for_state(client, job_id)
        services.jobs.update(job_id, state="converting")  # simulate a still-running job
        busy = await upload(client, b"second\n", "b.txt")
        assert busy.status_code == 429
        assert busy.json()["error"]["detail"]["concurrent_limit"] == 1


async def test_global_cap_returns_queue_unavailable(settings_factory: Callable[..., Settings]) -> None:
    async with api_client(settings_factory(max_active_jobs=1)) as (client, app):
        r = await upload(client, b"first\n", "a.txt")
        job_id = r.json()["job"]["id"]
        await wait_for_state(client, job_id)
        app.state.services.jobs.update(job_id, state="converting")
        busy = await upload(client, b"second\n", "b.txt")
        assert busy.status_code == 503
        assert busy.json()["error"]["code"] == "queue_unavailable"
        assert busy.headers["retry-after"] == "30"


async def test_upload_over_the_core_default_but_under_the_anon_cap_is_accepted(
    settings_factory: Callable[..., Settings], tmp_path: Path
) -> None:
    """Regression: 100-200 MB anonymous uploads hit ezmd.inputs' 100 MiB default during detection (500)."""
    import fakeredis

    from ezmd.inputs import DEFAULT_MAX_BYTES

    big = tmp_path / "big.txt"
    line = b"plain text line for the size regression\n"
    with big.open("wb") as fh:
        for _ in range(DEFAULT_MAX_BYTES // len(line) + 1024):
            fh.write(line)
    assert big.stat().st_size > DEFAULT_MAX_BYTES
    settings = settings_factory(queue="rq", anon_max_upload_mb=200)
    async with api_client(settings, redis_client=fakeredis.FakeRedis()) as (client, _):
        with big.open("rb") as fh:
            r = await client.post("/v1/convert", files={"file": ("big.txt", fh, "text/plain")})
    assert r.status_code == 202, r.text


def test_detection_input_too_large_is_a_413(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import ezmd.detect
    from ezmd.inputs import InputTooLarge
    from ezmd_api.errors import ApiError
    from ezmd_api.routes.convert import _detect_upload
    from ezmd_api.uploads import UploadedFile

    def too_big(ref: object) -> object:
        raise InputTooLarge("1 bytes exceeds cap 0")

    monkeypatch.setattr(ezmd.detect, "detect", too_big)
    path = tmp_path / "f.txt"
    path.write_bytes(b"x")
    with pytest.raises(ApiError) as info:
        _detect_upload(UploadedFile(path=path, filename="f.txt", content_type=None, size=1, sha256="0" * 64))
    assert info.value.code == "input_too_large"
    assert info.value.status == 413


@pytest.mark.parametrize("backend", ["memory", "redis"])
def test_retry_after_never_exceeds_the_window(backend: str) -> None:
    """N4: a 60 s window answered Retry-After: 61."""
    import fakeredis

    from ezmd_api.state import MemoryState, RedisState

    state = MemoryState() if backend == "memory" else RedisState(fakeredis.FakeRedis())
    assert state.rate_hit("k", 1, 60).allowed
    denied = state.rate_hit("k", 1, 60)
    assert not denied.allowed
    assert 59 <= denied.retry_after <= 60


async def test_413_and_429_do_not_spend_creation_tokens(settings_factory: Callable[..., Settings]) -> None:
    """N4: rejected requests (over the size cap, over the concurrency cap) no longer use up the window."""
    import fakeredis

    settings = settings_factory(queue="rq", anon_ratelimit_max=2, anon_max_upload_mb=1, anon_concurrency=1)
    async with api_client(settings, redis_client=fakeredis.FakeRedis()) as (client, app):
        for _ in range(3):
            assert (await upload(client, b"x" * (1024 * 1024 + 1), "big.txt")).status_code == 413
        first = await upload(client, b"first\n", "a.txt")
        assert first.status_code == 202  # stays queued: no worker in this test
        for _ in range(3):
            assert (await upload(client, b"second\n", "b.txt")).status_code == 429  # concurrency
        app.state.services.jobs.fail(first.json()["job"]["id"], "internal_error", "test")
        assert (await upload(client, b"third\n", "c.txt")).status_code == 202
        limited = await upload(client, b"fourth\n", "d.txt")
        assert limited.status_code == 429
        assert limited.json()["error"]["detail"]["window_seconds"] == 60


class _StubRequest:
    def __init__(self, chunks: list[bytes], fail: BaseException) -> None:
        self.headers = {"content-type": "multipart/form-data; boundary=x"}
        self._chunks = chunks
        self._fail = fail

    async def stream(self) -> Any:
        for chunk in self._chunks:
            yield chunk
        raise self._fail


BODY_START = b'--x\r\nContent-Disposition: form-data; name="file"; filename="a.txt"\r\n\r\nhello'


async def test_cancelled_upload_removes_its_temp_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Red team LOW: a client disconnect (CancelledError) left the spooled upload on /tmp."""
    import asyncio
    import tempfile

    from ezmd_api.uploads import parse_multipart

    made: list[str] = []
    real = tempfile.mkdtemp

    def mkdtemp(**kw: Any) -> str:
        made.append(real(dir=tmp_path, **kw))
        return made[-1]

    monkeypatch.setattr(tempfile, "mkdtemp", mkdtemp)
    with pytest.raises(asyncio.CancelledError):
        await parse_multipart(_StubRequest([BODY_START], asyncio.CancelledError()), max_file_bytes=1024)  # type: ignore[arg-type]
    assert made and not Path(made[0]).exists()


async def test_disk_full_is_a_logged_5xx(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    """Red team LOW: ENOSPC while spooling answered 400 "Malformed multipart body"."""
    import errno

    from ezmd_api import uploads
    from ezmd_api.errors import ApiError

    def full(self: Any, data: bytes, start: int, end: int) -> None:
        raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(uploads._Collector, "on_part_data", full)
    with pytest.raises(ApiError) as info:
        await uploads.parse_multipart(_StubRequest([BODY_START], StopAsyncIteration()), max_file_bytes=1024)  # type: ignore[arg-type]
    assert info.value.status >= 500
    assert info.value.code == "internal_error"
    assert any(r.levelname == "ERROR" for r in caplog.records)
