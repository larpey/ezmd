"""Generate the code-family fixtures (self-generated, CC0).

Run from the repo root: `uv run python fixtures/code/_generate.py`. Output is deterministic (fixed timestamps,
gzip mtime 0). Planted "secrets" are built here at generation time from a hash of a fixed label, so they match
the converter's generic-assignment and PEM-block rules but are not provider token formats (no ghp_/AKIA/xox
values are committed; provider rules are tested with values built at test runtime).
"""

from __future__ import annotations

import base64
import gzip
import hashlib
import io
import stat
import tarfile
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
NL = chr(10)
DATE = (2026, 1, 1, 0, 0, 0)
TAR_MTIME = 1767225600  # 2026-01-01T00:00:00Z


def fake_hex(label: str, n: int = 40) -> str:
    return hashlib.sha256(f"intomd-fixture-{label}".encode()).hexdigest()[:n]


def fake_pem(label: str) -> str:
    body = base64.b64encode((f"intomd fake key material for {label}; not a real key. " * 4).encode()).decode()
    lines = [body[i : i + 64] for i in range(0, len(body), 64)]
    return NL.join(["-----BEGIN PRIVATE KEY-----", *lines, "-----END PRIVATE KEY-----"])


def lines(*rows: str) -> str:
    return NL.join(rows) + NL


PY_MODULE = lines(
    "#!/usr/bin/env python3",
    "# inventory.py: a tiny stock ledger used as an intomd fixture.",
    '"""Track stock levels per SKU and report items that need reordering."""',
    "",
    "from __future__ import annotations",
    "",
    "import json",
    "from dataclasses import dataclass, field",
    "",
    "REORDER_THRESHOLD = 5",
    "Ledger = dict[str, int]",
    "",
    "",
    "@dataclass",
    "class Item:",
    '    """One stock-keeping unit."""',
    "",
    "    sku: str",
    "    name: str",
    "    quantity: int = 0",
    "    tags: list[str] = field(default_factory=list)",
    "",
    "    def needs_reorder(self, threshold: int = REORDER_THRESHOLD) -> bool:",
    '        """True when the quantity is at or below the threshold."""',
    "        return self.quantity <= threshold",
    "",
    "    def restock(self, amount: int) -> None:",
    "        if amount <= 0:",
    '            raise ValueError("amount must be positive")',
    "        self.quantity += amount",
    "",
    "",
    "class Inventory:",
    '    """A collection of items keyed by SKU."""',
    "",
    "    def __init__(self) -> None:",
    "        self._items: dict[str, Item] = {}",
    "",
    "    def add(self, item: Item) -> None:",
    "        self._items[item.sku] = item",
    "",
    "    def low_stock(self) -> list[Item]:",
    '        """Items that need reordering, sorted by SKU."""',
    "        return sorted((i for i in self._items.values() if i.needs_reorder()), key=lambda i: i.sku)",
    "",
    "    def to_json(self) -> str:",
    "        return json.dumps({sku: item.quantity for sku, item in self._items.items()}, indent=2)",
    "",
    "",
    "async def sync_remote(inventory: Inventory, endpoint: str, *, retries: int = 3) -> int:",
    '    """Push quantities to a remote endpoint; returns how many items were sent."""',
    "    sent = 0",
    "    for _attempt in range(retries):",
    "        sent = len(inventory.low_stock())",
    "    return sent",
    "",
    "",
    "def main() -> None:",
    "    inv = Inventory()",
    '    inv.add(Item("A-1", "Widget", 3))',
    '    inv.add(Item("B-2", "Gadget", 40))',
    "    for item in inv.low_stock():",
    '        print(f"reorder {item.sku}: {item.name}")',
    "",
    "",
    'if __name__ == "__main__":',
    "    main()",
)

PLANTED = lines(
    "# settings.py: application settings with planted fake secrets (intomd fixture).",
    "import os",
    "",
    'DEBUG = os.environ.get("APP_DEBUG", "0") == "1"',
    f'API_SECRET_KEY = "{fake_hex("api-secret")}"',
    f"SERVICE_TOKEN = {fake_hex('service-token', 32)}",
    'DATABASE_PASSWORD = "changeme"  # placeholder, must stay visible',
    "MAX_TOKENS = 4096",
    "",
    "SIGNING_KEY_PEM = '''",
    fake_pem("settings"),
    "'''",
    "",
    "",
    "def database_url(host: str) -> str:",
    f'    return f"postgresql://app:{fake_hex("db-password", 20)}@{{host}}/app"',
)

GO_FILE = lines(
    "// Package shapes computes areas.",
    "package shapes",
    "",
    'import "math"',
    "",
    "// Circle is a round shape.",
    "type Circle struct {",
    "\tRadius float64",
    "}",
    "",
    "// Area returns the area of the circle.",
    "func (c Circle) Area() float64 {",
    "\treturn math.Pi * c.Radius * c.Radius",
    "}",
)

TS_FILE = lines(
    "// greeter.ts: a tiny TypeScript module (intomd fixture).",
    'import { format } from "./format";',
    "",
    "export interface Greeting {",
    "  name: string;",
    "  excited?: boolean;",
    "}",
    "",
    "export function greet(g: Greeting): string {",
    "  const base = format(`Hello, ${g.name}`);",
    '  return g.excited ? base + "!" : base;',
    "}",
    "",
    "export const DEFAULT_NAME = 'world';",
)


def _long_module(n_funcs: int) -> str:
    rows = ['"""Generated-looking helpers to make the repo exceed small token budgets."""', ""]
    for i in range(n_funcs):
        rows += [
            f"def helper_{i:03d}(value: int, scale: int = {i + 1}) -> int:",
            f'    """Scale value by {i + 1} and add a fixed offset."""',
            f"    offset = {i * 7 % 13}",
            "    result = value * scale",
            "    if result > 1000:",
            "        result = result % 1000",
            "    return result + offset",
            "",
            "",
        ]
    return NL.join(rows).rstrip() + NL


PB2 = lines("# Generated by the protocol buffer compiler.  DO NOT EDIT!", "ITEM = 1")


def repo_files() -> list[tuple[str, bytes]]:
    readme = lines(
        "# stockroom",
        "",
        "A small inventory service used as an intomd repo-pack fixture.",
        "",
        "Run `python -m stockroom` to print items that need reordering.",
    )
    pyproject = lines(
        "[project]",
        'name = "stockroom"',
        'version = "0.1.0"',
        'description = "Tiny inventory service (intomd fixture)."',
        'requires-python = ">=3.12"',
    )
    gitignore = lines("*.log", "!keep.log", "build/", "local_settings.py", "__pycache__/")
    nested_ignore = lines("scratch/", "*.tmp")
    lock = lines(*[f"package-{i:03d}==1.{i}.0 --hash=sha256:{fake_hex(f'lock{i}', 64)}" for i in range(80)])
    creds = lines(
        "# Test credentials accidentally committed (fake values, intomd fixture).",
        f"aws_secret_access_key = {base64.b64encode(hashlib.sha256(b'aws-fixture').digest()).decode()[:40]}",
        f"auth_token: '{fake_hex('creds-token', 36)}'",
    )
    env = lines(f"DB_PASSWORD={fake_hex('env-db', 24)}", "DEBUG=1")
    utf16 = "Notes in UTF-16: café, naïve, 日本語." + NL
    minified = "!function(){" + ";".join(f"var a{i}={i}" for i in range(400)) + "}();" + NL
    png = bytes([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A]) + bytes(range(256)) * 2
    test_py = lines(
        "from stockroom.inventory import Inventory, Item",
        "",
        "",
        "def test_low_stock() -> None:",
        "    inv = Inventory()",
        '    inv.add(Item("A-1", "Widget", 1))',
        "    assert [i.sku for i in inv.low_stock()] == ['A-1']",
    )
    return [
        ("stockroom/README.md", readme.encode()),
        ("stockroom/pyproject.toml", pyproject.encode()),
        ("stockroom/LICENSE", lines("CC0 1.0 Universal (fixture placeholder license text).").encode()),
        ("stockroom/.gitignore", gitignore.encode()),
        ("stockroom/.env", env.encode()),
        ("stockroom/uv.lock", lock.encode()),
        ("stockroom/app.log", b"2026-01-01 ignored log line\n"),
        ("stockroom/keep.log", lines("2026-01-01 00:00:00 INFO kept by a !negation rule").encode()),
        ("stockroom/local_settings.py", lines(f'SECRET = "{fake_hex("ignored")}"').encode()),
        ("stockroom/src/stockroom/__init__.py", lines('"""stockroom package."""', "").encode()),
        ("stockroom/src/stockroom/inventory.py", PY_MODULE.encode()),
        ("stockroom/src/stockroom/scale.py", _long_module(40).encode()),
        ("stockroom/src/stockroom/helpers/units.py", lines("CM_PER_INCH = 2.54", "GRAMS_PER_OUNCE = 28.35").encode()),
        ("stockroom/src/stockroom/helpers/.gitignore", nested_ignore.encode()),
        ("stockroom/src/stockroom/helpers/scratch/draft.py", lines("x = 1").encode()),
        ("stockroom/src/stockroom/helpers/cache.tmp", b"temp\n"),
        ("stockroom/src/stockroom/proto/item_pb2.py", PB2.encode()),
        ("stockroom/web/greeter.ts", TS_FILE.encode()),
        ("stockroom/web/vendor.min.js", minified.encode()),
        ("stockroom/web/bundle.js", minified.encode()),
        ("stockroom/web/logo.png", png),
        ("stockroom/node_modules/left-pad/index.js", lines("module.exports = 1;").encode()),
        ("stockroom/node_modules/left-pad/package.json", b'{"name": "left-pad"}\n'),
        ("stockroom/docs/notes_utf16.txt", utf16.encode("utf-16")),
        ("stockroom/docs/deploy/signing.pem", fake_pem("repo").encode()),
        ("stockroom/tests/test_inventory.py", test_py.encode()),
        ("stockroom/tests/fixtures/creds.txt", creds.encode()),
        ("stockroom/build/out.txt", b"build output\n"),
    ]  # fmt: skip


SHELL_SCRIPT = lines(
    "#!/usr/bin/env bash",
    "# backup.sh: rotate nightly database dumps (intomd fixture).",
    "set -euo pipefail",
    "",
    'BACKUP_DIR="${BACKUP_DIR:-/var/backups/app}"',
    "KEEP_DAYS=14",
    "",
    "log() {",
    '  printf "%s %s" "$(date -u +%FT%TZ)" "$*" >&2',
    "}",
    "",
    "rotate() {",
    '  find "$BACKUP_DIR" -name "*.sql.gz" -mtime +"$KEEP_DAYS" -print -delete',
    "}",
    "",
    "cat <<'EOF' > /tmp/backup-banner.txt",
    "Nightly backup: do not interrupt.",
    "EOF",
    "",
    'case "${1:-run}" in',
    "  run) log starting; rotate ;;",
    "  dry-run) log dry run only ;;",
    '  *) echo "usage: $0 [run|dry-run]"; exit 2 ;;',
    "esac",
)

RUST_FILE = lines(
    "//! ledger.rs: a fixed-point ledger (intomd fixture).",
    "use std::collections::BTreeMap;",
    "use std::fmt;",
    "",
    "/// Amounts are stored in cents to avoid floating-point drift.",
    "#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]",
    "pub struct Cents(pub i64);",
    "",
    "impl fmt::Display for Cents {",
    "    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {",
    '        write!(f, "{}.{:02}", self.0 / 100, (self.0 % 100).abs())',
    "    }",
    "}",
    "",
    "pub trait Account {",
    "    fn balance(&self) -> Cents;",
    "}",
    "",
    "#[derive(Default)]",
    "pub struct Ledger<'a> {",
    "    entries: BTreeMap<&'a str, Vec<Cents>>,",
    "}",
    "",
    "impl<'a> Ledger<'a> {",
    "    pub fn post(&mut self, account: &'a str, amount: Cents) {",
    "        self.entries.entry(account).or_default().push(amount);",
    "    }",
    "",
    "    pub fn total(&self, account: &str) -> Option<Cents> {",
    "        self.entries.get(account).map(|v| Cents(v.iter().map(|c| c.0).sum()))",
    "    }",
    "}",
    "",
    "#[cfg(test)]",
    "mod tests {",
    "    use super::*;",
    "",
    "    #[test]",
    "    fn totals_in_cents() {",
    "        let mut l = Ledger::default();",
    '        l.post("cash", Cents(1050));',
    '        l.post("cash", Cents(-25));',
    '        assert_eq!(l.total("cash").unwrap().to_string(), "10.25");',
    "    }",
    "}",
)


def scatter_files() -> list[tuple[str, bytes]]:
    """A repo whose secrets sit inside files that ARE packed (YAML, Markdown, JS, Dockerfile, INI), next to
    placeholders that must stay visible, plus credential files that are excluded outright."""
    root = "tidepool/"
    readme = lines("# tidepool", "", "Sensor ingest service (intomd secret-scatter fixture).")
    ops = lines(
        "# Operations",
        "",
        "Connect to the staging replica:",
        "",
        "```",
        f"psql postgres://ingest:{fake_hex('ops-db', 18)}@db.staging.example.invalid/tide",
        "```",
        "",
        "Local default (placeholder, keep visible): `postgres://ingest:changeme@localhost/tide`.",
    )
    app_yaml = lines(
        "service: tidepool",
        "database:",
        "  host: db.example.invalid",
        f"  password: {fake_hex('yaml-db', 20)}",
        "  pool_size: 8",
        "upstream:",
        '  api_key: "${UPSTREAM_API_KEY}"',
    )
    client_js = lines(
        "// client.js: upstream HTTP client.",
        "export async function fetchReadings(base) {",
        "  const res = await fetch(base + '/readings', {",
        f"    headers: {{ Authorization: 'Bearer {fake_hex('bearer', 32)}' }},",
        "  });",
        "  return res.json();",
        "}",
        "export const MAX_RETRIES = 3;",
    )
    dockerfile = lines(
        "FROM python:3.12-slim",
        "WORKDIR /app",
        f"ENV INGEST_TOKEN={fake_hex('docker-token', 28)}",
        "ENV LOG_LEVEL=info",
        'CMD ["python", "-m", "tidepool"]',
    )
    ini = lines(
        "[alerts]",
        "smtp_host = mail.example.invalid",
        "smtp_password = <your password here>",
        f"webhook_secret = {fake_hex('ini-webhook', 24)}",
    )
    main_py = lines(
        '"""tidepool entry point."""',
        "import os",
        "",
        'TOKEN = os.environ["INGEST_TOKEN"]  # read at runtime, nothing to redact',
        "",
        "",
        "def main() -> None:",
        '    print("ingest ready")',
    )
    return [
        (root + "README.md", readme.encode()),
        (root + ".gitignore", lines("*.pyc", "secrets/", "!secrets/README.md").encode()),
        (root + "Dockerfile", dockerfile.encode()),
        (root + "config/app.yaml", app_yaml.encode()),
        (root + "config/alerts.ini", ini.encode()),
        (root + "docs/operations.md", ops.encode()),
        (root + "web/client.js", client_js.encode()),
        (root + "src/tidepool/__main__.py", main_py.encode()),
        (root + "secrets/README.md", lines("Keep real secrets out of git; this folder is ignored.").encode()),
        (root + "secrets/prod.txt", lines(f"token={fake_hex('ignored-prod', 30)}").encode()),
        (root + ".npmrc", lines(f"//registry.example.invalid/:_authToken={fake_hex('npmrc', 36)}").encode()),
        (root + "deploy/id_ed25519", fake_pem("deploy-ssh").encode()),
    ]  # fmt: skip


def write_zip(path: Path, files: list[tuple[str, bytes]], *, hostile: bool) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, data in files:
            info = zipfile.ZipInfo(name, date_time=DATE)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            zf.writestr(info, data)
        if hostile:
            link = zipfile.ZipInfo("stockroom/src/link_to_etc", date_time=DATE)
            link.external_attr = (stat.S_IFLNK | 0o777) << 16
            zf.writestr(link, "/etc/passwd")
            zf.writestr(zipfile.ZipInfo("stockroom/../escape.txt", date_time=DATE), "should never be read")


def write_tar_gz(path: Path, files: list[tuple[str, bytes]], commit: str) -> None:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w", format=tarfile.PAX_FORMAT, pax_headers={"comment": commit}) as tf:
        for name, data in files:
            info = tarfile.TarInfo(name)
            info.size = len(data)
            info.mtime = TAR_MTIME
            info.mode = 0o644
            tf.addfile(info, io.BytesIO(data))
    with path.open("wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as gz:
        gz.write(buf.getvalue())


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline=NL)


def main() -> None:
    write_text(HERE / "source-python" / "input.py", PY_MODULE)
    write_text(HERE / "source-python-signatures" / "input.py", PY_MODULE)
    write_text(HERE / "source-planted-secret" / "input.py", PLANTED)
    write_text(HERE / "source-go" / "input.go", GO_FILE)
    write_text(HERE / "source-typescript" / "input.ts", TS_FILE)
    write_text(HERE / "source-shell" / "input.sh", SHELL_SCRIPT)
    write_text(HERE / "source-rust" / "input.rs", RUST_FILE)
    (HERE / "repo-secrets-scatter").mkdir(parents=True, exist_ok=True)
    write_zip(HERE / "repo-secrets-scatter" / "input.repo.zip", scatter_files(), hostile=False)
    files = repo_files()
    for name in ("repo-small", "repo-budget"):
        (HERE / name).mkdir(parents=True, exist_ok=True)
        write_zip(HERE / name / "input.repo.zip", files, hostile=name == "repo-small")
    commit = fake_hex("commit", 40)
    gh = [(p.replace("stockroom/", "acme-stockroom-" + commit[:7] + "/", 1), d) for p, d in files[:4] + files[9:12]]
    (HERE / "repo-github-tarball").mkdir(parents=True, exist_ok=True)
    write_tar_gz(HERE / "repo-github-tarball" / "input.tar.gz", gh, commit)


if __name__ == "__main__":
    main()
