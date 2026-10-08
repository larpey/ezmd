"""Fast tier of the SSRF table (docs/spec/part4.md 4.14.5 item 1): no network, a fake resolver.

The redirect-to-private case runs against a loopback server in test_netguard.py
(test_redirect_to_private_rechecked); the network tier repeats this table against the compose stack.
"""

from __future__ import annotations

import pytest
from ssrf_table import DNS, LITERAL, PORTS, PUBLIC_DNS

from intomd.core import netguard
from intomd.core.netguard import UrlBlocked


def _resolver(table: dict[str, tuple[str, ...]]) -> netguard.Resolver:
    def resolve(host: str, port: int) -> list[str]:
        if host not in table:
            raise OSError("NXDOMAIN")
        return list(table[host])

    return resolve


def _refused(url: str, table: dict[str, tuple[str, ...]]) -> None:
    with pytest.raises(UrlBlocked):
        v = netguard.validate_url(url)
        netguard.resolve_checked(v, resolver=_resolver(table))


def test_table_has_the_spec_size() -> None:
    assert len(LITERAL) + len(DNS) + len(PORTS) >= 60
    assert len(set(LITERAL)) == len(LITERAL)


@pytest.mark.parametrize("url", LITERAL)
def test_literal_refused_before_dns(url: str) -> None:
    with pytest.raises(UrlBlocked):
        netguard.validate_url(url)


@pytest.mark.parametrize("host", sorted(DNS))
def test_names_resolving_to_blocked_addresses_refused(host: str) -> None:
    v = netguard.validate_url(f"http://{host}/")  # the name itself is fine
    with pytest.raises(UrlBlocked):
        netguard.resolve_checked(v, resolver=_resolver(DNS))


@pytest.mark.parametrize("url", PORTS)
@pytest.mark.xfail(strict=True, reason="netguard does not refuse internal service ports yet (P1-T15 core request)")
def test_internal_ports_on_public_hosts_refused(url: str) -> None:
    _refused(url, PUBLIC_DNS)


def test_public_name_still_allowed() -> None:
    v = netguard.validate_url("https://public.example.com/page")
    assert netguard.resolve_checked(v, resolver=_resolver(PUBLIC_DNS)) == "93.184.215.14"


@pytest.mark.parametrize("url", ["http://10.0.0.1/", "http://[::1]/", "http://loop.example.com/"])
def test_allow_private_is_the_only_escape_hatch(url: str) -> None:
    v = netguard.validate_url(url, allow_private=True)
    assert netguard.resolve_checked(v, resolver=_resolver(DNS), allow_private=True)
