"""Unsupported inputs are refused before a job exists (S6): 415 `unsupported_media_type`, not 202 then 500."""

from __future__ import annotations

import random
from collections.abc import Callable
from typing import Any

import pytest

from ezmd_api.settings import Settings
from ezmd_api.testing import api_client, upload, wait_for_state

# Seeded so the bytes never look like a real format (os.urandom once began like a DOS executable on macOS CI,
# turning `no_converter` into `executable`); same approach as packages/core/tests/test_detect.py.
NOISE = bytes([0xA5]) + random.Random(20261023).randbytes(4095)


def _detected(mime: str, label: str | None = None) -> Callable[[Any], Any]:
    from ezmd.inputs import Detected

    def detect(ref: Any) -> Any:
        ref.detected = Detected(mime=mime, extension=None, confidence=0.99, magika_label=label)
        return ref.detected

    return detect


async def test_unknown_binary_upload_is_415_with_no_job(settings_factory: Callable[..., Settings]) -> None:
    async with api_client(settings_factory()) as (client, app):
        r = await upload(client, NOISE, "blob.bin", content_type="application/octet-stream")
        assert r.status_code == 415, r.text
        err = r.json()["error"]
        assert err["code"] == "unsupported_media_type"
        assert err["detail"] == {"mime": "application/octet-stream", "reason": "no_converter"}
        assert app.state.services.jobs.count_active() == 0


async def test_elf_that_detection_names_differently_is_still_415(
    monkeypatch: pytest.MonkeyPatch, settings_factory: Callable[..., Settings]
) -> None:
    """Magika labels real ELF binaries `application/x-executable-elf`, which the core executable list misses."""
    import ezmd.detect

    monkeypatch.setattr(ezmd.detect, "detect", _detected("application/x-executable-elf", "elf"))
    async with api_client(settings_factory()) as (client, _app):
        r = await upload(client, b"\x7fELF" + NOISE[:512], "ls", content_type="application/octet-stream")
    assert r.status_code == 415, r.text
    assert r.json()["error"]["code"] == "unsupported_media_type"


async def test_executable_reason_is_reported(settings_factory: Callable[..., Settings]) -> None:
    pe = b"MZ" + b"\x00" * 58 + (64).to_bytes(4, "little") + b"PE\x00\x00" + b"\x00" * 512
    async with api_client(settings_factory()) as (client, _app):
        r = await upload(client, pe, "setup.exe", content_type="application/octet-stream")
    assert r.status_code == 415
    assert r.json()["error"]["detail"]["reason"] == "executable"


async def test_supported_text_still_accepted(client: Any) -> None:
    r = await upload(client, b"hello\n", "a.txt")
    assert r.status_code == 202


async def test_fetched_body_nothing_can_convert_fails_as_unsupported(
    monkeypatch: pytest.MonkeyPatch, client: Any
) -> None:
    from ezmd.core import netguard
    from ezmd.core.netguard import FetchResult

    def fetch(url: str, **kwargs: Any) -> FetchResult:
        return FetchResult(
            url=url,
            status=200,
            headers={"content-type": "application/octet-stream"},
            body=NOISE,
            resolved_ip="93.184.216.34",
            redirects=[],
            duration_seconds=0.01,
        )

    monkeypatch.setattr(netguard, "fetch", fetch)
    r = await client.post("/v1/convert", json={"url": "https://example.com/blob"})
    body = await wait_for_state(client, r.json()["job"]["id"])
    assert body["state"] == "failed"
    assert body["error"]["code"] == "unsupported_media_type"
    assert body["error"]["status"] == 415
