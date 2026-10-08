#!/bin/sh
# intomd worker entrypoint: optional egress allowlist (Part 1 section 8.1).
#
# Default (INTOMD_EGRESS_ALLOWLIST empty): no firewall work is done; the worker relies on the
# compose `internal` network, which has no route to the internet. The script just execs "$@".
#
# Allowlist mode (INTOMD_EGRESS_ALLOWLIST="huggingface.co cdn-lfs.huggingface.co ..."): the
# container must start as root with CAP_NET_ADMIN, CAP_SETUID, CAP_SETGID and CAP_SETPCAP on a
# network that has egress. The script resolves each host once, installs iptables OUTPUT rules
# (loopback, established, the container's own connected subnets, the resolved IPs on tcp/80 and
# tcp/443; everything else dropped, IPv6 dropped), then drops to uid/gid 10001 with every
# capability cleared and no_new_privs set before exec'ing the worker. If the rules cannot be
# installed the script exits non-zero: it fails closed, never open.
#
# Known limitation: addresses are resolved at container start; CDNs that rotate IPs may need a
# container restart. That is accepted for model-download hosts.
set -eu

log() { printf 'egress-allowlist: %s\n' "$*" >&2; }

ALLOW="$(printf '%s' "${INTOMD_EGRESS_ALLOWLIST:-}" | tr ',' ' ')"
RUN_UID="${INTOMD_RUN_UID:-10001}"
RUN_GID="${INTOMD_RUN_GID:-10001}"

if [ "$#" -eq 0 ]; then
  log "no command given"
  exit 64
fi

if [ -z "$(printf '%s' "$ALLOW" | tr -d ' ')" ]; then
  exec "$@"
fi

if [ "$(id -u)" != "0" ]; then
  log "INTOMD_EGRESS_ALLOWLIST is set but the container is not root; cannot install rules (failing closed)"
  exit 77
fi
for bin in iptables ip6tables setpriv python3; do
  command -v "$bin" >/dev/null 2>&1 || { log "missing $bin (failing closed)"; exit 69; }
done

# Connected IPv4 subnets of this container, from /proc/net/route (Redis, API, DNS stay reachable).
SUBNETS="$(python3 - <<'PY'
import ipaddress, socket, struct
with open("/proc/net/route") as fh:
    next(fh)
    for line in fh:
        f = line.split()
        if len(f) < 8 or f[2] != "00000000" or f[1] == "00000000":
            continue  # keep only on-link routes, skip the default route
        dest = socket.inet_ntoa(struct.pack("<L", int(f[1], 16)))
        mask = socket.inet_ntoa(struct.pack("<L", int(f[7], 16)))
        print(ipaddress.IPv4Network(f"{dest}/{mask}", strict=False))
PY
)"

resolve() {
  python3 - "$1" <<'PY'
import socket, sys
try:
    infos = socket.getaddrinfo(sys.argv[1], 443, socket.AF_INET, socket.SOCK_STREAM)
except OSError as exc:
    print(f"resolve failed for {sys.argv[1]}: {exc}", file=sys.stderr)
    sys.exit(1)
for ip in sorted({i[4][0] for i in infos}):
    print(ip)
PY
}

IPS=""
for host in $ALLOW; do
  r="$(resolve "$host")" || { log "cannot resolve $host (failing closed)"; exit 68; }
  IPS="$IPS $r"
done

iptables -w -F OUTPUT
iptables -w -P OUTPUT DROP
iptables -w -A OUTPUT -o lo -j ACCEPT
iptables -w -A OUTPUT -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT
for net in $SUBNETS; do
  iptables -w -A OUTPUT -d "$net" -j ACCEPT
done
for ip in $IPS; do
  iptables -w -A OUTPUT -d "$ip" -p tcp -m multiport --dports 80,443 -j ACCEPT
done
# DNS to the configured resolvers only (Docker's embedded 127.0.0.11 is already covered by lo).
# shellcheck disable=SC2013  # one IPv4 address per word is exactly what is wanted
for ns in $(awk '$1 == "nameserver" && $2 ~ /^[0-9.]+$/ { print $2 }' /etc/resolv.conf); do
  iptables -w -A OUTPUT -d "$ns" -p udp --dport 53 -j ACCEPT
  iptables -w -A OUTPUT -d "$ns" -p tcp --dport 53 -j ACCEPT
done
ip6tables -w -F OUTPUT 2>/dev/null || true
ip6tables -w -P OUTPUT DROP 2>/dev/null || true
ip6tables -w -A OUTPUT -o lo -j ACCEPT 2>/dev/null || true

# shellcheck disable=SC2086  # SUBNETS is a word list
log "allowlist installed for: $ALLOW (subnets: $(printf "%s " $SUBNETS))"
exec setpriv --reuid="$RUN_UID" --regid="$RUN_GID" --clear-groups \
  --inh-caps=-all --bounding-set=-all --no-new-privs -- "$@"
