// Full result bodies the user chose to keep on this device (spec part4 4.1.2 step 9). IndexedDB, not
// localStorage, because transcripts can be megabytes. Every call resolves (never rejects): with storage
// blocked or unavailable the UI simply has no local copy.

const DB_NAME = "intomd";
const STORE = "results";
const VERSION = 1;

export interface KeptResult {
  id: string;
  markdown: string;
  title: string;
  saved_at: string;
}

function openDb(): Promise<IDBDatabase | null> {
  return new Promise((resolve) => {
    try {
      if (typeof indexedDB === "undefined") return resolve(null);
      const req = indexedDB.open(DB_NAME, VERSION);
      req.onupgradeneeded = () => {
        if (!req.result.objectStoreNames.contains(STORE)) req.result.createObjectStore(STORE, { keyPath: "id" });
      };
      req.onsuccess = () => resolve(req.result);
      req.onerror = () => resolve(null);
      req.onblocked = () => resolve(null);
    } catch {
      resolve(null);
    }
  });
}

function run<T>(mode: IDBTransactionMode, op: (store: IDBObjectStore) => IDBRequest, map: (value: unknown) => T, fallback: T): Promise<T> {
  return openDb().then(
    (db) =>
      new Promise<T>((resolve) => {
        if (!db) return resolve(fallback);
        try {
          const tx = db.transaction(STORE, mode);
          const req = op(tx.objectStore(STORE));
          let value: unknown;
          req.onsuccess = () => {
            value = req.result;
          };
          tx.oncomplete = () => {
            db.close();
            resolve(map(value));
          };
          tx.onerror = tx.onabort = () => {
            db.close();
            resolve(fallback);
          };
        } catch {
          db.close();
          resolve(fallback);
        }
      }),
  );
}

function isKept(v: unknown): v is KeptResult {
  const r = v as Partial<KeptResult> | undefined;
  return typeof r?.id === "string" && typeof r.markdown === "string";
}

export const keptResults = {
  /** Resolves true when the body was stored. */
  put(result: KeptResult): Promise<boolean> {
    return run("readwrite", (s) => s.put(result), () => true, false);
  },
  get(id: string): Promise<KeptResult | null> {
    return run("readonly", (s) => s.get(id), (v) => (isKept(v) ? v : null), null);
  },
  remove(id: string): Promise<boolean> {
    return run("readwrite", (s) => s.delete(id), () => true, false);
  },
  clear(): Promise<boolean> {
    return run("readwrite", (s) => s.clear(), () => true, false);
  },
};

export type KeptResultStore = typeof keptResults;
