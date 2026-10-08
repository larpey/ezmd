"""ezmd_mcp.remote: backend that forwards to an ezmd REST instance (docs/spec/part3 REST contract).

Every request carries `User-Agent: ezmd-mcp/<version>` and, when configured, `X-API-Key`. Conversion
happens on the server; this module only creates jobs, polls them, and fetches rendered pages
(`GET /v1/jobs/{id}/result?profile=...&max_tokens=...&cursor=...`). There is no local fallback.
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import Any

import httpx
import yaml

from ezmd_mcp import USER_AGENT
from ezmd_mcp.backend import JobRef
from ezmd_mcp.errors import ToolFailure
from ezmd_mcp.paging import Outline, RenderedPage, sections_from_sidecar, warning_dict

__all__ = ["RemoteBackend", "split_frontmatter"]

MAX_UPLOAD_BYTES = 100 * 1024 * 1024
_TERMINAL = ("done", "failed", "needs_user_action", "expired")


def split_frontmatter(markdown: str) -> tuple[dict[str, Any], str]:
    """(frontmatter map, body) for Markdown that starts with a YAML frontmatter block."""
    if not markdown.startswith("---\n"):
        return {}, markdown
    end = markdown.find("\n---\n", 4)
    if end < 0:
        return {}, markdown
    try:
        data = yaml.safe_load(markdown[4:end])
    except yaml.YAMLError:
        return {}, markdown
    return (data if isinstance(data, dict) else {}), markdown[end + 5 :]


def _api_failure(resp: httpx.Response) -> ToolFailure:
    code, message = "internal_error", f"The remote instance answered HTTP {resp.status_code}."
    try:
        err = resp.json().get("error", {})
        if isinstance(err, dict):
            code = str(err.get("code") or code)
            message = str(err.get("message") or message)[:300]
    except (ValueError, AttributeError):
        pass
    return ToolFailure(code, message)


class RemoteBackend:
    mode = "remote"

    def __init__(
        self,
        base_url: str,
        *,
        api_key: str | None = None,
        wait_seconds: float = 120.0,
        poll_interval: float = 1.0,
        timeout: float = 60.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not base_url.startswith(("http://", "https://")):
            raise ValueError("--remote must be an http(s) URL")
        headers = {"User-Agent": USER_AGENT, "Accept": "application/json, text/markdown"}
        if api_key:
            headers["X-API-Key"] = api_key
        self.base_url = base_url.rstrip("/")
        self.wait_seconds = wait_seconds
        self.poll_interval = poll_interval
        self._client = httpx.AsyncClient(
            base_url=self.base_url, headers=headers, timeout=timeout, transport=transport, follow_redirects=False
        )
        self._outlines: dict[tuple[str, str], tuple[Outline, list[dict[str, Any]]]] = {}

    async def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        try:
            resp = await self._client.request(method, url, **kwargs)
        except httpx.HTTPError as e:
            msg = f"Could not reach the remote instance ({type(e).__name__})."
            raise ToolFailure("remote_unavailable", msg) from None
        if resp.status_code >= 400:
            raise _api_failure(resp)
        return resp

    # -- jobs --------------------------------------------------------------------------------------------

    @staticmethod
    def _job_status(job: dict[str, Any]) -> dict[str, Any]:
        out: dict[str, Any] = {
            "job_id": job.get("id"),
            "status": "running" if job.get("state") not in _TERMINAL else job.get("state"),
            "state": job.get("state"),
            "progress": job.get("progress"),
            "message": job.get("stage_message"),
        }
        if job.get("needs_action"):
            out["needs_action"] = job["needs_action"]
        return out

    async def _wait(self, job: dict[str, Any]) -> JobRef:
        job_id = str(job.get("id", ""))
        if not job_id:
            raise ToolFailure("internal_error", "The remote instance returned no job id.")
        deadline = time.monotonic() + self.wait_seconds
        interval = self.poll_interval
        while True:
            state = job.get("state")
            if state == "done":
                return JobRef(job_id)
            if state == "failed":
                err = job.get("error") or {}
                code = str(err.get("code") or "job_failed") if isinstance(err, dict) else "job_failed"
                msg = str(err.get("message") or "The conversion failed.") if isinstance(err, dict) else ""
                raise ToolFailure(code, msg[:300] or "The conversion failed.", detail={"job_id": job_id})
            if state in ("needs_user_action", "expired") or time.monotonic() >= deadline:
                status = self._job_status(job)
                if state not in ("needs_user_action", "expired"):
                    status["instructions"] = (
                        f'The job is still running. Call get_job(job_id="{job_id}") to check on it and page it.'
                    )
                return JobRef(job_id, running=status)
            await asyncio.sleep(interval)
            interval = min(interval * 1.5, 5.0)
            job = (await self._request("GET", f"/v1/jobs/{job_id}")).json()

    async def convert_url(self, url: str, profile: str, options: dict[str, Any]) -> JobRef:
        body = {"url": url, "profile": profile, "options": options}
        resp = await self._request("POST", "/v1/convert", json=body)
        return await self._wait(resp.json().get("job", {}))

    async def convert_bytes(self, data: bytes, filename: str, profile: str, options: dict[str, Any]) -> JobRef:
        files = {"file": (filename, data, "application/octet-stream")}
        form = {"profile": profile, "options": json.dumps(options)}
        resp = await self._request("POST", "/v1/convert", files=files, data=form)
        return await self._wait(resp.json().get("job", {}))

    async def convert_path(self, path: str, profile: str, options: dict[str, Any]) -> JobRef:
        p = Path(path)
        if p.stat().st_size > MAX_UPLOAD_BYTES:
            raise ToolFailure("input_too_large", "The file is over the 100 MB upload limit.")
        data = await asyncio.to_thread(p.read_bytes)
        return await self.convert_bytes(data, p.name, profile, options)

    async def status(self, job_id: str) -> dict[str, Any] | None:
        job = (await self._request("GET", f"/v1/jobs/{job_id}")).json()
        if job.get("state") == "done":
            return None
        if job.get("state") == "failed":
            err = job.get("error") or {}
            raise ToolFailure(str(err.get("code") or "job_failed"), str(err.get("message") or "The conversion failed."))
        return self._job_status(job)

    # -- results -----------------------------------------------------------------------------------------

    async def _outline_and_warnings(self, job_id: str, profile: str) -> tuple[Outline, list[dict[str, Any]]]:
        key = (job_id, profile)
        if key not in self._outlines:
            params = {"profile": profile, "format": "json", "max_tokens": "none"}
            payload = (await self._request("GET", f"/v1/jobs/{job_id}/result", params=params)).json()
            sidecar = payload.get("sidecar") or {}
            _, body = split_frontmatter(str(payload.get("markdown", "")))
            tokens = sidecar.get("tokens_total") if isinstance(sidecar, dict) else None
            if not isinstance(tokens, int):
                from ezmd_mcp.paging import count_tokens

                tokens = count_tokens(body)
            warnings = [warning_dict(w) for w in sidecar.get("warnings", []) if isinstance(w, dict)]
            self._outlines[key] = (Outline(sections_from_sidecar(sidecar, body), tokens), warnings)
            while len(self._outlines) > 64:
                self._outlines.pop(next(iter(self._outlines)))
        return self._outlines[key]

    async def render(self, job_id: str, profile: str, cursor: str | None, budget: int) -> RenderedPage:
        params: dict[str, Any] = {"profile": profile, "format": "md", "max_tokens": budget}
        if cursor:
            params["cursor"] = cursor
        try:
            resp = await self._request("GET", f"/v1/jobs/{job_id}/result", params=params)
        except ToolFailure as f:
            if f.code == "invalid_request" and "cursor" in f.message:
                raise ToolFailure("cursor_invalid", f.message) from None
            raise
        markdown = resp.text
        fm, body = split_frontmatter(markdown)
        try:
            _, job_warnings = await self._outline_and_warnings(job_id, profile)
        except ToolFailure:
            job_warnings = []
        seen = {w["code"] for w in job_warnings}
        extra = [
            warning_dict({"kind": code, "message": "Reported by the remote instance for this page."})
            for code in fm.get("warnings", []) or []
            if isinstance(code, str) and code not in seen
        ]
        return RenderedPage(markdown=markdown, body=body, frontmatter=fm, warnings=[*job_warnings, *extra])

    async def outline(self, job_id: str, profile: str) -> Outline:
        return (await self._outline_and_warnings(job_id, profile))[0]

    async def full_markdown(self, job_id: str, profile: str) -> str:
        params = {"profile": profile, "format": "md", "max_tokens": "none"}
        return (await self._request("GET", f"/v1/jobs/{job_id}/result", params=params)).text

    async def sidecar(self, job_id: str) -> dict[str, Any]:
        params = {"profile": "full", "format": "json"}
        payload = (await self._request("GET", f"/v1/jobs/{job_id}/result", params=params)).json()
        sidecar = payload.get("sidecar")
        return dict(sidecar) if isinstance(sidecar, dict) else {}

    async def capabilities(self) -> dict[str, Any]:
        caps = (await self._request("GET", "/v1/capabilities")).json()
        return {**(caps if isinstance(caps, dict) else {}), "mode": "remote", "remote": self.base_url}

    async def aclose(self) -> None:
        await self._client.aclose()
