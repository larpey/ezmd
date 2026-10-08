"""ezmd_mcp.local: in-process backend over `ezmd.convert` and `Result.render`.

Results are kept in a small in-memory LRU keyed by a random job id, so `get_job` can page them and the
`ezmd://jobs/{id}` resources can read them. Nothing is written to disk.
"""

from __future__ import annotations

import asyncio
import secrets
import threading
from collections import OrderedDict
from typing import TYPE_CHECKING, Any

from ezmd_mcp.backend import JobRef
from ezmd_mcp.errors import ToolFailure, from_exception
from ezmd_mcp.paging import Outline, RenderedPage, sections_from_sidecar, warning_dict

if TYPE_CHECKING:
    from ezmd.library import Options, Result

__all__ = ["LocalBackend"]

MAX_JOBS = 32


def _validation_message(exc: Exception) -> str:
    errors = getattr(exc, "errors", None)
    if callable(errors):
        fields = sorted({".".join(str(p) for p in e.get("loc", ())) for e in errors()})
        return "Invalid options: " + ", ".join(f for f in fields if f)[:300]
    return "Invalid options."


class LocalBackend:
    mode = "local"

    def __init__(self, *, allow_private_networks: bool = False, max_jobs: int = MAX_JOBS) -> None:
        self.allow_private_networks = allow_private_networks
        self.max_jobs = max_jobs
        self._jobs: OrderedDict[str, Result] = OrderedDict()
        self._lock = threading.Lock()

    # -- job store ---------------------------------------------------------------------------------------

    def _store(self, result: Result) -> str:
        job_id = "local_" + secrets.token_urlsafe(12)
        with self._lock:
            self._jobs[job_id] = result
            while len(self._jobs) > self.max_jobs:
                self._jobs.popitem(last=False)
        return job_id

    def _get(self, job_id: str) -> Result:
        with self._lock:
            result = self._jobs.get(job_id)
            if result is not None:
                self._jobs.move_to_end(job_id)
        if result is None:
            raise ToolFailure("job_not_found", f"Unknown or expired job {job_id[:64]!r}.")
        return result

    # -- conversion --------------------------------------------------------------------------------------

    def _options(self, options: dict[str, Any]) -> Options:
        from pydantic import ValidationError

        from ezmd.library import Options

        if options.get("allow_private_networks") and not self.allow_private_networks:
            raise ToolFailure(
                "invalid_request",
                "allow_private_networks is disabled on this server (start it with --allow-private-networks).",
            )
        try:
            return Options(**options)
        except (ValidationError, TypeError) as e:
            raise ToolFailure("invalid_request", _validation_message(e)) from None

    async def _convert(self, source: Any, profile: str, options: dict[str, Any], filename: str | None) -> JobRef:
        from ezmd.library import convert_async

        opts = self._options(options)
        try:
            result = await convert_async(source, profile=profile, options=opts, filename=filename)
        except ToolFailure:
            raise
        except ValueError as e:
            raise ToolFailure("invalid_request", f"Invalid render option: {str(e)[:200]}") from None
        except Exception as e:
            raise from_exception(e) from None
        return JobRef(self._store(result))

    async def convert_url(self, url: str, profile: str, options: dict[str, Any]) -> JobRef:
        return await self._convert(url, profile, options, None)

    async def convert_bytes(self, data: bytes, filename: str, profile: str, options: dict[str, Any]) -> JobRef:
        return await self._convert(data, profile, options, filename)

    async def convert_path(self, path: str, profile: str, options: dict[str, Any]) -> JobRef:
        from pathlib import Path

        return await self._convert(Path(path), profile, options, None)

    # -- results -----------------------------------------------------------------------------------------

    async def status(self, job_id: str) -> dict[str, Any] | None:
        self._get(job_id)
        return None  # local jobs finish before the convert tool returns

    async def render(self, job_id: str, profile: str, cursor: str | None, budget: int) -> RenderedPage:
        result = self._get(job_id)

        def run() -> RenderedPage:
            overrides: dict[str, object] = {"max_tokens": budget}
            if cursor:
                overrides["cursor"] = cursor
            out = result.render(profile, "md", **overrides)
            return RenderedPage(
                markdown=str(out.markdown),
                body=str(out.body),
                frontmatter=dict(out.frontmatter),
                warnings=[warning_dict(w.model_dump(mode="json")) for w in out.warnings],
            )

        try:
            return await asyncio.to_thread(run)
        except ValueError as e:
            if "cursor" in str(e):
                raise ToolFailure("cursor_invalid", str(e)[:200]) from None
            raise ToolFailure("invalid_request", f"Invalid render option: {str(e)[:200]}") from None

    def _unpaged(self, job_id: str, profile: str) -> Any:
        return self._get(job_id).render(profile, max_tokens="none")

    async def outline(self, job_id: str, profile: str) -> Outline:
        from ezmd.render.tokens import count_o200k

        def run() -> Outline:
            out = self._unpaged(job_id, profile)
            sidecar = out.sidecar
            if sidecar is None:  # profiles without a sidecar (compact): take the section list from `full`
                sidecar = self._unpaged(job_id, "full").sidecar
                full_body = str(self._unpaged(job_id, "full").body)
                sections = sections_from_sidecar(sidecar, full_body)
            else:
                sections = sections_from_sidecar(sidecar, str(out.body))
            return Outline(sections=sections, tokens_total=count_o200k(str(out.body)))

        return await asyncio.to_thread(run)

    async def full_markdown(self, job_id: str, profile: str) -> str:
        return str((await asyncio.to_thread(self._unpaged, job_id, profile)).markdown)

    async def sidecar(self, job_id: str) -> dict[str, Any]:
        out = await asyncio.to_thread(self._unpaged, job_id, "full")
        return dict(out.sidecar or {})

    async def capabilities(self) -> dict[str, Any]:
        from ezmd.library import Options, capabilities

        caps = await asyncio.to_thread(capabilities)
        defaults = Options()
        return {
            **caps,
            "mode": "local",
            "fetch_allowed": True,
            "private_networks_allowed": self.allow_private_networks,
            "limits": {
                "max_bytes": defaults.max_bytes,
                "max_pages": defaults.max_pages,
                "max_duration_seconds": defaults.max_duration_seconds,
                "max_seconds": defaults.max_seconds,
            },
        }

    async def aclose(self) -> None:
        with self._lock:
            self._jobs.clear()
