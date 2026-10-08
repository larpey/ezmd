import { beforeEach, describe, expect, it } from "vitest";
import { classifyText, downloadName, formatBytes } from "./input";
import { renderMarkdown, stripFrontmatter } from "./markdown";
import { HISTORY_KEY, HISTORY_LIMIT, loadHistory, upsertHistory, type HistoryEntry } from "./storage";

describe("input helpers", () => {
  it("classifies a lone URL, text and empty input", () => {
    expect(classifyText("  https://example.com/a?b=1 ")).toEqual({ kind: "url", url: "https://example.com/a?b=1" });
    expect(classifyText("see https://example.com now")).toMatchObject({ kind: "text", words: 3 });
    expect(classifyText("   ")).toEqual({ kind: "empty" });
  });

  it("formats bytes and download names", () => {
    expect(formatBytes(512)).toBe("512 B");
    expect(formatBytes(4.2 * 1024 * 1024)).toBe("4.2 MB");
    expect(downloadName("Q3 Fleet Report!", "job_1", "md")).toBe("q3-fleet-report.md");
    expect(downloadName(undefined, "job_1", "md")).toBe("job_1.md");
    expect(downloadName("x".repeat(200), "job_1", "md")).toHaveLength(83);
  });
});

describe("markdown", () => {
  it("strips frontmatter and renders GFM safely", () => {
    expect(stripFrontmatter("---\na: 1\n---\nbody")).toBe("body");
    const html = renderMarkdown("| a |\n|---|\n| 1 |\n\n- [x] done\n\n[l](javascript:alert(1))\n<img src=x onerror=alert(1)>");
    expect(html).toContain("<table>");
    expect(html).not.toContain("javascript:");
    expect(html).not.toContain("<img");
    expect(html).toContain("&lt;img");
  });
});

describe("history storage", () => {
  beforeEach(() => localStorage.clear());

  const entry = (id: string): HistoryEntry => ({ id, title: id, source_kind: "file", created_at: "", expires_at: "", profile: "compact" });

  it("caps history and moves updated entries to the top", () => {
    let list: HistoryEntry[] = [];
    for (let i = 0; i < HISTORY_LIMIT + 5; i++) list = upsertHistory(list, entry(`job_${i}`));
    expect(list).toHaveLength(HISTORY_LIMIT);
    list = upsertHistory(list, { ...entry("job_10"), tokens: 5 });
    expect(list[0]).toMatchObject({ id: "job_10", tokens: 5 });
  });

  it("tolerates corrupt storage", () => {
    localStorage.setItem(HISTORY_KEY, "{not json");
    expect(loadHistory()).toEqual([]);
  });
});
