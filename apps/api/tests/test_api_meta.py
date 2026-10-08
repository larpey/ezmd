"""Capabilities, OpenAPI staleness, env.example drift, migrations, static serving."""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest
from sqlalchemy import create_engine, inspect

from ezmd_api.db import Base
from ezmd_api.settings import Settings, env_names
from ezmd_api.testing import api_client

REPO = Path(__file__).resolve().parents[3]
ENV_EXAMPLE = REPO / "deploy" / "env.example"
DEPLOY_ONLY_MARKER = "# ---- Deployment"
ENV_LINE = re.compile(r"^(EZMD_[A-Z0-9_]+)=")


async def test_capabilities(client: httpx.AsyncClient) -> None:
    body = (await client.get("/v1/capabilities")).json()
    ids = {c["id"] for c in body["converters"]}
    assert {"text.plain", "text.markdown_passthrough"} <= ids
    conv = next(c for c in body["converters"] if c["id"] == "text.plain")
    assert set(conv) == {"id", "family", "mimes", "experimental", "loaded", "extras"}
    assert body["profiles"] == ["full", "compact", "rag", "agent"]
    assert body["formats"] == ["md", "json", "txt", "zip"]
    expected_limits = {"max_upload_bytes", "max_url_bytes", "max_audio_seconds", "max_pages", "retention_hours"}
    assert set(body["limits"]) == expected_limits
    assert body["fetch_node_online"] is False
    assert body["public_mode"] is False


def test_openapi_committed_file_is_fresh() -> None:
    from ezmd_api.openapi import openapi_document

    committed = (REPO / "docs" / "api" / "openapi.json").read_text(encoding="utf-8")
    assert committed == openapi_document(), "stale: run `uv run python apps/api/scripts/export_openapi.py`"


def _env_example_vars() -> tuple[set[str], set[str]]:
    settings_vars: set[str] = set()
    deploy_vars: set[str] = set()
    target = settings_vars
    for line in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines():
        if line.startswith(DEPLOY_ONLY_MARKER):
            target = deploy_vars
        m = ENV_LINE.match(line)
        if m:
            target.add(m.group(1))
    return settings_vars, deploy_vars


@pytest.mark.skipif(not ENV_EXAMPLE.is_file(), reason="deploy/env.example is missing")
def test_env_example_matches_settings() -> None:
    documented, deploy_only = _env_example_vars()
    fields = set(env_names())
    assert sorted(fields - documented) == [], "Settings fields missing from deploy/env.example"
    assert sorted(documented - fields) == [], "deploy/env.example lists variables Settings does not read"
    assert sorted(deploy_only & fields) == [], "Settings fields must not sit in the deployment-only section"


def test_alembic_migration_matches_models(tmp_path: Path) -> None:
    from ezmd_api.migrate import upgrade

    url = f"sqlite:///{(tmp_path / 'm.db').as_posix()}"
    upgrade(url)
    insp = inspect(create_engine(url))
    for table in Base.metadata.sorted_tables:
        migrated = {c["name"]: c["nullable"] for c in insp.get_columns(table.name)}
        modeled = {c.name: c.nullable for c in table.columns}
        assert migrated == modeled, table.name


async def test_static_spa_fallback(tmp_path: Path, settings_factory: Callable[..., Settings]) -> None:
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>ezmd</title>", encoding="utf-8")
    (dist / "assets" / "app-123.js").write_text("console.log(1)", encoding="utf-8")
    async with api_client(settings_factory(web_dist=dist)) as (client, _):
        index = await client.get("/")
        assert index.status_code == 200 and "ezmd" in index.text
        assert index.headers["cache-control"] == "no-cache"
        asset = await client.get("/assets/app-123.js")
        assert "immutable" in asset.headers["cache-control"]
        deep = await client.get("/jobs/job_abc")
        assert deep.status_code == 200 and "ezmd" in deep.text
        assert (await client.get("/assets/missing.js")).status_code == 404
        api_miss = await client.get("/v1/nope")
        assert api_miss.status_code == 404 and api_miss.json()["error"]["code"] == "not_found"
        assert (await client.post("/v1/nope")).status_code == 404
        assert (await client.get("/healthz")).json() == {"status": "ok"}


@pytest.mark.parametrize(
    "path",
    ["/admin", "/admin/", "/ADMIN/users", "/metrics", "/v1", "/v2/jobs", "/api/x", "/mcp", "/.well-known/x"],
)
async def test_static_fallback_404s_reserved_paths(
    path: str, tmp_path: Path, settings_factory: Callable[..., Settings]
) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<!doctype html><title>ezmd</title>", encoding="utf-8")
    async with api_client(settings_factory(web_dist=dist)) as (client, _):
        r = await client.get(path)
        assert r.status_code == 404, path
        assert r.json()["error"]["code"] == "not_found"
        # Paths that only share a prefix with a reserved segment stay SPA routes.
        assert (await client.get("/administration")).status_code == 200


@pytest.mark.skipif(not ENV_EXAMPLE.is_file(), reason="deploy/env.example is missing")
def test_env_example_has_no_inline_comments() -> None:
    """Docker Compose's env-file parser keeps `# ...` after an empty value as the value itself."""
    bad = [
        line
        for line in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines()
        if line[:1].isupper() and "=" in line and "#" in line.split("=", 1)[1]
    ]
    assert bad == [], f"put comments on their own line: {bad}"
