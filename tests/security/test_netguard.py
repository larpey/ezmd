"""docs/spec/part1.md 8.3 netguard tests. No real network: a fake resolver and a local HTTP server."""

from __future__ import annotations

import gzip
import http.server
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

from ezmd.core import netguard
from ezmd.core.netguard import (
    FetchFailed,
    PlatformDisabled,
    PlatformPolicy,
    ResidentialOnly,
    ResponseTooLarge,
    UrlBlocked,
    fetch,
    is_blocked_ip,
    parse_ip_literal,
    redact_url,
    validate_url,
)

PUBLIC = "93.184.215.14"


def fake_resolver(table: dict[str, list[str]]) -> netguard.Resolver:
    def resolve(host: str, port: int) -> list[str]:
        if host not in table:
            raise OSError("NXDOMAIN")
        return table[host]

    return resolve


@pytest.mark.parametrize(
    "url",
    [
        "http://169.254.169.254/latest/meta-data/",
        "http://[::ffff:169.254.169.254]/",
        "http://0x7f000001/",
        "http://2130706433/",
        "http://127.1/",
        "http://0177.0.0.1/",
        "http://100.100.100.100/",
        "http://10.0.0.1/",
        "http://[::1]/",
        "http://[fd00::1]/",
        "http://[fe80::1]/",
        "http://0.0.0.0/",
        "http://localhost/",
        "http://foo.localhost/",
        "http://metadata.google.internal/",
        "http://printer.local/",
        "http://1.168.192.in-addr.arpa/",
        "http://intranet/",
        "ftp://example.com/",
        "file:///etc/passwd",
        "gopher://example.com/",
        "http://user:pass@example.com/",
        "http://user@example.com/",
        "http://exa mple.com/",
    ],
)
def test_blocked_urls(url: str) -> None:
    with pytest.raises(UrlBlocked):
        v = validate_url(url)
        netguard.resolve_checked(v, resolver=fake_resolver({}))


@pytest.mark.parametrize(
    "port", [6379, 5432, 3306, 27017, 11211, 9200, 2375, 2376, 5672, 15672, 6443, 10250, 8500, 2379, 2380, 25]
)
@pytest.mark.parametrize("host", [PUBLIC, "public.example.com", f"[::ffff:{PUBLIC}]"])
def test_internal_service_ports_refused_on_public_hosts(host: str, port: int) -> None:
    with pytest.raises(UrlBlocked, match=f"port {port}"):
        validate_url(f"http://{host}:{port}/")


@pytest.mark.parametrize(
    "url", ["http://public.example.com:8080/", "https://public.example.com:8443/x", "http://public.example.com:3000/"]
)
def test_web_ports_still_allowed(url: str) -> None:
    v = validate_url(url)
    assert netguard.resolve_checked(v, resolver=fake_resolver({"public.example.com": [PUBLIC]})) == PUBLIC


def test_blocked_port_lifted_only_by_allow_private() -> None:
    assert validate_url("http://redis.example.com:6379/", allow_private=True).port == 6379
    assert 80 not in netguard.BLOCKED_PORTS and 443 not in netguard.BLOCKED_PORTS


def test_public_url_ok() -> None:
    v = validate_url("https://Example.COM./path?q=1")
    assert v.host == "example.com" and v.port == 443
    assert netguard.resolve_checked(v, resolver=fake_resolver({"example.com": [PUBLIC]})) == PUBLIC


def test_hostname_resolving_private_blocked_only_then() -> None:
    v = validate_url("http://localhost.example.com/")
    with pytest.raises(UrlBlocked):
        netguard.resolve_checked(v, resolver=fake_resolver({"localhost.example.com": ["127.0.0.1"]}))
    assert netguard.resolve_checked(v, resolver=fake_resolver({"localhost.example.com": [PUBLIC]})) == PUBLIC


def test_two_a_records_one_private() -> None:
    v = validate_url("http://mixed.example.com/")
    with pytest.raises(UrlBlocked):
        netguard.resolve_checked(v, resolver=fake_resolver({"mixed.example.com": [PUBLIC, "192.168.1.5"]}))


def test_dns_failure_and_timeout() -> None:
    v = validate_url("http://nx.example.com/")
    with pytest.raises(FetchFailed):
        netguard.resolve_checked(v, resolver=fake_resolver({}))

    def slow(host: str, port: int) -> list[str]:
        time.sleep(1)
        return [PUBLIC]

    with pytest.raises(FetchFailed, match="timed out"):
        netguard.resolve_checked(v, resolver=slow, timeout=0.1)


def test_ip_helpers() -> None:
    assert str(parse_ip_literal("0x7f000001")) == "127.0.0.1"
    assert str(parse_ip_literal("2130706433")) == "127.0.0.1"
    assert parse_ip_literal("example.com") is None
    assert parse_ip_literal("deadbeef") is None
    for a in ("::ffff:10.0.0.1", "2002:0a00:0001::", "64:ff9b::7f00:1", "198.18.0.1", "240.0.0.1"):
        ip = parse_ip_literal(a)
        assert ip is not None and is_blocked_ip(ip), a
    pub = parse_ip_literal(PUBLIC)
    assert pub is not None and not is_blocked_ip(pub)


def test_redact_url() -> None:
    r = redact_url("https://u:p@example.com:8443/a?token=" + "x" * 100 + "&b=1#frag")
    assert "u:p" not in r and "frag" not in r and "x" * 65 not in r and ":8443" in r


def test_platform_policy(tmp_path: Path) -> None:
    p = tmp_path / "platforms.toml"
    p.write_text(
        '[hosts]\n"youtube.com" = "residential_only"\n"bad.example" = "disabled"\n"ok.bad.example" = "sanctioned"\n'
    )
    pol = PlatformPolicy.load(p)
    assert pol.state("www.youtube.com") == "residential_only"
    assert pol.state("bad.example") == "disabled"
    assert pol.state("ok.bad.example") == "sanctioned"
    assert pol.state("other.org") == "default"
    with pytest.raises(PlatformDisabled):
        fetch("https://x.bad.example/", policy=pol, resolver=fake_resolver({}))
    with pytest.raises(ResidentialOnly):
        fetch("https://m.youtube.com/watch?v=1", policy=pol, resolver=fake_resolver({}))
    p.write_text('[hosts]\n"a.com" = "maybe"\n')
    with pytest.raises(ValueError):
        PlatformPolicy.load(p)


class _Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a: object) -> None:
        pass

    def do_GET(self) -> None:
        bomb = gzip.compress(b"\0" * 2_000_000)
        routes: dict[str, tuple[int, dict[str, str], bytes]] = {
            "/ok": (200, {"Content-Type": "text/plain"}, b"hello"),
            "/big": (200, {"Content-Type": "text/plain"}, b"x" * 5000),
            "/liar": (200, {"Content-Type": "text/plain", "Content-Length": "999999999"}, b"tiny"),
            "/exe": (200, {"Content-Type": "application/x-dosexec"}, b"MZ"),
            "/gzbomb": (200, {"Content-Type": "text/plain", "Content-Encoding": "gzip"}, bomb),
            "/redir-private": (302, {"Location": "http://127.0.0.1:6379/"}, b""),
            "/redir-meta": (302, {"Location": "http://169.254.169.254/"}, b""),
            "/loop": (302, {"Location": "/loop"}, b""),
        }
        status, headers, body = routes.get(self.path, (404, {}, b""))
        self.send_response(status)
        for k, v in headers.items():
            self.send_header(k, v)
        if "Content-Length" not in headers:
            self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass


@pytest.fixture(scope="module")
def server() -> Iterator[int]:
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield int(httpd.server_address[1])
    httpd.shutdown()


def _loopback(host: str, port: int) -> list[str]:
    return ["127.0.0.1"]


def test_pinned_fetch_ok(server: int) -> None:
    r = fetch(f"http://public.test:{server}/ok", resolver=_loopback, allow_private=True)
    assert r.body == b"hello" and r.resolved_ip == "127.0.0.1" and r.status == 200


def test_body_caps(server: int) -> None:
    for path, cap in (("/big", 1000), ("/liar", 1000), ("/gzbomb", 100_000)):
        with pytest.raises(ResponseTooLarge):
            fetch(f"http://public.test:{server}{path}", resolver=_loopback, allow_private=True, max_bytes=cap)


def test_executable_refused(server: int) -> None:
    with pytest.raises(UrlBlocked):
        fetch(f"http://public.test:{server}/exe", resolver=_loopback, allow_private=True)


def test_http_error(server: int) -> None:
    with pytest.raises(FetchFailed) as ei:
        fetch(f"http://public.test:{server}/404", resolver=_loopback, allow_private=True)
    assert ei.value.status == 404


def test_redirect_loop_capped(server: int) -> None:
    with pytest.raises(FetchFailed, match="redirects"):
        fetch(f"http://public.test:{server}/loop", resolver=_loopback, allow_private=True)


def test_redirect_to_private_rechecked(server: int, monkeypatch: pytest.MonkeyPatch) -> None:
    """The first hop (the loopback test server) is allowed; the redirect target is a blocked IP literal and
    must be refused because every hop is re-validated."""
    real_validate = netguard.validate_url
    calls: list[str] = []

    def validate(url: str, *, allow_private: bool = False) -> netguard.ValidatedUrl:
        calls.append(url)
        return real_validate(url, allow_private=len(calls) == 1)

    real_resolve = netguard.resolve_checked

    def resolve(v: netguard.ValidatedUrl, **kw: object) -> str:
        return "127.0.0.1" if len(calls) == 1 else real_resolve(v)

    monkeypatch.setattr(netguard, "validate_url", validate)
    monkeypatch.setattr(netguard, "resolve_checked", resolve)
    for path in ("/redir-private", "/redir-meta"):
        calls.clear()
        with pytest.raises(UrlBlocked):
            fetch(f"http://public.test:{server}{path}", resolver=_loopback, allow_private=False)
        assert len(calls) == 2


def test_pinned_backend_refuses_other_hosts() -> None:
    import httpcore

    b = netguard._PinnedBackend("example.com", PUBLIC)
    with pytest.raises(httpcore.ConnectError):
        b.connect_tcp("evil.com", 80)


def _capture_headers(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, str]]:
    seen: list[dict[str, str]] = []

    def fake_one(v: object, ip: str, headers: dict[str, str], *args: object) -> tuple[int, dict[str, str], bytes, None]:
        seen.append(dict(headers))
        return 200, {"content-type": "text/html"}, b"<p>ok</p>", None

    monkeypatch.setattr(netguard, "_fetch_one", fake_one)
    return seen


@pytest.mark.parametrize("host", ["www.sec.gov", "data.sec.gov", "efts.sec.gov", "sec.gov"])
def test_sec_hosts_get_edgar_identity(host: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """SEC refuses requests whose User-Agent does not name the requester (P1-T07 core change request)."""
    monkeypatch.setenv("EZMD_EDGAR_IDENTITY", "Example Operator ops@example.com")
    seen = _capture_headers(monkeypatch)
    fetch(f"https://{host}/Archives/edgar/data/1/x.htm", resolver=fake_resolver({host: [PUBLIC]}))
    assert seen[0]["user-agent"] == "Example Operator ops@example.com"


@pytest.mark.parametrize("host", ["example.com", "notsec.gov", "sec.gov.evil.com"])
def test_other_hosts_keep_default_user_agent(host: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EZMD_EDGAR_IDENTITY", "Example Operator ops@example.com")
    seen = _capture_headers(monkeypatch)
    fetch(f"https://{host}/", resolver=fake_resolver({host: [PUBLIC]}))
    assert seen[0]["user-agent"] == netguard.USER_AGENT


def test_sec_without_identity_or_with_explicit_header(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EZMD_EDGAR_IDENTITY", raising=False)
    seen = _capture_headers(monkeypatch)
    resolver = fake_resolver({"www.sec.gov": [PUBLIC]})
    fetch("https://www.sec.gov/", resolver=resolver)
    monkeypatch.setenv("EZMD_EDGAR_IDENTITY", "Example Operator ops@example.com")
    fetch("https://www.sec.gov/", resolver=resolver, headers={"User-Agent": "caller ua@example.com"})
    assert seen[0]["user-agent"] == netguard.USER_AGENT
    assert seen[1]["user-agent"] == "caller ua@example.com"


@pytest.mark.parametrize(
    ("literal", "blocked"),
    [
        (f"::ffff:{PUBLIC}", False),
        ("::ffff:127.0.0.1", True),
        ("::ffff:10.0.0.1", True),
        ("::ffff:169.254.169.254", True),
        ("::ffff:100.64.0.1", True),
    ],
)
def test_ipv4_mapped_addresses_are_judged_by_the_ipv4_address(literal: str, blocked: bool) -> None:
    """Same answer on every CPython patch level (3.12.3 calls every mapped address private)."""
    import ipaddress

    assert is_blocked_ip(ipaddress.IPv6Address(literal)) is blocked


@pytest.mark.parametrize("module", ["brotli", "brotlicffi"])
def test_brotli_bomb_is_capped_without_full_allocation(module: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """64 MB of zeros compresses to a few bytes; decoding with a 1 MB cap must stop near the cap."""
    import sys
    import tracemalloc

    lib = pytest.importorskip(module)
    bomb = lib.compress(b"\0" * (64 * 1024 * 1024), quality=1)
    assert len(bomb) < 64 * 1024
    if module == "brotlicffi":  # force the fallback import path
        monkeypatch.setitem(sys.modules, "brotli", None)
    cap = 1024 * 1024
    tracemalloc.start()
    try:
        with pytest.raises(ResponseTooLarge):
            netguard._decode_capped(bomb, "br", cap, "https://example.com/")
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert peak < 8 * cap, f"peak {peak} bytes"


@pytest.mark.parametrize("module", ["brotli", "brotlicffi"])
def test_brotli_under_cap_round_trips(module: str, monkeypatch: pytest.MonkeyPatch) -> None:
    import sys

    lib = pytest.importorskip(module)
    if module == "brotlicffi":
        monkeypatch.setitem(sys.modules, "brotli", None)
    payload = b"hello brotli " * 5000
    out = netguard._decode_capped(lib.compress(payload), "br", len(payload), "https://example.com/")
    assert out == payload
    with pytest.raises(ResponseTooLarge):
        netguard._decode_capped(lib.compress(payload), "br", len(payload) - 1, "https://example.com/")
