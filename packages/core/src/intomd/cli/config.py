"""CLI configuration: the config file (docs/spec/part4.md 4.2.1), environment overrides, and precedence.

Precedence, highest first: command-line flags, environment variables (`INTOMD_PROFILE`, `INTOMD_FORMAT`,
`INTOMD_REMOTE`, `INTOMD_API_KEY`, `INTOMD_SIDECAR`), the config file, built-in defaults. The file lives at
`INTOMD_CONFIG` when set, else `%APPDATA%/intomd/config.toml` on Windows,
`~/Library/Application Support/intomd/config.toml` on macOS, and `$XDG_CONFIG_HOME/intomd/config.toml`
(default `~/.config/intomd/config.toml`) elsewhere. A missing default file is fine; a missing
`INTOMD_CONFIG` file, invalid TOML, or a value of the wrong type is a usage error (exit 2).
"""

from __future__ import annotations

import os
import sys
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

__all__ = ["PROFILES", "Config", "ConfigError", "config_path", "load_config"]

PROFILES = ("full", "compact", "rag", "agent")
FORMATS = ("md", "txt", "json", "docx", "srt")
SUPPORTED_FORMATS = ("md", "txt", "json")
_TRUE = ("1", "true", "yes", "on")
_FALSE = ("0", "false", "no", "off")

# section -> key -> accepted python types (bool is checked before int because bool subclasses int)
_SCHEMA: dict[str, dict[str, tuple[type, ...]]] = {
    "defaults": {"profile": (str,), "format": (str,), "out_dir": (str,), "sidecar": (bool,)},
    "remote": {"url": (str,), "api_key": (str,)},
    "engines": {},  # free-form family = engine name strings
    "fetch": {"cookies_file": (str,), "proxy": (str,), "yt_dlp_extra_args": (list,)},
    "limits": {"max_file_mb": (int, float), "max_duration_s": (int, float)},
    "watch": {"debounce_ms": (int,), "delete_source": (bool,)},
}


class ConfigError(ValueError):
    """The config file or an environment override is invalid."""


@dataclass(frozen=True, slots=True)
class Config:
    """Effective configuration after merging the file and the environment (flags are applied later)."""

    path: Path | None = None
    """The config file that was read, or None when there was none."""
    profile: str | None = None
    """None means automatic: `compact` for an interactive terminal, `full` for file or piped output."""
    format: str = "md"
    out_dir: str | None = None
    sidecar: bool = True
    remote_url: str = ""
    api_key: str = ""
    engines: dict[str, str] = field(default_factory=dict)
    max_file_mb: float | None = None
    max_duration_s: float | None = None
    unknown_keys: tuple[str, ...] = ()
    """Keys present in the file that this version does not know (reported, not fatal)."""


def config_path(env: Mapping[str, str] | None = None, platform: str | None = None) -> Path:
    """Where the config file is looked for (it may not exist)."""
    env = os.environ if env is None else env
    plat = platform or sys.platform
    override = env.get("INTOMD_CONFIG")
    if override:
        return Path(override).expanduser()
    home = Path(env.get("HOME") or env.get("USERPROFILE") or Path.home())
    if plat == "win32":
        base = Path(env["APPDATA"]) if env.get("APPDATA") else home / "AppData" / "Roaming"
    elif plat == "darwin":
        base = home / "Library" / "Application Support"
    else:
        base = Path(env["XDG_CONFIG_HOME"]) if env.get("XDG_CONFIG_HOME") else home / ".config"
    return base / "intomd" / "config.toml"


def _read_file(path: Path) -> dict[str, object]:
    try:
        with path.open("rb") as f:
            return tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"invalid TOML in {path}: {e}") from e
    except OSError as e:
        raise ConfigError(f"cannot read config file {path}: {e.strerror or e}") from e


def _validate(data: dict[str, object], path: Path) -> list[str]:
    unknown: list[str] = []
    for section, body in data.items():
        if section not in _SCHEMA:
            unknown.append(section)
            continue
        if not isinstance(body, dict):
            raise ConfigError(f"{path}: [{section}] must be a table")
        keys = _SCHEMA[section]
        for key, value in body.items():
            if section == "engines":
                if not isinstance(value, str):
                    raise ConfigError(f"{path}: engines.{key} must be a string")
                continue
            if key not in keys:
                unknown.append(f"{section}.{key}")
                continue
            types = keys[key]
            ok = isinstance(value, types) and not (isinstance(value, bool) and bool not in types)
            if not ok:
                names = " or ".join(t.__name__ for t in types)
                raise ConfigError(f"{path}: {section}.{key} must be {names}, got {type(value).__name__}")
    return unknown


def _section(data: dict[str, object], name: str) -> dict[str, object]:
    body = data.get(name)
    return body if isinstance(body, dict) else {}


def _env_bool(env: Mapping[str, str], name: str) -> bool | None:
    raw = env.get(name)
    if raw is None or raw == "":
        return None
    low = raw.strip().lower()
    if low in _TRUE:
        return True
    if low in _FALSE:
        return False
    raise ConfigError(f"{name} must be true or false, got {raw!r}")


def check_profile(value: str, origin: str) -> str:
    if value not in PROFILES:
        raise ConfigError(f"{origin}: unknown profile {value!r}; expected one of {', '.join(PROFILES)}")
    return value


def check_format(value: str, origin: str) -> str:
    if value not in FORMATS:
        raise ConfigError(f"{origin}: unknown format {value!r}; expected one of {', '.join(FORMATS)}")
    return value


def load_config(env: Mapping[str, str] | None = None, platform: str | None = None) -> Config:
    """Read the config file (if any) and apply environment overrides."""
    env = os.environ if env is None else env
    path = config_path(env, platform)
    data: dict[str, object] = {}
    found: Path | None = None
    if path.is_file():
        data = _read_file(path)
        found = path
    elif env.get("INTOMD_CONFIG"):
        raise ConfigError(f"INTOMD_CONFIG points at {path}, which does not exist")
    unknown = _validate(data, path) if data else []
    defaults, remote, limits = _section(data, "defaults"), _section(data, "remote"), _section(data, "limits")
    engines = {str(k): str(v) for k, v in _section(data, "engines").items()}

    profile = defaults.get("profile")
    profile = check_profile(str(profile), f"{path} defaults.profile") if profile is not None else None
    fmt = check_format(str(defaults.get("format", "md")), f"{path} defaults.format")
    out_dir = defaults.get("out_dir")
    sidecar = bool(defaults.get("sidecar", True))
    remote_url = str(remote.get("url", ""))
    api_key = str(remote.get("api_key", ""))

    if env.get("INTOMD_PROFILE"):
        profile = check_profile(env["INTOMD_PROFILE"], "INTOMD_PROFILE")
    if env.get("INTOMD_FORMAT"):
        fmt = check_format(env["INTOMD_FORMAT"], "INTOMD_FORMAT")
    if env.get("INTOMD_REMOTE") is not None:
        remote_url = env["INTOMD_REMOTE"]
    if env.get("INTOMD_API_KEY"):
        api_key = env["INTOMD_API_KEY"]
    env_sidecar = _env_bool(env, "INTOMD_SIDECAR")
    if env_sidecar is not None:
        sidecar = env_sidecar

    def _num(key: str) -> float | None:
        v = limits.get(key)
        if v is None:
            return None
        n = float(v) if isinstance(v, (int, float)) else 0.0
        if n <= 0:
            raise ConfigError(f"{path}: limits.{key} must be positive")
        return n

    return Config(
        path=found,
        profile=profile,
        format=fmt,
        out_dir=str(out_dir) if out_dir else None,
        sidecar=sidecar,
        remote_url=remote_url.strip(),
        api_key=api_key.strip(),
        engines=engines,
        max_file_mb=_num("max_file_mb"),
        max_duration_s=_num("max_duration_s"),
        unknown_keys=tuple(unknown),
    )
