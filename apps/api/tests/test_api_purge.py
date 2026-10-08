"""Retention purge and DELETE (docs/spec/part1.md section 8.4)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta

from ezmd_api.purge import purge_expired
from ezmd_api.settings import Settings
from ezmd_api.testing import api_client, upload, wait_for_state
from ezmd_api.util import utcnow


async def test_purge_deletes_rows_and_blobs(settings_factory: Callable[..., Settings]) -> None:
    async with api_client(settings_factory()) as (client, app):
        services = app.state.services
        keep = (await upload(client, b"keep me", "k.txt")).json()["job"]["id"]
        gone = (await upload(client, b"purge me", "p.txt")).json()["job"]["id"]
        await wait_for_state(client, keep)
        await wait_for_state(client, gone)
        await client.get(f"/v1/jobs/{gone}/result", params={"profile": "compact"})
        assert services.blobs.list_prefix(f"jobs/{gone}/")
        services.jobs.update(gone, expires_at=utcnow() - timedelta(seconds=1))
        assert purge_expired(services) == 1
        assert services.blobs.list_prefix(f"jobs/{gone}/") == []
        assert services.jobs.get(gone) is None
        assert services.state.events_since(gone, 0) == []
        assert (await client.get(f"/v1/jobs/{gone}")).status_code == 404
        assert services.blobs.list_prefix(f"jobs/{keep}/")
        assert (await client.get(f"/v1/jobs/{keep}")).status_code == 200


async def test_delete_removes_blobs(settings_factory: Callable[..., Settings]) -> None:
    async with api_client(settings_factory()) as (client, app):
        job_id = (await upload(client, b"bye", "b.txt")).json()["job"]["id"]
        await wait_for_state(client, job_id)
        assert app.state.services.blobs.list_prefix(f"jobs/{job_id}/")
        assert (await client.delete(f"/v1/jobs/{job_id}")).status_code == 204
        assert app.state.services.blobs.list_prefix(f"jobs/{job_id}/") == []
        assert (await client.delete(f"/v1/jobs/{job_id}")).status_code == 404


async def test_retention_zero_deletes_on_first_download(settings_factory: Callable[..., Settings]) -> None:
    async with api_client(settings_factory(retention_hours=0)) as (client, _):
        job_id = (await upload(client, b"once", "o.txt")).json()["job"]["id"]
        await wait_for_state(client, job_id)
        assert (await client.get(f"/v1/jobs/{job_id}/result")).status_code == 200
        assert (await client.get(f"/v1/jobs/{job_id}")).status_code == 404
