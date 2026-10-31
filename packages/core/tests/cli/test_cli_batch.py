"""`ezmd batch` (docs/internal/spec/part4.md 4.2.2 item 2 and the idempotency acceptance criterion)."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from typer.testing import CliRunner

from ezmd.cli import app
from ezmd.cli.batch import default_workers

runner = CliRunner()
ELF = bytes([0x7F]) + b"ELF" + bytes([2, 1, 1, 0]) + bytes(8) + bytes([2, 0, 0x3E, 0]) + bytes(200)


def _tree(root: Path, n: int = 3) -> Path:
    src = root / "in"
    (src / "sub").mkdir(parents=True)
    for i in range(n):
        (src / f"note{i}.txt").write_text(f"Note {i}\n=======\n\nbody {i}\n", encoding="utf-8", newline="\n")
    (src / "sub" / "deep.md").write_text("# Deep\n\ntext\n", encoding="utf-8", newline="\n")
    (src / ".hidden.txt").write_text("secret", encoding="utf-8")
    return src


def _manifest(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_mirrors_tree_and_writes_manifest(tmp_path: Path) -> None:
    src, out = _tree(tmp_path), tmp_path / "out"
    res = runner.invoke(app, ["batch", str(src), "--out", str(out), "--recursive", "--workers", "1"])
    assert res.exit_code == 0, res.output
    assert (out / "note0.md").is_file() and (out / "sub" / "deep.md").is_file()
    assert (out / "sub" / "deep.ezmd.json").is_file()
    assert not (out / ".hidden.md").exists()
    lines = _manifest(out / "manifest.jsonl")
    assert len(lines) == 4
    assert {"path", "status", "out", "warnings", "seconds", "tokens", "sha256"} <= set(lines[0])
    assert all(r["status"] == "converted" for r in lines)
    assert "converted" in res.stderr and "total tokens" in res.stderr


DOCX_WITH_PICTURE = Path(__file__).resolve().parents[4] / "fixtures" / "office" / "docx-lists-restart" / "input.docx"


def test_image_dir_gets_one_folder_per_input(tmp_path: Path) -> None:
    """`--image-dir` (#32): each input's images go under `<image-dir>/<its relative stem>/images/`, so two
    documents that both carry `image1.png` cannot overwrite each other, and links resolve from each .md."""
    src, out, img = tmp_path / "in", tmp_path / "out", tmp_path / "img"
    (src / "a").mkdir(parents=True)
    (src / "a" / "guide.docx").write_bytes(DOCX_WITH_PICTURE.read_bytes())
    (src / "guide.docx").write_bytes(DOCX_WITH_PICTURE.read_bytes())
    args = ["batch", str(src), "--out", str(out), "--image-dir", str(img), "-r", "-w", "1", "--json"]
    res = runner.invoke(app, args)
    assert res.exit_code == 0, res.output
    assert (img / "a" / "guide" / "images" / "plan.png").is_file()
    assert (img / "guide" / "images" / "plan.png").is_file()
    assert "](../../img/a/guide/images/plan.png)" in (out / "a" / "guide.md").read_text(encoding="utf-8")
    assert "](../img/guide/images/plan.png)" in (out / "guide.md").read_text(encoding="utf-8")


def _one_docx(tmp_path: Path) -> tuple[Path, list[str]]:
    src = tmp_path / "in"
    src.mkdir()
    (src / "guide.docx").write_bytes(DOCX_WITH_PICTURE.read_bytes())
    return src, ["batch", str(src), "--out", str(tmp_path / "out"), "-r", "-w", "1", "--json"]


def test_adding_or_dropping_image_dir_reconverts(tmp_path: Path) -> None:
    """The manifest records the image directory, so a re-run that adds, keeps or drops `--image-dir` converts
    exactly when the directory changed: the first run wrote no images, so a skip would leave none."""
    _, plain = _one_docx(tmp_path)
    with_images = [*plain, "--image-dir", str(tmp_path / "pics")]
    assert json.loads(runner.invoke(app, plain).stdout)["converted"] == 1
    first = json.loads(runner.invoke(app, with_images).stdout)
    assert first["converted"] == 1 and first["skipped"] == 0
    assert (tmp_path / "pics" / "guide" / "images" / "plan.png").is_file()
    second = json.loads(runner.invoke(app, with_images).stdout)
    assert second["skipped"] == 1 and second["converted"] == 0
    assert json.loads(runner.invoke(app, plain).stdout)["converted"] == 1
    assert "](word/media/plan.png)" in (tmp_path / "out" / "guide.md").read_text(encoding="utf-8")


def test_image_tree_inside_the_inputs_is_never_an_input(tmp_path: Path) -> None:
    src, plain = _one_docx(tmp_path)
    with_images = [*plain, "--image-dir", str(src / "pics")]
    assert json.loads(runner.invoke(app, with_images).stdout)["total"] == 1
    assert (src / "pics" / "guide" / "images" / "plan.png").is_file()
    second = json.loads(runner.invoke(app, with_images).stdout)
    assert second["total"] == 1 and second["skipped"] == 1


def test_non_recursive_skips_subdirs(tmp_path: Path) -> None:
    src, out = _tree(tmp_path), tmp_path / "out"
    res = runner.invoke(app, ["batch", str(src), "--out", str(out), "--workers", "1", "--json"])
    assert res.exit_code == 0, res.output
    assert json.loads(res.stdout)["converted"] == 3
    assert not (out / "sub").exists()


def test_second_run_skips_everything_quickly(tmp_path: Path) -> None:
    src, out = _tree(tmp_path, n=100), tmp_path / "out"
    first = runner.invoke(app, ["batch", str(src), "--out", str(out), "-r", "-w", "1", "--json"])
    assert first.exit_code == 0, first.output
    assert json.loads(first.stdout)["converted"] == 101
    start = time.perf_counter()
    second = runner.invoke(app, ["batch", str(src), "--out", str(out), "-r", "-w", "1", "--json"])
    elapsed = time.perf_counter() - start
    assert second.exit_code == 0, second.output
    summary = json.loads(second.stdout)
    assert summary["skipped"] == 101 and summary["converted"] == 0
    assert elapsed < 5.0, f"skip-only re-run of 101 files took {elapsed:.2f}s"  # spec: under 1 s per 100


def test_changed_input_is_reconverted_and_sidecar_alone_skips(tmp_path: Path) -> None:
    src, out = _tree(tmp_path, n=2), tmp_path / "out"
    args = ["batch", str(src), "--out", str(out), "-w", "1", "--json"]
    assert runner.invoke(app, args).exit_code == 0
    (src / "note1.txt").write_text("Changed\n=======\n\nnew\n", encoding="utf-8")
    (out / "manifest.jsonl").unlink()  # only the sidecars remain as the record of the first run
    summary = json.loads(runner.invoke(app, args).stdout)
    assert summary["skipped"] == 1 and summary["converted"] == 1
    assert "new" in (out / "note1.md").read_text(encoding="utf-8")


def test_profile_change_reconverts(tmp_path: Path) -> None:
    src, out = _tree(tmp_path, n=1), tmp_path / "out"
    base = ["batch", str(src), "--out", str(out), "-w", "1", "--json"]
    assert runner.invoke(app, base).exit_code == 0
    summary = json.loads(runner.invoke(app, [*base, "--profile", "compact"]).stdout)
    assert summary["converted"] == 1


def test_failure_exit_codes(tmp_path: Path) -> None:
    src, out = _tree(tmp_path, n=2), tmp_path / "out"
    (src / "a_bad.pdf").write_bytes(ELF)
    stop = runner.invoke(app, ["batch", str(src), "--out", str(out), "-w", "1", "--json"])
    assert stop.exit_code == 1
    summary = json.loads(stop.stdout)
    assert summary["failed"] == 1 and summary["cancelled"] == 2
    keep = runner.invoke(app, ["batch", str(src), "--out", str(out), "-w", "1", "--continue-on-error", "--json"])
    assert keep.exit_code == 3
    summary = json.loads(keep.stdout)
    assert summary["failed"] == 1 and summary["converted"] == 2
    bad = next(r for r in summary["files"] if r["status"] == "failed")
    assert bad["warnings"][0]["severity"] == "error" and bad["out"] is None


def test_process_pool(tmp_path: Path) -> None:
    src, out = _tree(tmp_path, n=3), tmp_path / "out"
    res = runner.invoke(app, ["batch", str(src), "--out", str(out), "-r", "--workers", "2", "--json"])
    assert res.exit_code == 0, res.output
    assert json.loads(res.stdout)["converted"] == 4


def test_glob_input(tmp_path: Path) -> None:
    src, out = _tree(tmp_path, n=2), tmp_path / "out"
    res = runner.invoke(app, ["batch", (src / "*.txt").as_posix(), "--out", str(out), "-w", "1", "--json"])
    assert res.exit_code == 0, res.output
    assert json.loads(res.stdout)["converted"] == 2 and (out / "note1.md").is_file()


def test_stem_collisions_keep_full_names(tmp_path: Path) -> None:
    src, out = tmp_path / "in", tmp_path / "out"
    src.mkdir()
    (src / "a.txt").write_text("one\n", encoding="utf-8")
    (src / "a.md").write_text("# two\n", encoding="utf-8")
    assert runner.invoke(app, ["batch", str(src), "--out", str(out), "-w", "1"]).exit_code == 0
    assert (out / "a.txt.md").is_file() and (out / "a.md.md").is_file()


def test_out_inside_input_is_not_reread(tmp_path: Path) -> None:
    src = _tree(tmp_path, n=1)
    args = ["batch", str(src), "--out", str(src), "-w", "1", "--json"]
    assert json.loads(runner.invoke(app, args).stdout)["converted"] == 1
    second = json.loads(runner.invoke(app, args).stdout)
    assert second["skipped"] == 1 and second["total"] == 1


def test_bad_arguments(tmp_path: Path) -> None:
    assert runner.invoke(app, ["batch", str(tmp_path / "missing"), "--out", str(tmp_path)]).exit_code == 2
    assert runner.invoke(app, ["batch", str(tmp_path)]).exit_code == 2  # no --out and no config out_dir
    assert runner.invoke(app, ["batch", str(tmp_path), "--out", str(tmp_path), "-f", "docx"]).exit_code == 2


def test_default_workers_bounds() -> None:
    assert 1 <= default_workers() <= 8


def test_parallel_batch_stops_dispatching_at_the_first_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Without --continue-on-error, a failure stops new work: only jobs already running finish. Before, every
    job was submitted to the pool up front and the ones a worker had already taken could not be cancelled."""
    import threading
    from concurrent.futures import ThreadPoolExecutor

    from ezmd.cli import batch as batch_mod

    mp = monkeypatch
    started: list[str] = []
    release = threading.Event()

    def fake_job(job: batch_mod.Job) -> dict[str, object]:
        started.append(Path(job.src).name)
        if Path(job.src).name.startswith("a_bad"):
            return {"path": job.src, "status": "failed", "out": None, "warnings": [], "tokens": 0,
                    "error": {"code": "conversion_failed", "message": "boom", "exit_code": 1}}  # fmt: skip
        release.wait(5)
        return {"path": job.src, "status": "converted", "out": job.out, "warnings": [], "tokens": 1}

    # a pool that starts everything it is given at once, like a process pool whose workers already took them
    mp.setattr(batch_mod, "ProcessPoolExecutor", lambda max_workers, mp_context: ThreadPoolExecutor(max_workers=32))
    mp.setattr(batch_mod, "convert_job", fake_job)
    src, out = _tree(tmp_path, n=6), tmp_path / "out"
    (src / "a_bad.pdf").write_bytes(ELF)
    timer = threading.Timer(0.5, release.set)
    timer.start()
    res = runner.invoke(app, ["batch", str(src), "--out", str(out), "-w", "2", "--json"])
    timer.cancel()
    release.set()
    summary = json.loads(res.stdout)
    assert res.exit_code == 1
    assert len(started) == 2, started  # the failing job and the one running beside it
    assert summary["failed"] == 1 and summary["converted"] == 1 and summary["cancelled"] == 5


def test_stopped_batch_says_so_in_the_table(tmp_path: Path) -> None:
    src, out = _tree(tmp_path, n=2), tmp_path / "out"
    (src / "a_bad.pdf").write_bytes(ELF)
    res = runner.invoke(app, ["batch", str(src), "--out", str(out), "-w", "1"], env={"COLUMNS": "200"})
    assert res.exit_code == 1
    assert "cancelled" in res.stderr and "--continue-on-error" in res.stderr


def test_quiet_silences_third_party_progress_bars(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Docling's model load prints tqdm "Loading weights" bars; -q turns them off for convert and batch."""
    import os

    mp = monkeypatch
    for cmd in (["convert", str(_tree(tmp_path / "c", 1) / "note0.txt"), "-q"],
                ["batch", str(_tree(tmp_path / "b", 1)), "--out", str(tmp_path / "o"), "-w", "1", "-q"]):  # fmt: skip
        mp.delenv("TQDM_DISABLE", raising=False)
        mp.delenv("HF_HUB_DISABLE_PROGRESS_BARS", raising=False)
        assert runner.invoke(app, cmd).exit_code == 0
        assert os.environ.get("TQDM_DISABLE") == "1" and os.environ.get("HF_HUB_DISABLE_PROGRESS_BARS") == "1"
