"""ezmd_api.util: identifiers, hashing, filename sanitization, URL normalization."""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import unicodedata
from datetime import UTC, datetime
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

BASE62 = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
JOB_ID_RE = re.compile(r"^job_[0-9A-Za-z]{22}$")
MAX_FILENAME_BYTES = 255
_TRACKING_PARAMS = frozenset({"fbclid", "gclid", "si"})
_SEPARATORS = re.compile(r"[\\/]")


def utcnow() -> datetime:
    return datetime.now(UTC)


def as_utc(value: datetime) -> datetime:
    """SQLite drops tzinfo; every timestamp we store is UTC."""
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return as_utc(value).strftime("%Y-%m-%dT%H:%M:%SZ")


def base62(n: int, width: int) -> str:
    out: list[str] = []
    while n:
        n, r = divmod(n, 62)
        out.append(BASE62[r])
    return "".join(reversed(out)).rjust(width, "0")


def random_base62(nbytes: int, width: int) -> str:
    return base62(int.from_bytes(secrets.token_bytes(nbytes), "big"), width)


def new_job_id() -> str:
    """`job_` + 22-char base62 from 16 random bytes (128 bits)."""
    return "job_" + random_base62(16, 22)


def new_request_id() -> str:
    return "req_" + random_base62(16, 22)


def new_claim_token() -> str:
    return "ct_" + secrets.token_urlsafe(24)


def is_job_id(value: str) -> bool:
    return bool(JOB_ID_RE.match(value))


def sha256_hex(data: bytes | str) -> str:
    if isinstance(data, str):
        data = data.encode()
    return hashlib.sha256(data).hexdigest()


def keyed_hash(secret: bytes, value: str) -> str:
    """Salted/peppered sha256 (HMAC-SHA256). Used for client IPs, API keys, claim tokens."""
    return hmac.new(secret, value.encode(), hashlib.sha256).hexdigest()


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sanitize_filename(raw: str | None, *, fallback: str = "upload") -> str:
    """Multipart filename rule (docs/spec/part1.md section 8.2): basename only, control characters
    and path separators stripped, capped at 255 bytes. The result is for display and extension hints;
    it is never used as a path on disk."""
    if not raw:
        return fallback
    name = _SEPARATORS.split(raw)[-1]
    name = "".join(ch for ch in name if unicodedata.category(ch)[0] != "C")
    name = name.strip().strip(".").strip()
    if not name or name in {".", ".."}:
        return fallback
    encoded = name.encode("utf-8")
    if len(encoded) > MAX_FILENAME_BYTES:
        name = encoded[:MAX_FILENAME_BYTES].decode("utf-8", errors="ignore")
    return name or fallback


def normalize_url(url: str) -> str:
    """Dedup key for URL inputs: lowercase scheme and host, strip fragment and tracking params."""
    parts = urlsplit(url.strip())
    netloc = (parts.hostname or "").lower()
    if parts.port:
        netloc = f"{netloc}:{parts.port}"
    query = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if not k.lower().startswith("utm_") and k.lower() not in _TRACKING_PARAMS
    ]
    return urlunsplit((parts.scheme.lower(), netloc, parts.path or "/", urlencode(query), ""))


def strip_fragment(url: str) -> str:
    parts = urlsplit(url.strip())
    return urlunsplit((parts.scheme, parts.netloc, parts.path, parts.query, ""))
