// Extracts warning code -> {severity, suggestion} from the canonical Python registry
// (packages/core/src/intomd/warnings/codes.py) into src/generated/warning-codes.json, so the UI's
// suggested actions cannot drift from core. Run after codes.py changes: `pnpm -F @intomd/web gen:warnings`.
import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const SRC = fileURLToPath(new URL("../../../packages/core/src/intomd/warnings/codes.py", import.meta.url));
const OUT = fileURLToPath(new URL("../src/generated/warning-codes.json", import.meta.url));

const STR = String.raw`"(?:[^"\\]|\\.)*"`;
const STRS = String.raw`(?:${STR}\s*)+`;
const SPEC_RE = new RegExp(String.raw`CodeSpec\(\s*WarningKind\.(\w+)\s*,\s*"(info|warning|error)"\s*,\s*${STR}\s*,\s*(${STRS}),\s*(${STRS})\)`, "g");

function joinLiterals(src) {
  return [...src.matchAll(new RegExp(STR, "g"))].map((m) => JSON.parse(m[0])).join("");
}

export function parseCodes(py) {
  const enumBody = py.slice(py.indexOf("class WarningKind"), py.indexOf("@dataclass"));
  const members = new Map([...enumBody.matchAll(/^\s+([A-Z0-9_]+)\s*=\s*"([a-z0-9_]+)"/gm)].map((m) => [m[1], m[2]]));
  const codes = {};
  for (const m of py.matchAll(SPEC_RE)) {
    const value = members.get(m[1]);
    if (value) codes[value] = { severity: m[2], suggestion: joinLiterals(m[4]) };
  }
  return { members: [...members.values()], codes };
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  const { members, codes } = parseCodes(readFileSync(SRC, "utf8"));
  const missing = members.filter((c) => !codes[c]);
  const sorted = Object.fromEntries(Object.entries(codes).sort(([a], [b]) => a.localeCompare(b)));
  writeFileSync(OUT, JSON.stringify(sorted, null, 2) + "\n");
  console.log(`gen-warning-codes: ${Object.keys(codes).length}/${members.length} codes written to src/generated/warning-codes.json`);
  if (missing.length) {
    console.error(`gen-warning-codes: no CodeSpec parsed for: ${missing.join(", ")}`);
    process.exit(1);
  }
}
