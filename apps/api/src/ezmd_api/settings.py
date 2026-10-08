"""ezmd_api.settings: every EZMD_* variable the API and its workers read.

Implemented from docs/spec/part1.md sections 7 and 8 and docs/spec/part4.md 4.9.6 / 4.11.1.
`deploy/env.example` documents exactly these fields; `tests/test_env_example.py` fails on drift.
"""

from __future__ import annotations

import ipaddress
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

MIB = 1024 * 1024
MIN_SECRET_BYTES = 32

# Per-queue RQ worker timeouts (docs/spec/part1.md section 7.2). EZMD_JOB_TIMEOUT_S caps all of them.
QUEUE_TIMEOUTS: dict[str, int] = {"default": 600, "media": 3600, "fetch": 120, "fetch_residential": 3600}

CommaList = Annotated[list[str], NoDecode]


def _split_csv(value: object) -> object:
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    return value


class Settings(BaseSettings):
    """API and worker configuration. Field `foo_bar` is read from `EZMD_FOO_BAR`."""

    model_config = SettingsConfigDict(env_prefix="EZMD_", extra="ignore", frozen=True, env_ignore_empty=True)

    # ---- Instance ----
    public_mode: bool = False
    public_url: str = "http://localhost:8000"
    data_dir: Path = Field(default_factory=lambda: Path.home() / ".ezmd")
    web_dist: Path | None = None
    scheduler_enabled: bool = True

    # ---- Storage ----
    database_url: str | None = None
    blob_backend: Literal["fs", "s3"] = "fs"
    blob_fs_root: Path | None = None
    s3_endpoint: str | None = None
    s3_bucket: str = "ezmd"
    s3_access_key: SecretStr | None = None
    s3_secret_key: SecretStr | None = None
    s3_region: str = "us-east-1"
    retention_hours: int = Field(default=24, ge=0)
    purge_interval_s: int = Field(default=600, ge=5)

    # ---- Queue ----
    redis_url: str = "redis://localhost:6379/0"
    queue: Literal["rq", "inline"] = "rq"
    job_timeout_s: int = Field(default=1800, ge=10)
    job_mem_mb: int = Field(default=4096, ge=256)
    media_job_mem_mb: int = Field(default=8192, ge=256)
    worker_default_concurrency: int = Field(default=2, ge=1)
    worker_media_concurrency: int = Field(default=1, ge=1)
    max_active_jobs: int | None = None
    residential_wait_seconds: int = Field(default=180, ge=0)
    max_result_bytes: int = Field(default=256 * MIB, ge=1024)
    """Cap on the IR JSON a conversion child may hand back (D-0017 item 6)."""

    # ---- Limits (anonymous callers; API keys carry their own) ----
    anon_max_upload_mb: int = Field(default=200, ge=1)
    anon_max_html_mb: int = Field(default=10, ge=1)
    anon_max_duration_s: int = Field(default=10800, ge=1)
    anon_max_pages: int = Field(default=2000, ge=1)
    anon_ratelimit_max: int = Field(default=20, ge=1)
    anon_ratelimit_window_s: int = Field(default=60, ge=1)
    anon_daily_max: int = Field(default=200, ge=1)
    anon_concurrency: int = Field(default=1, ge=1)
    anon_result_ratelimit_max: int = Field(default=40, ge=1)
    anon_sse_max: int = Field(default=10, ge=1)
    fetch_node_claims_per_minute: int = Field(default=60, ge=1)

    # ---- Auth ----
    require_api_key: bool = False
    key_pepper: SecretStr = SecretStr("")
    jwt_secret: SecretStr = SecretStr("")
    ip_hash_salt: SecretStr = SecretStr("")
    keys_file: Path | None = Field(
        default=None,
        description="keys.json of API keys with per-key limits (hashed; docs/api.md). Unset: database keys only.",
    )

    # ---- Challenge ----
    turnstile_sitekey: str = ""
    turnstile_secret: SecretStr = SecretStr("")
    turnstile_required_for_fetch: bool = False
    turnstile_jwt_ttl_s: int = Field(default=120, ge=10)

    # ---- Fetch ----
    allow_private_networks: bool = False
    platforms_file: Path | None = None
    fetch_node_secret: SecretStr | None = None
    fetch_node_cidr: CommaList = Field(default_factory=lambda: ["100.64.0.0/10"])

    # ---- HTTP ----
    cors_origins: CommaList = Field(default_factory=list)
    trust_proxy_header: str = ""
    trusted_proxies: CommaList = Field(default_factory=list)

    # ---- Observability ----
    log_level: Literal["debug", "info", "warning", "error"] = "info"
    log_format: Literal["json", "text"] = "json"
    metrics_token: SecretStr | None = Field(
        default=None,
        description="Bearer token (16+ chars, secret) for GET /metrics. Unset: /metrics is not mounted.",
    )

    @field_validator("fetch_node_cidr", "cors_origins", "trusted_proxies", mode="before")
    @classmethod
    def _csv(cls, value: object) -> object:
        return _split_csv(value)

    @field_validator("fetch_node_cidr", "trusted_proxies")
    @classmethod
    def _cidrs(cls, value: list[str]) -> list[str]:
        for cidr in value:
            ipaddress.ip_network(cidr, strict=False)
        return value

    @field_validator("fetch_node_secret", "metrics_token", mode="before")
    @classmethod
    def _empty_secret_is_none(cls, value: object) -> object:
        return None if value in ("", None) else value

    @field_validator("log_level", mode="before")
    @classmethod
    def _lower(cls, value: object) -> object:
        return value.lower() if isinstance(value, str) else value

    @model_validator(mode="after")
    def _public_mode_secrets(self) -> Settings:
        if self.public_mode:
            for name in ("jwt_secret", "key_pepper"):
                secret: SecretStr = getattr(self, name)
                if len(secret.get_secret_value().encode()) < MIN_SECRET_BYTES:
                    raise ValueError(
                        f"EZMD_{name.upper()} must be at least {MIN_SECRET_BYTES} bytes when EZMD_PUBLIC_MODE=true"
                    )
        if self.fetch_node_secret is not None and len(self.fetch_node_secret.get_secret_value()) < 16:
            raise ValueError("EZMD_FETCH_NODE_SECRET must be at least 16 characters")
        if self.metrics_token is not None and len(self.metrics_token.get_secret_value()) < 16:
            raise ValueError("EZMD_METRICS_TOKEN must be at least 16 characters")
        return self

    # ---- Derived values ----

    @property
    def resolved_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        return f"sqlite:///{(self.data_dir / 'ezmd.db').as_posix()}"

    @property
    def resolved_blob_root(self) -> Path:
        return self.blob_fs_root or (self.data_dir / "blobs")

    @property
    def max_upload_bytes(self) -> int:
        return self.anon_max_upload_mb * MIB

    @property
    def max_url_bytes(self) -> int:
        return self.anon_max_html_mb * MIB

    @property
    def active_job_cap(self) -> int:
        if self.max_active_jobs is not None:
            return self.max_active_jobs
        return 2 * (self.worker_default_concurrency + self.worker_media_concurrency)

    @property
    def retention_seconds(self) -> int:
        # 0 means "delete on first download"; keep the job for one hour so the download can happen.
        return self.retention_hours * 3600 if self.retention_hours > 0 else 3600

    @property
    def ip_salt(self) -> bytes:
        salt = self.ip_hash_salt.get_secret_value() or self.key_pepper.get_secret_value() or "ezmd-local-ip-salt"
        return salt.encode()

    @property
    def turnstile_enabled(self) -> bool:
        return bool(self.turnstile_secret.get_secret_value())

    @property
    def turnstile_required(self) -> bool:
        return self.public_mode or self.turnstile_required_for_fetch or self.turnstile_enabled

    def queue_timeout(self, queue: str) -> int:
        return min(QUEUE_TIMEOUTS.get(queue, 600), self.job_timeout_s)


ENV_PREFIX = "EZMD_"


def env_names() -> list[str]:
    """Every environment variable name Settings reads, for the drift test and docs."""
    return sorted(ENV_PREFIX + name.upper() for name in Settings.model_fields)
