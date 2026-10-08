// @vitest-environment node
import { existsSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
// @ts-expect-error -- plain ESM script without type declarations
import { parseCodes } from "../../scripts/gen-warning-codes.mjs";
import generated from "../generated/warning-codes.json";
import { BUNDLED_REGISTRY, canonicalCode, clock, codesWithoutAction, registryFrom, suggestedAction, warningSeverity } from "./warnings";

const CODES_PY = fileURLToPath(new URL("../../../../packages/core/src/intomd/warnings/codes.py", import.meta.url));
const hasCore = existsSync(CODES_PY);

function core(): { members: string[]; codes: Record<string, { aliases: string[] }> } {
  return parseCodes(readFileSync(CODES_PY, "utf8"));
}

describe("warning suggestion coverage (spec part4 4.1.3)", () => {
  it.skipIf(!hasCore)("src/generated/warning-codes.json is fresh", () => {
    // If this fails: `pnpm -F @intomd/web gen:warnings`.
    expect(generated).toEqual(Object.fromEntries(Object.entries(core().codes).sort(([a], [b]) => a.localeCompare(b))));
  });

  it.skipIf(!hasCore)("has a non-empty suggested action for every code and alias in packages/core", () => {
    const { members, codes } = core();
    expect(members.length).toBeGreaterThan(100);
    const aliases = Object.values(codes).flatMap((c) => c.aliases);
    expect(aliases.length).toBeGreaterThan(0);
    expect(codesWithoutAction([...members, ...aliases])).toEqual([]);
    for (const c of [...members, ...aliases]) expect(suggestedAction({ kind: c, message: "" }).trim()).not.toBe("");
  });
});

describe("registry", () => {
  it("normalizes aliases and uses registry severity when the warning has none", () => {
    expect(canonicalCode({ kind: "injection_flagged", message: "" })).toBe("injection_suspected");
    expect(suggestedAction({ kind: "injection_flagged", message: "" })).toContain("instructions aimed at an AI");
    const code = Object.keys(BUNDLED_REGISTRY.codes).find((c) => BUNDLED_REGISTRY.codes[c]!.severity === "error")!;
    expect(warningSeverity({ kind: code, message: "" })).toBe("error");
    expect(warningSeverity({ kind: code, severity: "info", message: "" })).toBe("info");
  });

  it("layers /v1/warnings over the bundled registry", () => {
    const reg = registryFrom([{ code: "brand_new", severity: "error", family: "x", description: "d", suggestion: "Do the new thing.", truncates: false, aliases: ["old_new"] }]);
    expect(suggestedAction({ kind: "old_new", message: "" }, reg)).toBe("Do the new thing.");
    expect(warningSeverity({ kind: "brand_new", message: "" }, reg)).toBe("error");
    expect(suggestedAction({ kind: "truncated", message: "" }, reg)).toContain("truncated at the size cap");
    expect(suggestedAction({ kind: "never_heard_of_it", message: "" }, reg)).toBe("Check the result against the original.");
  });

  it("fills counts and durations into the spec wording", () => {
    expect(suggestedAction({ kind: "pages_without_text", message: "", count: 3 })).toMatch(/^3 pages had no text layer/);
    expect(suggestedAction({ kind: "duration_cap_exceeded", message: "", detail: { limit_seconds: 600 } })).toBe(
      "This instance caps audio at 10:00. The transcript covers the first 10:00.",
    );
    expect(clock(3725)).toBe("1:02:05");
  });
});
