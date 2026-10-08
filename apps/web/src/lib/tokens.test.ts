import { describe, expect, it } from "vitest";
import { tokenBadge } from "./tokens";

describe("tokenBadge", () => {
  it("prefers o200k_base from the per-tokenizer object the API sends", () => {
    expect(tokenBadge({ cl100k_base: 11210, o200k_base: 10950, claude_approx: 11800 })).toEqual({ count: 10950, tokenizer: "o200k_base" });
  });

  it("falls back to the first finite count", () => {
    expect(tokenBadge({ claude_approx: "n/a", cl100k_base: 12 })).toEqual({ count: 12, tokenizer: "cl100k_base" });
  });

  it("accepts a bare number", () => {
    expect(tokenBadge(42)).toEqual({ count: 42, tokenizer: null });
  });

  it("ignores missing or malformed values", () => {
    for (const v of [undefined, null, "12", [], {}, { o200k_base: Number.NaN }, -1]) expect(tokenBadge(v)).toBeUndefined();
  });
});
