"""`--remote URL`: run a conversion on an intomd instance over the REST API (docs/spec/part3.md).

Flow: `POST /v1/convert?wait=30&format=json` (multipart upload for files and stdin, a JSON body for
URLs). A 200 carrying `X-Intomd-Job` is the finished result; a 202 envelope means the job is still
running, so poll `GET /v1/jobs/{id}` and then fetch `GET /v1/jobs/{id}/result`. Every request sends
`User-Agent: intomd-cli/<version>` and, when configured, `X-API-Key`. No conversion logic lives here.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from pathlib import Path
from typing import IO, Any

import httpx

from intomd import __version__
from intomd.cli.exitcodes import RemoteError
from intomd.cli.output import Outcome, ProgressSink, safe_stem

__all__ = ["USER_AGENT", "RemoteClient"]

USER_AGENT = f"intomd-cli/{__version__}"
WAIT_SECONDS = 30
POLL_INTERVAL = 0.5
POLL_TIMEOUT = 3600.0
TERMINAL = ("done", "failed", "needs_user_action", "expired")


def _no_transport() -> httpx.BaseTransport | None:
    return None


transport_factory: Callable[[], httpx.BaseTransport | None] = _no_transport
"""Tests replace this with a factory returning `httpx.MockTransport`."""
sleep: Callable[[float], None] = time.sleep


def _is_url(s: str) -> bool:
    return s.startswith(("http://", "https://"))


def _error_from(resp: httpx.Response) -> RemoteError:
    code, message = f"http_{resp.status_code}", f"The instance answered HTTP {resp.status_code}."
    try:
        body = resp.json()
    except ValueError:
        body = None
    if isinstance(body, dict) and isinstance(body.get("error"), dict):
        err = body["error"]
        code = str(err.get("code") or code)
        message = str(err.get("message") or message)
    return RemoteError(code, message, status=resp.status_code)


class RemoteClient:
    def __init__(self, base_url: str, api_key: str = "", *, timeout: float = WAIT_SECONDS + 30) -> None:
        base = base_url.strip().rstrip("/")
        if not _is_url(base):
            raise ValueError(f"--remote must be an http(s) URL, got {base_url!r}")
        headers = {"User-Agent": USER_AGENT}
        if api_key:
            headers["X-API-Key"] = api_key
        self._client = httpx.Client(
            base_url=base, headers=headers, timeout=timeout, transport=transport_factory(), follow_redirects=False
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> RemoteClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _request(self, method: str, url: str, **kw: Any) -> httpx.Response:
        try:
            resp = self._client.request(method, url, **kw)
        except httpx.HTTPError as e:
            raise RemoteError("remote_unreachable", f"Could not reach the instance: {type(e).__name__}.") from e
        if resp.status_code >= 400:
            raise _error_from(resp)
        return resp

    def capabilities(self) -> dict[str, object]:
        data = self._request("GET", "/v1/capabilities").json()
        if not isinstance(data, dict):
            raise RemoteError("bad_response", "The instance returned malformed capabilities.")
        return data

    def convert(
        self,
        source: str,
        *,
        profile: str,
        fmt: str,
        options: dict[str, object],
        stdin: IO[bytes] | None = None,
        max_bytes: int = 100 * 1024 * 1024,
        progress: ProgressSink | None = None,
    ) -> Outcome:
        sink = progress or (lambda stage, fraction, message: None)
        params = {"wait": WAIT_SECONDS, "format": "json"}
        if _is_url(source):
            body = {"url": source, "profile": profile, "options": options}
            resp = self._request("POST", "/v1/convert", params=params, json=body)
        else:
            name, data = _read_source(source, stdin, max_bytes)
            files = {"file": (name, data, "application/octet-stream")}
            form = {"options": json.dumps(options), "profile": profile}
            resp = self._request("POST", "/v1/convert", params=params, files=files, data=form)
        header = resp.headers.get("x-intomd-job")
        if resp.status_code == 200 and header:
            job_id = str(json.loads(header).get("id", ""))
            payload = resp.json()
        else:
            job_id = self._job_id(resp)
            self._poll(job_id, sink)
            payload = self._request("GET", f"/v1/jobs/{job_id}/result", params={"format": "json", "profile": profile})
            payload = payload.json()
        if not isinstance(payload, dict):
            raise RemoteError("bad_response", "The instance returned a malformed result.")
        text = self._text(job_id, payload, profile, fmt)
        return _outcome(source, payload, text, profile, fmt)

    def _job_id(self, resp: httpx.Response) -> str:
        try:
            env = resp.json()
            job_id = str(env["job"]["id"])
        except (ValueError, KeyError, TypeError) as e:
            raise RemoteError("bad_response", "The instance returned a malformed job envelope.") from e
        return job_id

    def _poll(self, job_id: str, sink: ProgressSink) -> None:
        deadline = time.monotonic() + POLL_TIMEOUT
        while True:
            job = self._request("GET", f"/v1/jobs/{job_id}").json()
            state = str(job.get("state", ""))
            prog = job.get("progress")
            sink(state, float(prog) if isinstance(prog, (int, float)) else None, str(job.get("stage_message") or ""))
            if state == "done":
                return
            if state == "failed":
                err = job.get("error") or {}
                raise RemoteError(str(err.get("code") or "conversion_failed"), str(err.get("message") or "Failed."))
            if state == "needs_user_action":
                raise RemoteError("needs_user_action", "The instance needs a file or captions supplied for this job.")
            if state == "expired":
                raise RemoteError("expired", "The job expired before it finished.")
            if time.monotonic() > deadline:
                raise RemoteError("timeout", f"Gave up waiting for job {job_id}.")
            sleep(POLL_INTERVAL)

    def _text(self, job_id: str, payload: dict[str, Any], profile: str, fmt: str) -> str:
        if fmt == "json":
            return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        if fmt == "txt":
            if not job_id:
                raise RemoteError("bad_response", "The instance did not report a job id.")
            resp = self._request("GET", f"/v1/jobs/{job_id}/result", params={"format": "txt", "profile": profile})
            return resp.text
        return str(payload.get("markdown") or "")


def _read_source(source: str, stdin: IO[bytes] | None, max_bytes: int) -> tuple[str, bytes]:
    from intomd.inputs import InputTooLarge

    if source == "-":
        if stdin is None:
            raise ValueError("no stdin available")
        data = stdin.read(max_bytes + 1)
        name = "stdin"
    else:
        p = Path(source)
        if not p.is_file():
            raise FileNotFoundError(source)
        if p.stat().st_size > max_bytes:
            raise InputTooLarge(f"{source} is larger than {max_bytes} bytes")
        data = p.read_bytes()
        name = p.name
    if len(data) > max_bytes:
        raise InputTooLarge(f"input is larger than {max_bytes} bytes")
    return name, data


def _warnings(payload: dict[str, Any]) -> list[dict[str, object]]:
    sidecar = payload.get("sidecar")
    if isinstance(sidecar, dict) and isinstance(sidecar.get("warnings"), list):
        return [w for w in sidecar["warnings"] if isinstance(w, dict)]
    from intomd.warnings.codes import CODES, WarningKind

    out: list[dict[str, object]] = []
    front = payload.get("frontmatter") or {}
    for code in front.get("warnings") or [] if isinstance(front, dict) else []:
        try:
            spec = CODES[WarningKind(str(code))]
            out.append({"kind": str(code), "severity": spec.severity, "message": spec.description})
        except ValueError:
            out.append({"kind": str(code), "severity": "warning", "message": ""})
    return out


def _outcome(source: str, payload: dict[str, Any], text: str, profile: str, fmt: str) -> Outcome:
    front = payload.get("frontmatter")
    front = dict(front) if isinstance(front, dict) else {}
    sidecar = payload.get("sidecar")
    tokens = front.get("tokens")
    tail = source.split("?", 1)[0].rstrip("/")
    return Outcome(
        source=source,
        text=text,
        profile=profile,
        format=fmt,
        frontmatter=front,
        sidecar=dict(sidecar) if isinstance(sidecar, dict) else None,
        warnings=_warnings(payload),
        tokens=int(tokens) if isinstance(tokens, int) else 0,
        truncated=bool(front.get("truncated", False)),
        stem=safe_stem(Path(tail).stem) or "output",
    )
