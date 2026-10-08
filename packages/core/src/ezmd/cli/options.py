"""Parsing of `--opt key=value` pairs into ConvertOptions fields and profile overrides."""

from __future__ import annotations

import dataclasses

from ezmd.registry import ConvertOptions, ExtraValue

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


def library_options(opts: dict[str, ExtraValue]) -> dict[str, object]:
    """Split parsed `--opt` pairs for `ezmd.Options`: its own field names become fields, `extra.<k>` goes
    to `extra`, and every other key is a profile override in `render` (validated when rendering)."""
    from ezmd.library import Options

    fields = set(Options.model_fields) - {"extra", "render"}
    out: dict[str, object] = {}
    extra: dict[str, ExtraValue] = {}
    render: dict[str, object] = {}
    for k, v in opts.items():
        if k.startswith("extra."):
            extra[k[6:]] = v
        elif k in fields:
            out[k] = [s for s in str(v).split(",") if s] if k == "languages" else v
        else:
            render[k] = v
    if extra:
        out["extra"] = extra
    if render:
        out["render"] = render
    return out


def resolve_engine(spec: str, converters: list[dict[str, object]]) -> str:
    """Map `--engine family=name` to one converter id, or raise ValueError when it is not unambiguous.

    Tried in order, stopping at the first tier with matches: the exact id `name`; the id `family.name`;
    ids whose dotted segments contain `name` and whose family (or a segment) is `family`; ids whose last
    segment is `name`.
    """
    family, sep, name = (s.strip() for s in spec.partition("="))
    if not sep or not family or not name:
        raise ValueError(f"--engine expects family=name, got {spec!r}")
    ids = sorted({str(c.get("id")) for c in converters if c.get("id")})
    fam_of = {str(c.get("id")): str(c.get("family", "")) for c in converters}

    def seg(i: str) -> list[str]:
        return i.split(".")

    tiers = [
        [i for i in ids if i == name],
        [i for i in ids if i == f"{family}.{name}"],
        [i for i in ids if name in seg(i) and (fam_of.get(i) == family or family in seg(i))],
        [i for i in ids if seg(i)[-1] == name],
    ]
    for tier in tiers:
        if len(tier) == 1:
            return tier[0]
        if len(tier) > 1:
            raise ValueError(f"--engine {spec} is ambiguous: {', '.join(tier)}; use --converter <id>")
    raise ValueError(f"--engine {spec}: no converter matches; see `ezmd capabilities`")
