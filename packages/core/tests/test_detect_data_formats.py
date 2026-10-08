"""Detection of notebooks, SQLite databases and Parquet files (converter-family request, P1-core-renderer)."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from ezmd.detect import _MAGIKA_LABEL_MIMES, detect, extension_mime, is_textual, normalize_mime
from ezmd.inputs import InputRef

NOTEBOOK = {
    "cells": [
        {"cell_type": "markdown", "metadata": {}, "source": ["# Analysis\n", "Some notes about the data."]},
        {
            "cell_type": "code",
            "execution_count": 1,
            "metadata": {},
            "outputs": [],
            "source": ["import os\n", "print(os.getcwd())\n"],
        },
    ],
    "metadata": {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python"},
    },
    "nbformat": 4,
    "nbformat_minor": 5,
}


@pytest.mark.parametrize(
    ("name", "mime"),
    [
        ("a.ipynb", "application/x-ipynb+json"),
        ("a.sqlite", "application/vnd.sqlite3"),
        ("a.sqlite3", "application/vnd.sqlite3"),
        ("a.db", "application/vnd.sqlite3"),
        ("a.parquet", "application/vnd.apache.parquet"),
    ],
)
def test_extension_mimes(name: str, mime: str) -> None:
    assert extension_mime(name) == mime


def test_magika_labels_and_aliases() -> None:
    assert _MAGIKA_LABEL_MIMES["ipynb"] == "application/x-ipynb+json"
    assert _MAGIKA_LABEL_MIMES["sqlite"] == "application/vnd.sqlite3"
    assert _MAGIKA_LABEL_MIMES["parquet"] == "application/vnd.apache.parquet"
    assert normalize_mime("application/x-sqlite3") == "application/vnd.sqlite3"


def test_textual_only_where_textual() -> None:
    assert is_textual("application/x-ipynb+json")
    assert not is_textual("application/vnd.sqlite3")
    assert not is_textual("application/vnd.apache.parquet")


def test_notebook_detects_as_ipynb_without_misnamed_condition(tmp_path: Path) -> None:
    path = tmp_path / "analysis.ipynb"
    path.write_text(json.dumps(NOTEBOOK, indent=1), encoding="utf-8", newline="\n")
    ref = InputRef.from_path(path)
    d = detect(ref)
    assert d.mime == "application/x-ipynb+json"
    # The pipeline warns misnamed_file only when the extension mime differs from the detected mime.
    assert d.extension_mime == d.mime


def test_sqlite_detects_by_content(tmp_path: Path) -> None:
    path = tmp_path / "data.bin"
    con = sqlite3.connect(path)
    try:
        con.execute("create table t (a integer)")
        con.execute("insert into t values (1)")
        con.commit()
    finally:
        con.close()
    ref = InputRef.from_path(path)
    assert detect(ref).mime == "application/vnd.sqlite3"
