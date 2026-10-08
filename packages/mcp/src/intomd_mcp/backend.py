"""intomd_mcp.backend: the interface the tools call, implemented in-process (local) or over REST (remote)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from intomd_mcp.paging import Outline, RenderedPage

__all__ = ["PROFILES", "Backend", "JobRef", "check_profile"]

PROFILES = ("full", "compact", "rag", "agent")


def check_profile(profile: str | None, default: str) -> str:
    from intomd_mcp.errors import ToolFailure

    p = (profile or default).strip().lower()
    if p not in PROFILES:
        raise ToolFailure("invalid_request", f"Unknown profile {p!r}; expected one of {', '.join(PROFILES)}.")
    return p


@dataclass(slots=True)
class JobRef:
    """A created job. `running` is set when a remote job did not finish within the wait window."""

    job_id: str
    running: dict[str, Any] | None = None
    extra: dict[str, Any] = field(default_factory=dict)


class Backend(Protocol):
    mode: str

    async def convert_url(self, url: str, profile: str, options: dict[str, Any]) -> JobRef: ...

    async def convert_bytes(self, data: bytes, filename: str, profile: str, options: dict[str, Any]) -> JobRef: ...

    async def convert_path(self, path: str, profile: str, options: dict[str, Any]) -> JobRef: ...

    async def status(self, job_id: str) -> dict[str, Any] | None:
        """None when the job is done and renderable; else a status object ({job_id, status, ...})."""
        ...

    async def render(self, job_id: str, profile: str, cursor: str | None, budget: int) -> RenderedPage: ...

    async def outline(self, job_id: str, profile: str) -> Outline: ...

    async def full_markdown(self, job_id: str, profile: str) -> str: ...

    async def sidecar(self, job_id: str) -> dict[str, Any]: ...

    async def capabilities(self) -> dict[str, Any]: ...

    async def aclose(self) -> None: ...
