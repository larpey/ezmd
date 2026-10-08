"""Remote mode against a fake ezmd REST instance (an in-process Starlette app speaking the Part 3
contract): headers, job waiting, error mapping, and cursor paging over `GET /v1/jobs/{id}/result`."""

from __future__ import annotations

import json
import secrets
from pathlib import Path
from typing import Any

import httpx
from conftest import call, text_of, unwrap
from mcp import Client
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route
from test_mcp_pagination import long_document

import ezmd
from ezmd_mcp import USER_AGENT
from ezmd_mcp.config import Settings
from ezmd_mcp.paths import AllowedRoots
from ezmd_mcp.remote import RemoteBackend
from ezmd_mcp.server import build_server

KEY = "imd_test_key"


class FakeApi:
    def __init__(self) -> None:
        self.jobs: dict[str, dict[str, Any]] = {}
        self.seen: list[httpx.Headers | dict[str, str]] = []
        self.app = Starlette(
            routes=[
                Route("/v1/convert", self.convert, methods=["POST"]),
                Route("/v1/jobs/{job_id}", self.job, methods=["GET"]),
                Route("/v1/jobs/{job_id}/result", self.result, methods=["GET"]),
                Route("/v1/capabilities", self.caps, methods=["GET"]),
            ]
        )

    def _record(self, request: Request) -> None:
        self.seen.append(dict(request.headers))

    @staticmethod
    def error(code: str, message: str, status: int) -> JSONResponse:
        return JSONResponse({"error": {"code": code, "message": message, "status": status}}, status_code=status)

    async def convert(self, request: Request) -> Response:
        self._record(request)
        if request.headers.get("x-api-key") != KEY:
            return self.error("unauthorized", "This instance requires an API key (X-API-Key header).", 401)
        if request.headers.get("content-type", "").startswith("application/json"):
            body = json.loads(await request.body())
            url = body["url"]
            if "127.0.0.1" in url:
                return self.error("url_blocked", "This URL is not allowed.", 422)
            job_id = secrets.token_hex(8)
            state = "fetching" if "slow" in url else "failed"
            self.jobs[job_id] = {"state": state, "profile": body["profile"]}
            return JSONResponse({"job": self._out(job_id)}, status_code=202)
        form = await request.form()
        upload = form["file"]
        data = await upload.read()  # type: ignore[union-attr]
        options = json.loads(str(form.get("options") or "{}"))
        assert isinstance(options, dict)
        job_id = secrets.token_hex(8)
        result = ezmd.convert(data, filename=upload.filename, profile=str(form["profile"]))  # type: ignore[union-attr]
        self.jobs[job_id] = {"state": "done", "result": result, "profile": str(form["profile"])}
        return JSONResponse({"job": self._out(job_id)}, status_code=202)

    def _out(self, job_id: str) -> dict[str, Any]:
        job = self.jobs[job_id]
        out: dict[str, Any] = {"id": job_id, "state": job["state"], "progress": 10, "stage_message": "working"}
        if job["state"] == "failed":
            out["error"] = {"code": "fetch_failed", "message": "The URL could not be fetched."}
        return out

    async def job(self, request: Request) -> Response:
        self._record(request)
        job_id = request.path_params["job_id"]
        if job_id not in self.jobs:
            return self.error("not_found", "Not found.", 404)
        return JSONResponse(self._out(job_id))

    async def result(self, request: Request) -> Response:
        self._record(request)
        job = self.jobs.get(request.path_params["job_id"])
        if job is None or "result" not in job:
            return self.error("not_found", "Not found.", 404)
        q = dict(request.query_params)
        profile, fmt = q.pop("profile", job["profile"]), q.pop("format", "md")
        overrides: dict[str, Any] = {k: (int(v) if v.isdigit() else v) for k, v in q.items()}
        try:
            out = job["result"].render(profile, fmt, **overrides)
        except ValueError as e:
            return self.error("invalid_request", f"Invalid render option: {e}", 400)
        media = "application/json" if fmt == "json" else "text/markdown"
        return Response(out.markdown, media_type=media)

    async def caps(self, request: Request) -> Response:
        self._record(request)
        return JSONResponse({"version": "0.0.1", "converters": [], "limits": {"max_upload_bytes": 1}})


def remote_server(api: FakeApi, root: Path, *, key: str | None = KEY, wait: float = 5.0) -> Any:
    transport = httpx.ASGITransport(app=api.app)
    backend = RemoteBackend(
        "https://ezmd.test", api_key=key, wait_seconds=wait, poll_interval=0.01, transport=transport
    )
    settings = Settings(remote="https://ezmd.test", allowed_dirs=AllowedRoots.from_strings([str(root)]))
    return build_server(settings, backend)


async def test_headers_and_capabilities(root: Path) -> None:
    api = FakeApi()
    async with Client(remote_server(api, root)) as client:
        res = await call(client, "list_capabilities")
    assert not res.is_error
    assert res.structured_content["mode"] == "remote" and res.structured_content["remote"] == "https://ezmd.test"
    assert api.seen and all(h["user-agent"] == USER_AGENT and h["x-api-key"] == KEY for h in api.seen)
    assert USER_AGENT.startswith("ezmd-mcp/")


async def test_remote_convert_file_and_pages(root: Path) -> None:
    api = FakeApi()
    src = root / "doc.md"
    src.write_bytes(long_document(40).encode("utf-8"))
    async with Client(remote_server(api, root)) as client:
        first = await call(client, "convert_file", {"path": str(src), "max_tokens": 2500})
        assert not first.is_error, text_of(first)
        pages = [first.structured_content]
        while pages[-1]["next_cursor"]:
            args = {"job_id": pages[-1]["job_id"], "cursor": pages[-1]["next_cursor"], "max_tokens": 2500}
            res = await call(client, "get_job", args)
            assert not res.is_error, text_of(res)
            pages.append(res.structured_content)
    assert len(pages) >= 3
    assert pages[0]["profile"] == "agent" and len(pages[0]["sections"]) == 40
    expected = ezmd.convert(src, profile="agent").render("agent", max_tokens="none").body
    assert "\n\n".join(unwrap(p["content"]) for p in pages) == unwrap(expected)
    result_calls = [h for h in api.seen if h.get("x-api-key") == KEY]
    assert len(result_calls) == len(api.seen)


async def test_remote_convert_text(root: Path) -> None:
    api = FakeApi()
    async with Client(remote_server(api, root)) as client:
        res = await call(client, "convert_text", {"text": "# Hi\n\n## Part\n\nText.\n", "source_hint": "md"})
    assert not res.is_error, text_of(res)
    assert "Part" in res.structured_content["content"]
    assert [s["heading"] for s in res.structured_content["sections"]] == ["Part"]


async def test_remote_errors(root: Path) -> None:
    api = FakeApi()
    async with Client(remote_server(api, root)) as client:
        blocked = await call(client, "convert_url", {"url": "http://127.0.0.1/admin"})
        assert blocked.is_error and blocked.structured_content["error"]["code"] == "url_blocked"
        failed = await call(client, "convert_url", {"url": "https://example.com/fails"})
        assert failed.is_error and failed.structured_content["error"]["code"] == "fetch_failed"
        missing = await call(client, "get_job", {"job_id": "nope"})
        assert missing.is_error and missing.structured_content["error"]["code"] == "not_found"
    async with Client(remote_server(api, root, key=None)) as client:
        res = await call(client, "convert_text", {"text": "hi"})
        assert res.is_error and res.structured_content["error"]["code"] == "unauthorized"
        assert "EZMD_API_KEY" in text_of(res)


async def test_remote_running_job_returns_status(root: Path) -> None:
    api = FakeApi()
    async with Client(remote_server(api, root, wait=0.05)) as client:
        res = await call(client, "convert_url", {"url": "https://example.com/slow"})
        assert not res.is_error
        out = res.structured_content
        assert out["status"] == "running" and "get_job" in out["instructions"]
        again = await call(client, "get_job", {"job_id": out["job_id"]})
        assert not again.is_error and again.structured_content["status"] == "running"


async def test_remote_unreachable(root: Path) -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    backend = RemoteBackend("https://down.test", transport=httpx.MockTransport(refuse))
    settings = Settings(remote="https://down.test", allowed_dirs=AllowedRoots.from_strings([str(root)]))
    async with Client(build_server(settings, backend)) as client:
        res = await call(client, "list_capabilities")
    assert res.is_error and res.structured_content["error"]["code"] == "remote_unavailable"
    assert "refused" not in text_of(res)
