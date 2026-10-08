"""GET /metrics (docs/spec/part4.md 4.10.5, P1-T10): not mounted without EZMD_METRICS_TOKEN, bearer
required, Prometheus text with the job, queue, duration, warning, rate-limit, and fetch-node series."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from ezmd_api.metrics import escape_label, series
from ezmd_api.settings import Settings
from ezmd_api.testing import api_client, make_settings, upload, use_in_process_isolation, wait_for_state

TOKEN = "metrics-token-0123456789"


@pytest.fixture(autouse=True)
def _isolated(monkeypatch: pytest.MonkeyPatch) -> None:
    use_in_process_isolation(monkeypatch)


async def test_metrics_not_mounted_without_token(tmp_path: Path) -> None:
    async with api_client(make_settings(tmp_path / "data")) as (client, _app):
        r = await client.get("/metrics", headers={"Authorization": f"Bearer {TOKEN}"})
        assert r.status_code == 404
        assert "/metrics" not in (await client.get("/openapi.json")).text


@pytest.mark.parametrize(
    "header", [None, "Bearer wrong-token-0123456789", f"Basic {TOKEN}", f"Bearer {TOKEN}x", "Bearer"]
)
async def test_metrics_requires_the_bearer_token(tmp_path: Path, header: str | None) -> None:
    async with api_client(make_settings(tmp_path / "data", metrics_token=TOKEN)) as (client, _app):
        headers = {"Authorization": header} if header else {}
        r = await client.get("/metrics", headers=headers)
        assert r.status_code == 401
        assert r.json()["error"]["code"] == "unauthorized"
        assert TOKEN not in r.text


def test_short_metrics_token_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="EZMD_METRICS_TOKEN"):
        Settings(data_dir=tmp_path, metrics_token="short")


async def test_metrics_series_after_a_job(tmp_path: Path) -> None:
    settings = make_settings(tmp_path / "data", metrics_token=TOKEN, anon_ratelimit_max=1)
    async with api_client(settings) as (client, app):
        created = await upload(client, b"# Title\n\nhello\n", "notes.md", content_type="text/markdown")
        await wait_for_state(client, created.json()["job"]["id"])
        limited = await upload(client, b"again\n", "b.txt")
        assert limited.status_code == 429
        app.state.services.state.node_heartbeat("pi-home-1", {})
        r = await client.get("/metrics", headers={"Authorization": f"Bearer {TOKEN}"})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/plain; version=0.0.4")
    assert r.headers["cache-control"] == "no-store"
    text = r.text
    assert 'ezmd_jobs{queue="default",state="done"} 1' in text
    assert 'ezmd_queue_depth{queue="media"} 0' in text
    assert 'ezmd_jobs_finished_total{queue="default",state="done"} 1' in text
    assert "# TYPE ezmd_conversion_duration_seconds histogram" in text
    assert re.search(r'^ezmd_conversion_duration_seconds_bucket\{converter="text\.[a-z_]+",le="\+Inf"\} 1$', text, re.M)
    assert re.search(r'^ezmd_conversion_duration_seconds_count\{converter="text\.[a-z_]+"\} 1$', text, re.M)
    assert 'ezmd_rate_limited_total{reason="create"} 1' in text
    assert 'ezmd_fetch_node_online{node_id="pi-home-1"} 1' in text
    assert "ezmd_fetch_nodes_online 1" in text
    assert "ezmd_build_info{" in text
    for line in text.splitlines():
        assert line.startswith("#") or line.count(" ") >= 1, line


def test_label_values_are_escaped() -> None:
    nasty = 'a"b' + chr(92) + "c" + chr(10) + "d"
    rendered = series("ezmd_x", code=nasty)
    assert chr(10) not in rendered
    assert rendered == 'ezmd_x{code="' + escape_label(nasty) + '"}'
    assert escape_label(nasty) == "a" + chr(92) + '"b' + chr(92) * 2 + "c" + chr(92) + "nd"
