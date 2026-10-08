"""Static checks on deploy/docker-compose.yml that the CI smoke run would otherwise find late."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from intomd_api.purge import Scheduler

COMPOSE = Path(__file__).resolve().parents[3] / "deploy" / "docker-compose.yml"


def _services() -> dict[str, Any]:
    data = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    services: dict[str, Any] = data["services"]
    return services


def _stages_with_healthcheck() -> set[str]:
    stages: set[str] = set()
    current = ""
    for line in (COMPOSE.parent / "Dockerfile").read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if parts[:1] == ["FROM"] and len(parts) >= 4 and parts[2].upper() == "AS":
            current = parts[3]
        elif parts[:1] == ["HEALTHCHECK"] and parts[1:2] != ["NONE"]:
            stages.add(current)
    return stages


def test_every_default_service_has_a_healthcheck() -> None:
    """`docker compose up --wait` (newer Compose) fails on a container without a healthcheck, so each
    default-profile service needs one: from compose, or from its Dockerfile build target."""
    image_checks = _stages_with_healthcheck()
    missing = []
    for name, svc in _services().items():
        if svc.get("profiles"):
            continue
        hc = svc.get("healthcheck") or {}
        if hc.get("disable"):
            missing.append(name)
            continue
        target = (svc.get("build") or {}).get("target")
        if not hc.get("test") and target not in image_checks and "image" in svc and "build" in svc:
            missing.append(name)
    assert missing == [], f"services without an enabled healthcheck: {missing}"


def test_images_with_a_shared_tag_are_built_not_pulled() -> None:
    """A service that reuses another service's ghcr tag must also build it, or a clean host tries to pull it."""
    for name, svc in _services().items():
        image = str(svc.get("image", ""))
        if image.startswith("ghcr.io/") and "build" not in svc:
            raise AssertionError(f"{name} uses {image} without a build section")


def test_scheduler_heartbeat(tmp_path: Path) -> None:
    beat = tmp_path / "hb"
    sched = Scheduler.__new__(Scheduler)
    sched.heartbeat = beat
    sched._beat()
    assert beat.exists()
    sched.heartbeat = tmp_path / "missing-dir" / "hb"
    sched._beat()  # logs a warning, never raises
