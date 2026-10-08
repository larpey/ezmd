"""intomd_api.migrate: programmatic Alembic upgrade (`python -m intomd_api.migrate`)."""

from __future__ import annotations

from alembic import command
from alembic.config import Config


def alembic_config(url: str) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", "intomd_api:migrations")
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def upgrade(url: str, revision: str = "head") -> None:
    command.upgrade(alembic_config(url), revision)


def main() -> None:
    from intomd_api.settings import Settings

    upgrade(Settings().resolved_database_url)


if __name__ == "__main__":
    main()
