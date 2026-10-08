"""Static checks on the operator scripts in deploy/ (P1-T14). The end-to-end run (bootstrap, backup,
wipe, restore, upgrade with rollback) needs Docker and is recorded in docs/decisions/P1-T14-T16.md."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[3]
DEPLOY = REPO / "deploy"
BASH_SCRIPTS = ["bootstrap.sh", "backup.sh", "restore.sh", "upgrade.sh", "smoke.sh"]
SCRIPTS = [*BASH_SCRIPTS, "egress-allowlist.sh"]  # the entrypoint is POSIX sh (set -eu)
OPERATOR = ["bootstrap.sh", "backup.sh", "restore.sh", "upgrade.sh"]


def _git_mode(path: Path) -> str | None:
    git = shutil.which("git")
    if git is None:
        return None
    out = subprocess.run(
        [git, "ls-files", "--stage", "--", path.relative_to(REPO).as_posix()],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    ).stdout.split()
    return out[0] if out else None


@pytest.mark.parametrize("name", BASH_SCRIPTS)
def test_scripts_are_strict_bash(name: str) -> None:
    text = (DEPLOY / name).read_text(encoding="utf-8")
    assert text.startswith("#!/usr/bin/env bash\n"), name
    assert "\nset -euo pipefail\n" in text, name
    assert "\r" not in text, f"{name} has CRLF line endings"


@pytest.mark.parametrize("name", SCRIPTS)
def test_scripts_are_executable_in_git(name: str) -> None:
    mode = _git_mode(DEPLOY / name)
    if mode is None:
        pytest.skip("not tracked yet or git unavailable")
    assert mode == "100755", f"{name} is {mode}; run git update-index --chmod=+x"


@pytest.mark.parametrize("name", [*OPERATOR, "smoke.sh"])
def test_scripts_share_lib(name: str) -> None:
    text = (DEPLOY / name).read_text(encoding="utf-8")
    assert '. "$(dirname "$0")/lib.sh"' in text
    raw = [
        ln
        for ln in text.splitlines()
        if ln.lstrip().startswith(("docker compose", '"${COMPOSE[@]}" =', "COMPOSE=(docker"))
    ]
    assert raw == [], f"{name}: call the compose() helper so the env file and project files apply: {raw}"


def test_bootstrap_never_rotates_secrets() -> None:
    text = (DEPLOY / "bootstrap.sh").read_text(encoding="utf-8")
    for key in ("EZMD_KEY_PEPPER", "EZMD_JWT_SECRET", "EZMD_REDIS_PASSWORD", "EZMD_METRICS_TOKEN"):
        assert f"ensure_secret {key} " in text, key
    assert 'if [ -z "$(env_get "$key")" ]' in text
    assert "keys create --store file" in text and "stackctl has-keys" in text


def test_upgrade_backs_up_first_and_rolls_back() -> None:
    text = (DEPLOY / "upgrade.sh").read_text(encoding="utf-8")
    assert text.index("backup.sh") < text.index('env_set EZMD_VERSION "$NEW"')
    assert "rollback()" in text and "restore.sh" in text
    assert "--no-build" in text, "upgrade must never fall back to building from source"


def test_restore_verifies_before_stopping() -> None:
    text = (DEPLOY / "restore.sh").read_text(encoding="utf-8")
    assert text.index("sha256sum -c") < text.index("compose stop")
    assert text.index("stackctl verify") < text.index("compose stop")


def test_backup_contents_and_retention() -> None:
    text = (DEPLOY / "backup.sh").read_text(encoding="utf-8")
    for part in ("app.tar", "caddy_data.tar", "SHA256SUMS", "EZMD_BACKUP_KEEP", "chmod 700", "chmod 600"):
        assert part in text, part


def test_deploy_only_env_vars_documented() -> None:
    text = (DEPLOY / "env.example").read_text(encoding="utf-8")
    section = text.split("# ---- Deployment", 1)[1]
    for var in ("EZMD_BACKUP_DIR", "EZMD_BACKUP_KEEP"):
        assert f"\n{var}=" in section, var


@pytest.mark.skipif(shutil.which("shellcheck") is None, reason="shellcheck not installed (CI and docker run it)")
def test_shellcheck_clean() -> None:
    result = subprocess.run(
        [str(shutil.which("shellcheck")), "-x", "-P", str(DEPLOY), *(str(DEPLOY / s) for s in [*SCRIPTS, "lib.sh"])],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_compose_core_profile_shape() -> None:
    data = yaml.safe_load((DEPLOY / "docker-compose.yml").read_text(encoding="utf-8"))
    services = data["services"]
    assert {"caddy", "api", "worker-default", "worker-fetch", "redis", "purge"} <= set(services)
    assert data["networks"]["internal"]["internal"] is True
    for name, svc in services.items():
        if svc.get("profiles"):
            continue
        assert svc.get("read_only") is True, name
        assert svc.get("cap_drop") == ["ALL"], name
        assert "no-new-privileges:true" in svc.get("security_opt", []), name
        assert "ports" not in svc or name == "caddy", f"{name} must not publish host ports"
    for name in ("api", "worker-default", "worker-fetch", "purge"):
        svc = services[name]
        assert svc["user"] == "10001:10001", name
        assert svc["environment"]["EZMD_BLOB_FS_ROOT"] == "/var/lib/ezmd-blobs", name
        assert svc["environment"]["EZMD_WEB_DIST"] == "${EZMD_WEB_DIST:-/app/apps/web/dist}", name
        assert svc["env_file"][0]["path"] == "${EZMD_ENV_FILE:-.env}", name
        assert "egress" not in svc["networks"] or name == "worker-fetch", f"{name} must not have egress"
