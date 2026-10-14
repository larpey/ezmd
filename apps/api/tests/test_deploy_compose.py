"""Static checks on deploy/docker-compose.yml that the CI smoke run would otherwise find late."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from ezmd_api.purge import Scheduler

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


def _api_commands() -> list[list[str]]:
    """The uvicorn argv from compose and from the Dockerfile api stage CMD."""
    import json

    compose_cmd = [str(a) for a in _services()["api"]["command"]]
    docker_cmd: list[str] = []
    stage = ""
    for line in (COMPOSE.parent / "Dockerfile").read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if parts[:1] == ["FROM"] and len(parts) >= 4:
            stage = parts[3]
        elif stage == "api" and line.startswith("CMD "):
            docker_cmd = json.loads(line[4:])
    assert docker_cmd, "api stage has no exec-form CMD"
    return [compose_cmd, docker_cmd]


def test_uvicorn_never_rewrites_the_peer_from_forwarded_headers() -> None:
    """--forwarded-allow-ips * makes uvicorn take the leftmost (client-supplied) X-Forwarded-For entry.
    The app derives the client IP itself (ezmd_api.auth.client_ip), so uvicorn must not."""
    for cmd in _api_commands():
        assert "--forwarded-allow-ips" not in cmd, cmd
        assert "--proxy-headers" not in cmd, cmd
        assert "--no-proxy-headers" in cmd, cmd


def test_compose_api_trusts_only_caddys_x_real_ip() -> None:
    env = _services()["api"]["environment"]
    assert str(env["EZMD_TRUST_PROXY_HEADER"]).endswith(":-X-Real-IP}")
    proxies = str(env["EZMD_TRUSTED_PROXIES"])
    assert "0.0.0.0/0" not in proxies
    assert "172.16.0.0/12" in proxies


def test_caddy_sets_x_real_ip_on_every_api_proxy() -> None:
    """Caddy forwards client headers; a reverse_proxy without header_up X-Real-IP would pass a spoofed one."""
    lines = (COMPOSE.parent / "Caddyfile").read_text(encoding="utf-8").splitlines()
    proxies = [i for i, line in enumerate(lines) if line.strip().startswith("reverse_proxy api:8000")]
    assert proxies
    for i in proxies:
        assert lines[i].rstrip().endswith("{"), f"reverse_proxy on line {i + 1} has no block"
        block: list[str] = []
        for line in lines[i + 1 :]:
            if line.strip() == "}" and line.startswith("\t\t}"):
                break
            block.append(line.strip())
        assert "header_up X-Real-IP {client_ip}" in block, f"line {i + 1}"


def test_caddy_access_log_never_records_job_ids() -> None:
    """F3: a job id grants access to the job; the access log keeps the path shape, never the id."""
    import re

    text = (COMPOSE.parent / "Caddyfile").read_text(encoding="utf-8")
    line = next(ln.strip() for ln in text.splitlines() if ln.strip().startswith("request>uri regexp"))
    pattern, repl = re.findall(r'"([^"]*)"', line)
    sub = re.sub(
        pattern, repl.replace("${1}", r"\1").replace("${2}", r"\2"), "/v1/jobs/job_abc/result?format=md&token=t"
    )
    assert sub == "/v1/jobs/REDACTED/result?format=md&token=REDACTED"


def test_workers_ship_bubblewrap_and_require_the_office_sandbox() -> None:
    """LibreOffice is opt-in (EZMD_WORKER_APT_PACKAGES); when present it must run under bwrap or be refused
    (office.require_sandbox via EZMD_REQUIRE_SANDBOX), never unsandboxed (D-0064)."""
    services = _services()
    for name in ("worker-default", "worker-fetch"):
        assert services[name]["environment"]["EZMD_REQUIRE_SANDBOX"] == "${EZMD_REQUIRE_SANDBOX:-1}", name
    dockerfile = (COMPOSE.parent / "Dockerfile").read_text(encoding="utf-8")
    worker = dockerfile.split("FROM runtime-common AS worker", 1)[1].split("\nFROM ", 1)[0]
    assert "bubblewrap" in worker.split("apt-get install", 1)[1].split("\n", 1)[0]


def test_worker_job_memory_leaves_room_below_the_container_limit() -> None:
    """The child's RLIMIT_AS (EZMD_JOB_MEM_MB) equalled the 4g worker limit, and the input copy on the /tmp
    tmpfs plus the RQ parent count against the same cgroup, so a large job could be OOM-killed."""
    import re

    worker = _services()["worker-default"]
    job_mb = int(re.fullmatch(r"\$\{EZMD_JOB_MEM_MB:-(\d+)\}", worker["environment"]["EZMD_JOB_MEM_MB"]).group(1))
    limit = worker["deploy"]["resources"]["limits"]["memory"]
    limit_mb = int(re.fullmatch(r"\$\{EZMD_WORKER_DEFAULT_MEM:-(\d+)g\}", limit).group(1)) * 1024
    assert job_mb <= limit_mb - 1024, (job_mb, limit_mb)
