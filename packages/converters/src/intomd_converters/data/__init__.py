"""Data family: CSV/TSV, JSON/JSON Lines, YAML, TOML, XML, SQLite, Parquet (extra), connection strings.

docs/spec/part2.md section 10 (and section 2c steps 35 to 37 for CSV). Parquet needs pyarrow from the
`data` extra; without it `data.parquet` is listed as unavailable.
"""

from __future__ import annotations

import importlib.util
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from intomd.registry import Converter, Unavailable

PARQUET_MIMES = ("application/vnd.apache.parquet", "application/x-parquet")

CHAINS: dict[str, list[str]] = {
    "text/csv": ["data.csv"],
    "text/tab-separated-values": ["data.csv"],
    "application/json": ["data.json"],
    "application/jsonl": ["data.json"],
    "application/x-ndjson": ["data.json"],
    "application/yaml": ["data.yaml"],
    "application/toml": ["data.toml"],
    "application/xml": ["data.xml"],
    "application/vnd.sqlite3": ["data.sqlite"],
    "application/x-sqlite3": ["data.sqlite"],
    "application/vnd.apache.parquet": ["data.parquet"],
    "application/x-parquet": ["data.parquet"],
}


def converters() -> list[Converter | Unavailable]:
    from intomd.registry import Unavailable
    from intomd_converters.data.connstr import ConnectionStringConverter
    from intomd_converters.data.csv_conv import CsvConverter
    from intomd_converters.data.json_conv import JsonConverter
    from intomd_converters.data.sqlite_conv import SqliteConverter
    from intomd_converters.data.toml_conv import TomlConverter
    from intomd_converters.data.xml_conv import XmlConverter
    from intomd_converters.data.yaml_conv import YamlConverter

    out: list[Converter | Unavailable] = [
        CsvConverter(),
        JsonConverter(),
        YamlConverter(),
        TomlConverter(),
        XmlConverter(),
        SqliteConverter(),
        ConnectionStringConverter(),
    ]
    if importlib.util.find_spec("pyarrow") is None:
        out.append(
            Unavailable(
                id="data.parquet",
                family="data",
                reason="Parquet needs pyarrow; install it with pip install 'intomd[data]'.",
                requires_extras=("data",),
                mimes=PARQUET_MIMES,
            )
        )
    else:
        from intomd_converters.data.parquet_conv import ParquetConverter

        out.append(ParquetConverter())
    return out
