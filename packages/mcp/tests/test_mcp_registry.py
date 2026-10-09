"""Registry listing (docs/spec/part4.md 4.4.5): server.json validates against the official schema (vendored
from modelcontextprotocol/registry, 2025-12-11) and agrees with the package metadata and README marker.
The release workflow publishes it with `mcp-publisher publish`, which the registry validates on upload; CI
does not run `mcp-publisher validate` separately, so this schema test is the pre-release check."""

from __future__ import annotations

import json
import tomllib
from pathlib import Path

import jsonschema

PKG = Path(__file__).resolve().parents[1]


def _server() -> dict[str, object]:
    return json.loads((PKG / "server.json").read_text(encoding="utf-8"))


def test_server_json_validates_against_registry_schema() -> None:
    schema = json.loads((PKG / "tests" / "data" / "server.schema.json").read_text(encoding="utf-8"))
    server = _server()
    assert server["$schema"] == schema["$id"]
    jsonschema.Draft7Validator.check_schema(schema)
    errors = sorted(jsonschema.Draft7Validator(schema).iter_errors(server), key=lambda e: list(e.path))
    assert not errors, [f"{list(e.path)}: {e.message}" for e in errors]


def test_server_json_matches_package() -> None:
    project = tomllib.loads((PKG / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    server = _server()
    assert len(str(server["description"])) < 100
    packages = server["packages"]
    assert isinstance(packages, list) and len(packages) == 1
    pkg = packages[0]
    assert pkg["registryType"] == "pypi" and pkg["identifier"] == project["name"] == "ezmd-mcp"
    assert pkg["version"] == server["version"] == project["version"]
    assert pkg["transport"] == {"type": "stdio"}
    if _api_mounts_mcp():
        remotes = server["remotes"]
        assert isinstance(remotes, list) and remotes[0]["type"] == "streamable-http"
        assert any(h["isRequired"] and h["isSecret"] for h in remotes[0]["headers"])  # token required
    assert project["scripts"]["ezmd-mcp"] == "ezmd_mcp.cli:main"


def _api_mounts_mcp() -> bool:
    main = PKG.parents[1] / "apps" / "api" / "src" / "ezmd_api" / "main.py"
    return '"/mcp"' in main.read_text(encoding="utf-8")


def test_remote_is_listed_only_when_the_api_serves_mcp() -> None:
    """Advertising `https://{host}/mcp` before the API mounts it would send registry users to a 404
    (D-0024 left the hosted endpoint pending)."""
    assert ("remotes" in _server()) == _api_mounts_mcp()


def test_readme_carries_the_registry_marker() -> None:
    readme = (PKG / "README.md").read_text(encoding="utf-8")
    assert f"mcp-name: {_server()['name']}" in readme
