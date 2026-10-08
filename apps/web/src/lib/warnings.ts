import type { EzmdWarning, Severity, WarningCodeInfo } from "@ezmd/sdk";

import generated from "../generated/warning-codes.json";

interface CodeEntry {
  severity: Severity;
  suggestion: string;
  aliases: readonly string[];
}

/** Warning registry the UI consults: canonical code -> entry, plus alias -> canonical code. */
export interface WarningRegistry {
  readonly codes: Readonly<Record<string, CodeEntry>>;
  readonly aliases: Readonly<Record<string, string>>;
}

/** Wording the web UI uses instead of the registry text (spec part4 4.1.2 step 8). */
const UI_OVERRIDES: Readonly<Record<string, (w: EzmdWarning) => string>> = {
  fetch_blocked_by_platform: () =>
    "This platform blocked our server. Upload the file directly, or install the browser extension to fetch from your own connection.",
  pages_without_text: (w) =>
    `${w.count != null ? `${w.count} page${w.count === 1 ? "" : "s"}` : "Some pages"} had no text layer and OCR is off on this instance. Self-host with the \`ocr\` extra to read them.`,
  duration_cap_exceeded: (w) => {
    const cap = numberDetail(w, "limit_seconds", "max_seconds", "cap_seconds");
    return cap != null
      ? `This instance caps audio at ${clock(cap)}. The transcript covers the first ${clock(cap)}.`
      : "This instance caps audio length. The transcript covers only the first part.";
  },
  injection_suspected: () => "Some text looks like instructions aimed at an AI. It was kept, not removed, and is flagged in the sidecar.",
  truncated: () => "Output was truncated at the size cap. Download the full result or self-host.",
};

export const EXTENSION_DOCS_URL = "/docs/extension";
const DEFAULT_ACTION = "Check the result against the original.";

function numberDetail(w: EzmdWarning, ...keys: string[]): number | undefined {
  for (const k of keys) {
    const v = w.detail?.[k];
    if (typeof v === "number" && Number.isFinite(v)) return v;
  }
  return undefined;
}

/** Seconds as MM:SS (or H:MM:SS). */
export function clock(totalSeconds: number): string {
  const s = Math.max(0, Math.round(totalSeconds));
  const hh = Math.floor(s / 3600);
  const mm = Math.floor((s % 3600) / 60);
  const ss = String(s % 60).padStart(2, "0");
  return hh ? `${hh}:${String(mm).padStart(2, "0")}:${ss}` : `${String(mm).padStart(2, "0")}:${ss}`;
}

function aliasIndex(codes: Readonly<Record<string, CodeEntry>>): Record<string, string> {
  return Object.fromEntries(Object.entries(codes).flatMap(([code, e]) => e.aliases.map((a) => [a, code] as const)));
}

/** The registry bundled at build time from packages/core (works offline and before /v1/warnings answers). */
export const BUNDLED_REGISTRY: WarningRegistry = (() => {
  const codes = generated as Record<string, CodeEntry>;
  return { codes, aliases: aliasIndex(codes) };
})();

/** Builds a registry from GET /v1/warnings, layered over the bundled one so unknown-to-server codes still resolve. */
export function registryFrom(list: readonly WarningCodeInfo[], base: WarningRegistry = BUNDLED_REGISTRY): WarningRegistry {
  const served = Object.fromEntries(list.map((i) => [i.code, { severity: i.severity, suggestion: i.suggestion, aliases: i.aliases ?? [] }]));
  const codes = { ...base.codes, ...served };
  return { codes, aliases: aliasIndex(codes) };
}

/** Raw kind as sent by the server (`kind`, or `code` on some surfaces). */
export function warningKind(w: EzmdWarning): string {
  return w.kind ?? w.code ?? "other";
}

/** Canonical code after alias normalization. */
export function canonicalCode(w: EzmdWarning, reg: WarningRegistry = BUNDLED_REGISTRY): string {
  const k = warningKind(w);
  return reg.codes[k] ? k : (reg.aliases[k] ?? k);
}

export function warningSeverity(w: EzmdWarning, reg: WarningRegistry = BUNDLED_REGISTRY): Severity {
  return w.severity ?? reg.codes[canonicalCode(w, reg)]?.severity ?? "warning";
}

/** Suggested action: UI override, else the registry suggestion, else a generic fallback. Never empty. */
export function suggestedAction(w: EzmdWarning, reg: WarningRegistry = BUNDLED_REGISTRY): string {
  const code = canonicalCode(w, reg);
  const override = UI_OVERRIDES[code];
  if (override) return override(w);
  const s = reg.codes[code]?.suggestion?.trim();
  return s || DEFAULT_ACTION;
}

/** Codes that would fall back to the generic action because neither the registry nor the UI map covers them. */
export function codesWithoutAction(codes: readonly string[], reg: WarningRegistry = BUNDLED_REGISTRY): string[] {
  return codes.filter((c) => {
    const code = canonicalCode({ kind: c, message: "" }, reg);
    return !UI_OVERRIDES[code] && !reg.codes[code]?.suggestion?.trim();
  });
}

/** Merges warnings from SSE events and the sidecar, dropping exact duplicates, preserving order. */
export function mergeWarnings(...lists: ReadonlyArray<readonly EzmdWarning[] | undefined>): EzmdWarning[] {
  const seen = new Set<string>();
  const out: EzmdWarning[] = [];
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
