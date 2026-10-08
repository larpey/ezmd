import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
// @ts-expect-error -- plain ESM script without type declarations
import { OUT_PATH, render } from "../scripts/generate.mjs";

describe("openapi drift", () => {
  it("src/openapi.d.ts matches docs/api/openapi.json", async () => {
    const expected = (await render()) as string;
    const committed = readFileSync(OUT_PATH as string, "utf8");
    // If this fails: `uv run python apps/api/scripts/export_openapi.py && pnpm -F @ezmd/sdk generate`.
    expect(committed === expected).toBe(true);
  }, 30_000);
});
