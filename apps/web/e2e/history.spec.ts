import type { Page } from "@playwright/test";
import { convertAndWait, expect, openApp, test, uniqueText } from "./helpers";

const HISTORY_KEY = "intomd.history.v1";

async function openHistory(page: Page): Promise<void> {
  const history = page.getByTestId("history");
  await expect(history).toBeVisible();
  if (!(await history.evaluate((el) => (el as HTMLDetailsElement).open))) await history.locator("summary").click();
}

/** Pretend the server TTL passed for every history entry (the server copy is untouched). */
async function expireHistory(page: Page): Promise<void> {
  await page.evaluate((key) => {
    const raw = window.localStorage.getItem(key);
    const entries = raw ? (JSON.parse(raw) as Array<Record<string, unknown>>) : [];
    const past = new Date(Date.now() - 60_000).toISOString();
    window.localStorage.setItem(key, JSON.stringify(entries.map((e) => ({ ...e, expires_at: past }))));
  }, HISTORY_KEY);
}

async function keptIds(page: Page): Promise<string[]> {
  return page.evaluate(
    () =>
      new Promise<string[]>((resolve) => {
        const req = indexedDB.open("intomd", 1);
        req.onerror = () => resolve([]);
        req.onsuccess = () => {
          const db = req.result;
          if (!db.objectStoreNames.contains("results")) return resolve([]);
          const keys = db.transaction("results").objectStore("results").getAllKeys();
          keys.onsuccess = () => resolve(keys.result.map(String));
          keys.onerror = () => resolve([]);
        };
      }),
  );
}

test("history survives a reload and re-opens the live result", async ({ page }) => {
  await openApp(page);
  await page.getByTestId("input-text").fill(uniqueText("History entry"));
  const card = await convertAndWait(page);
  const jobId = await card.getAttribute("data-job-id");

  await page.reload();
  await expect(page.getByTestId("job-card")).toHaveCount(0);
  await openHistory(page);
  const row = page.locator(`[data-testid="history-row"][data-job-id="${jobId}"]`);
  // Pasted text keeps its submit-time title (not the server's "pasted"); the preview holds the first characters.
  await expect(row).toContainText(/Pasted text \(\d+ words\)/);
  await expect(row).toContainText("History entry");
  await expect(row).toContainText("compact");
  await row.getByTestId("history-open").click();
  const reopened = page.locator(`[data-testid="job-card"][data-job-id="${jobId}"]`);
  await expect(reopened).toHaveAttribute("data-state", "done", { timeout: 60_000 });
  await expect(reopened.getByTestId("result-rendered")).toContainText("History entry");
});

test("a kept result opens from this device after the server copy expires", async ({ page }) => {
  await openApp(page);
  await page.getByTestId("input-text").fill(uniqueText("Kept locally"));
  const card = await convertAndWait(page);
  const jobId = (await card.getAttribute("data-job-id")) ?? "";

  await openHistory(page);
  const row = page.locator(`[data-testid="history-row"][data-job-id="${jobId}"]`);
  await row.getByTestId("history-keep").check();
  await expect.poll(() => keptIds(page)).toContain(jobId);

  await expireHistory(page);
  await page.reload();
  await openHistory(page);
  await expect(row).toContainText("Expired on the server");
  await expect(row.getByTestId("history-open")).toHaveCount(0);
  await row.getByTestId("history-open-local").click();

  const local = page.locator(`[data-testid="job-card"][data-job-id="${jobId}"]`);
  await expect(local).toHaveAttribute("data-state", "local");
  await expect(local).toContainText("Showing the copy kept on this device");
  await expect(local.getByTestId("result-rendered")).toContainText("Kept locally");
});

test("clearing history removes rows and kept copies", async ({ page }) => {
  await openApp(page);
  await page.getByTestId("input-text").fill(uniqueText("Clear me"));
  const card = await convertAndWait(page);
  const jobId = (await card.getAttribute("data-job-id")) ?? "";
  await openHistory(page);
  await page.locator(`[data-testid="history-row"][data-job-id="${jobId}"]`).getByTestId("history-keep").check();
  await expect.poll(() => keptIds(page)).toContain(jobId);

  await page.getByTestId("history-clear").click();
  await expect(page.getByTestId("history")).toHaveCount(0);
  await expect.poll(() => keptIds(page)).toEqual([]);
  await page.reload();
  await expect(page.getByTestId("input-form")).toBeVisible();
  await expect(page.getByTestId("history")).toHaveCount(0);
});
