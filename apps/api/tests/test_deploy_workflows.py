"""Structural checks on the release and image workflows (P1-T16): the human publish gate, OIDC-only
publishing, release candidates on PyPI only as pre-releases, and scan/SBOM/sign before any image is tagged."""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import yaml

REPO = Path(__file__).resolve().parents[3]
WORKFLOWS = REPO / ".github" / "workflows"
PUBLISH_JOBS = {"pypi", "npm", "mcp-registry"}
FINAL_ONLY = {"npm", "mcp-registry"}
SHA_PIN = re.compile(r"^[\w.-]+/[\w./-]+@[0-9a-f]{40}$")


def _load(name: str) -> dict[str, Any]:
    data: dict[str, Any] = yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))
    return data


def _on(wf: dict[str, Any]) -> Any:
    return wf.get("on", wf.get(True))  # PyYAML reads the bare key `on` as True


def _steps(job: dict[str, Any]) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = job.get("steps", [])
    return steps


@pytest.fixture(scope="module")
def release() -> dict[str, Any]:
    return _load("release.yml")


@pytest.fixture(scope="module")
def images() -> dict[str, Any]:
    return _load("images.yml")


@pytest.mark.parametrize("name", sorted(p.name for p in WORKFLOWS.glob("*.yml")))
def test_every_action_is_pinned_by_sha(name: str) -> None:
    for job_id, job in _load(name)["jobs"].items():
        for step in _steps(job):
            uses = step.get("uses")
            if uses and not uses.startswith("./"):
                assert SHA_PIN.match(uses), f"{name}:{job_id} uses {uses!r} without a commit SHA"


@pytest.mark.parametrize("name", sorted(p.name for p in WORKFLOWS.glob("*.yml")))
def test_top_level_permissions_are_read_only(name: str) -> None:
    assert _load(name).get("permissions") == {"contents": "read"}


def test_release_triggers_only_on_version_tags(release: dict[str, Any]) -> None:
    assert _on(release) == {"push": {"tags": ["v*"]}}


def test_publish_jobs_are_gated(release: dict[str, Any]) -> None:
    jobs = release["jobs"]
    for name in PUBLISH_JOBS:
        job = jobs[name]
        assert "publish-gate" in job["needs"], name
        assert "needs.publish-gate.outputs.enabled == 'true'" in job["if"], name
        env = job["environment"]["name"]
        assert env == "release", name
        assert job["permissions"].get("id-token") == "write", name


def test_release_candidates_reach_pypi_but_not_npm_or_mcp(release: dict[str, Any]) -> None:
    """Candidates go to PyPI as pre-releases (installers skip them without --pre); npm and the MCP registry
    get final releases only. TestPyPI is not used (D-0038)."""
    jobs = release["jobs"]
    assert "testpypi" not in jobs
    assert "prerelease" not in jobs["pypi"]["if"]
    for name in FINAL_ONLY:
        assert "needs.preflight.outputs.prerelease == 'false'" in jobs[name]["if"], name
    prod_step = next(s for s in _steps(jobs["pypi"]) if "gh-action-pypi-publish" in s.get("uses", ""))
    assert "repository-url" not in prod_step["with"]


def test_publish_gate_requires_reviewers(release: dict[str, Any]) -> None:
    gate = release["jobs"]["publish-gate"]
    script = "".join(s.get("run", "") for s in _steps(gate))
    assert "vars.EZMD_PUBLISH_ENABLED" in str(gate)
    assert "environments/release" in script and "required_reviewers" in script


def test_no_long_lived_publish_tokens(release: dict[str, Any]) -> None:
    for name in ("release.yml", "images.yml"):
        text = (WORKFLOWS / name).read_text(encoding="utf-8")
        assert set(re.findall(r"secrets\.(\w+)", text)) <= {"GITHUB_TOKEN"}, name
        assert "NODE_AUTH_TOKEN" not in text and "api-token" not in text, name


def test_mcp_publisher_is_pinned_and_verified(release: dict[str, Any]) -> None:
    job = release["jobs"]["mcp-registry"]
    assert re.fullmatch(r"v\d+\.\d+\.\d+", job["env"]["MCP_PUBLISHER_VERSION"])
    assert re.fullmatch(r"[0-9a-f]{64}", job["env"]["MCP_PUBLISHER_SHA256"])
    assert "sha256sum -c" in "".join(s.get("run", "") for s in _steps(job))
    assert "pypi" in job["needs"]


def test_release_builds_images_through_the_images_workflow(release: dict[str, Any]) -> None:
    job = release["jobs"]["images"]
    assert job["uses"] == "./.github/workflows/images.yml"
    assert job["permissions"] == {"contents": "read", "packages": "write", "id-token": "write"}


def test_images_scan_sbom_sign_before_tagging(images: dict[str, Any]) -> None:
    assert set(_on(images)) == {"workflow_call"}
    job = images["jobs"]["image"]
    assert set(job["strategy"]["matrix"]["target"]) == {"api", "worker", "fetch-node"}
    steps = _steps(job)

    def index(pred: Any) -> int:
        return next(i for i, s in enumerate(steps) if pred(s))

    build = index(lambda s: "build-push-action" in s.get("uses", ""))
    trivy = index(lambda s: "trivy-action" in s.get("uses", ""))
    sbom = index(lambda s: "sbom-action" in s.get("uses", ""))
    sign = index(lambda s: "cosign sign" in s.get("run", ""))
    tag = index(lambda s: "imagetools create" in s.get("run", ""))
    assert build < trivy < sbom < sign < tag
    assert "push-by-digest=true" in steps[build]["with"]["outputs"]
    assert "tags" not in steps[build]["with"], "tags must only be applied after scan and signing"
    assert steps[trivy]["with"]["exit-code"] == "1"
    assert steps[trivy]["with"]["severity"] == "HIGH,CRITICAL"
    assert steps[sbom]["with"]["format"] == "spdx-json"
    assert "cosign attest" in steps[sign]["run"]
    assert steps[build]["with"]["sbom"] is True


def _release_version() -> ModuleType:
    spec = importlib.util.spec_from_file_location("release_version", REPO / "tools" / "release_version.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    ("tag", "expected"),
    [
        ("v1.2.0", ("1.2.0", "1.2.0", False)),
        ("v0.1.0-rc1", ("0.1.0-rc1", "0.1.0rc1", True)),
        ("v10.0.3-rc12", ("10.0.3-rc12", "10.0.3rc12", True)),
    ],
)
def test_release_tag_parsing(tag: str, expected: tuple[str, str, bool]) -> None:
    assert _release_version().parse_tag(tag) == expected


@pytest.mark.parametrize("tag", ["1.2.0", "v1.2", "v1.2.0-beta1", "v01.2.0", "v1.2.0-rc0", "v1.2.0rc1", "vX"])
def test_release_tag_rejects(tag: str) -> None:
    with pytest.raises(ValueError):
        _release_version().parse_tag(tag)


def test_release_version_checks_packages(tmp_path: Path) -> None:
    mod = _release_version()
    for pkg in mod.PYTHON_PACKAGES:
        (tmp_path / pkg).mkdir(parents=True)
        (tmp_path / pkg / "pyproject.toml").write_text(
            f'[project]\nname = "{pkg.split("/")[-1]}"\nversion = "1.2.0rc1"\n', encoding="utf-8"
        )
    (tmp_path / "packages" / "sdk-ts").mkdir(parents=True)
    (tmp_path / mod.NPM_PACKAGE).write_text('{"name": "@ezmd/sdk", "version": "1.1.0"}', encoding="utf-8")
    assert mod.check_versions(tmp_path, "1.2.0rc1", "1.2.0-rc1", True) == []  # npm not checked for rc
    problems = mod.check_versions(tmp_path, "1.2.0", "1.2.0", False)
    assert len(problems) == 4 and any("sdk" in p for p in problems)
