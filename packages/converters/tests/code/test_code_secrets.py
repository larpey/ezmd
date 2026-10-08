from __future__ import annotations

import pytest

from ezmd_converters.code.common import secret_warning
from ezmd_converters.code.secrets import is_secret_file, redact

# Provider-format values are assembled at runtime so no committed file contains a token-shaped string.
AWS_ID = "AK" + "IA" + "Q3EXAMPLE7VALUE9Z"[:16]
GH_TOKEN = "gh" + "p_" + "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8"
SLACK = "xo" + "xb-" + "1234567890-0987654321-AbCdEfGhIjKl"
STRIPE = "sk" + "_live_" + "4eC39HqLyjWDarjtT1zdp7dcAbCd"
JWT = "ey" + "JhbGciOiJIUzI1NiJ9" + ".ey" + "JzdWIiOiIxMjM0NTY3ODkwIn0" + "." + "dozjgNryP4J3jVmNHl0w5N_XgL0n3"


@pytest.mark.parametrize(
    ("text", "rule", "secret"),
    [
        (f"key = {AWS_ID}", "aws_access_key_id", AWS_ID),
        (f"token: {GH_TOKEN}", "github_token", GH_TOKEN),
        (f"SLACK={SLACK}", "slack_token", SLACK),
        (f"stripe.api_key = '{STRIPE}'", "stripe_key", STRIPE),
        (f"auth = {JWT}", "jwt", JWT),
        ('API_SECRET_KEY = "9f8e7d6c5b4a39281706f5e4d3c2b1a0"', "generic_secret", "9f8e7d6c5b4a39281706f5e4d3c2b1a0"),
        ("SERVICE_TOKEN = ff92775fbcbc69fb116ec46bcb2846a2", "generic_secret", "ff92775fbcbc69fb116ec46bcb2846a2"),
        ('"db_password": "Xk2!pQ9#mZ4wL7"', "generic_secret", "Xk2!pQ9#mZ4wL7"),
        ("postgres://app:S3cr3tPassw0rd@db/app", "basic_auth_url", "S3cr3tPassw0rd"),
        ("Authorization: Bearer abcdefghijklmnop1234567890", "authorization_header", "abcdefghijklmnop1234567890"),
    ],
)
def test_rules_redact_and_count(text: str, rule: str, secret: str) -> None:
    out, found = redact(text, "f.py")
    assert secret not in out
    assert f"[REDACTED:{rule}]" in out
    assert found.by_rule[rule] >= 1
    w = secret_warning(found)
    assert w is not None and secret not in w.message and all(secret not in str(v) for v in w.detail.values())


def test_private_key_block_redacted_whole() -> None:
    body = "MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQC7"
    pem = "-----BEGIN RSA PRIVATE KEY-----\n" + body + "\n" + body + "\n-----END RSA PRIVATE KEY-----"
    out, found = redact(f"x = '''\n{pem}\n'''\n", "k.py")
    assert body not in out and "[REDACTED:private_key]" in out and found.by_rule["private_key"] == 1
    assert found.locations == [("k.py", 2, "private_key")]


def test_unterminated_private_key_is_still_redacted() -> None:
    out, _ = redact("-----BEGIN OPENSSH PRIVATE KEY-----\nb3BlbnNzaC1rZXktdjEAAAAABG5vbmU\n", "id")
    assert "b3BlbnNzaC1rZXktdjEAAAAABG5vbmU" not in out


@pytest.mark.parametrize(
    "text",
    [
        'DATABASE_PASSWORD = "changeme"',
        "MAX_TOKENS = 4096",
        'token = os.environ["TOKEN"]',
        "self.token = get_token()",
        "secret_key = settings.SECRET_KEY_V2",
        'api_key = "${API_KEY}"',
        "password: hunter2",
        "token_budget = 200000",
    ],
)
def test_non_secrets_are_left_alone(text: str) -> None:
    out, found = redact(text)
    assert out == text and found.total == 0


def test_redaction_is_idempotent() -> None:
    once, _ = redact('API_TOKEN = "9f8e7d6c5b4a39281706f5e4d3c2b1a0"')
    twice, found = redact(once)
    assert twice == once and found.total == 0


@pytest.mark.parametrize(
    ("path", "head", "expected"),
    [
        (".env", "", True),
        ("config/.env.production", "", True),
        ("prod.env", "", True),
        ("certs/server.pem", "", True),
        ("keys/id_rsa", "", True),
        ("keys/id_ed25519", "", True),
        ("keys/id_ed25519.pub", "", False),
        ("store.p12", "", True),
        ("credentials.json", "", True),
        (".netrc", "", True),
        (".npmrc", "//registry.npmjs.org/:_authToken=abc", True),
        (".npmrc", "registry=https://registry.npmjs.org/", False),
        ("src/env.py", "", False),
        ("README.md", "", False),
    ],
)
def test_secret_file_names(path: str, head: str, expected: bool) -> None:
    assert is_secret_file(path, head) is expected


def test_multiline_redaction_keeps_source_line_numbers() -> None:
    body = "MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQC7"
    pem = "-----BEGIN PRIVATE KEY-----\n" + body + "\n" + body + "\n-----END PRIVATE KEY-----"
    src = f"a = 1\nK = '''\n{pem}\n'''\nurl = 'postgres://u:S3cr3tPassw0rd@db/app'\n"
    out, found = redact(src, "s.py")
    assert out.count("\n") == src.count("\n")
    assert sorted(found.locations) == [("s.py", 3, "private_key"), ("s.py", 8, "basic_auth_url")]
    assert out.split("\n")[7].startswith("url = 'postgres://u:[REDACTED:basic_auth_url]@db")
