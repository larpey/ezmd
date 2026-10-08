"""Apply an Excel number format to a cached numeric value, the way the spreadsheet displays it.

Covers the formats users actually see: fixed decimals (`0.00`), thousands separators (`#,##0`), currency
symbols as literals or `[$€-407]` tokens, quoted and escaped literals, `_x` padding, `*x` fill, colour and
condition brackets (dropped), a negative section (`#,##0.00;(#,##0.00)`), percent, and scientific (`0.00E+00`).
Fractions and anything unparsed return None so the caller keeps the raw number. The raw value is always kept
separately in `TableCell.raw_value`.
"""

from __future__ import annotations

from dataclasses import dataclass

_PLACEHOLDERS = "0#?,."


@dataclass(slots=True)
class _Section:
    prefix: str
    suffix: str
    pattern: str
    percent: bool
    scientific: str | None


def _sections(fmt: str) -> list[str]:
    out: list[str] = []
    cur = ""
    quoted = False
    i = 0
    while i < len(fmt):
        ch = fmt[i]
        if ch == '"':
            quoted = not quoted
        elif ch == chr(92) and not quoted and i + 1 < len(fmt):
            cur += ch + fmt[i + 1]
            i += 2
            continue
        elif ch == ";" and not quoted:
            out.append(cur)
            cur = ""
            i += 1
            continue
        cur += ch
        i += 1
    out.append(cur)
    return out


def _parse(section: str) -> _Section | None:
    prefix, suffix, pattern = "", "", ""
    percent = False
    scientific: str | None = None
    seen_pattern = False
    i = 0
    n = len(section)

    def emit(text: str) -> None:
        nonlocal prefix, suffix
        if seen_pattern:
            suffix += text
        else:
            prefix += text

    while i < n:
        ch = section[i]
        if ch == '"':
            end = section.find('"', i + 1)
            if end < 0:
                return None
            emit(section[i + 1 : end])
            i = end + 1
        elif ch == chr(92):
            emit(section[i + 1 : i + 2])
            i += 2
        elif ch == "_":
            emit(" ")
            i += 2
        elif ch == "*":
            i += 2
        elif ch == "[":
            end = section.find("]", i)
            if end < 0:
                return None
            token = section[i + 1 : end]
            if token.startswith("$"):
                emit(token[1:].split("-", 1)[0])
            i = end + 1
        elif ch in _PLACEHOLDERS and (not seen_pattern or not suffix):
            if ch == "?" or (ch == "/" and pattern):
                return None
            pattern += ch
            seen_pattern = seen_pattern or ch in "0#"
            i += 1
        elif ch in "Ee" and pattern and i + 1 < n and section[i + 1] in "+-":
            j = i + 2
            while j < n and section[j] in "0#":
                j += 1
            scientific = section[i + 1 : j]
            i = j
        elif ch == "%":
            percent = True
            emit("%")
            i += 1
        elif ch in "/?":
            return None
        elif ch.isalpha() and ch.lower() in "ymdhs":
            return None  # date/time tokens: openpyxl already returns datetimes for those
        else:
            emit(ch)
            i += 1
    if pattern and not seen_pattern:
        return None
    return _Section(prefix=prefix, suffix=suffix, pattern=pattern, percent=percent, scientific=scientific)


def _digits(value: float, pattern: str) -> str:
    int_part, _, dec_part = pattern.partition(".")
    scale = 0
    while int_part.endswith(","):
        int_part = int_part[:-1]
        scale += 1
    value = value / (1000**scale)
    thousands = "," in int_part
    max_dec = sum(1 for ch in dec_part if ch in "0#")
    min_dec = sum(1 for ch in dec_part if ch == "0")
    min_int = sum(1 for ch in int_part if ch == "0")
    text = f"{value:,.{max_dec}f}" if thousands else f"{value:.{max_dec}f}"
    if max_dec > min_dec and "." in text:
        head, tail = text.split(".")
        tail = tail.rstrip("0")
        tail = tail + "0" * max(0, min_dec - len(tail))
        text = head + ("." + tail if tail else "")
    head, dot, tail = text.partition(".")
    if min_int == 0 and head == "0":
        head = ""
    elif len(head.replace(",", "")) < min_int:
        head = head.zfill(min_int)
    return head + dot + tail


def format_number(value: float, fmt: str) -> str | None:
    """Displayed text for `value` under Excel format `fmt`, or None when the format is not understood."""
    if not fmt or fmt.lower() in ("general", "@"):
        return None
    sections = _sections(fmt)
    negative = value < 0
    if negative and len(sections) > 1 and sections[1].strip():
        sec = _parse(sections[1])
        value = -value
        sign = ""
    elif value == 0 and len(sections) > 2 and sections[2].strip():
        sec = _parse(sections[2])
        sign = ""
    else:
        sec = _parse(sections[0])
        sign = "-" if negative else ""
        value = abs(value)
    if sec is None:
        return None
    if sec.percent:
        value *= 100
    if not sec.pattern:
        return (sec.prefix + sec.suffix).strip() or None
    if sec.scientific is not None:
        dec = sec.pattern.partition(".")[2]
        mantissa_dec = sum(1 for ch in dec if ch in "0#")
        text = f"{value:.{mantissa_dec}E}"
        mant, _, exp = text.partition("E")
        exp_n = int(exp)
        width = max(1, len(sec.scientific) - 1)
        exp_text = ("+" if exp_n >= 0 else "-") if sec.scientific[0] == "+" else ("-" if exp_n < 0 else "")
        body = f"{mant}E{exp_text}{abs(exp_n):0{width}d}"
    else:
        body = _digits(value, sec.pattern)
    if not body:
        body = "0"
    return f"{sign}{sec.prefix}{body}{sec.suffix}".strip()
