"""REST options vs `intomd.library.Options`: they cannot drift (P1-T10)."""

from __future__ import annotations

import dataclasses
from typing import Any

import pytest
from pydantic import ValidationError

from intomd.library import Options
from intomd.registry import ConvertOptions
from intomd_api.options import (
    API_TIGHTENING,
    CLIENT_FIELDS,
    FIELD_DOCS,
    SERVER_FIELDS,
    ConvertOptionsIn,
    to_convert_options,
    validate_client_options,
)


def test_every_library_option_is_classified() -> None:
    library = set(Options.model_fields)
    client, server = set(CLIENT_FIELDS), set(SERVER_FIELDS)
    assert not client & server, "a field cannot be both client-settable and server-controlled"
    assert sorted(library - client - server) == [], "new Options field: add it to CLIENT_FIELDS or SERVER_FIELDS"
    assert sorted((client | server) - library) == [], "classified field no longer exists in Options"


def test_rest_model_mirrors_library_types_and_constraints() -> None:
    assert list(ConvertOptionsIn.model_fields) == list(CLIENT_FIELDS)
    for name in CLIENT_FIELDS:
        lib = Options.model_fields[name]
        rest = ConvertOptionsIn.model_fields[name]
        assert rest.annotation == (lib.annotation | None), name
        assert rest.default is None, name
        for constraint in lib.metadata:
            assert constraint in rest.metadata, f"{name}: library constraint {constraint!r} missing"
        for extra in API_TIGHTENING.get(name, ()):
            assert extra in rest.metadata, name
        assert rest.description == FIELD_DOCS[name][0]
    assert ConvertOptionsIn.model_config.get("extra") == "forbid"


def test_client_fields_reach_convert_options() -> None:
    known = {f.name for f in dataclasses.fields(ConvertOptions)}
    for name in CLIENT_FIELDS:
        assert name in known, f"{name} is accepted over REST but ConvertOptions has no such field"


def test_example_values_round_trip_into_the_library() -> None:
    sample = {name: FIELD_DOCS[name][1] for name in CLIENT_FIELDS}
    convert = validate_client_options(sample)
    assert convert == sample
    opts = to_convert_options(convert, max_seconds=42.0)
    for name, value in sample.items():
        assert getattr(opts, name) == value, name
    assert opts.max_seconds == 42.0


@pytest.mark.parametrize(
    "bad",
    [
        {"max_pages": 0},
        {"max_duration_seconds": 0},
        {"asr_model": "x" * 65},
        {"languages": ["en"] * 11},
        {"experimental": False},
        {"converter": "text.plain"},
        {"allow_private_networks": True},
        {"max_seconds": 1},
        {"no_such_option": 1},
    ],
)
def test_rejects_invalid_and_server_controlled_options(bad: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        validate_client_options(bad)


def test_omitted_options_use_library_defaults() -> None:
    opts = to_convert_options(validate_client_options({}), max_seconds=10.0)
    defaults = Options()
    for name in CLIENT_FIELDS:
        assert getattr(opts, name) == getattr(defaults, name), name
