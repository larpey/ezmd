"""The SSRF URL table (docs/spec/part4.md 4.14.5 item 1), shared by the fast and network tiers.

LITERAL: refused by `netguard.validate_url` alone (IP literals in every notation, blocked names, schemes,
credentials), so the API answers 422 `url_blocked` at submit time.
DNS: names that resolve to blocked addresses; the fast tier resolves them with a fake resolver, the
network tier uses the compose fixture alias (`web.fixtures.example`, a private Docker address).
PORTS: internal service ports on a public host. The guard does not filter ports yet (reported as a core
change request in docs/decisions/P1-T15.md), so these are strict xfails until it does.
"""

from __future__ import annotations

PUBLIC_IP = "93.184.215.14"

LITERAL: tuple[str, ...] = (
    # loopback, every notation
    "http://127.0.0.1/",
    "http://127.0.0.1:8000/v1/capabilities",
    "http://127.1/",
    "http://127.0.1/",
    "http://127.255.255.254/",
    "http://0x7f000001/",
    "http://0x7f.0x0.0x0.0x1/",
    "http://2130706433/",
    "http://017700000001/",
    "http://0177.0.0.1/",
    "http://[::1]/",
    "http://[0:0:0:0:0:0:0:1]/",
    "http://[::ffff:127.0.0.1]/",
    "http://[::ffff:7f00:1]/",
    # unspecified
    "http://0.0.0.0/",
    "http://0/",
    "http://[::]/",
    # RFC 1918
    "http://10.0.0.1/",
    "http://10.255.255.255/",
    "http://172.16.0.1/",
    "http://172.31.255.254/",
    "http://192.168.0.1/",
    "http://192.168.1.1:8080/admin",
    # link-local and cloud metadata
    "http://169.254.169.254/latest/meta-data/",
    "http://[::ffff:169.254.169.254]/",
    "http://0xa9fea9fe/",
    "http://2852039166/",
    "http://169.254.0.1/",
    "http://[fe80::1]/",
    # CGNAT (and Tailscale)
    "http://100.64.0.1/",
    "http://100.100.100.100/",
    "http://100.127.255.254/",
    # IPv6 unique local
    "http://[fd00::1]/",
    "http://[fc00::1]/",
    # blocked host names
    "http://localhost/",
    "http://LOCALHOST:6379/",
    "http://localhost./",
    "http://foo.localhost/",
    "http://metadata.google.internal/computeMetadata/v1/",
    "http://metadata/",
    "http://instance-data/latest/",
    "http://printer.local/",
    "http://nas.lan/",
    "http://router.home.arpa/",
    "http://1.168.192.in-addr.arpa/",
    "http://intranet/",
    "http://redis:6379/",
    # schemes and credentials
    "file:///etc/passwd",
    "gopher://example.com/_SET%20x%201",
    "ftp://example.com/",
    "dict://example.com:11211/stat",
    "ldap://example.com/",
    "http://user:pass@example.com/",
    "http://user@example.com/",
)

# name -> addresses the (fake) resolver returns; every one must be refused.
DNS: dict[str, tuple[str, ...]] = {
    "private-a.example.com": ("10.0.0.5",),
    "loop.example.com": ("127.0.0.1",),
    "meta.example.com": ("169.254.169.254",),
    "cgnat.example.com": ("100.64.1.1",),
    "v6loop.example.com": ("::1",),
    "mixed.example.com": (PUBLIC_IP, "10.0.0.1"),
    "mapped.example.com": ("::ffff:192.168.0.10",),
}

PORTS: tuple[str, ...] = (
    f"http://{PUBLIC_IP}:6379/",
    "http://public.example.com:5432/",
)

PUBLIC_DNS: dict[str, tuple[str, ...]] = {"public.example.com": (PUBLIC_IP,)}
