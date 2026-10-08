import type { IntomdWarning } from "@intomd/sdk";

import registry from "../generated/warning-codes.json";

/** Wording the web UI uses instead of the registry text (spec part4 4.1.2 step 8). */
const UI_OVERRIDES: Readonly<Record<string, string>> = {
  fetch_blocked_by_platform:
    "This platform blocked our server. Upload the file directly, or install the browser extension to fetch from your own connection.",
  pages_without_text: "Some pages had no text layer and OCR is off on this instance. Self-host with the `ocr` extra to read them.",
  duration_cap_exceeded: "This instance caps audio length. The transcript covers only the first part.",
  injection_flagged: "Some text looks like instructions aimed at an AI. It was kept, not removed, and is flagged in the sidecar.",
  truncated: "Output was truncated at the size cap. Download the full result or self-host.",
};

/**
 * Suggested action per warning code: the canonical registry in packages/core (extracted into
 * src/generated/warning-codes.json by scripts/gen-warning-codes.mjs) plus UI wording overrides.
 * The warning message itself is always shown verbatim.
 */
export const SUGGESTED_ACTIONS: Readonly<Record<string, string>> = {
  ...Object.fromEntries(Object.entries(registry as Record<string, { suggestion: string }>).map(([code, spec]) => [code, spec.suggestion])),
  ...UI_OVERRIDES,
};

const DEFAULT_ACTION = "Check the result against the original.";

export function warningKind(w: IntomdWarning): string {
  return w.kind ?? w.code ?? "other";
}

export function suggestedAction(w: IntomdWarning): string {
  return SUGGESTED_ACTIONS[warningKind(w)] ?? DEFAULT_ACTION;
}

/** Merges warnings from SSE events and the sidecar, dropping exact duplicates, preserving order. */
export function mergeWarnings(...lists: ReadonlyArray<readonly IntomdWarning[] | undefined>): IntomdWarning[] {
  const seen = new Set<string>();
  const out: IntomdWarning[] = [];
  for (const list of lists) {
    for (const w of list ?? []) {
      const key = `${warningKind(w)}|${w.message}|${w.page ?? ""}|${w.block_id ?? ""}`;
      if (!seen.has(key)) {
        seen.add(key);
        out.push(w);
      }
    }
  }
  return out;
}
