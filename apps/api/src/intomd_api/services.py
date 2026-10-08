"""intomd_api.services: the per-process service container shared by the API and the workers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from intomd_api.blobs import BlobStore, build_blob_store
from intomd_api.db import Database
from intomd_api.jobs import JobStore
from intomd_api.keys import KeyStore
from intomd_api.queue import InlineQueue, JobQueue, RQQueue
from intomd_api.settings import Settings
from intomd_api.state import MemoryState, RedisState, StateBackend


@dataclass
class Services:
    settings: Settings
    db: Database
    blobs: BlobStore
    state: StateBackend
    jobs: JobStore
    queue: JobQueue
    redis: Any = None
    keys: KeyStore | None = None
    """Keys from INTOMD_KEYS_FILE (None when unset)."""

    def close(self) -> None:
        self.queue.shutdown()
        self.db.dispose()


def connect_redis(settings: Settings) -> Any:
    import redis

    return redis.Redis.from_url(settings.redis_url, socket_timeout=10, socket_connect_timeout=5)


def build_services(settings: Settings, *, redis_client: Any = None) -> Services:
    """Wire storage, state, and the queue. In inline mode Redis is optional: when a client is
    passed (tests with fakeredis) it backs the state, otherwise state lives in memory."""
    db = Database(settings.resolved_database_url)
    blobs = build_blob_store(settings)
    redis = redis_client
    if redis is None and settings.queue == "rq":
        redis = connect_redis(settings)
    state: StateBackend = RedisState(redis) if redis is not None else MemoryState()
    jobs = JobStore(db, state)
    queue: JobQueue
    holder: dict[str, Services] = {}
    if settings.queue == "inline":
        from intomd_api.worker import process_job

        def runner(job_id: str) -> None:
            process_job(holder["services"], job_id)

        queue = InlineQueue(runner, max_workers=settings.worker_default_concurrency)
    else:
        queue = RQQueue(redis)
    keys = None
    if settings.keys_file is not None:
        keys = KeyStore(settings)
        keys.load()  # a malformed keys file stops startup (KeysFileError)
    services = Services(
        settings=settings, db=db, blobs=blobs, state=state, jobs=jobs, queue=queue, redis=redis, keys=keys
    )
    holder["services"] = services
    return services
