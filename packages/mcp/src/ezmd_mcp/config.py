"""ezmd_mcp.config: server settings from flags and environment.

Environment variables (flags win):

- `EZMD_PROFILE`: default profile for every tool (`agent` when unset).
- `EZMD_REMOTE`: base URL of an ezmd instance; switches to remote mode.
- `EZMD_API_KEY`: sent as `X-API-Key` in remote mode.
- `EZMD_MCP_ALLOWED_DIRS`: allowed roots for `convert_file`, separated by the OS path separator.
- `EZMD_MCP_WAIT_SECONDS`: how long remote convert tools wait before returning `status: running`.
- `EZMD_MCP_TOKEN`: bearer token for the HTTP transport.
- `EZMD_MCP_BIND`: host for the HTTP transport (default `127.0.0.1`).
- `EZMD_MCP_PORT`: port for the HTTP transport (default `8765`).
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from ezmd_mcp.options import OperatorLimits
from ezmd_mcp.paths import AllowedRoots

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
    limits: OperatorLimits = field(default_factory=OperatorLimits)

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
        max_bytes: int | None = None,
        max_seconds: float | None = None,
        max_pages: int | None = None,
        max_duration_seconds: float | None = None,
    ) -> Settings:
        env = os.environ if env is None else env
        dirs = allowed_dirs
        if not dirs:
            raw = env.get("EZMD_MCP_ALLOWED_DIRS", "")
            dirs = [d for d in raw.split(os.pathsep) if d.strip()] or [str(Path.cwd())]
        wait = wait_seconds
        if wait is None:
            try:
                wait = float(env.get("EZMD_MCP_WAIT_SECONDS", "120"))
            except ValueError:
                wait = 120.0
        return cls(
            profile=(profile or env.get("EZMD_PROFILE") or "agent").strip().lower(),
            remote=remote or env.get("EZMD_REMOTE") or None,
            api_key=api_key or env.get("EZMD_API_KEY") or None,
            allowed_dirs=AllowedRoots.from_strings(dirs),
            wait_seconds=max(0.0, wait),
            allow_private_networks=allow_private_networks,
            limits=_limits(max_bytes, max_seconds, max_pages, max_duration_seconds),
        )


def _limits(
    max_bytes: int | None, max_seconds: float | None, max_pages: int | None, max_duration_seconds: float | None
) -> OperatorLimits:
    base = OperatorLimits()
    return OperatorLimits(
        max_bytes=base.max_bytes if max_bytes is None else max_bytes,
        max_seconds=base.max_seconds if max_seconds is None else float(max_seconds),
        max_pages=base.max_pages if max_pages is None else max_pages,
        max_duration_seconds=base.max_duration_seconds if max_duration_seconds is None else float(max_duration_seconds),
    )
