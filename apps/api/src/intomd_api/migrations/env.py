"""Alembic environment. The database URL comes from INTOMD_DATABASE_URL (via Settings) unless the
Alembic config already sets `sqlalchemy.url`."""

from __future__ import annotations

from alembic import context
from sqlalchemy import engine_from_config, pool

from intomd_api.db import Base

config = context.config
target_metadata = Base.metadata

if not config.get_main_option("sqlalchemy.url"):
    from intomd_api.settings import Settings

    config.set_main_option("sqlalchemy.url", Settings().resolved_database_url)


def run_offline() -> None:
    context.configure(url=config.get_main_option("sqlalchemy.url"), target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_online() -> None:
    section = config.get_section(config.config_ini_section, {})
    connectable = engine_from_config(section, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_offline()
else:
    run_online()
