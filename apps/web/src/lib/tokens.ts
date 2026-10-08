/**
 * Frontmatter `tokens`: one count per tokenizer (docs/spec/part2.md frontmatter table and section 20), for
 * example `{o200k_base: 10950, cl100k_base: 11210, claude_approx: 11800}`. The OpenAPI document does not
 * model the `format=json` body (the SDK types `frontmatter` as `Record<string, unknown>`), so the shape is
 * declared here and every value is checked at runtime.
 */
export type TokenCounts = Readonly<Partial<Record<"o200k_base" | "cl100k_base" | "claude_approx", number>> & Record<string, unknown>>;

export interface TokenBadge {
  count: number;
  /** Tokenizer the count comes from; null when the server sent a bare number. */
  tokenizer: string | null;
}

/** The tokenizer the rest of intomd counts with (chunk budgets, `rag` per-chunk counts). */
export const PREFERRED_TOKENIZER = "o200k_base";

function isCount(v: unknown): v is number {
  return typeof v === "number" && Number.isFinite(v) && v >= 0;
}

/** Picks the badge count: `o200k_base` when present, else the first finite count; a bare number is accepted too. */
export function tokenBadge(value: unknown): TokenBadge | undefined {
  if (isCount(value)) return { count: value, tokenizer: null };
  if (typeof value !== "object" || value === null || Array.isArray(value)) return undefined;
  const counts = value as TokenCounts;
  const preferred = counts[PREFERRED_TOKENIZER];
  if (isCount(preferred)) return { count: preferred, tokenizer: PREFERRED_TOKENIZER };
  const first = Object.entries(counts).find(([, v]) => isCount(v));
  return first ? { count: first[1] as number, tokenizer: first[0] } : undefined;
}
