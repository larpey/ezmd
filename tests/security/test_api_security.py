"""API hardening (docs/spec/part1.md sections 7.5, 8.2, 8.4): security headers, error schema,
executables, multipart filename sanitization, CORS, log redaction, settings guards."""

from __future__ import annotations

import logging
import struct
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from ezmd_api.main import SECURITY_HEADERS
from ezmd_api.settings import Settings
from ezmd_api.testing import api_client, make_settings, upload, use_in_process_isolation, wait_for_state

ELF = b"\x7fELF\x02\x01\x01\x00" + b"\x00" * 8 + struct.pack("<HHI", 2, 0x3E, 1) + b"\x00" * 200
PE = b"MZ\x90\x00\x03" + b"\x00" * 55 + struct.pack("<I", 64) + b"PE\x00\x00" + b"\x4c\x01" + b"\x00" * 200


@pytest.fixture(autouse=True)
def _isolated(monkeypatch: pytest.MonkeyPatch) -> None:
    use_in_process_isolation(monkeypatch)


@pytest.fixture
async def pair(tmp_path: Path) -> AsyncIterator[tuple[httpx.AsyncClient, FastAPI]]:
    async with api_client(make_settings(tmp_path / "data")) as p:
        yield p


def _assert_security_headers(r: httpx.Response) -> None:
    for name, value in SECURITY_HEADERS.items():
        assert r.headers.get(name) == value, name
    assert r.headers["x-request-id"]


def _assert_error_shape(r: httpx.Response, code: str, status: int) -> dict[str, Any]:
    body = r.json()
    assert set(body) == {"error"}
    err = body["error"]
    assert set(err) == {"code", "message", "status", "request_id", "detail", "docs"}
    assert err["code"] == code and err["status"] == status == r.status_code
    assert err["request_id"] == r.headers["x-request-id"]
    assert err["docs"].endswith(f"/docs/errors#{code}")
    assert isinstance(err["detail"], dict)
    return dict(err)


def test_csp_is_exactly_the_spec_value() -> None:
    assert SECURITY_HEADERS["Content-Security-Policy"] == (
        "default-src 'self'; script-src 'self' https://challenges.cloudflare.com; "
        "frame-src https://challenges.cloudflare.com; img-src 'self' data: blob:; connect-src 'self'; "
        "object-src 'none'; base-uri 'none'; form-action 'self'"
    )


async def test_security_headers_on_every_response(pair: tuple[httpx.AsyncClient, FastAPI]) -> None:
    client, _ = pair
    for r in (
        await client.get("/healthz"),
        await client.get("/v1/capabilities"),
        await client.get("/v1/jobs/job_0000000000000000000000"),
        await client.get("/openapi.json"),
        await client.post("/v1/convert", json={"nope": 1}),
    ):
        _assert_security_headers(r)


async def test_error_schema_shapes(pair: tuple[httpx.AsyncClient, FastAPI]) -> None:
    client, _ = pair
    _assert_error_shape(await client.get("/v1/jobs/job_0000000000000000000000"), "not_found", 404)
    _assert_error_shape(await client.post("/v1/convert", json={"nope": 1}), "invalid_request", 400)
    _assert_error_shape(await client.get("/v1/does-not-exist"), "not_found", 404)
    _assert_error_shape(await client.put("/healthz"), "method_not_allowed", 405)


async def test_unexpected_errors_do_not_leak(pair: tuple[httpx.AsyncClient, FastAPI]) -> None:
    client, app = pair

    def boom() -> None:
        raise RuntimeError("secret path /srv/ezmd/engine.py line 42")

    app.add_api_route("/v1/boom", boom)
    app.router.routes.insert(0, app.router.routes.pop())

    r = await client.get("/v1/boom")
    err = _assert_error_shape(r, "internal_error", 500)
    assert "secret" not in r.text and "/srv" not in r.text
    assert err["message"] == "An internal error occurred."
    _assert_security_headers(r)


@pytest.mark.parametrize(("data", "name"), [(ELF, "ok.txt"), (PE, "setup.pdf"), (ELF, "noext")])
async def test_executables_rejected_415(pair: tuple[httpx.AsyncClient, FastAPI], data: bytes, name: str) -> None:
    client, app = pair
    r = await upload(client, data, name, content_type="text/plain")
    _assert_error_shape(r, "unsupported_media_type", 415)
    services = app.state.services
    assert services.jobs.count_active() == 0


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("../../../../etc/passwd", "passwd"),
        ("..\\..\\windows\\system32\\evil.txt", "evil.txt"),
        ("/abs/path/notes.txt", "notes.txt"),
        ("..", "upload"),
        ("x" * 400 + ".txt", "x" * 255),
    ],
)
async def test_multipart_filename_sanitized(
    pair: tuple[httpx.AsyncClient, FastAPI], tmp_path: Path, raw: str, expected: str
) -> None:
    client, app = pair
    r = await upload(client, b"traversal attempt\n", raw)
    assert r.status_code == 202, r.text
    job = r.json()["job"]
    assert job["input"]["display"] == expected
    await wait_for_state(client, job["id"])
    root = app.state.settings.resolved_blob_root.resolve()
    files = [p for p in root.rglob("*") if p.is_file()]
    assert files, "blobs were written"
    for p in files:
        rel = p.relative_to(root).as_posix()
        assert rel.startswith(f"jobs/{job['id']}/")
        assert "passwd" not in rel and "evil" not in rel and "notes" not in rel
    assert not (tmp_path / "etc").exists()


async def test_control_characters_stripped_from_raw_filename(pair: tuple[httpx.AsyncClient, FastAPI]) -> None:
    client, _ = pair
    crlf = bytes([13, 10])
    ctrl = bytes([1, 127, 27])
    boundary = b"b0undary"
    body = b"".join(
        [
            b"--" + boundary + crlf,
            b'Content-Disposition: form-data; name="file"; filename="../na' + ctrl + b'me.txt"' + crlf,
            b"Content-Type: text/plain" + crlf + crlf,
            b"hello" + crlf,
            b"--" + boundary + b"--" + crlf,
        ]
    )
    r = await client.post(
        "/v1/convert", content=body, headers={"content-type": "multipart/form-data; boundary=b0undary"}
    )
    assert r.status_code == 202, r.text
    assert r.json()["job"]["input"]["display"] == "name.txt"


def test_sanitize_filename_unit() -> None:
    from ezmd_api.util import sanitize_filename

    assert sanitize_filename("a/b/c.md") == "c.md"
    assert sanitize_filename("\u202eexe.txt") == "exe.txt"
    assert len(sanitize_filename("é" * 300).encode()) <= 255
    assert sanitize_filename(None) == "upload"


async def test_attachment_path_traversal_404(pair: tuple[httpx.AsyncClient, FastAPI]) -> None:
    client, _ = pair
    r = await upload(client, b"text\n", "a.txt")
    job_id = r.json()["job"]["id"]
    await wait_for_state(client, job_id)
    for path in ("../ir.json", "..%2Fir.json", "tables/../../input", "input", ".hidden"):
        resp = await client.get(f"/v1/jobs/{job_id}/attachments/{path}")
        assert resp.status_code == 404, path


async def test_cors_same_origin_by_default(pair: tuple[httpx.AsyncClient, FastAPI]) -> None:
    client, _ = pair
    r = await client.get("/v1/capabilities", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in r.headers


async def test_cors_allows_listed_origin(tmp_path: Path) -> None:
    settings = make_settings(tmp_path / "data", cors_origins="chrome-extension://abc,https://app.example")
    async with api_client(settings) as (client, _):
        ok = await client.options(
            "/v1/convert",
            headers={"Origin": "chrome-extension://abc", "Access-Control-Request-Method": "POST"},
        )
        assert ok.headers["access-control-allow-origin"] == "chrome-extension://abc"
        denied = await client.get("/v1/capabilities", headers={"Origin": "https://evil.example"})
        assert "access-control-allow-origin" not in denied.headers


async def test_api_key_never_logged(pair: tuple[httpx.AsyncClient, FastAPI], caplog: pytest.LogCaptureFixture) -> None:
    from ezmd.core.logging import RedactionFilter

    client, _ = pair
    caplog.handler.addFilter(RedactionFilter())
    caplog.set_level(logging.INFO)
    key = "ak_live_" + "A" * 22
    r = await upload(client, b"x", "a.txt", headers={"X-API-Key": key})
    assert r.status_code == 401
    logging.getLogger("ezmd.api").info("probe X-API-Key: " + key)
    assert key not in caplog.text


async def test_invalid_api_key_401(pair: tuple[httpx.AsyncClient, FastAPI]) -> None:
    client, _ = pair
    r = await upload(client, b"x\n", "a.txt", headers={"X-API-Key": "ak_live_doesnotexist0000000000"})
    _assert_error_shape(r, "unauthorized", 401)


async def test_require_api_key(tmp_path: Path) -> None:
    async with api_client(make_settings(tmp_path / "data", require_api_key=True)) as (client, app):
        from ezmd_api.auth import create_api_key

        r = await upload(client, b"x\n", "a.txt")
        _assert_error_shape(r, "unauthorized", 401)
        key, _ = create_api_key(app.state.services.db, app.state.settings, "ci", env="test")
        assert (await upload(client, b"x\n", "a.txt", headers={"X-API-Key": key})).status_code == 202


def test_api_keys_stored_hashed(tmp_path: Path) -> None:
    from sqlalchemy import select

    from ezmd_api.auth import create_api_key, lookup_api_key
    from ezmd_api.db import ApiKeyRow, Database

    settings = make_settings(tmp_path / "data", key_pepper="p" * 32)
    db = Database(settings.resolved_database_url)
    db.create_all()
    key, key_id = create_api_key(db, settings, "ci")
    assert key.startswith("ak_live_") and len(key.split("_")[-1]) == 22
    with db.session() as s:
        row = s.execute(select(ApiKeyRow)).scalar_one()
    assert key not in row.key_hash and row.id == key_id
    assert lookup_api_key(db, settings, key) is not None
    other = make_settings(tmp_path / "data", key_pepper="q" * 32)
    assert lookup_api_key(db, other, key) is None


def test_client_ip_hash_is_salted_and_raw_ip_not_stored(tmp_path: Path) -> None:
    from ezmd_api.auth import hash_ip

    a = make_settings(tmp_path, ip_hash_salt="one")
    b = make_settings(tmp_path, ip_hash_salt="two")
    assert hash_ip(a, "203.0.113.9") != hash_ip(b, "203.0.113.9")
    assert "203.0.113.9" not in hash_ip(a, "203.0.113.9")


async def test_raw_ip_absent_from_database(tmp_path: Path) -> None:
    settings = make_settings(tmp_path / "data")
    async with api_client(settings, client_addr=("203.0.113.77", 1)) as (client, _):
        r = await upload(client, b"x\n", "a.txt")
        await wait_for_state(client, r.json()["job"]["id"])
    raw = Path(settings.resolved_database_url.removeprefix("sqlite:///")).read_bytes()
    assert b"203.0.113.77" not in raw


@pytest.mark.parametrize("name", ["EZMD_JWT_SECRET", "EZMD_KEY_PEPPER"])
def test_public_mode_refuses_short_secrets(tmp_path: Path, name: str) -> None:
    good = "k" * 32
    values = {"jwt_secret": good, "key_pepper": good}
    values[name.removeprefix("EZMD_").lower()] = "short"
    with pytest.raises(ValueError, match=name):
        Settings(public_mode=True, data_dir=tmp_path, **values)  # type: ignore[arg-type]
    Settings(public_mode=True, data_dir=tmp_path, jwt_secret=good, key_pepper=good)  # type: ignore[arg-type]
