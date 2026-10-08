"""pytest plugin: one test per golden fixture under `fixtures/` (loaded via `-p ezmd.testing.pytest_fixtures`).

Collected only when pytest is pointed at the fixtures directory (or a path inside it), so ordinary
unit-test runs do not convert the whole corpus.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from ezmd.testing.fixtures import Fixture

# Everything from ezmd is imported lazily: this plugin is loaded with `-p` before pytest-cov starts
# measuring, so a module-level import would hide ezmd's module-level code from coverage.


class FixtureItem(pytest.Item):
    def __init__(self, *, fixture: Fixture, root: Path, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.fx = fixture
        self.root = root

    def runtest(self) -> None:
        from ezmd.testing.fixtures import run_fixture

        reason = self.fx.skip_reason
        if reason:
            pytest.skip(f"{self.fx.id}: {reason}")
        run = run_fixture(self.fx, self.root)
        if run.hard_failures:
            raise FixtureFailure("; ".join(run.hard_failures))
        assert run.score is not None
        if run.score.overall < run.threshold:
            raise FixtureFailure(f"score {run.score.as_dict()} below threshold {run.threshold}")
        self.user_properties.append(("score", run.score.as_dict()))

    def repr_failure(self, excinfo: pytest.ExceptionInfo[BaseException], style: Any = None) -> str:
        if isinstance(excinfo.value, FixtureFailure):
            return f"{self.fx.id} [{self.fx.converter}]: {excinfo.value}"
        return str(super().repr_failure(excinfo))

    def reportinfo(self) -> tuple[Path, int, str]:
        return self.fx.path, 0, f"fixture {self.fx.id}"


class FixtureFailure(Exception):
    pass


class FixtureFile(pytest.File):
    def collect(self) -> Iterator[FixtureItem]:
        from ezmd.testing.fixtures import discover

        root = self.path.parent
        for fx in discover(root):
            yield FixtureItem.from_parent(self, name=fx.id, fixture=fx, root=root)


def pytest_collect_file(parent: pytest.Collector, file_path: Path) -> pytest.Collector | None:
    if file_path.name == "thresholds.toml" and file_path.parent.name == "fixtures":
        from ezmd.testing.fixtures import fixtures_root

        try:
            fixtures_root(file_path.parent)
        except Exception:
            return None
        return FixtureFile.from_parent(parent, path=file_path)
    return None
