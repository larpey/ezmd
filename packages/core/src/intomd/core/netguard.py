"""intomd.core.netguard: SSRF-safe URL fetching (docs/spec/part1.md section 8.3).

Every outbound fetch of user-supplied URLs goes through `fetch()` (or `guarded_client()` for
adapters that need a client). Guarantees:

1. Scheme allowlist (http, https); URLs with userinfo are rejected.
2. IP literals in private, loopback, link-local, multicast, reserved, unspecified, CGNAT
   (100.64.0.0/10, also the Tailscale range), IPv4-mapped/6to4/Teredo-embedded private, and IPv6
   ULA/link-local ranges are rejected. Legacy IPv4 spellings (`0x7f000001`, `2130706433`, `127.1`)
   are normalized first. Hostnames `localhost`, `*.localhost`, `*.internal`, `*.local`, `*.arpa`,
   and cloud metadata names are rejected.
3. DNS is resolved once (3 s timeout); if any A/AAAA answer is blocked the fetch is refused. The
   connection is then pinned to the resolved address while SNI and Host keep the original name, so
   the HTTP client never re-resolves (no DNS rebinding).
4. Redirects are followed manually, at most 5, re-running 1 to 3 on every hop; Authorization and
   cookies are dropped across hosts.
5. Bodies are streamed and capped (abort at cap + 1), total time is bounded, and executable
   content types are refused.
6. A platform policy file maps hosts to `sanctioned`, `residential_only`, or `disabled`.
7. Every fetch is logged with a redacted URL, the resolved IP, status, bytes, and duration.
"""

from __future__ import annotations

import ipaddress
import logging
import os
import socket
import ssl
import time
import tomllib
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpcore
import httpx

from intomd.detect import EXECUTABLE_MIMES, normalize_mime

log = logging.getLogger(__name__)

ALLOWED_SCHEMES = frozenset({"http", "https"})
MAX_REDIRECTS = 5
DNS_TIMEOUT = 3.0
DEFAULT_MAX_BYTES = 10 * 1024 * 1024
DEFAULT_TOTAL_TIMEOUT = 30.0
USER_AGENT = "intomd-fetch/0.0.1 (+https://github.com/larpey/intomd)"
# The SEC refuses automated requests whose User-Agent does not name the requester with a contact email
# (https://www.sec.gov/os/accessing-edgar-data), so sec.gov hosts get the operator's EDGAR identity.
EDGAR_IDENTITY_ENV = "INTOMD_EDGAR_IDENTITY"


def _host_user_agent(host: str) -> str:
    identity = os.environ.get(EDGAR_IDENTITY_ENV, "").strip()
    if identity and (host == "sec.gov" or host.endswith(".sec.gov")):
        return identity
    return USER_AGENT


_BLOCKED_HOSTNAMES = frozenset(
    {"localhost", "metadata.google.internal", "metadata", "instance-data", "metadata.azure.com"}
)
_BLOCKED_SUFFIXES = (".localhost", ".internal", ".local", ".arpa", ".home.arpa", ".lan", ".intranet")

_EXTRA_BLOCKED_NETS: tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...] = (
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),  # CGNAT and Tailscale
    ipaddress.ip_network("192.0.0.0/24"),
    ipaddress.ip_network("192.0.2.0/24"),
    ipaddress.ip_network("198.18.0.0/15"),
    ipaddress.ip_network("198.51.100.0/24"),
    ipaddress.ip_network("203.0.113.0/24"),
    ipaddress.ip_network("240.0.0.0/4"),
    ipaddress.ip_network("255.255.255.255/32"),
    ipaddress.ip_network("64:ff9b::/96"),  # NAT64 can reach IPv4 private space
    ipaddress.ip_network("64:ff9b:1::/48"),
    ipaddress.ip_network("100::/64"),
    ipaddress.ip_network("2001:db8::/32"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
    ipaddress.ip_network("fec0::/10"),
)


class NetguardError(Exception):
    """Base class. `code` maps to the API error schema (docs/spec/part1.md section 7.5)."""

    code = "url_blocked"

    def __init__(self, message: str, *, url: str | None = None) -> None:
        super().__init__(message)
        self.url = redact_url(url) if url else None


class UrlBlocked(NetguardError):
    code = "url_blocked"


class PlatformDisabled(NetguardError):
    code = "platform_disabled"


class ResidentialOnly(NetguardError):
    """The host only works from a residential IP; the caller should route to a fetch node."""

    code = "fetch_blocked_by_platform"


class FetchFailed(NetguardError):
    code = "fetch_failed"

    def __init__(self, message: str, *, url: str | None = None, status: int | None = None) -> None:
        super().__init__(message, url=url)
        self.status = status


class ResponseTooLarge(NetguardError):
    code = "input_too_large"


# ---------------------------------------------------------------------------
# Address and URL validation
# ---------------------------------------------------------------------------

IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address


def parse_ip_literal(host: str) -> IPAddress | None:
    """Parse `host` as an IP literal, including legacy IPv4 spellings accepted by inet_aton
    (`0x7f000001`, `2130706433`, `0177.0.0.1`, `127.1`). Returns None for real hostnames."""
    h = host.strip("[]")
    try:
        return ipaddress.ip_address(h)
    except ValueError:
        pass
    if not h or not all(c in "0123456789abcdefxABCDEFX." for c in h):
        return None
    if not any(c.isdigit() for c in h):
        return None
    try:
        packed = socket.inet_aton(h)
    except OSError:
        return None
    return ipaddress.IPv4Address(packed)


def _embedded_v4(ip: ipaddress.IPv6Address) -> ipaddress.IPv4Address | None:
    if ip.ipv4_mapped is not None:
        return ip.ipv4_mapped
    if ip.sixtofour is not None:
        return ip.sixtofour
    if ip.teredo is not None:
        return ip.teredo[1]
    # IPv4-compatible ::a.b.c.d (deprecated but still routable by some stacks)
    if int(ip) >> 32 == 0 and int(ip) > 1:
        return ipaddress.IPv4Address(int(ip) & 0xFFFFFFFF)
    return None


def is_blocked_ip(ip: IPAddress) -> bool:
    if isinstance(ip, ipaddress.IPv6Address):
        v4 = _embedded_v4(ip)
        if v4 is not None and is_blocked_ip(v4):
            return True
    if (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
        or (isinstance(ip, ipaddress.IPv6Address) and ip.is_site_local)
    ):
        return True
    return any(ip in net for net in _EXTRA_BLOCKED_NETS if net.version == ip.version)


def is_blocked_hostname(host: str) -> bool:
    h = host.lower().rstrip(".")
    return h in _BLOCKED_HOSTNAMES or h.endswith(_BLOCKED_SUFFIXES) or "." not in h


def redact_url(url: str) -> str:
    """Remove userinfo and truncate long query values for logs and error messages."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return "<unparseable url>"
    netloc = parts.hostname or ""
    if parts.port:
        netloc = f"{netloc}:{parts.port}"
    query_items = []
    for item in parts.query.split("&") if parts.query else []:
        k, _, v = item.partition("=")
        query_items.append(f"{k}={v[:64]}{'...' if len(v) > 64 else ''}" if v else k)
    return urlunsplit((parts.scheme, netloc, parts.path, "&".join(query_items), ""))


@dataclass(frozen=True, slots=True)
class ValidatedUrl:
    url: str
    scheme: str
    host: str
    port: int
    ip_literal: IPAddress | None


def validate_url(url: str, *, allow_private: bool = False) -> ValidatedUrl:
    """Steps 1 and 2: scheme, userinfo, host syntax, IP-literal ranges, blocked names."""
    if len(url) > 8192:
        raise UrlBlocked("URL is too long", url=url[:200])
    if any(ord(c) < 0x21 for c in url):
        raise UrlBlocked("URL contains whitespace or control characters", url=url)
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError as e:
        raise UrlBlocked(f"malformed URL: {e}", url=url) from e
    scheme = parts.scheme.lower()
    if scheme not in ALLOWED_SCHEMES:
        raise UrlBlocked(f"scheme {scheme!r} is not allowed", url=url)
    if parts.username is not None or parts.password is not None or "@" in parts.netloc:
        raise UrlBlocked("URLs with credentials are not allowed", url=url)
    host = parts.hostname
    if not host:
        raise UrlBlocked("URL has no host", url=url)
    host = host.rstrip(".")
    try:
        host_idna = host.encode("idna").decode("ascii") if not host.isascii() else host
    except UnicodeError as e:
        raise UrlBlocked("invalid internationalized hostname", url=url) from e
    ip = parse_ip_literal(host_idna)
    if ip is not None:
        if not allow_private and is_blocked_ip(ip):
            raise UrlBlocked(f"address {ip} is in a blocked range", url=url)
    elif not allow_private and is_blocked_hostname(host_idna):
        raise UrlBlocked(f"host {host_idna!r} is not allowed", url=url)
    eff_port = port if port is not None else (443 if scheme == "https" else 80)
    return ValidatedUrl(url=url, scheme=scheme, host=host_idna.lower(), port=eff_port, ip_literal=ip)


# ---------------------------------------------------------------------------
# DNS
# ---------------------------------------------------------------------------

Resolver = Callable[[str, int], list[str]]
_dns_pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix="intomd-dns")


def system_resolver(host: str, port: int) -> list[str]:
    infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    out: list[str] = []
    for _family, _type, _proto, _canon, sockaddr in infos:
        addr = str(sockaddr[0])
        if addr not in out:
            out.append(addr)
    return out


def resolve_checked(
    v: ValidatedUrl, *, resolver: Resolver = system_resolver, timeout: float = DNS_TIMEOUT, allow_private: bool = False
) -> str:
    """Step 3: resolve once, reject if any answer is blocked, return the address to pin."""
    if v.ip_literal is not None:
        return str(v.ip_literal)
    fut = _dns_pool.submit(resolver, v.host, v.port)
    try:
        addrs = fut.result(timeout=timeout)
    except FutureTimeout as e:
        raise FetchFailed(f"DNS lookup for {v.host} timed out", url=v.url) from e
    except OSError as e:
        raise FetchFailed(f"DNS lookup for {v.host} failed", url=v.url) from e
    if not addrs:
        raise FetchFailed(f"DNS lookup for {v.host} returned no addresses", url=v.url)
    parsed: list[IPAddress] = []
    for a in addrs:
        try:
            parsed.append(ipaddress.ip_address(a.split("%", 1)[0]))
        except ValueError as e:
            raise UrlBlocked(f"resolver returned a non-address {a!r}", url=v.url) from e
    if not allow_private:
        bad = [str(ip) for ip in parsed if is_blocked_ip(ip)]
        if bad:
            raise UrlBlocked(f"{v.host} resolves to a blocked address ({bad[0]})", url=v.url)
    v4 = [ip for ip in parsed if ip.version == 4]
    return str((v4 or parsed)[0])


# ---------------------------------------------------------------------------
# Pinned transports
# ---------------------------------------------------------------------------


class _PinnedBackend(httpcore.NetworkBackend):
    """Connects to the pinned address for the one hostname this client may reach."""

    def __init__(self, host: str, ip: str) -> None:
        self._host = host
        self._ip = ip
        self._inner = httpcore.SyncBackend()

    def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Iterable[Any] | None = None,
    ) -> httpcore.NetworkStream:
        if host.lower().strip("[]") not in (self._host, self._ip):
            raise httpcore.ConnectError(f"connection to unpinned host {host!r} refused")
        return self._inner.connect_tcp(self._ip, port, timeout, local_address, socket_options)

    def connect_unix_socket(
        self, path: str, timeout: float | None = None, socket_options: Iterable[Any] | None = None
    ) -> httpcore.NetworkStream:
        raise httpcore.ConnectError("unix sockets are not allowed")

    def sleep(self, seconds: float) -> None:
        self._inner.sleep(seconds)


class _AsyncPinnedBackend(httpcore.AsyncNetworkBackend):
    def __init__(self, host: str, ip: str) -> None:
        self._host = host
        self._ip = ip
        self._inner = httpcore.AnyIOBackend()

    async def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options: Iterable[Any] | None = None,
    ) -> httpcore.AsyncNetworkStream:
        if host.lower().strip("[]") not in (self._host, self._ip):
            raise httpcore.ConnectError(f"connection to unpinned host {host!r} refused")
        return await self._inner.connect_tcp(self._ip, port, timeout, local_address, socket_options)

    async def connect_unix_socket(
        self, path: str, timeout: float | None = None, socket_options: Iterable[Any] | None = None
    ) -> httpcore.AsyncNetworkStream:
        raise httpcore.ConnectError("unix sockets are not allowed")

    async def sleep(self, seconds: float) -> None:
        await self._inner.sleep(seconds)


class PinnedTransport(httpx.HTTPTransport):
    """httpx transport whose connection pool can only connect to one pre-resolved address."""

    def __init__(self, host: str, ip: str, *, verify: ssl.SSLContext | bool = True) -> None:
        super().__init__(verify=verify, trust_env=False)
        ctx = verify if isinstance(verify, ssl.SSLContext) else httpx.create_ssl_context(verify=verify)
        self._pool = httpcore.ConnectionPool(ssl_context=ctx, network_backend=_PinnedBackend(host, ip))


class AsyncPinnedTransport(httpx.AsyncHTTPTransport):
    def __init__(self, host: str, ip: str, *, verify: ssl.SSLContext | bool = True) -> None:
        super().__init__(verify=verify, trust_env=False)
        ctx = verify if isinstance(verify, ssl.SSLContext) else httpx.create_ssl_context(verify=verify)
        self._pool = httpcore.AsyncConnectionPool(ssl_context=ctx, network_backend=_AsyncPinnedBackend(host, ip))


# ---------------------------------------------------------------------------
# Platform policy
# ---------------------------------------------------------------------------

PolicyState = Literal["sanctioned", "residential_only", "disabled", "default"]


@dataclass(slots=True)
class PlatformPolicy:
    """Host policy from `platforms.toml`:

    ```toml
    [hosts]
    "youtube.com" = "residential_only"
    "example-disabled.com" = "disabled"
    "api.github.com" = "sanctioned"
    ```

    A host matches itself and its subdomains. The most specific entry wins.
    """

    hosts: dict[str, PolicyState] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path | str) -> PlatformPolicy:
        data = tomllib.loads(Path(path).read_text(encoding="utf-8"))
        raw = data.get("hosts", {})
        hosts: dict[str, PolicyState] = {}
        for k, v in raw.items():
            if v not in ("sanctioned", "residential_only", "disabled"):
                raise ValueError(f"platform policy for {k!r} must be sanctioned, residential_only, or disabled")
            hosts[k.lower().lstrip(".")] = v
        return cls(hosts=hosts)

    def state(self, host: str) -> PolicyState:
        h = host.lower().rstrip(".")
        best: tuple[int, PolicyState] | None = None
        for k, v in self.hosts.items():
            if (h == k or h.endswith("." + k)) and (best is None or len(k) > best[0]):
                best = (len(k), v)
        return best[1] if best else "default"


# ---------------------------------------------------------------------------
# Fetch
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class FetchResult:
    url: str
    """Final URL after redirects."""
    status: int
    headers: dict[str, str]
    body: bytes
    resolved_ip: str
    redirects: list[str]
    duration_seconds: float

    @property
    def content_type(self) -> str | None:
        return normalize_mime(self.headers.get("content-type"))


_HOP_DROP_HEADERS = frozenset({"authorization", "cookie", "proxy-authorization"})


def fetch(
    url: str,
    *,
    max_bytes: int = DEFAULT_MAX_BYTES,
    total_timeout: float = DEFAULT_TOTAL_TIMEOUT,
    headers: dict[str, str] | None = None,
    resolver: Resolver = system_resolver,
    policy: PlatformPolicy | None = None,
    allow_private: bool = False,
    verify: ssl.SSLContext | bool = True,
    request_id: str | None = None,
) -> FetchResult:
    """GET `url` with the full SSRF guard. See the module docstring."""
    t0 = time.monotonic()
    send_headers = {"accept": "*/*", **{k.lower(): v for k, v in (headers or {}).items()}}
    caller_agent = "user-agent" in send_headers
    current = url
    redirects: list[str] = []
    first_host: str | None = None
    while True:
        v = validate_url(current, allow_private=allow_private)
        if first_host is None:
            first_host = v.host
        elif v.host != first_host:
            send_headers = {k: val for k, val in send_headers.items() if k not in _HOP_DROP_HEADERS}
        if not caller_agent:
            send_headers["user-agent"] = _host_user_agent(v.host)
        if policy is not None:
            state = policy.state(v.host)
            if state == "disabled":
                raise PlatformDisabled(f"{v.host} is disabled on this instance", url=current)
            if state == "residential_only":
                raise ResidentialOnly(f"{v.host} requires a residential fetch", url=current)
        remaining = total_timeout - (time.monotonic() - t0)
        if remaining <= 0:
            raise FetchFailed("fetch timed out", url=current)
        ip = resolve_checked(v, resolver=resolver, allow_private=allow_private)
        status, resp_headers, body, location = _fetch_one(v, ip, send_headers, max_bytes, remaining, verify)
        if status in (301, 302, 303, 307, 308) and location:
            if len(redirects) >= MAX_REDIRECTS:
                raise FetchFailed(f"more than {MAX_REDIRECTS} redirects", url=url)
            nxt = urljoin(current, location)
            redirects.append(redact_url(nxt))
            current = nxt
            continue
        dt = time.monotonic() - t0
        log.info(
            "fetch",
            extra={
                "request_id": request_id,
                "url": redact_url(current),
                "resolved_ip": ip,
                "status": status,
                "bytes": len(body),
                "duration": round(dt, 3),
            },
        )
        if status >= 400:
            raise FetchFailed(f"HTTP {status}", url=current, status=status)
        return FetchResult(
            url=current,
            status=status,
            headers=resp_headers,
            body=body,
            resolved_ip=ip,
            redirects=redirects,
            duration_seconds=dt,
        )


def _fetch_one(
    v: ValidatedUrl,
    ip: str,
    headers: dict[str, str],
    max_bytes: int,
    timeout: float,
    verify: ssl.SSLContext | bool,
) -> tuple[int, dict[str, str], bytes, str | None]:
    transport = PinnedTransport(v.host, ip, verify=verify)
    t = httpx.Timeout(min(timeout, 30.0), read=min(timeout, 30.0))
    with (
        httpx.Client(transport=transport, timeout=t, follow_redirects=False, trust_env=False) as client,
        client.stream("GET", v.url, headers=headers) as resp,
    ):
        resp_headers = {k.lower(): val for k, val in resp.headers.items()}
        location = resp_headers.get("location") if resp.is_redirect else None
        if location is not None:
            return resp.status_code, resp_headers, b"", location
        ctype = normalize_mime(resp_headers.get("content-type"))
        if ctype in EXECUTABLE_MIMES:
            raise UrlBlocked(f"refusing executable content type {ctype}", url=v.url)
        declared = resp_headers.get("content-length")
        if declared and declared.isdigit() and int(declared) > max_bytes:
            raise ResponseTooLarge(f"declared size {declared} exceeds cap {max_bytes}", url=v.url)
        buf = bytearray()
        deadline = time.monotonic() + timeout
        for chunk in resp.iter_raw():
            buf.extend(chunk)
            if len(buf) > max_bytes:
                raise ResponseTooLarge(f"body exceeds cap {max_bytes}", url=v.url)
            if time.monotonic() > deadline:
                raise FetchFailed("fetch timed out while reading body", url=v.url)
        body = bytes(buf)
        enc = resp_headers.get("content-encoding", "").lower()
        if enc and enc != "identity":
            body = _decode_capped(body, enc, max_bytes, v.url)
        return resp.status_code, resp_headers, body, None


def _decode_capped(body: bytes, encoding: str, max_bytes: int, url: str) -> bytes:
    """Decompress with a size cap so a gzip bomb cannot expand past `max_bytes`."""
    import zlib

    if encoding in ("gzip", "x-gzip", "deflate"):
        wbits = 16 + zlib.MAX_WBITS if "gzip" in encoding else zlib.MAX_WBITS
        d = zlib.decompressobj(wbits)
        out = d.decompress(body, max_bytes + 1)
        if len(out) > max_bytes or d.unconsumed_tail:
            raise ResponseTooLarge(f"decompressed body exceeds cap {max_bytes}", url=url)
        return out
    if encoding == "br":
        try:
            import brotli
        except ImportError as e:
            raise FetchFailed("brotli-encoded response but brotli is not installed", url=url) from e
        dec = brotli.Decompressor()
        out = dec.process(body)
        if len(out) > max_bytes:
            raise ResponseTooLarge(f"decompressed body exceeds cap {max_bytes}", url=url)
        return bytes(out)
    raise FetchFailed(f"unsupported content-encoding {encoding!r}", url=url)
