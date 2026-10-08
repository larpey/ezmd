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
  preview?: string;
}

export function loadHistory(): HistoryEntry[] {
  const list = readJson<unknown>(HISTORY_KEY, []);
  return Array.isArray(list) ? (list as HistoryEntry[]).slice(0, HISTORY_LIMIT) : [];
}

export function upsertHistory(list: readonly HistoryEntry[], entry: HistoryEntry): HistoryEntry[] {
  const prev = list.find((e) => e.id === entry.id);
  const merged = prev ? { ...prev, ...entry } : entry;
  return [merged, ...list.filter((e) => e.id !== entry.id)].slice(0, HISTORY_LIMIT);
}
