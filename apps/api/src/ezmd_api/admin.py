"""ezmd_api.admin: the host-only `ezmd-admin` CLI (docs/spec/part1.md 7.4, docs/spec/part4.md 4.11.6).

There are no admin HTTP endpoints. Run these on the host (or `docker compose exec api ezmd-admin ...`);
they read the same EZMD_* environment as the API.

- `ezmd-admin keys create|list|revoke`: API keys in the database or in `keys.json` (`--store file`).
  The plaintext key is printed once and never stored.
- `ezmd-admin jobs list|kill`: inspect jobs, stop a runaway job.
- `ezmd-admin reap`: one reaper pass now (residential claims, stale jobs, expired jobs, temp dirs).
"""

from __future__ import annotations

import json
from datetime import timedelta
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any

import typer
from sqlalchemy import select

from ezmd_api.db import ApiKeyRow, JobRow
from ezmd_api.jobs import ACTIVE_STATES, STATES
from ezmd_api.keys import (
    KeyFileEntry,
    KeysFileError,
    create_api_key,
    file_key_id,
    generate_api_key,
    hash_api_key,
    read_keys_file,
    record_from_row,
    revoke_db_key,
    write_keys_file,
)
from ezmd_api.services import Services, build_services
from ezmd_api.settings import Settings
from ezmd_api.util import iso, utcnow

app = typer.Typer(name="ezmd-admin", help="Host-only administration for an ezmd API instance.", no_args_is_help=True)
keys_app = typer.Typer(help="Create, list, and revoke API keys.", no_args_is_help=True)
jobs_app = typer.Typer(help="List jobs and stop runaway ones.", no_args_is_help=True)
app.add_typer(keys_app, name="keys")
app.add_typer(jobs_app, name="jobs")

KILLED_CODE = "conversion_failed"
KILLED_MESSAGE = "An operator stopped this job."
_settings_override: Settings | None = None
"""Tests set this instead of the environment."""


class Store(StrEnum):
    db = "db"
    file = "file"


def _settings() -> Settings:
    return _settings_override or Settings()


def _services() -> Services:
    settings = _settings()
    if settings.keys_file is not None:
        # Admin commands read keys.json themselves, so they still work when it is malformed.
        settings = settings.model_copy(update={"keys_file": None})
    services = build_services(settings)
    services.db.ensure_schema()
    return services


def _fail(message: str, code: int = 1) -> None:
    typer.echo(f"error: {message}", err=True)
    raise typer.Exit(code)


def _print_json(value: Any) -> None:
    typer.echo(json.dumps(value, indent=2, ensure_ascii=False))


# ---------------------------------------------------------------------------
# keys
# ---------------------------------------------------------------------------


def _limits(
    requests_per_window: int,
    window_s: int,
    per_day: int,
    concurrency: int,
    max_upload_mb: int,
    max_duration_s: int,
    max_pages: int,
) -> dict[str, int]:
    return {
        "requests_per_window": requests_per_window,
        "window_s": window_s,
        "requests_per_day": per_day,
        "concurrency": concurrency,
        "max_upload_mb": max_upload_mb,
        "max_duration_s": max_duration_s,
        "max_pages": max_pages,
    }


def _keys_file_path(settings: Settings, explicit: Path | None) -> Path:
    path = explicit or settings.keys_file
    if path is None:
        _fail("no keys file: set EZMD_KEYS_FILE or pass --keys-file")
    assert path is not None
    return path


def _raw_entries(path: Path) -> tuple[list[dict[str, Any]], list[KeyFileEntry]]:
    if not path.exists():
        return [], []
    try:
        parsed = read_keys_file(path)
        raw = json.loads(path.read_text(encoding="utf-8") or "[]")
    except (KeysFileError, json.JSONDecodeError) as e:
        _fail(str(e))
        raise AssertionError from e
    return list(raw), parsed


@keys_app.command("create")
def keys_create(
    name: Annotated[str, typer.Option(help="Who or what the key is for")],
    store: Annotated[Store, typer.Option(help="db (api_keys table) or file (keys.json)")] = Store.db,
    keys_file: Annotated[Path | None, typer.Option(help="keys.json path (default EZMD_KEYS_FILE)")] = None,
    env: Annotated[str, typer.Option(help="Key prefix environment: ak_<env>_...")] = "live",
    requests_per_window: Annotated[int, typer.Option(min=1, help="Requests per window")] = 200,
    window_s: Annotated[int, typer.Option(min=1, max=86400, help="Window length in seconds (file keys)")] = 60,
    per_day: Annotated[int, typer.Option(min=1, help="Job creations per day")] = 10_000,
    concurrency: Annotated[int, typer.Option(min=1, help="Concurrent active jobs")] = 3,
    max_upload_mb: Annotated[int, typer.Option(min=1, help="Upload cap in MB")] = 200,
    max_duration_s: Annotated[int, typer.Option(min=1, help="Audio/video duration cap in seconds")] = 3600,
    max_pages: Annotated[int, typer.Option(min=1, help="Page cap")] = 10_000,
    allow_residential: Annotated[bool, typer.Option(help="May use the residential fetch node")] = False,
    unlimited: Annotated[bool, typer.Option(help="Skip rate and concurrency limits (owner/sponsor)")] = False,
    expires_days: Annotated[int | None, typer.Option(min=1, help="Expire after this many days")] = None,
) -> None:
    """Create a key and print it once."""
    if not env.isalnum() or len(env) > 16:
        _fail("--env must be 1 to 16 letters or digits")
    settings = _settings()
    expires = utcnow() + timedelta(days=expires_days) if expires_days else None
    if store is Store.db:
        services = _services()
        try:
            if window_s != 60:
                _fail("database keys use a 60 s window; use --store file for other windows")
            key, key_id = create_api_key(
                services.db,
                settings,
                name,
                env=env,
                requests_per_minute=requests_per_window,
                requests_per_day=per_day,
                concurrency=concurrency,
                max_upload_bytes=max_upload_mb * 1024 * 1024,
                max_audio_seconds=max_duration_s,
                max_pages=max_pages,
                residential_allowed=allow_residential,
                unlimited=unlimited,
                expires_at=expires,
            )
        finally:
            services.close()
    else:
        path = _keys_file_path(settings, keys_file)
        raw, _ = _raw_entries(path)
        key = generate_api_key(env)
        digest = hash_api_key(settings, key)
        entry: dict[str, Any] = {
            "key_hash": digest,
            "name": name,
            "tier": "owner" if unlimited else "free",
            "unlimited": unlimited,
            "limits": _limits(
                requests_per_window, window_s, per_day, concurrency, max_upload_mb, max_duration_s, max_pages
            ),
            "residential_allowed": allow_residential,
            "notes": f"created {iso(utcnow())} by ezmd-admin",
        }
        if expires is not None:
            entry["expires"] = iso(expires)
        KeyFileEntry.model_validate(entry)
        write_keys_file(path, [*raw, entry])
        key_id = file_key_id(digest)
    typer.echo(f"id:  {key_id}")
    typer.echo(f"key: {key}")
    typer.echo("Store the key now; it is not shown again.", err=True)


def _key_rows(services: Services) -> list[dict[str, Any]]:
    with services.db.session() as s:
        rows = list(s.execute(select(ApiKeyRow).order_by(ApiKeyRow.created_at)).scalars())
    out = []
    for row in rows:
        rec = record_from_row(row)
        out.append(
            {
                "id": rec.id,
                "name": rec.name,
                "store": "db",
                "created_at": iso(row.created_at),
                "revoked": row.revoked_at is not None,
                "expires_at": iso(rec.expires_at),
                "unlimited": rec.unlimited,
                "limits": f"{rec.requests_per_window}/{rec.window_s}s {rec.requests_per_day}/day x{rec.concurrency}",
                "residential": rec.residential_allowed,
            }
        )
    return out


def _file_rows(settings: Settings, keys_file: Path | None) -> list[dict[str, Any]]:
    path = keys_file or settings.keys_file
    if path is None or not path.exists():
        return []
    _, parsed = _raw_entries(path)
    out = []
    for entry in parsed:
        rec = entry.record(settings)
        out.append(
            {
                "id": rec.id,
                "name": rec.name,
                "store": "file",
                "created_at": None,
                "revoked": False,
                "expires_at": iso(rec.expires_at),
                "unlimited": rec.unlimited,
                "limits": f"{rec.requests_per_window}/{rec.window_s}s {rec.requests_per_day}/day x{rec.concurrency}",
                "residential": rec.residential_allowed,
            }
        )
    return out


@keys_app.command("list")
def keys_list(
    as_json: Annotated[bool, typer.Option("--json", help="Print JSON")] = False,
    keys_file: Annotated[Path | None, typer.Option(help="keys.json path (default EZMD_KEYS_FILE)")] = None,
) -> None:
    """List keys from the database and the keys file. Hashes and plaintext are never printed."""
    services = _services()
    try:
        rows = _key_rows(services) + _file_rows(_settings(), keys_file)
    finally:
        services.close()
    if as_json:
        _print_json(rows)
        return
    if not rows:
        typer.echo("no keys")
        return
    for r in rows:
        flags = " ".join(
            f
            for f, on in (("revoked", r["revoked"]), ("unlimited", r["unlimited"]), ("residential", r["residential"]))
            if on
        )
        typer.echo(f"{r['id']:<22} {r['store']:<4} {r['name'][:32]:<32} {r['limits']:<28} {flags}".rstrip())


@keys_app.command("revoke")
def keys_revoke(
    key_id: Annotated[str, typer.Argument(help="Key id from `keys list` (key_... or kf_...)")],
    keys_file: Annotated[Path | None, typer.Option(help="keys.json path (default EZMD_KEYS_FILE)")] = None,
) -> None:
    """Revoke a database key, or remove a file key from keys.json (the API reloads it within seconds)."""
    settings = _settings()
    if key_id.startswith("kf_"):
        path = _keys_file_path(settings, keys_file)
        raw, parsed = _raw_entries(path)
        kept = [r for r, e in zip(raw, parsed, strict=True) if file_key_id(e.digest(settings)) != key_id]
        if len(kept) == len(raw):
            _fail(f"no key {key_id} in {path.name}")
        write_keys_file(path, kept)
        typer.echo(f"removed {key_id} from {path.name}")
        return
    services = _services()
    try:
        if not revoke_db_key(services.db, key_id):
            _fail(f"no active key {key_id}")
    finally:
        services.close()
    typer.echo(f"revoked {key_id}")


# ---------------------------------------------------------------------------
# jobs
# ---------------------------------------------------------------------------


@jobs_app.command("list")
def jobs_list(
    state: Annotated[str | None, typer.Option(help=f"Filter by state ({', '.join(STATES)}, or active)")] = None,
    limit: Annotated[int, typer.Option(min=1, max=10_000)] = 50,
    as_json: Annotated[bool, typer.Option("--json", help="Print JSON")] = False,
) -> None:
    """Most recent jobs first."""
    if state is not None and state != "active" and state not in STATES:
        _fail(f"unknown state {state!r}")
    services = _services()
    try:
        stmt = select(JobRow).order_by(JobRow.created_at.desc()).limit(limit)
        if state == "active":
            stmt = stmt.where(JobRow.state.in_(ACTIVE_STATES))
        elif state is not None:
            stmt = stmt.where(JobRow.state == state)
        with services.db.session() as s:
            rows = list(s.execute(stmt).scalars())
    finally:
        services.close()
    out = [
        {
            "id": r.id,
            "state": r.state,
            "queue": r.queue,
            "created_at": iso(r.created_at),
            "updated_at": iso(r.updated_at),
            "kind": r.input_kind,
            "mime": r.mime,
            "converter_id": r.converter_id,
            "key_id": r.api_key_id,
            "progress": r.progress,
        }
        for r in rows
    ]
    if as_json:
        _print_json(out)
        return
    if not out:
        typer.echo("no jobs")
        return
    for j in out:
        typer.echo(
            f"{j['id']}  {j['state']:<17} {j['queue']:<17} {j['progress']:>3}%  {j['created_at']}  {j['mime'] or '-'}"
        )


@jobs_app.command("kill")
def jobs_kill(job_id: Annotated[str, typer.Argument(help="The job id")]) -> None:
    """Fail an active job now and stop its queue entry or running worker job."""
    services = _services()
    try:
        row = services.jobs.get(job_id)
        if row is None:
            _fail(f"no job {job_id}")
        assert row is not None
        if row.state not in ACTIVE_STATES and row.state != "needs_user_action":
            _fail(f"job {job_id} is {row.state}, not active")
        services.queue.cancel(job_id, row.rq_job_id)
        if services.jobs.fail(job_id, KILLED_CODE, KILLED_MESSAGE) is None:
            _fail(f"job {job_id} changed state; not killed")
    finally:
        services.close()
    typer.echo(f"killed {job_id}")


# ---------------------------------------------------------------------------
# reap
# ---------------------------------------------------------------------------


@app.command("reap")
def reap(
    now: Annotated[bool, typer.Option("--now", help="Fail stale jobs at their wall time, without the grace")] = False,
    temp_age_s: Annotated[int | None, typer.Option(min=60, help="Remove temp dirs older than this")] = None,
) -> None:
    """One reaper pass: residential claims, stale jobs, expired jobs and blobs, orphaned temp dirs."""
    from ezmd_api.purge import clean_temp, purge_expired, reap_residential, reap_stale

    services = _services()
    try:
        claims = reap_residential(services)
        stale = reap_stale(services, now_grace=now)
        purged = purge_expired(services)
        age = temp_age_s if temp_age_s is not None else services.settings.job_timeout_s + 600
        temp = clean_temp(age)
    finally:
        services.close()
    typer.echo(f"claims={claims} stale={stale} purged={purged} temp_dirs={temp}")


def main() -> None:  # pragma: no cover - console entry
    app(prog_name="ezmd-admin")


if __name__ == "__main__":  # pragma: no cover
    main()
