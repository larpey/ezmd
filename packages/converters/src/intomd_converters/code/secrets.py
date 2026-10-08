"""Secret scanning and redaction (docs/spec/part2.md 8b step 4, 8c step 8).

Secretlint/detect-secrets style rules implemented natively with `re` so the scan has no extra dependency:
provider token formats (AWS, GitHub, Slack, Stripe, JWT), PEM private key blocks, and generic assignments to
`*_KEY` / `*_SECRET` / `*_TOKEN` / `password` names whose value has high Shannon entropy. Matches are replaced
in place with `[REDACTED:<rule>]`. Reports carry rule names, files, and line numbers, never the secret.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import PurePosixPath

__all__ = ["RULES", "Redactions", "is_secret_file", "redact", "redaction_marker"]


def redaction_marker(rule: str) -> str:
    return f"[REDACTED:{rule}]"


@dataclass(slots=True)
class Redactions:
    """What a scan redacted: counts by rule and (path, line, rule) locations."""

    by_rule: Counter[str] = field(default_factory=Counter)
    locations: list[tuple[str, int, str]] = field(default_factory=list)

    @property
    def total(self) -> int:
        return sum(self.by_rule.values())

    def merge(self, other: Redactions) -> None:
        self.by_rule.update(other.by_rule)
        self.locations.extend(other.locations)


@dataclass(frozen=True, slots=True)
class Rule:
    name: str
    pattern: re.Pattern[str]
    group: str | None = None
    """Named group holding the secret; None redacts the whole match."""
    accept: Callable[[str], bool] | None = None
    """Extra check on the secret text (entropy, placeholder filter)."""


def shannon_entropy(value: str) -> float:
    if not value:
        return 0.0
    counts = Counter(value)
    n = len(value)
    return -sum(c / n * math.log2(c / n) for c in counts.values())


_PLACEHOLDER = re.compile(
    r"^(?:x+|\*+|\.+|changeme|change_me|password|secret|token|example|dummy|test|placeholder|none|null|"
    r"redacted|your[_-].*|<.*>|\$\{.*\}|\{\{.*\}\}|%\(.*\)s)$",
    re.IGNORECASE,
)


def _high_entropy_quoted(value: str) -> bool:
    return not _PLACEHOLDER.match(value) and shannon_entropy(value) >= 3.0


_DOTTED_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+$")


def _high_entropy_bare(value: str) -> bool:
    """Unquoted values must mix letters and digits, not be a dotted name (`settings.KEY_V2`), and not be a
    placeholder."""
    has_digit = any(ch.isdigit() for ch in value)
    has_alpha = any(ch.isalpha() for ch in value)
    if not (has_digit and has_alpha) or _DOTTED_NAME.match(value) or _PLACEHOLDER.match(value):
        return False
    return shannon_entropy(value) >= 3.0


_NAME = r"[A-Za-z0-9_.-]*?(?:api[_-]?key|[_-]key|secret|token|password|passwd|pwd)"
_ASSIGN = r"""["']?\s*(?::=|=>|[:=])\s*"""

RULES: tuple[Rule, ...] = (
    Rule(
        "private_key",
        re.compile(
            r"-----BEGIN (?:[A-Z0-9]+ )*PRIVATE KEY(?: BLOCK)?-----"
            r"(?:.*?-----END (?:[A-Z0-9]+ )*PRIVATE KEY(?: BLOCK)?-----|(?:\n[A-Za-z0-9+/=:\- ]*)*)",
            re.DOTALL,
        ),
    ),
    Rule("aws_access_key_id", re.compile(r"\b(?:AKIA|ASIA|ABIA|ACCA)[0-9A-Z]{16}\b")),
    Rule(
        "aws_secret_access_key",
        re.compile(r"(?i)aws_?secret_?access_?key[\"']?\s*[:=]\s*[\"']?(?P<v>[A-Za-z0-9/+=]{40})\b"),
        group="v",
    ),
    Rule("github_token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{36,255}|github_pat_[A-Za-z0-9_]{22,255})\b")),
    Rule("slack_token", re.compile(r"\bxox[abposr]-[A-Za-z0-9-]{10,250}")),
    Rule(
        "slack_webhook",
        re.compile(r"https://hooks\.slack\.com/services/T[A-Za-z0-9_]+/B[A-Za-z0-9_]+/[A-Za-z0-9_]+"),
    ),
    Rule("stripe_key", re.compile(r"\b[rs]k_live_[0-9A-Za-z]{24,99}\b")),
    Rule("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")),
    Rule(
        "basic_auth_url",
        re.compile(r"\b[a-z][a-z0-9+.-]*://[^\s:/@]+:(?P<v>[^\s:/@]{6,})@[^\s/]+"),
        group="v",
        accept=lambda v: not _PLACEHOLDER.match(v),
    ),
    Rule(
        "authorization_header",
        re.compile(r"(?i)\bauthorization\s*[:=]\s*[\"']?(?:bearer|token|basic)\s+(?P<v>[A-Za-z0-9._~+/=-]{16,})"),
        group="v",
    ),
    Rule(
        "generic_secret",
        re.compile(rf"(?i)\b{_NAME}\b{_ASSIGN}(?P<q>[\"'`])(?P<v>[^\"'`\s]{{8,256}})(?P=q)"),
        group="v",
        accept=_high_entropy_quoted,
    ),
    Rule(
        "generic_secret",
        re.compile(rf"(?i)\b{_NAME}\b{_ASSIGN}(?P<v>[A-Za-z0-9+/=_\-.!@#$%^&*~]{{12,256}})(?![A-Za-z0-9(\[])"),
        group="v",
        accept=_high_entropy_bare,
    ),
)


def redact(text: str, path: str = "", rules: tuple[Rule, ...] = RULES) -> tuple[str, Redactions]:
    """Return `text` with every rule match replaced by its marker, plus what was redacted."""
    found = Redactions()
    for rule in rules:
        if not _cheap_hint(rule, text):
            continue
        text = _apply(rule, text, path, found)
    return text, found


def _cheap_hint(rule: Rule, text: str) -> bool:
    """Quick prefilter: skip a rule's regex when its anchor substring cannot occur."""
    hints = {
        "private_key": "PRIVATE KEY",
        "aws_access_key_id": "A",
        "github_token": "_",
        "slack_token": "xox",
        "slack_webhook": "hooks.slack.com",
        "stripe_key": "_live_",
        "jwt": "eyJ",
        "basic_auth_url": "@",
        "authorization_header": "uthorization",
        "generic_secret": "=",
    }
    hint = hints.get(rule.name)
    return hint is None or hint in text or (rule.name == "generic_secret" and ":" in text)


def _apply(rule: Rule, text: str, path: str, found: Redactions) -> str:
    out: list[str] = []
    pos = 0
    for m in rule.pattern.finditer(text):
        start, end = m.span(rule.group) if rule.group else m.span()
        if start < pos or start < 0:
            continue
        secret = text[start:end]
        if secret.startswith("[REDACTED:") or (rule.accept is not None and not rule.accept(secret)):
            continue
        out.append(text[pos:start])
        # Keep the secret's line breaks so every later line keeps its source line number (provenance and
        # reported locations stay in source numbering even when a multi-line PEM block is collapsed).
        out.append(redaction_marker(rule.name) + chr(10) * secret.count(chr(10)))
        found.by_rule[rule.name] += 1
        found.locations.append((path, text.count("\n", 0, start) + 1, rule.name))
        pos = end
    if pos == 0:
        return text
    out.append(text[pos:])
    return "".join(out)


_SECRET_SUFFIXES = (".pem", ".key", ".p12", ".pfx", ".jks", ".keystore", ".kdbx", ".asc", ".gpg", ".ppk")
_SECRET_NAMES = frozenset(
    {"credentials.json", "credentials", ".netrc", "_netrc", ".pgpass", ".htpasswd", ".pypirc", "secrets.yml"}
)
_SSH_KEY = re.compile(r"^id_(?:rsa|dsa|ecdsa|ed25519)(?:_sk)?$")


def is_secret_file(path: str, head: str = "") -> bool:
    """Files named like credentials (`.env*`, `*.pem`, `*.key`, `id_rsa*`, `*.p12`, `credentials.json`, `.netrc`,
    `.npmrc` carrying an auth token) are excluded from packs entirely (8b step 4)."""
    name = PurePosixPath(path.replace("\\", "/")).name.lower()
    if name == ".env" or name.startswith(".env.") or name.endswith(".env"):
        return True
    if name in _SECRET_NAMES or _SSH_KEY.match(name) or name.endswith(_SECRET_SUFFIXES):
        return True
    if name in (".npmrc", ".yarnrc", ".yarnrc.yml"):
        return "_auth" in head or "npmAuthToken" in head
    return False
