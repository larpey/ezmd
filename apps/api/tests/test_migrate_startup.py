"""Schema bootstrap at startup: Alembic owns the schema, including databases made by older `create_all` starts."""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Callable
from pathlib import Path

import pytest

from intomd_api.db import Base, Database
from intomd_api.migrate import SchemaDrift, ensure_schema, head_revision
from intomd_api.settings import Settings
from intomd_api.testing import api_client


def _url(tmp_path: Path) -> str:
    return f"sqlite:///{(tmp_path / 'state' / 'intomd.sqlite').as_posix()}"


def _revision(url: str) -> str | None:
    con = sqlite3.connect(url.removeprefix("sqlite:///"))
    try:
        row = con.execute("SELECT version_num FROM alembic_version").fetchone()
    finally:
        con.close()
    return row[0] if row else None


def test_fresh_database_is_migrated_to_head(tmp_path: Path) -> None:
    url = _url(tmp_path)
    assert ensure_schema(url) == "migrated"
    assert _revision(url) == head_revision()


def test_second_call_is_a_no_op(tmp_path: Path) -> None:
    url = _url(tmp_path)
    ensure_schema(url)
    assert ensure_schema(url) == "current"
    assert _revision(url) == head_revision()


def test_legacy_create_all_database_is_stamped(tmp_path: Path) -> None:
    url = _url(tmp_path)
    db = Database(url)
    db.create_all()
    db.engine.dispose()
    assert ensure_schema(url) == "stamped"
    assert _revision(url) == head_revision()


def test_legacy_database_with_drift_is_refused(tmp_path: Path) -> None:
    url = _url(tmp_path)
    db = Database(url)
    db.create_all()
    table = sorted(Base.metadata.tables)[0]
    with db.engine.begin() as con:
        con.exec_driver_sql(f'DROP TABLE "{table}"')
    db.engine.dispose()
    with pytest.raises(SchemaDrift, match=table):
        ensure_schema(url)
    assert not _has_alembic_version(url)


def _has_alembic_version(url: str) -> bool:
    con = sqlite3.connect(url.removeprefix("sqlite:///"))
    try:
        names = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        con.close()
    return "alembic_version" in names


def test_concurrent_starts_both_succeed(tmp_path: Path) -> None:
    url = _url(tmp_path)
    errors: list[BaseException] = []

    def run() -> None:
        try:
            ensure_schema(url)
        except BaseException as exc:
            errors.append(exc)

    threads = [threading.Thread(target=run) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    assert _revision(url) == head_revision()


def test_in_memory_database_skips_alembic() -> None:
    assert ensure_schema("sqlite://") == "skipped"


async def test_api_startup_puts_file_database_under_alembic(
    settings_factory: Callable[..., Settings], tmp_path: Path
) -> None:
    url = _url(tmp_path)
    async with api_client(settings_factory(database_url=url)) as (client, _app):
        assert (await client.get("/healthz")).status_code == 200
    assert _revision(url) == head_revision()
