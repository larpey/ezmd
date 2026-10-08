import { strFromU8, unzipSync } from "fflate";
import { afterEach, describe, expect, it, vi } from "vitest";
import { keptResults } from "./localstore";
import { HISTORY_KEY, loadHistory, readJson, removeKey, upsertHistory, writeJson, type HistoryEntry } from "./storage";
import { zipEntryNames, zipResults } from "./zip";

describe("zip all", () => {
  it("names entries from titles, deduplicated, falling back to the job id", () => {
    expect(
      zipEntryNames([
        { id: "j1", title: "Report", markdown: "" },
        { id: "j2", title: "Report", markdown: "" },
        { id: "j3", title: "", markdown: "" },
      ]),
    ).toEqual(["report.md", "report-2.md", "j3.md"]);
  });

  it("builds a zip with every result body", async () => {
    const blob = await zipResults([
      { id: "j1", title: "A", markdown: "# A\n" },
      { id: "j2", title: "B", markdown: "# B\n" },
    ]);
    expect(blob.type).toBe("application/zip");
    const buf = await new Promise<ArrayBuffer>((resolve) => {
      const r = new FileReader();
      r.onload = () => resolve(r.result as ArrayBuffer);
      r.readAsArrayBuffer(blob);
    });
    const files = unzipSync(new Uint8Array(buf));
    expect(Object.keys(files).sort()).toEqual(["a.md", "b.md"]);
    expect(strFromU8(files["b.md"]!)).toBe("# B\n");
  });
});

describe("storage unavailable", () => {
  afterEach(() => vi.restoreAllMocks());

  it("localStorage helpers never throw", () => {
    const boom = () => {
      throw new DOMException("denied", "SecurityError");
    };
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(boom);
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(boom);
    vi.spyOn(Storage.prototype, "removeItem").mockImplementation(boom);
    expect(readJson("x", 1)).toBe(1);
    expect(() => writeJson("x", 2)).not.toThrow();
    expect(() => removeKey("x")).not.toThrow();
    expect(loadHistory()).toEqual([]);
  });

  it("IndexedDB helpers resolve with fallbacks when indexedDB is missing", async () => {
    expect(typeof indexedDB).toBe("undefined");
    await expect(keptResults.put({ id: "a", title: "t", markdown: "m", saved_at: "" })).resolves.toBe(false);
    await expect(keptResults.get("a")).resolves.toBeNull();
    await expect(keptResults.clear()).resolves.toBe(false);
  });

  it("drops malformed history rows and updates in place when asked", () => {
    localStorage.setItem(HISTORY_KEY, JSON.stringify([{ id: "ok", title: "t" }, { nope: true }, 5]));
    expect(loadHistory().map((e) => e.id)).toEqual(["ok"]);
    const list: HistoryEntry[] = [
      { id: "a", title: "a", source_kind: "url", created_at: "", expires_at: "", profile: "rag" },
      { id: "b", title: "b", source_kind: "url", created_at: "", expires_at: "", profile: "rag" },
    ];
    expect(upsertHistory(list, { ...list[1]!, keep: true }, { moveToTop: false }).map((e) => [e.id, e.keep])).toEqual([
      ["a", undefined],
      ["b", true],
    ]);
  });
});
