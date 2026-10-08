"""intomd_mcp.config: server settings from flags and environment.

Environment variables (flags win):

- `INTOMD_PROFILE`: default profile for every tool (`agent` when unset).
- `INTOMD_REMOTE`: base URL of an intomd instance; switches to remote mode.
- `INTOMD_API_KEY`: sent as `X-API-Key` in remote mode.
- `INTOMD_MCP_ALLOWED_DIRS`: allowed roots for `convert_file`, separated by the OS path separator.
- `INTOMD_MCP_WAIT_SECONDS`: how long remote convert tools wait before returning `status: running`.
- `INTOMD_MCP_TOKEN`: bearer token for the HTTP transport.
- `INTOMD_MCP_BIND`: host for the HTTP transport (default `127.0.0.1`).
- `INTOMD_MCP_PORT`: port for the HTTP transport (default `8765`).
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from intomd_mcp.paths import AllowedRoots

__all__ = ["DEFAULT_PORT", "LOOPBACK_HOSTS", "Settings", "is_loopback"]

DEFAULT_PORT = 8765
LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "::1")


def is_loopback(host: str) -> bool:
    import ipaddress

    if host in LOOPBACK_HOSTS:
        return True
    try:
        return ipaddress.ip_address(host.strip("[]")).is_loopback
    except ValueError:
        return False


@dataclass(slots=True)
class Settings:
    profile: str = "agent"
    remote: str | None = None
    api_key: str | None = None
    allowed_dirs: AllowedRoots = field(default_factory=lambda: AllowedRoots((Path.cwd().resolve(),)))
    wait_seconds: float = 120.0
    allow_private_networks: bool = False

    @classmethod
    def from_env(
        cls,
        env: Mapping[str, str] | None = None,
        *,
        profile: str | None = None,
        remote: str | None = None,
        api_key: str | None = None,
        allowed_dirs: list[str] | None = None,
        wait_seconds: float | None = None,
        allow_private_networks: bool = False,
    ) -> Settings:
        env = os.environ if env is None else env
        dirs = allowed_dirs
        if not dirs:
            raw = env.get("INTOMD_MCP_ALLOWED_DIRS", "")
            dirs = [d for d in raw.split(os.pathsep) if d.strip()] or [str(Path.cwd())]
        wait = wait_seconds
        if wait is None:
            try:
                wait = float(env.get("INTOMD_MCP_WAIT_SECONDS", "120"))
            except ValueError:
                wait = 120.0
        return cls(
            profile=(profile or env.get("INTOMD_PROFILE") or "agent").strip().lower(),
            remote=remote or env.get("INTOMD_REMOTE") or None,
            api_key=api_key or env.get("INTOMD_API_KEY") or None,
            allowed_dirs=AllowedRoots.from_strings(dirs),
            wait_seconds=max(0.0, wait),
            allow_private_networks=allow_private_networks,
        )
