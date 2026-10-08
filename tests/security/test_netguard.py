"""docs/spec/part1.md 8.3 netguard tests. No real network: a fake resolver and a local HTTP server."""

from __future__ import annotations

import gzip
import http.server
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

from intomd.core import netguard
from intomd.core.netguard import (
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
