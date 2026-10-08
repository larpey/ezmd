"""intomd_api.migrate: programmatic Alembic upgrade (`python -m intomd_api.migrate`).

`ensure_schema` is what every process calls at startup. Alembic owns the schema:

- empty database: upgrade to head;
- Alembic-managed database: upgrade to head (a no-op when current);
- database made by an older release's `create_all` start (tables, no `alembic_version`): stamped at head when its
  schema matches the current models exactly, refused with `SchemaDrift` otherwise, so a stale schema is never
  silently marked current;
- in-memory SQLite (tests, single-process dev): `create_all` is enough and Alembic is skipped.

Concurrent starts (api, worker, purge) are serialized by an exclusive SQLite transaction on a sidecar lock file.
The operating system drops that lock when a process dies, so a crash never leaves a stale lock.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Literal

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect

LOCK_TIMEOUT_SECONDS = 120.0

SchemaAction = Literal["migrated", "current", "stamped", "skipped"]


class SchemaDrift(RuntimeError):
    """An unmanaged database whose tables do not match the current models."""


def alembic_config(url: str) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", "intomd_api:migrations")
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def head_revision() -> str:
    head = ScriptDirectory.from_config(alembic_config("sqlite://")).get_current_head()
    if head is None:
        raise RuntimeError("no Alembic revisions found")
    return head


def upgrade(url: str, revision: str = "head") -> None:
    command.upgrade(alembic_config(url), revision)


def _is_memory(url: str) -> bool:
    return url in ("sqlite://", "sqlite:///:memory:") or "mode=memory" in url


def _sqlite_path(url: str) -> Path | None:
    if url.startswith("sqlite:///") and not _is_memory(url):
        return Path(url.removeprefix("sqlite:///").split("?", 1)[0])
    return None


@contextmanager
def _startup_lock(url: str) -> Iterator[None]:
    path = _sqlite_path(url)
    if path is None:
        yield
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(path) + ".migrate-lock", timeout=LOCK_TIMEOUT_SECONDS, isolation_level=None)
    try:
        con.execute("BEGIN EXCLUSIVE")
        try:
            yield
        finally:
            con.execute("ROLLBACK")
    finally:
        con.close()


def _drift(url: str) -> list[str]:
    from intomd_api.db import Base

    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            diffs = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    finally:
        engine.dispose()
    return [repr(d) for d in diffs]


def _tables(url: str) -> set[str]:
    engine = create_engine(url)
    try:
        return set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def ensure_schema(url: str) -> SchemaAction:
    """Bring the database at `url` to the Alembic head. Returns what was done."""
    if _is_memory(url):
        return "skipped"
    with _startup_lock(url):
        tables = _tables(url)
        if tables and "alembic_version" not in tables:
            drift = _drift(url)
            if drift:
                raise SchemaDrift(
                    "the database was created without Alembic and does not match this release's schema; "
                    "restore a backup made by deploy/backup.sh or recreate the database. Differences: "
                    + "; ".join(drift)
                )
            command.stamp(alembic_config(url), "head")
            return "stamped"
        before = _revision(url) if tables else None
        upgrade(url)
        return "current" if before == head_revision() else "migrated"


def _revision(url: str) -> str | None:
    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            return MigrationContext.configure(conn).get_current_revision()
    finally:
        engine.dispose()


def main() -> None:
    from intomd_api.settings import Settings

    print(ensure_schema(Settings().resolved_database_url))


if __name__ == "__main__":
    main()
