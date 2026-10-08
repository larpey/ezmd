"""intomd_api.keys: API keys from the `api_keys` table and from the `keys.json` bootstrap file
(docs/spec/part1.md section 7.4, docs/spec/part4.md section 4.11.1).

Both sources store only HMAC-SHA256(INTOMD_KEY_PEPPER, key) and yield the same `KeyRecord`, so the
rest of the API never cares where a key came from.

`keys.json` (path `INTOMD_KEYS_FILE`) is a JSON list in cobalt's shape. Each entry carries either
`key_hash` (preferred; what `intomd-admin keys create --file` writes) or a plaintext `key`, which is
hashed at load time and never kept. The file is read at startup (a malformed file stops the API) and
re-read when its modification time changes (checked at most every `RELOAD_CHECK_SECONDS`); a file
that turns malformed later keeps the previous keys and logs an error.
"""

from __future__ import annotations

import fnmatch
import ipaddress
import json
import logging
import os
import stat
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError, field_validator, model_validator
from sqlalchemy import select

from intomd_api.db import KEY_DEFAULT_MAX_PAGES, ApiKeyRow, Database
from intomd_api.settings import MIB, Settings
from intomd_api.util import as_utc, keyed_hash, random_base62, utcnow

log = logging.getLogger("intomd.api.keys")

MAX_KEY_LENGTH = 256
MAX_KEYS_FILE_BYTES = 5 * MIB
MAX_KEYS_FILE_ENTRIES = 10_000
RELOAD_CHECK_SECONDS = 2.0
FILE_KEY_PREFIX = "kf_"
LOCAL_PEPPER = "intomd-local-pepper"


@dataclass(frozen=True, slots=True)
class KeyRecord:
    """One API key and its limits, wherever it is stored."""

    id: str
    name: str
    source: Literal["db", "file"]
    unlimited: bool = False
    requests_per_window: int = 200
    window_s: int = 60
    requests_per_day: int = 10_000
    concurrency: int = 3
    max_upload_bytes: int = 200 * MIB
    max_audio_seconds: int = 3600
    max_pages: int = KEY_DEFAULT_MAX_PAGES
    residential_allowed: bool = False
    allowed_families: tuple[str, ...] = ("*",)
    ips: tuple[str, ...] = ()
    """CIDR allowlist; empty allows any address."""
    user_agents: tuple[str, ...] = ()
    """Glob allowlist (`intomd-obsidian/*`); empty allows any user agent."""
    allowed_sources: tuple[str, ...] = ("*",)
    """Host globs URL inputs must match (`*.example.com`); `*` allows any host."""
    disabled_sources: tuple[str, ...] = ()
    """Host globs URL inputs must not match; checked before `allowed_sources`."""
    expires_at: datetime | None = None
    tier: str = "free"

    def expired(self, now: datetime | None = None) -> bool:
        return self.expires_at is not None and as_utc(self.expires_at) <= (now or utcnow())

    def allows_ip(self, ip: str) -> bool:
        if not self.ips:
            return True
        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            return False
        return any(addr in ipaddress.ip_network(c, strict=False) for c in self.ips)

    def allows_source(self, host: str) -> bool:
        host = host.lower().rstrip(".")
        if any(fnmatch.fnmatchcase(host, p.lower()) for p in self.disabled_sources):
            return False
        return any(fnmatch.fnmatchcase(host, p.lower()) for p in self.allowed_sources)

    def allows_user_agent(self, user_agent: str) -> bool:
        if not self.user_agents:
            return True
        return any(fnmatch.fnmatchcase(user_agent, pattern) for pattern in self.user_agents)


# ---------------------------------------------------------------------------
# Hashing
# ---------------------------------------------------------------------------


def pepper(settings: Settings) -> bytes:
    return (settings.key_pepper.get_secret_value() or LOCAL_PEPPER).encode()


def hash_api_key(settings: Settings, key: str) -> str:
    return keyed_hash(pepper(settings), key)


def generate_api_key(env: str = "live") -> str:
    return f"ak_{env}_{random_base62(16, 22)}"


def file_key_id(key_hash: str) -> str:
    return FILE_KEY_PREFIX + key_hash[:16]


# ---------------------------------------------------------------------------
# keys.json schema
# ---------------------------------------------------------------------------


class KeyLimitsIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requests_per_window: int = Field(default=200, ge=1)
    window_s: int = Field(default=60, ge=1, le=86_400)
    requests_per_day: int = Field(default=10_000, ge=1)
    concurrency: int = Field(default=3, ge=1, le=1000)
    max_upload_mb: int = Field(default=200, ge=1, le=100_000)
    max_duration_s: int = Field(default=3600, ge=1)
    max_pages: int = Field(default=KEY_DEFAULT_MAX_PAGES, ge=1)


class KeyFileEntry(BaseModel):
    """One `keys.json` entry (cobalt shape plus `key_hash`, `unlimited`, `residential_allowed`)."""

    model_config = ConfigDict(extra="forbid")

    key: SecretStr | None = Field(default=None, description="Plaintext key; hashed at load. Prefer key_hash.")
    key_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    name: str = Field(min_length=1, max_length=128)
    tier: Literal["free", "sponsor", "owner"] = "free"
    unlimited: bool = False
    limits: KeyLimitsIn = Field(default_factory=KeyLimitsIn)
    ips: list[str] = Field(default_factory=list, max_length=256)
    user_agents: list[str] = Field(default_factory=list, max_length=64)
    allowed_sources: list[str] = Field(default_factory=lambda: ["*"], max_length=256)
    disabled_sources: list[str] = Field(default_factory=list, max_length=256)
    allowed_families: list[str] = Field(default_factory=lambda: ["*"], max_length=64)
    residential_allowed: bool = False
    expires: datetime | None = None
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator("ips")
    @classmethod
    def _cidrs(cls, value: list[str]) -> list[str]:
        for cidr in value:
            ipaddress.ip_network(cidr, strict=False)
        return value

    @model_validator(mode="after")
    def _one_key(self) -> KeyFileEntry:
        if (self.key is None) == (self.key_hash is None):
            raise ValueError("each entry needs exactly one of `key_hash` or `key`")
        if self.key is not None and not 8 <= len(self.key.get_secret_value()) <= MAX_KEY_LENGTH:
            raise ValueError(f"`key` must be 8 to {MAX_KEY_LENGTH} characters")
        return self

    def digest(self, settings: Settings) -> str:
        if self.key_hash is not None:
            return self.key_hash
        assert self.key is not None
        return hash_api_key(settings, self.key.get_secret_value())

    def record(self, settings: Settings) -> KeyRecord:
        digest = self.digest(settings)
        lim = self.limits
        return KeyRecord(
            id=file_key_id(digest),
            name=self.name,
            source="file",
            unlimited=self.unlimited,
            requests_per_window=lim.requests_per_window,
            window_s=lim.window_s,
            requests_per_day=lim.requests_per_day,
            concurrency=lim.concurrency,
            max_upload_bytes=lim.max_upload_mb * MIB,
            max_audio_seconds=lim.max_duration_s,
            max_pages=lim.max_pages,
            residential_allowed=self.residential_allowed,
            allowed_families=tuple(self.allowed_families),
            ips=tuple(self.ips),
            user_agents=tuple(self.user_agents),
            allowed_sources=tuple(self.allowed_sources),
            disabled_sources=tuple(self.disabled_sources),
            expires_at=as_utc(self.expires) if self.expires is not None else None,
            tier=self.tier,
        )


class KeysFileError(ValueError):
    """`keys.json` is unreadable or invalid. The message never contains key material."""


def read_keys_file(path: Path) -> list[KeyFileEntry]:
    try:
        size = path.stat().st_size
    except OSError as e:
        raise KeysFileError(f"cannot read keys file {path.name}: {e.strerror}") from None
    if size > MAX_KEYS_FILE_BYTES:
        raise KeysFileError(f"keys file {path.name} exceeds {MAX_KEYS_FILE_BYTES // MIB} MB")
    try:
        raw = json.loads(path.read_text(encoding="utf-8") or "[]")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
        raise KeysFileError(f"keys file {path.name} is not valid JSON: {type(e).__name__}") from None
    if not isinstance(raw, list):
        raise KeysFileError(f"keys file {path.name} must be a JSON list")
    if len(raw) > MAX_KEYS_FILE_ENTRIES:
        raise KeysFileError(f"keys file {path.name} has more than {MAX_KEYS_FILE_ENTRIES} entries")
    entries: list[KeyFileEntry] = []
    for index, item in enumerate(raw):
        try:
            entries.append(KeyFileEntry.model_validate(item))
        except ValidationError as e:
            problems = "; ".join(
                f"{'.'.join(str(p) for p in err['loc']) or 'entry'}: {err['msg']}" for err in e.errors()
            )
            raise KeysFileError(f"keys file {path.name} entry {index}: {problems[:500]}") from None
    return entries


def write_keys_file(path: Path, entries: list[dict[str, Any]]) -> None:
    """Atomically replace the keys file with mode 600."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    data = json.dumps(entries, indent=2, ensure_ascii=False) + chr(10)
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8", newline=chr(10)) as fh:
        fh.write(data)
    os.replace(tmp, path)


def _warn_if_world_readable(path: Path) -> None:
    if os.name != "posix":
        return
    try:
        mode = path.stat().st_mode
    except OSError:
        return
    if mode & (stat.S_IRWXG | stat.S_IRWXO):
        log.warning("keys file is readable by group or others; run chmod 600", extra={"path": path.name})


class KeyStore:
    """The keys loaded from `INTOMD_KEYS_FILE`, keyed by hash."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.path = settings.keys_file
        self._lock = threading.Lock()
        self._by_hash: dict[str, KeyRecord] = {}
        self._mtime: float | None = None
        self._checked = 0.0

    def load(self) -> int:
        """(Re)load the file. Raises KeysFileError; the current keys stay in place on error."""
        if self.path is None:
            return 0
        entries = read_keys_file(self.path)
        by_hash: dict[str, KeyRecord] = {}
        for entry in entries:
            record = entry.record(self.settings)
            digest = entry.digest(self.settings)
            if digest in by_hash:
                raise KeysFileError(f"keys file {self.path.name}: duplicate key for entry {entry.name!r}")
            by_hash[digest] = record
        _warn_if_world_readable(self.path)
        with self._lock:
            self._by_hash = by_hash
            self._mtime = self.path.stat().st_mtime
            self._checked = time.monotonic()
        log.info("loaded API keys file", extra={"count": len(by_hash)})
        return len(by_hash)

    def maybe_reload(self) -> None:
        if self.path is None or time.monotonic() - self._checked < RELOAD_CHECK_SECONDS:
            return
        self._checked = time.monotonic()
        try:
            mtime = self.path.stat().st_mtime
        except OSError:
            log.error("API keys file disappeared; keeping the loaded keys")
            return
        if mtime == self._mtime:
            return
        try:
            self.load()
        except KeysFileError as e:
            self._mtime = mtime
            log.error("API keys file reload failed; keeping the previous keys: %s", e)

    def get(self, digest: str) -> KeyRecord | None:
        self.maybe_reload()
        with self._lock:
            return self._by_hash.get(digest)

    def records(self) -> list[KeyRecord]:
        with self._lock:
            return sorted(self._by_hash.values(), key=lambda r: r.name)


# ---------------------------------------------------------------------------
# Database keys
# ---------------------------------------------------------------------------


def record_from_row(row: ApiKeyRow) -> KeyRecord:
    try:
        families = tuple(str(f) for f in json.loads(row.allowed_families or '["*"]'))
    except (json.JSONDecodeError, TypeError):
        families = ("*",)
    return KeyRecord(
        id=row.id,
        name=row.name,
        source="db",
        unlimited=bool(row.unlimited),
        requests_per_window=int(row.requests_per_minute),
        window_s=60,
        requests_per_day=int(row.requests_per_day),
        concurrency=int(row.concurrency),
        max_upload_bytes=int(row.max_upload_bytes),
        max_audio_seconds=int(row.max_audio_seconds),
        max_pages=int(row.max_pages),
        residential_allowed=bool(row.residential_allowed),
        allowed_families=families,
        expires_at=row.expires_at,
        tier="owner" if row.unlimited else "free",
    )


def create_api_key(db: Database, settings: Settings, name: str, *, env: str = "live", **limits: Any) -> tuple[str, str]:
    """Create a database key. Returns (plaintext key, key id); the plaintext is shown once, never stored."""
    key = generate_api_key(env)
    key_id = "key_" + random_base62(12, 17)
    families = limits.pop("allowed_families", None)
    row = ApiKeyRow(id=key_id, name=name[:128], key_hash=hash_api_key(settings, key), **limits)
    if families is not None:
        row.allowed_families = json.dumps(list(families))
    with db.session() as s:
        s.add(row)
    return key, key_id


def lookup_db_key(db: Database, digest: str) -> KeyRecord | None:
    with db.session() as s:
        row = s.execute(select(ApiKeyRow).where(ApiKeyRow.key_hash == digest)).scalar_one_or_none()
    if row is None or row.revoked_at is not None:
        return None
    return record_from_row(row)


def lookup_api_key(db: Database, settings: Settings, key: str, store: KeyStore | None = None) -> KeyRecord | None:
    """The live (not revoked, not expired) key for a presented plaintext key, file keys first."""
    if not key or len(key) > MAX_KEY_LENGTH:
        return None
    digest = hash_api_key(settings, key)
    record = store.get(digest) if store is not None else None
    if record is None:
        record = lookup_db_key(db, digest)
    if record is None or record.expired():
        return None
    return record


def revoke_db_key(db: Database, key_id: str) -> bool:
    with db.session() as s:
        row = s.get(ApiKeyRow, key_id)
        if row is None or row.revoked_at is not None:
            return False
        row.revoked_at = datetime.now(UTC)
    return True
