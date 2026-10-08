// @vitest-environment node
import { existsSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { SUGGESTED_ACTIONS } from "./warnings";

const CODES_PY = fileURLToPath(new URL("../../../../packages/core/src/intomd/warnings/codes.py", import.meta.url));

function registryCodes(): string[] {
  const py = readFileSync(CODES_PY, "utf8");
  const body = py.slice(py.indexOf("class WarningKind"), py.indexOf("@dataclass"));
  return [...body.matchAll(/^\s+[A-Z0-9_]+\s*=\s*"([a-z0-9_]+)"/gm)].map((m) => m[1]!);
}

describe("warning suggestion coverage (spec part4 4.1.3)", () => {
  it.skipIf(!existsSync(CODES_PY))("has a non-empty suggested action for every code in packages/core", () => {
    const codes = registryCodes();
    expect(codes.length).toBeGreaterThan(0);
    const missing = codes.filter((c) => !SUGGESTED_ACTIONS[c]?.trim());
    // If this fails, run `pnpm -F @intomd/web gen:warnings` to refresh src/generated/warning-codes.json.
    expect(missing).toEqual([]);
  });
});
