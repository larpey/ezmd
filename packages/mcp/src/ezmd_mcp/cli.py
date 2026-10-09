"""ezmd_mcp.cli: the `ezmd-mcp` console script.

    ezmd-mcp                                   # stdio, local mode (the `uvx ezmd-mcp` default)
    ezmd-mcp --allowed-dirs ~/docs ~/papers    # widen the convert_file roots (default: the working dir)
    ezmd-mcp --remote https://ezmd.example   # forward to an instance (EZMD_API_KEY sent as X-API-Key)
    ezmd-mcp --transport http --port 8765      # streamable HTTP on 127.0.0.1 with a bearer token

stdout belongs to the MCP stdio protocol, so every diagnostic goes to stderr.
"""

from __future__ import annotations

import argparse
import logging
import os
import secrets
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from ezmd_mcp import __version__
from ezmd_mcp.backend import PROFILES, Backend
from ezmd_mcp.config import DEFAULT_PORT, Settings, is_loopback
from ezmd_mcp.options import OperatorLimits

__all__ = ["HttpConfig", "main", "parse_args", "resolve_http"]


def _positive_int(raw: str) -> int:
    value = int(raw)
    if value < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return value


def _positive_float(raw: str) -> float:
    value = float(raw)
    if not value > 0:
        raise argparse.ArgumentTypeError("must be a positive number")
    return value


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="ezmd-mcp", description="MCP server for ezmd (convert anything to Markdown).")
    p.add_argument("--transport", choices=("stdio", "http"), default="stdio", help="stdio (default) or http")
    p.add_argument("--host", default=None, help="HTTP bind host (default EZMD_MCP_BIND or 127.0.0.1)")
    p.add_argument("--port", type=int, default=None, help=f"HTTP port (default EZMD_MCP_PORT or {DEFAULT_PORT})")
    p.add_argument("--token", default=None, help="HTTP bearer token (default EZMD_MCP_TOKEN)")
    p.add_argument("--no-auth", action="store_true", help="HTTP without a token; loopback hosts only")
    p.add_argument("--remote", default=None, help="Forward to an ezmd instance at this URL (EZMD_REMOTE)")
    p.add_argument("--api-key", default=None, help="API key for --remote (default EZMD_API_KEY)")
    p.add_argument("--profile", choices=PROFILES, default=None, help="Default profile (EZMD_PROFILE, else agent)")
    p.add_argument(
        "--allowed-dirs",
        nargs="+",
        action="extend",
        default=None,
        metavar="DIR",
        help="Directories convert_file may read (EZMD_MCP_ALLOWED_DIRS; default the working directory)",
    )
    p.add_argument("--wait-seconds", type=float, default=None, help="Remote: wait this long before status=running")
    p.add_argument(
        "--allow-private-networks",
        action="store_true",
        help="Local mode: let tool callers set options.allow_private_networks (intranet URLs)",
    )
    limits = OperatorLimits()
    p.add_argument(
        "--max-bytes", type=_positive_int, default=None, help=f"Local mode: input size cap ({limits.max_bytes})"
    )
    p.add_argument(
        "--max-seconds",
        type=_positive_float,
        default=None,
        help=f"Local mode: per-conversion time cap ({limits.max_seconds:g})",
    )
    p.add_argument("--max-pages", type=_positive_int, default=None, help=f"Local mode: page cap ({limits.max_pages})")
    p.add_argument(
        "--max-duration-seconds",
        type=_positive_float,
        default=None,
        help=f"Local mode: audio/video duration cap ({limits.max_duration_seconds:g})",
    )
    p.add_argument("--log-level", default="WARNING", help="stderr log level (default WARNING)")
    p.add_argument("--version", action="version", version=f"ezmd-mcp {__version__}")
    return p.parse_args(argv)


@dataclass(frozen=True, slots=True)
class HttpConfig:
    host: str
    port: int
    token: str | None
    generated: bool


class StartupError(Exception):
    pass


def resolve_http(args: argparse.Namespace, env: Mapping[str, str] | None = None) -> HttpConfig:
    """Bind loopback unless --host or EZMD_MCP_BIND says otherwise; a token is required by default, and a
    non-loopback bind without an explicit token refuses to start (docs/spec/part4.md 4.4.3, part1 8.4)."""
    env = os.environ if env is None else env
    host = args.host or env.get("EZMD_MCP_BIND") or "127.0.0.1"
    try:
        port = args.port if args.port is not None else int(env.get("EZMD_MCP_PORT", str(DEFAULT_PORT)))
    except ValueError:
        raise StartupError("EZMD_MCP_PORT must be an integer.") from None
    token = args.token or env.get("EZMD_MCP_TOKEN") or None
    loopback = is_loopback(host)
    if not loopback and not token:
        raise StartupError(
            f"refusing to bind non-loopback host {host!r} without a bearer token; pass --token or set EZMD_MCP_TOKEN"
        )
    if args.no_auth:
        if not loopback:
            raise StartupError("--no-auth is only allowed on a loopback host")
        return HttpConfig(host, port, None, False)
    if token:
        if len(token) < 16:
            raise StartupError("the bearer token must be at least 16 characters")
        return HttpConfig(host, port, token, False)
    return HttpConfig(host, port, secrets.token_urlsafe(32), True)


def _backend(settings: Settings) -> Backend:
    if settings.remote:
        from ezmd_mcp.remote import RemoteBackend

        return RemoteBackend(settings.remote, api_key=settings.api_key, wait_seconds=settings.wait_seconds)
    from ezmd_mcp.local import LocalBackend

    return LocalBackend(allow_private_networks=settings.allow_private_networks, limits=settings.limits)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(level=args.log_level.upper(), stream=sys.stderr, format="ezmd-mcp %(levelname)s %(message)s")
    try:
        settings = Settings.from_env(
            profile=args.profile,
            remote=args.remote,
            api_key=args.api_key,
            allowed_dirs=args.allowed_dirs,
            wait_seconds=args.wait_seconds,
            allow_private_networks=args.allow_private_networks,
            max_bytes=args.max_bytes,
            max_seconds=args.max_seconds,
            max_pages=args.max_pages,
            max_duration_seconds=args.max_duration_seconds,
        )
        if settings.profile not in PROFILES:
            raise StartupError(f"unknown profile {settings.profile!r}; expected one of {', '.join(PROFILES)}")
        if settings.remote and not settings.remote.startswith(("http://", "https://")):
            raise StartupError("--remote must be an http(s) URL")
        http = resolve_http(args) if args.transport == "http" else None
    except StartupError as e:
        print(f"ezmd-mcp: error: {e}", file=sys.stderr)
        return 2

    from ezmd_mcp.server import build_server

    server = build_server(settings, _backend(settings))
    if http is None:
        server.run("stdio")
        return 0

    import uvicorn

    from ezmd_mcp.http import build_http_app

    if http.generated:
        print(f"ezmd-mcp: generated bearer token (set EZMD_MCP_TOKEN to fix it): {http.token}", file=sys.stderr)
    print(f"ezmd-mcp: streamable HTTP on http://{http.host}:{http.port}/mcp", file=sys.stderr)
    app = build_http_app(server, token=http.token, host=http.host)
    uvicorn.run(app, host=http.host, port=http.port, log_level=args.log_level.lower(), server_header=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
