"""intomd_api.db: SQLAlchemy 2 models for `jobs` and `api_keys` (docs/spec/part1.md section 7.1).

SQLite by default (`INTOMD_DATABASE_URL` unset), Postgres via `postgresql+psycopg://...`. Tables are
created on startup; `migrations/` holds the Alembic history for deployments that manage schema
explicitly.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Engine, Integer, String, Text, create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker
from sqlalchemy.pool import StaticPool

from intomd_api.util import utcnow

KEY_DEFAULT_MAX_PAGES = 10_000
"""Page cap for API keys created without an explicit `max_pages`."""


class Base(DeclarativeBase):
    pass


class JobRow(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    state: Mapped[str] = mapped_column(String(32), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    input_kind: Mapped[str] = mapped_column(String(32))
    input_display: Mapped[str] = mapped_column(Text)
    input_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    input_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    input_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    content_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    mime: Mapped[str | None] = mapped_column(String(255), nullable=True)
    declared_mime: Mapped[str | None] = mapped_column(String(255), nullable=True)
    converter_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    profile: Mapped[str] = mapped_column(String(32))
    options_json: Mapped[str] = mapped_column(Text, default="{}")
    queue: Mapped[str] = mapped_column(String(32))
    rq_job_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    stage_message: Mapped[str] = mapped_column(Text, default="")
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    needs_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    blob_input: Mapped[str | None] = mapped_column(Text, nullable=True)
    blob_ir: Mapped[str | None] = mapped_column(Text, nullable=True)
    blob_result_prefix: Mapped[str | None] = mapped_column(Text, nullable=True)
    api_key_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    client_ip_hash: Mapped[str] = mapped_column(String(64), index=True)
    metrics_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    warnings_count: Mapped[int] = mapped_column(Integer, default=0)
    truncated: Mapped[bool] = mapped_column(Boolean, default=False)
    claim_token_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    claim_node_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    claim_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    claim_attempts: Mapped[int] = mapped_column(Integer, default=0)
    fetch_depth: Mapped[int] = mapped_column(Integer, default=0)
    """How many converter-requested fetches (FetchRequired) this job has followed (D-0017 item 4)."""
    ir_cache_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    """Fingerprint of the IR schema, converter, and engine versions that produced `blob_ir`."""


class ApiKeyRow(Base):
    __tablename__ = "api_keys"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    key_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    unlimited: Mapped[bool] = mapped_column(Boolean, default=False)
    requests_per_minute: Mapped[int] = mapped_column(Integer, default=200)
    requests_per_day: Mapped[int] = mapped_column(Integer, default=10000)
    concurrency: Mapped[int] = mapped_column(Integer, default=3)
    max_upload_bytes: Mapped[int] = mapped_column(Integer, default=200 * 1024 * 1024)
    max_audio_seconds: Mapped[int] = mapped_column(Integer, default=3600)
    max_pages: Mapped[int] = mapped_column(Integer, default=KEY_DEFAULT_MAX_PAGES)
    allowed_families: Mapped[str] = mapped_column(Text, default='["*"]')
    residential_allowed: Mapped[bool] = mapped_column(Boolean, default=False)


class Database:
    """Engine plus session factory. One per process."""

    def __init__(self, url: str) -> None:
        self.url = url
        kwargs: dict[str, object] = {"future": True}
        if url.startswith("sqlite"):
            kwargs["connect_args"] = {"check_same_thread": False, "timeout": 30}
            if url in ("sqlite://", "sqlite:///:memory:"):
                kwargs["poolclass"] = StaticPool
        else:
            kwargs["pool_pre_ping"] = True
        self.engine: Engine = create_engine(url, **kwargs)
        if url.startswith("sqlite"):
            event.listen(self.engine, "connect", _sqlite_pragmas)
        self._sessions = sessionmaker(self.engine, expire_on_commit=False)

    def create_all(self) -> None:
        if self.url.startswith("sqlite:///") and self.url not in ("sqlite:///:memory:",):
            from pathlib import Path

            Path(self.url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
        Base.metadata.create_all(self.engine)

    @contextmanager
    def session(self) -> Iterator[Session]:
        with self._sessions() as s, s.begin():
            yield s

    def ping(self) -> bool:
        try:
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return True
        except Exception:
            return False

    def dispose(self) -> None:
        self.engine.dispose()


def _sqlite_pragmas(dbapi_conn: object, _record: object) -> None:
    cur = dbapi_conn.cursor()  # type: ignore[attr-defined]
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA busy_timeout=30000")
    cur.close()
