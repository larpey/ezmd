"""The host-only `ezmd-admin` CLI (P1-T10): keys create|list|revoke, jobs list|kill, reap."""

from __future__ import annotations

import json
import os
import time
from datetime import timedelta
from pathlib import Path

import pytest
from typer.testing import CliRunner

from ezmd_api import admin
from ezmd_api.db import JobRow
from ezmd_api.keys import hash_api_key, lookup_api_key
from ezmd_api.services import build_services
from ezmd_api.settings import Settings
from ezmd_api.testing import make_settings
from ezmd_api.util import new_job_id, utcnow

runner = CliRunner()


@pytest.fixture
def settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Settings:
    s = make_settings(tmp_path / "data", key_pepper="q" * 40, keys_file=tmp_path / "keys.json")
    monkeypatch.setattr(admin, "_settings_override", s)
    return s


def _key_from(output: str) -> str:
    return next(line.split(" ", 1)[1].strip() for line in output.splitlines() if line.startswith("key:"))


def _id_from(output: str) -> str:
    return next(line.split(" ", 1)[1].strip() for line in output.splitlines() if line.startswith("id:"))


def test_db_key_create_list_revoke(settings: Settings) -> None:
    created = runner.invoke(admin.app, ["keys", "create", "--name", "ci", "--env", "test", "--concurrency", "5"])
    assert created.exit_code == 0, created.output
    key, key_id = _key_from(created.output), _id_from(created.output)
    assert key.startswith("ak_test_")
    services = build_services(settings.model_copy(update={"keys_file": None}))
    try:
        record = lookup_api_key(services.db, settings, key)
        assert record is not None and record.concurrency == 5
        listed = runner.invoke(admin.app, ["keys", "list", "--json"])
        assert listed.exit_code == 0
        assert key not in listed.output and hash_api_key(settings, key) not in listed.output
        assert any(r["id"] == key_id for r in json.loads(listed.output))
        revoked = runner.invoke(admin.app, ["keys", "revoke", key_id])
        assert revoked.exit_code == 0, revoked.output
        assert lookup_api_key(services.db, settings, key) is None
        again = runner.invoke(admin.app, ["keys", "revoke", key_id])
        assert again.exit_code == 1
    finally:
        services.close()


def test_file_key_create_stores_only_the_hash(settings: Settings) -> None:
    assert settings.keys_file is not None
    created = runner.invoke(
        admin.app,
        ["keys", "create", "--name", "plugin", "--store", "file", "--window-s", "10", "--requests-per-window", "3"],
    )
    assert created.exit_code == 0, created.output
    key, key_id = _key_from(created.output), _id_from(created.output)
    text = settings.keys_file.read_text(encoding="utf-8")
    assert key not in text
    entries = json.loads(text)
    assert entries[0]["key_hash"] == hash_api_key(settings, key)
    assert entries[0]["limits"]["window_s"] == 10
    if os.name == "posix":
        assert settings.keys_file.stat().st_mode & 0o077 == 0
    listed = runner.invoke(admin.app, ["keys", "list"])
    assert key_id in listed.output and "file" in listed.output
    removed = runner.invoke(admin.app, ["keys", "revoke", key_id])
    assert removed.exit_code == 0, removed.output
    assert json.loads(settings.keys_file.read_text(encoding="utf-8")) == []


def test_db_key_rejects_custom_window(settings: Settings) -> None:
    r = runner.invoke(admin.app, ["keys", "create", "--name", "x", "--window-s", "10"])
    assert r.exit_code == 1
    assert "60 s window" in r.output


def _job(settings: Settings, state: str, *, updated_ago: float = 0.0, queue: str = "default") -> str:
    services = build_services(settings.model_copy(update={"keys_file": None}))
    services.db.create_all()
    now = utcnow()
    job_id = new_job_id()
    try:
        services.jobs.create(
            JobRow(
                id=job_id,
                state=state,
                created_at=now,
                updated_at=now - timedelta(seconds=updated_ago),
                expires_at=now + timedelta(hours=1),
                input_kind="bytes",
                input_display="a.txt",
                profile="full",
                queue=queue,
                client_ip_hash="h",
            )
        )
        if updated_ago:
            with services.db.session() as s:
                row = s.get(JobRow, job_id)
                assert row is not None
                row.updated_at = now - timedelta(seconds=updated_ago)
    finally:
        services.close()
    return job_id


def _state(settings: Settings, job_id: str) -> tuple[str, str | None]:
    services = build_services(settings.model_copy(update={"keys_file": None}))
    try:
        row = services.jobs.require(job_id)
        return row.state, row.error_code
    finally:
        services.close()


def test_jobs_list_and_kill(settings: Settings) -> None:
    running = _job(settings, "converting")
    done = _job(settings, "done")
    listed = runner.invoke(admin.app, ["jobs", "list", "--state", "active", "--json"])
    assert listed.exit_code == 0, listed.output
    assert [j["id"] for j in json.loads(listed.output)] == [running]
    assert runner.invoke(admin.app, ["jobs", "list", "--state", "nope"]).exit_code == 1
    killed = runner.invoke(admin.app, ["jobs", "kill", running])
    assert killed.exit_code == 0, killed.output
    assert _state(settings, running) == ("failed", "conversion_failed")
    assert runner.invoke(admin.app, ["jobs", "kill", done]).exit_code == 1
    assert runner.invoke(admin.app, ["jobs", "kill", "job_doesnotexist0000000000"]).exit_code == 1


def test_reap_fails_stale_jobs_and_cleans_temp(
    settings: Settings, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import tempfile

    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path / "tmp"))
    (tmp_path / "tmp").mkdir()
    old = tmp_path / "tmp" / "ezmd-job-orphan"
    old.mkdir()
    past = time.time() - 10 * 3600
    os.utime(old, (past, past))
    fresh = tmp_path / "tmp" / "ezmd-upload-live"
    fresh.mkdir()
    timeout = settings.queue_timeout("default")
    stale = _job(settings, "converting", updated_ago=timeout + 1000)
    recent = _job(settings, "converting", updated_ago=10)
    r = runner.invoke(admin.app, ["reap"])
    assert r.exit_code == 0, r.output
    assert "stale=1" in r.output and "temp_dirs=1" in r.output
    assert _state(settings, stale) == ("failed", "timeout")
    assert _state(settings, recent)[0] == "converting"
    assert not old.exists() and fresh.exists()
