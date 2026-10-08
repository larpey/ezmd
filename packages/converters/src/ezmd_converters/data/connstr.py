"""data.connection_string: database connection strings are refused (docs/spec/part2.md 10c step 14).

Matches URL inputs with a database scheme (`postgres://`, `mysql://`, `mongodb+srv://`, `jdbc:...`, ...) and
tiny text bodies that consist of one connection string (including ADO.NET `Server=...;Database=...`). The
result is a stub: one paragraph saying why nothing was converted plus a `connection_string_refused` error.
Credentials are never echoed: the message names only the scheme, and a URL input's source is reduced to
scheme, host and database.
"""

from __future__ import annotations

import re
from urllib.parse import urlsplit

from ezmd.inputs import InputRef
from ezmd.ir import Document, InlineSpan, Metadata, Paragraph, Provenance, SourceType, Warning, WarningKind
from ezmd.registry import ConvertOptions

MAX_TEXT_BYTES = 4096
STUB_TEXT = (
    "This input is a {kind} connection string. ezmd does not connect to live databases, so nothing was "
    "converted. Export the data to CSV, Parquet, or SQLite and convert that file instead."
)
_URL = re.compile(
    r"^(postgres(ql)?|mysql|mariadb|mssql|sqlserver|oracle|mongodb(\+srv)?|redis(s)?|sqlite|cockroachdb|"
    r"clickhouse|snowflake|db2|couchdb|cassandra|neo4j|amqp)(\+[a-z0-9]+)?://\S+$",
    re.I,
)
_JDBC = re.compile(r"^jdbc:[a-z0-9]+:\S+$", re.I)
_ADO = re.compile(r"^(?=.*\b(server|data source|host)\s*=)(?=.*\b(database|initial catalog)\s*=)[^\n]*;[^\n]*$", re.I)


def looks_like_connection_string(text: str) -> bool:
    s = text.strip()
    if not s or "\n" in s:
        return False
    return bool(_URL.match(s) or _JDBC.match(s) or _ADO.match(s))


def redacted(text: str) -> str:
    """scheme://host/database with userinfo, password, port and query removed; a fixed label otherwise."""
    s = text.strip()
    if _URL.match(s):
        parts = urlsplit(s)
        return f"{parts.scheme}://{parts.hostname or ''}{parts.path}"
    if _JDBC.match(s):
        return "jdbc connection string"
    return "connection string"


class ConnectionStringConverter:
    id = "data.connection_string"
    family = "data"
    priority = 50
    experimental = False
    requires_extras: tuple[str, ...] = ()
    mimes: tuple[str, ...] = ("text/x-uri", "text/plain")

    def can_handle(self, ref: InputRef) -> float:
        if not ref.has_body:
            return 1.0 if ref.url and looks_like_connection_string(ref.url) else 0.0
        mime = ref.detected.mime if ref.detected else None
        if mime not in ("text/plain", None) or ref.size() > MAX_TEXT_BYTES:
            return 0.0
        try:
            text = ref.head(MAX_TEXT_BYTES).decode("utf-8")
        except UnicodeDecodeError:
            return 0.0
        return 1.0 if looks_like_connection_string(text) else 0.0

    def convert(self, ref: InputRef, options: ConvertOptions) -> Document:
        if ref.has_body:
            text = ref.head(MAX_TEXT_BYTES).decode("utf-8", errors="replace")
            source = ref.display
        else:
            text = ref.url or ""
            source = redacted(text)
        kind = "JDBC" if _JDBC.match(text.strip()) else ("ADO.NET" if _ADO.match(text.strip()) else "database URL")
        doc = Document(metadata=Metadata(title="Connection string refused", source=source, source_type=SourceType.DATA))
        doc.blocks.append(
            Paragraph(
                spans=[InlineSpan(text=STUB_TEXT.format(kind=kind))],
                provenance=Provenance(source=source, path="/"),
            )
        )
        doc.warnings.append(
            Warning(
                kind=WarningKind.CONNECTION_STRING_REFUSED,
                message=f"The input is a {kind} connection string; live databases are not queried. "
                "Export the data to CSV, Parquet, or SQLite and convert that file.",
                detail={"kind": kind},
            )
        )
        return doc.finalize()
