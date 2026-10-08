"""Lint docs/api/openapi.json (P1-T10 "spectral clean").

The Python checks below always run and cover what the Spectral ruleset (apps/api/.spectral.yaml) enforces
that matters most: unique operationIds, summaries, descriptions, known tags, documented 2xx responses with
schemas, and error responses that use the 7.5 ErrorResponse schema. Set EZMD_SPECTRAL=1 (needs Node and
network for npx) to also run Spectral itself.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[3]
DOC = REPO / "docs" / "api" / "openapi.json"
RULESET = REPO / "apps" / "api" / ".spectral.yaml"
SPECTRAL = "@stoplight/spectral-cli@6.15.0"
ERROR_REF = "#/components/schemas/ErrorResponse"


def _operations() -> list[tuple[str, str, dict[str, Any]]]:
    doc = json.loads(DOC.read_text(encoding="utf-8"))
    return [(path, method, op) for path, ops in doc["paths"].items() for method, op in ops.items()]


def test_info_tags_servers_and_security_schemes() -> None:
    doc = json.loads(DOC.read_text(encoding="utf-8"))
    assert doc["info"]["license"]["name"] == "Apache-2.0"
    assert doc["info"]["contact"] and doc["info"]["description"]
    assert doc["servers"]
    tag_names = {t["name"] for t in doc["tags"]}
    assert all(t.get("description") for t in doc["tags"])
    used = {tag for _, _, op in _operations() for tag in op.get("tags", [])}
    assert used <= tag_names
    assert set(doc["components"]["securitySchemes"]) == {"ApiKey", "FetchNodeBearer"}
    assert "HTTPValidationError" not in doc["components"]["schemas"]


def test_every_operation_is_documented() -> None:
    ids: list[str] = []
    for path, method, op in _operations():
        where = f"{method.upper()} {path}"
        ids.append(op["operationId"])
        assert op.get("summary"), where
        assert len(op.get("description", "")) >= 40, where
        assert op.get("tags"), where
        assert "security" in op, where
        responses = op["responses"]
        ok = [code for code in responses if code.startswith("2")]
        assert ok, f"{where}: no success response"
        for code in ok:
            assert responses[code].get("description"), f"{where} {code}"
            for media, body in responses[code].get("content", {}).items():
                assert body.get("schema"), f"{where} {code} {media}: no schema"
        errors = [code for code in responses if code[0] in "45"]
        assert "400" in errors and "500" in errors, where
        for code in errors:
            resp = responses[code]
            assert resp.get("description"), f"{where} {code}"
            if path == "/readyz" and code == "503":
                continue
            ref = resp["content"]["application/json"]["schema"]["$ref"]
            assert ref == ERROR_REF, f"{where} {code}: {ref}"
    assert len(ids) == len(set(ids)), "duplicate operationId"


def test_job_routes_document_not_found_and_auth() -> None:
    for path, method, op in _operations():
        if path.startswith("/v1/jobs/"):
            assert {"401", "404"} <= set(op["responses"]), f"{method} {path}"
        if path.startswith("/v1/fetch-node/"):
            assert op["security"] == [{"FetchNodeBearer": []}]


def test_request_body_schemas_resolve() -> None:
    doc = json.loads(DOC.read_text(encoding="utf-8"))
    schemas = doc["components"]["schemas"]
    text = json.dumps(doc)
    for name in schemas:
        assert f"#/components/schemas/{name}" in text, f"unused component {name}"
    options = schemas["ConvertUrlRequest"]["properties"]["options"]
    assert options["allOf"] == [{"$ref": "#/components/schemas/ConvertOptionsIn"}]
    assert schemas["ConvertOptionsIn"]["additionalProperties"] is False
    assert schemas["ConvertOptionsIn"]["patternProperties"]


@pytest.mark.skipif(os.environ.get("EZMD_SPECTRAL") != "1", reason="set EZMD_SPECTRAL=1 to run Spectral")
def test_spectral_clean() -> None:
    from ezmd.core import sandbox

    npx = shutil.which("npx")
    if npx is None:
        pytest.skip("npx not on PATH")
    argv = [npx, "-y", SPECTRAL, "lint", str(DOC), "--ruleset", str(RULESET), "--fail-severity", "hint"]
    result = sandbox.run(argv, timeout=600, env_allowlist=("PATH", "HOME", "APPDATA", "USERPROFILE", "SYSTEMROOT"))
    out = result.stdout.decode(errors="replace") + result.stderr.decode(errors="replace")
    assert result.returncode == 0, out
