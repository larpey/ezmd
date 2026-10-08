// Every storage access is wrapped: private windows and blocked storage must not break the page.
export function readJson<T>(key: string, fallback: T): T {
  try {
    const raw = window.localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}

export function writeJson(key: string, value: unknown): void {
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // Storage unavailable or full; the UI keeps working without persistence.
  }
}

export function removeKey(key: string): void {
  try {
    window.localStorage.removeItem(key);
  } catch {
    // ignore
  }
}

export const HISTORY_KEY = "intomd.history.v1";
export const THEME_KEY = "intomd.theme";
export const HISTORY_LIMIT = 50;

export interface HistoryEntry {
  id: string;
  title: string;
  source_kind: "file" | "url" | "text";
  created_at: string;
  profile: string;
  tokens?: number;
  expires_at: string;
  /** First 200 characters of the result; full bodies never go to localStorage. */
  preview?: string;
  /** "Keep result on this device": the full body is in IndexedDB (lib/localstore). */
  keep?: boolean;
}

export const PREVIEW_CHARS = 200;

function isEntry(v: unknown): v is HistoryEntry {
  const e = v as Partial<HistoryEntry> | null;
  return typeof e?.id === "string" && typeof e.title === "string";
}

/** True when the server TTL has passed (unknown expiry counts as live; the server answers 404 if not). */
export function isExpired(e: Pick<HistoryEntry, "expires_at">, now: number = Date.now()): boolean {
  const at = Date.parse(e.expires_at);
  return Number.isFinite(at) && at < now;
}

export function loadHistory(): HistoryEntry[] {
  const list = readJson<unknown>(HISTORY_KEY, []);
  return Array.isArray(list) ? list.filter(isEntry).slice(0, HISTORY_LIMIT) : [];
}

export function upsertHistory(list: readonly HistoryEntry[], entry: HistoryEntry, opts: { moveToTop?: boolean } = {}): HistoryEntry[] {
  const index = list.findIndex((e) => e.id === entry.id);
  const merged = index >= 0 ? { ...list[index], ...entry } : entry;
  if (index >= 0 && opts.moveToTop === false) return list.map((e, i) => (i === index ? merged : e));
  return [merged, ...list.filter((e) => e.id !== entry.id)].slice(0, HISTORY_LIMIT);
}
