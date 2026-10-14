"""The conversion child's process limit (S3, D-0047): RLIMIT_NPROC counts every thread of the uid on the
host kernel, across containers, so under a cgroup pids limit the child relies on that instead."""

from __future__ import annotations

from pathlib import Path

from ezmd_api import isolation


def test_cgroup_pids_limit_replaces_rlimit_nproc(tmp_path: Path) -> None:
    v2 = tmp_path / "pids.max"
    v2.write_text("256\n", encoding="utf-8")
    assert isolation.nproc_limit([v2]) is None


def test_cgroup_v1_path_is_read_too(tmp_path: Path) -> None:
    v1 = tmp_path / "v1" / "pids.max"
    v1.parent.mkdir()
    v1.write_text("512\n", encoding="utf-8")
    assert isolation.nproc_limit([tmp_path / "missing", v1]) is None


def test_unlimited_or_absent_cgroup_falls_back_to_a_backstop(tmp_path: Path) -> None:
    unlimited = tmp_path / "pids.max"
    unlimited.write_text("max\n", encoding="utf-8")
    assert isolation.nproc_limit([unlimited]) == isolation.NPROC_FALLBACK
    assert isolation.nproc_limit([tmp_path / "nope"]) == isolation.NPROC_FALLBACK
    # Magika's numpy/OpenBLAS and ONNX Runtime start a thread per core; 64 failed on a 24-core host.
    assert isolation.NPROC_FALLBACK >= 1024


def test_child_caps_math_library_thread_pools() -> None:
    env: dict[str, str] = {"OMP_NUM_THREADS": "2"}
    isolation.cap_thread_pools(env)
    assert env["OMP_NUM_THREADS"] == "2"  # an operator's choice wins
    for name in ("OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
        assert env[name] == str(isolation.CHILD_THREADS)
