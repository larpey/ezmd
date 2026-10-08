"""EDGAR HTTP client: declared identity, a process-wide rate limit, and an injectable transport.

The SEC requires every automated request to carry a User-Agent naming the requester with a contact email
(https://www.sec.gov/os/accessing-edgar-data) and allows at most 10 requests per second; we use 5 (part2
12c step 1). Without an identity the converter fails at once with a clear message; a 403 or 429 is never
retried in a loop. The default transport is `intomd.core.netguard.fetch`, so every request gets the SSRF
guard, the byte cap, and redirect re-validation. Tests pass a fake transport and never touch the network.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from intomd.registry import ConversionError, ConvertOptions

IDENTITY_ENV = "INTOMD_EDGAR_IDENTITY"
IDENTITY_OPTION = "specialized.edgar_identity"
REQUESTS_PER_SECOND = 5.0
MAX_RESPONSE_BYTES = 25 * 1024 * 1024
TIMEOUT_SECONDS = 30.0
_EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
IDENTITY_MISSING = "edgar_identity_missing"
IDENTITY_HELP = (
    "SEC EDGAR requires a declared identity (a name and contact email) on every request. Set "
    f'{IDENTITY_ENV}="Your Name you@example.com" or pass the option {IDENTITY_OPTION}.'
)


@dataclass(frozen=True, slots=True)
class Response:
    status: int
    headers: dict[str, str]
    body: bytes
    url: str

    @property
    def content_type(self) -> str:
        return (self.headers.get("content-type") or "").split(";", 1)[0].strip().lower()


Transport = Callable[[str, dict[str, str]], Response]
"""transport(url, headers) -> Response. Raises ConversionError on transport failure."""


def resolve_identity(options: ConvertOptions, env: dict[str, str] | None = None) -> str | None:
    """The identity string from options, then the environment. None when absent or not `Name email`."""
    raw = options.extra.get(IDENTITY_OPTION)
    value = raw if isinstance(raw, str) and raw.strip() else (env if env is not None else os.environ).get(IDENTITY_ENV)
    if not value:
        return None
    value = " ".join(value.split())
    if len(value) > 200 or not _EMAIL.search(value) or any(ord(ch) < 32 for ch in value):
        return None
    return value


def require_identity(options: ConvertOptions, env: dict[str, str] | None = None) -> str:
    identity = resolve_identity(options, env)
    if identity is None:
        raise ConversionError(
            f"{IDENTITY_MISSING}: no valid {IDENTITY_ENV}",
            user_message=IDENTITY_HELP,
            retryable_with_fallback=False,
        )
    return identity


class RateLimiter:
    """Minimum spacing between requests, shared by every client in the process (the SEC limit is per
    requester, not per conversion). `clock` and `sleep` are injectable for tests."""

    def __init__(
        self,
        per_second: float = REQUESTS_PER_SECOND,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.interval = 1.0 / per_second
        self._clock = clock
        self._sleep = sleep
        self._next = 0.0
        self._lock = threading.Lock()

    def wait(self) -> None:
        with self._lock:
            now = self._clock()
            if now < self._next:
                self._sleep(self._next - now)
                now = self._next
            self._next = now + self.interval


SHARED_LIMITER = RateLimiter()


def netguard_transport(max_bytes: int = MAX_RESPONSE_BYTES) -> Transport:
    def send(url: str, headers: dict[str, str]) -> Response:
        from intomd.core import netguard

        try:
            res = netguard.fetch(url, headers=headers, max_bytes=max_bytes, total_timeout=TIMEOUT_SECONDS)
        except netguard.FetchFailed as e:
            if e.status is not None:
                return Response(status=e.status, headers={}, body=b"", url=url)
            raise ConversionError(f"EDGAR fetch failed: {e}", user_message="Could not reach SEC EDGAR.") from e
        except netguard.NetguardError as e:
            raise ConversionError(
                f"EDGAR fetch refused: {e}", user_message="The EDGAR URL was refused by the fetch guard."
            ) from e
        return Response(status=res.status, headers=res.headers, body=res.body, url=res.url)

    return send


@dataclass(slots=True)
class EdgarClient:
    identity: str
    options: ConvertOptions
    transport: Transport = field(default_factory=netguard_transport)
    limiter: RateLimiter = field(default_factory=lambda: SHARED_LIMITER)
    requests: list[str] = field(default_factory=list)
    """URLs requested, in order (diagnostics and tests)."""

    def get(self, url: str, *, accept: str = "*/*") -> Response:
        self.options.ctx.check_deadline()
        self.limiter.wait()
        self.requests.append(url)
        headers = {"user-agent": self.identity, "accept": accept, "accept-encoding": "gzip, deflate"}
        res = self.transport(url, headers)
        if res.status in (403, 429):
            raise ConversionError(
                f"rate_limited: SEC EDGAR answered HTTP {res.status} for {url}",
                user_message=(
                    f"SEC EDGAR refused the request (HTTP {res.status}). The SEC blocks requests without a valid "
                    "identity or above 10 requests per second; check the identity and retry in a few minutes."
                ),
                retryable_with_fallback=False,
            )
        if res.status == 404:
            raise ConversionError(f"EDGAR returned 404 for {url}", user_message="That EDGAR filing was not found.")
        if res.status >= 400:
            raise ConversionError(f"EDGAR returned HTTP {res.status} for {url}", user_message="SEC EDGAR failed.")
        return res

    def get_json(self, url: str) -> Any:
        res = self.get(url, accept="application/json")
        try:
            return json.loads(res.body)
        except ValueError as e:
            raise ConversionError(
                f"EDGAR returned non-JSON for {url}", user_message="SEC EDGAR returned an unexpected response."
            ) from e
