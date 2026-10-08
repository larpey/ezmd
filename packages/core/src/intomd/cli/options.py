"""Parsing of `--opt key=value` pairs into ConvertOptions fields and profile overrides."""

from __future__ import annotations

import dataclasses

from intomd.registry import ConvertOptions, ExtraValue

_OPTION_FIELDS = {
    f.name: f for f in dataclasses.fields(ConvertOptions) if not f.name.startswith("_") and f.name != "ctx"
}


def _coerce(raw: str) -> ExtraValue:
    low = raw.lower()
    if low in ("true", "yes", "on"):
        return True
    if low in ("false", "no", "off"):
        return False
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        return raw


def parse_opts(pairs: list[str]) -> dict[str, ExtraValue]:
    out: dict[str, ExtraValue] = {}
    for p in pairs:
        if "=" not in p:
            raise ValueError(f"--opt expects key=value, got {p!r}")
        k, v = p.split("=", 1)
        k = k.strip()
        if not k:
            raise ValueError(f"--opt has an empty key: {p!r}")
        out[k] = _coerce(v.strip())
    return out


def split_options(opts: dict[str, ExtraValue]) -> tuple[ConvertOptions, dict[str, object]]:
    """Known ConvertOptions fields go to ConvertOptions; `extra.<k>` goes to options.extra; every other
    key is treated as a profile override (validated later by the renderer)."""
    kwargs: dict[str, object] = {}
    extra: dict[str, ExtraValue] = {}
    profile: dict[str, object] = {}
    for k, v in opts.items():
        if k.startswith("extra."):
            extra[k[6:]] = v
        elif k in _OPTION_FIELDS and k != "extra":
            if k == "languages":
                kwargs[k] = [s for s in str(v).split(",") if s]
            else:
                kwargs[k] = v
        else:
            profile[k] = v
    options = ConvertOptions(**kwargs, extra=extra)  # type: ignore[arg-type]
    return options, profile
