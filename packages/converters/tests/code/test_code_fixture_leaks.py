"""Independent leak check over the committed code goldens (docs/spec/part2.md 8e item 1): every planted fake
secret from fixtures/code/_generate.py must be absent from expected outputs, and the redaction markers present."""

from __future__ import annotations

import base64
import hashlib
import importlib.util
import re
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[4] / "fixtures" / "code"


def _gen() -> ModuleType:
    spec = importlib.util.spec_from_file_location("code_fixture_gen", ROOT / "_generate.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _planted(gen: ModuleType) -> list[str]:
    hexes = [
        gen.fake_hex("api-secret"),
        gen.fake_hex("service-token", 32),
        gen.fake_hex("db-password", 20),
        gen.fake_hex("creds-token", 36),
        gen.fake_hex("env-db", 24),
        gen.fake_hex("ignored"),
        base64.b64encode(hashlib.sha256(b"aws-fixture").digest()).decode()[:40],
    ]
    pem_lines = gen.fake_pem("settings").split(chr(10)) + gen.fake_pem("repo").split(chr(10))
    return hexes + [ln for ln in pem_lines if "PRIVATE KEY" not in ln]


def _goldens() -> list[Path]:
    return sorted(p for p in ROOT.glob("*/expected.*") if p.is_file())


@pytest.mark.skipif(not ROOT.exists(), reason="fixtures not present")
def test_no_planted_secret_in_any_golden() -> None:
    planted = _planted(_gen())
    goldens = _goldens()
    assert goldens
    for path in goldens:
        text = path.read_text(encoding="utf-8")
        for secret in planted:
            assert secret not in text, f"{path} leaks a planted secret"
        assert not re.search(r"-----BEGIN [A-Z ]*PRIVATE KEY-----", text), path


@pytest.mark.skipif(not ROOT.exists(), reason="fixtures not present")
def test_redaction_markers_present() -> None:
    planted_md = (ROOT / "source-planted-secret" / "expected.full.md").read_text(encoding="utf-8")
    for marker in ("[REDACTED:generic_secret]", "[REDACTED:private_key]", "[REDACTED:basic_auth_url]"):
        assert marker in planted_md
    assert '"changeme"' in planted_md
    repo_md = (ROOT / "repo-small" / "expected.full.md").read_text(encoding="utf-8")
    assert "[REDACTED:aws_secret_access_key]" in repo_md and ".env (excluded: secret file)" in repo_md
