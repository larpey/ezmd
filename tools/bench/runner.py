"""Run one tool over a corpus in an isolated worker process (tools/bench/adapters/worker.py).

The worker loads the tool once (model loading is reported as `startup_seconds`, not per document). For each
document the harness sends one job and waits up to the per-document timeout while a sampler thread polls the
RSS of the worker's whole process tree; the peak during that document is recorded. A document that exceeds the
timeout is recorded as `timeout` and the worker tree is killed; a worker that exits mid-document is recorded as
`crash`. Either way the next document gets a fresh worker, so one bad input cannot take down the run.
"""

from __future__ import annotations

import itertools
import json
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO, Any

import psutil

from tools.bench.config import ROOT, WORKER, Tool, cache_dir
from tools.bench.schema import Doc, DocResult, append_result, read_results
from tools.bench.warmup import warmup_input

_WINDOWS_DOCKER = Path(r"C:\Program Files\Docker\Docker\resources\bin\docker.exe")
CONTAINER_SAMPLE_INTERVAL = 1.0
DEFAULT_TIMEOUT = 300.0
STARTUP_TIMEOUT = 3600.0
"""First start may download model weights."""
SAMPLE_INTERVAL = 0.05
_EOF = object()

QUIET_ENV = {
    # No usage telemetry from any competitor during measurement.
    "DO_NOT_TRACK": "1",
    "HF_HUB_DISABLE_TELEMETRY": "1",
    "SCARF_NO_ANALYTICS": "true",
    "ANONYMIZED_TELEMETRY": "False",
    "MINERU_TELEMETRY": "0",
    "TOKENIZERS_PARALLELISM": "false",
    "PYTHONIOENCODING": "utf-8",
    "PYTHONUTF8": "1",
}


def docker_exe() -> str | None:
    found = shutil.which("docker")
    if found:
        return found
    return str(_WINDOWS_DOCKER) if _WINDOWS_DOCKER.exists() else None


def worker_env(extra: dict[str, str] | None = None) -> dict[str, str]:
    env = dict(os.environ)
    models = cache_dir() / "models"
    env.update(QUIET_ENV)
    env.setdefault("HF_HOME", str(models / "hf"))
    env.setdefault("MODELSCOPE_CACHE", str(models / "modelscope"))
    env.setdefault("TORCH_HOME", str(models / "torch"))
    env.setdefault("XDG_CACHE_HOME", str(models / "xdg"))
    env.setdefault("MODEL_CACHE_DIR", str(models / "marker"))
    docker = docker_exe()
    if docker and not shutil.which("docker"):
        # Marker 2 spawns its VLM server as a Docker container when an NVIDIA GPU is present.
        env["PATH"] = f"{Path(docker).parent}{os.pathsep}{env.get('PATH', '')}"
    env.pop("VIRTUAL_ENV", None)
    for key, value in (extra or {}).items():
        env[key] = value.replace("{cache}", str(cache_dir()))
    return env


def tree_rss(proc: psutil.Process) -> int:
    total = 0
    try:
        procs = [proc, *proc.children(recursive=True)]
    except psutil.Error:
        return 0
    for p in procs:
        try:
            total += p.memory_info().rss
        except psutil.Error:  # noqa: S112 - a child exited between listing and sampling
            continue
    return total


def kill_tree(pid: int) -> None:
    try:
        root = psutil.Process(pid)
        procs = [*root.children(recursive=True), root]
    except psutil.Error:
        return
    for p in procs:
        try:
            p.kill()
        except psutil.Error:  # noqa: S112 - already gone
            continue
    psutil.wait_procs(procs, timeout=10)


_UNITS = {"b": 1, "kib": 2**10, "mib": 2**20, "gib": 2**30, "tib": 2**40, "kb": 10**3, "mb": 10**6, "gb": 10**9}


def parse_mem_usage(text: str) -> int:
    """Bytes from the first half of `docker stats` MemUsage, e.g. "1.5GiB / 31.2GiB"."""
    used = text.split("/", 1)[0].strip()
    num = "".join(ch for ch in used if ch.isdigit() or ch == ".")
    unit = used[len(num) :].strip().lower()
    if not num or unit not in _UNITS:
        raise ValueError(f"unparseable memory usage: {text!r}")
    return int(float(num) * _UNITS[unit])


def container_mem(prefixes: tuple[str, ...]) -> int:
    """Summed memory of running containers whose name starts with one of `prefixes` (0 when none)."""
    docker = docker_exe()
    if not prefixes or not docker:
        return 0
    try:
        out = subprocess.run(
            [docker, "stats", "--no-stream", "--format", "{{.Name}}\t{{.MemUsage}}"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        ).stdout
    except (OSError, subprocess.TimeoutExpired):
        return 0
    total = 0
    for line in out.splitlines():
        name, _, usage = line.partition("\t")
        if name.startswith(prefixes):
            try:
                total += parse_mem_usage(usage)
            except ValueError:  # noqa: S112 - a container that is starting or stopping reports "--"
                continue
    return total


def kill_containers(prefixes: tuple[str, ...]) -> None:
    docker = docker_exe()
    if not prefixes or not docker:
        return
    out = subprocess.run([docker, "ps", "--format", "{{.Names}}"], capture_output=True, text=True, check=False).stdout
    names = [n for n in out.split() if n.startswith(prefixes)]
    if names:
        subprocess.run([docker, "kill", *names], capture_output=True, check=False)


class _Sampler(threading.Thread):
    """Peak memory while one document converts: the worker's process tree plus any of its containers."""

    def __init__(self, pid: int, containers: tuple[str, ...] = ()) -> None:
        super().__init__(daemon=True)
        self._proc = psutil.Process(pid)
        self._containers = containers
        self._halt = threading.Event()
        self.peak = 0
        self._container_peak = 0
        self._poller: threading.Thread | None = None

    def _poll_containers(self) -> None:
        while not self._halt.is_set():
            self._container_peak = max(self._container_peak, container_mem(self._containers))
            self._halt.wait(CONTAINER_SAMPLE_INTERVAL)

    def run(self) -> None:
        if self._containers:
            self._poller = threading.Thread(target=self._poll_containers, daemon=True)
            self._poller.start()
        while not self._halt.is_set():
            self.peak = max(self.peak, tree_rss(self._proc))
            self._halt.wait(SAMPLE_INTERVAL)

    def stop(self) -> int:
        self._halt.set()
        self.join(timeout=5)
        if self._poller is not None:
            self._poller.join(timeout=35)
        self.peak = max(self.peak, tree_rss(self._proc))
        return self.peak + self._container_peak


@dataclass(frozen=True, slots=True)
class Reply:
    kind: str  # "message" | "timeout" | "eof"
    data: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class Launch:
    """How to start a tool's worker: the command, extra environment, how host paths appear to the worker,
    and the name prefixes of Docker containers whose memory counts toward the tool's peak."""

    command: list[str]
    env: dict[str, str] = field(default_factory=dict)
    path_map: tuple[tuple[str, str], ...] = ()
    containers: tuple[str, ...] = ()

    def map_path(self, path: Path) -> str:
        resolved = str(path.resolve())
        for host, inner in self.path_map:
            if resolved.lower().startswith(host.lower()):
                return inner + resolved[len(host) :].replace("\\", "/")
        return str(path)


class Worker:
    """One live worker process for a tool."""

    def __init__(self, launch: Launch, log: Path) -> None:
        self.launch = launch
        self.log = log
        self.proc: subprocess.Popen[str] | None = None
        self._lines: queue.Queue[object] = queue.Queue()
        self.version = ""
        self.startup_seconds = 0.0
        self.warmup_error: str | None = None

    def start(self, timeout: float | None = None) -> None:
        self.log.parent.mkdir(parents=True, exist_ok=True)
        err: IO[str] = self.log.open("a", encoding="utf-8", errors="replace")
        workdir = cache_dir()
        workdir.mkdir(parents=True, exist_ok=True)
        self.proc = subprocess.Popen(
            self.launch.command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=err,
            text=True,
            encoding="utf-8",
            env=worker_env(self.launch.env),
            cwd=str(workdir),
        )
        self._lines = queue.Queue()
        threading.Thread(target=self._pump, args=(self.proc.stdout, self._lines), daemon=True).start()
        reply = self._read(STARTUP_TIMEOUT if timeout is None else timeout)
        if reply.kind != "message" or not reply.data or not reply.data.get("ready"):
            detail = reply.data if reply.data else reply.kind
            self.stop()
            raise RuntimeError(f"worker failed to start: {detail}")
        self.version = str(reply.data.get("version", ""))
        self.startup_seconds = float(reply.data.get("startup_seconds", 0.0))
        self.warmup_error = reply.data.get("warmup_error")

    @staticmethod
    def _pump(stream: IO[str] | None, sink: queue.Queue[object]) -> None:
        if stream is None:
            sink.put(_EOF)
            return
        for line in stream:
            line = line.strip()
            if line:
                try:
                    sink.put(json.loads(line))
                except json.JSONDecodeError:  # noqa: S112 - only protocol lines are JSON
                    continue
        sink.put(_EOF)

    def _read(self, timeout: float) -> Reply:
        try:
            item = self._lines.get(timeout=timeout)
        except queue.Empty:
            return Reply("timeout")
        if item is _EOF:
            return Reply("eof")
        assert isinstance(item, dict)
        return Reply("message", item)

    @property
    def alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def convert(self, job_id: str, src: Path, dst: Path, timeout: float) -> tuple[Reply, float, int]:
        """Send one job; return the reply, harness-measured wall seconds and peak memory in bytes."""
        assert self.proc is not None and self.proc.stdin is not None
        sampler = _Sampler(self.proc.pid, self.launch.containers)
        sampler.start()
        job = {"id": job_id, "input": self.launch.map_path(src), "output": self.launch.map_path(dst)}
        t0 = time.perf_counter()
        try:
            self.proc.stdin.write(json.dumps(job) + "\n")
            self.proc.stdin.flush()
        except OSError:
            sampler.stop()
            return Reply("eof"), time.perf_counter() - t0, 0
        reply = self._read(timeout)
        wall = time.perf_counter() - t0
        return reply, wall, sampler.stop()

    def stop(self) -> None:
        if self.proc is None:
            return
        if self.proc.poll() is None:
            kill_tree(self.proc.pid)
        kill_containers(self.launch.containers)
        self.proc = None


_LAUNCHES = itertools.count(1)


def worker_launch(tool: Tool, pandoc: Path | None = None) -> Launch:
    env = {str(k): str(v) for k, v in dict(tool.extra.get("env", {})).items()}
    containers = tuple(str(c) for c in tool.extra.get("containers", ()))
    warm = warmup_input(tool)
    if tool.kind == "binary":
        # The pandoc adapter is pure stdlib; it runs under the harness's own interpreter.
        cmd = [sys.executable, "-I", str(WORKER), "--adapter", tool.adapter, "--pandoc", str(pandoc or "")]
        return Launch([*cmd, "--warmup", str(warm or "")], env)
    if tool.kind == "docker":
        docker = docker_exe()
        if docker is None:
            raise RuntimeError("docker not found")
        name = f"ezmd-bench-{tool.name}-{os.getpid()}-{next(_LAUNCHES)}"
        mounts = (
            (ROOT, "/repo", "ro"),
            (cache_dir() / "corpora", "/cache/corpora", "ro"),
            (cache_dir() / "runs", "/cache/runs", "rw"),
        )
        path_map = tuple((str(h.resolve()), inner) for h, inner, _ in mounts)
        launch = Launch([], {}, path_map, (name, *containers))
        cmd = [docker, "run", "-i", "--rm", "--name", name]
        for host, inner, mode in mounts:
            cmd += ["-v", f"{host.resolve()}:{inner}:{mode}"]
        for k, v in {**QUIET_ENV, **env}.items():
            cmd += ["-e", f"{k}={v}"]
        cmd += [str(tool.extra["image"]), str(tool.extra.get("python", "python3")), "-I"]
        cmd += ["/repo/tools/bench/adapters/worker.py", "--adapter", tool.adapter]
        cmd += ["--warmup", launch.map_path(warm) if warm else ""]
        return Launch(cmd, {}, path_map, launch.containers)
    cmd = [str(tool.python), "-I", str(WORKER), "--adapter", tool.adapter, "--warmup", str(warm or "")]
    return Launch(cmd, env, (), containers)


def doc_output(run_dir: Path, tool: str, doc: Doc) -> Path:
    return run_dir / tool / f"{doc.id}.md"


def run_tool(
    tool: Tool,
    docs: Iterable[Doc],
    run_dir: Path,
    *,
    timeout: float = DEFAULT_TIMEOUT,
    pandoc: Path | None = None,
    launch: Launch | None = None,
) -> Iterator[DocResult]:
    """Convert every document the tool supports; yields (and appends to results.jsonl) one result per doc.

    Documents already recorded for this tool in `run_dir/results.jsonl` are skipped, so an interrupted run
    resumes where it stopped."""
    results_path = run_dir / "results.jsonl"
    done = {(r.tool, r.doc_id) for r in read_results(results_path)}
    worker: Worker | None = None
    log = run_dir / "logs" / f"{tool.name}.log"
    meta_path = run_dir / "logs" / f"{tool.name}.startup.jsonl"
    version = ""
    try:
        for doc in docs:
            if (tool.name, doc.id) in done:
                continue
            if not tool.supports(doc.input.suffix):
                result = DocResult(doc.corpus, doc.id, doc.category, tool.name, version, "unsupported")
                append_result(results_path, result)
                yield result
                continue
            if worker is None or not worker.alive:
                worker = Worker(launch or worker_launch(tool, pandoc), log)
                try:
                    worker.start()
                except RuntimeError as exc:
                    result = DocResult(
                        doc.corpus,
                        doc.id,
                        doc.category,
                        tool.name,
                        version,
                        "crash",
                        error_class="StartupError",
                        error=str(exc)[:2000],
                    )
                    append_result(results_path, result)
                    yield result
                    worker = None
                    continue
                version = worker.version
                meta_path.parent.mkdir(parents=True, exist_ok=True)
                with meta_path.open("a", encoding="utf-8") as fh:
                    rec = {"version": version, "startup_seconds": worker.startup_seconds}
                    fh.write(json.dumps({**rec, "warmup_error": worker.warmup_error}) + "\n")
            dst = doc_output(run_dir, tool.name, doc)
            reply, wall, peak = worker.convert(doc.id, doc.input, dst, timeout)
            result = _result(doc, tool.name, version, reply, wall, peak, dst, run_dir, timeout)
            if reply.kind != "message":
                worker.stop()
                worker = None
            append_result(results_path, result)
            yield result
    finally:
        if worker is not None:
            worker.stop()


def _result(
    doc: Doc, tool: str, version: str, reply: Reply, wall: float, peak: int, dst: Path, run_dir: Path, timeout: float
) -> DocResult:
    def make(status: str, **kw: Any) -> DocResult:
        rss = round(peak / 2**20, 1) if peak else None
        return DocResult(
            doc.corpus, doc.id, doc.category, tool, version, status, seconds=round(wall, 3), peak_rss_mb=rss, **kw
        )

    if reply.kind == "timeout":
        return make("timeout", error_class="Timeout", error=f"exceeded {timeout:.0f}s")
    if reply.kind == "eof" or reply.data is None:
        return make("crash", error_class="WorkerExited", error="worker process exited during conversion")
    data = reply.data
    if data.get("ok"):
        return make("ok", output=dst.relative_to(run_dir).as_posix(), chars=int(data.get("chars", 0)))
    return make("error", error_class=str(data.get("error_class")), error=str(data.get("error", ""))[:2000])
