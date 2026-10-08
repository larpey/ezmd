import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import AxeBuilder from "@axe-core/playwright";
import { test as base, expect, type Locator, type Page } from "@playwright/test";

export const BASE_URL = process.env.PLAYWRIGHT_BASE_URL ?? "http://127.0.0.1:8000";
const ORIGIN = new URL(BASE_URL).origin;
// The only third-party origin the page may contact, and only when Turnstile is enabled (spec part4 4.1).
const ALLOWED_THIRD_PARTY = new Set(["challenges.cloudflare.com"]);
const JOB_TIMEOUT = 60_000;

/** Absolute path of a file under the repository's fixtures/ directory. */
export function fixture(rel: string): string {
  return fileURLToPath(new URL(`../../../fixtures/${rel}`, import.meta.url));
}

let reachable: boolean | undefined;
async function stackReachable(): Promise<boolean> {
  if (reachable === undefined) {
    try {
      const res = await fetch(new URL("/healthz", BASE_URL), { signal: AbortSignal.timeout(3000) });
      reachable = res.ok;
    } catch {
      reachable = false;
    }
  }
  return reachable;
}

interface Fixtures {
  /** Skips the test (before any browser starts) when the stack is not reachable. */
  stack: void;
  /** Every request that left the page's origin; asserted empty after each test. */
  offOrigin: string[];
  /** POST /v1/convert calls the page made (one per created or deduplicated job). */
  convertCalls: string[];
}

export const test = base.extend<Fixtures>({
  stack: [
    // eslint-disable-next-line no-empty-pattern -- Playwright fixtures must destructure their dependencies
    async ({}, provide, testInfo) => {
      testInfo.skip(!(await stackReachable()), `ezmd not reachable at ${BASE_URL}/healthz; start it or set PLAYWRIGHT_BASE_URL`);
      await provide();
    },
    { auto: true },
  ],
  offOrigin: [
    async ({ page, stack }, provide) => {
      void stack; // ordering only: skip before the page starts
      const seen: string[] = [];
      page.on("request", (req) => {
        const url = new URL(req.url());
        if (url.protocol === "blob:" || url.protocol === "data:") return;
        if (url.origin !== ORIGIN && !ALLOWED_THIRD_PARTY.has(url.hostname)) seen.push(req.url());
      });
      await provide(seen);
      expect(seen, "requests left the instance's origin").toEqual([]);
    },
    { auto: true },
  ],
  convertCalls: async ({ page }, provide) => {
    const calls: string[] = [];
    page.on("request", (req) => {
      if (req.method() === "POST" && new URL(req.url()).pathname === "/v1/convert") calls.push(req.url());
    });
    await provide(calls);
  },
});

export { expect };

/** Load the app with a clean history and wait until capabilities have loaded (the footer shows retention). */
export async function openApp(page: Page): Promise<void> {
  await page.goto("/");
  await expect(page.getByTestId("input-form")).toBeVisible();
  await expect(page.getByTestId("footer")).toContainText("Results are deleted after");
}

/** A unique pasted-text body, so each run creates its own job instead of reusing a deduplicated one. */
export function uniqueText(title: string): string {
  const id = `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
  return `${title}\n\nThis paragraph was pasted by the Playwright suite, run ${id}.\n\nA second paragraph keeps the word count honest.`;
}

export async function chooseFiles(page: Page, ...paths: string[]): Promise<void> {
  await page.getByTestId("input-file").setInputFiles(paths);
}

/** Submit and wait until the newest job card shows a result. Returns that card. */
export async function convertAndWait(page: Page): Promise<Locator> {
  await page.getByTestId("convert-button").click();
  return waitForNewestDone(page);
}

export async function waitForNewestDone(page: Page): Promise<Locator> {
  const card = page.getByTestId("job-card").first();
  await expect(card).toHaveAttribute("data-state", "done", { timeout: JOB_TIMEOUT });
  await expect(card.getByTestId("result")).toBeVisible();
  return card;
}

export async function download(page: Page, trigger: Locator): Promise<{ name: string; body: Buffer }> {
  const [dl] = await Promise.all([page.waitForEvent("download"), trigger.click()]);
  const path = await dl.path();
  return { name: dl.suggestedFilename(), body: await readFile(path) };
}

/** Serious and critical axe-core violations (WCAG 2.1 A/AA rules). */
export async function seriousViolations(page: Page): Promise<string[]> {
  const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]).analyze();
  return results.violations
    .filter((v) => v.impact === "serious" || v.impact === "critical")
    .map((v) => `${v.id} (${v.impact}): ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`);
}

/** Press Tab until `target` has focus; fails when it is not reachable by keyboard. */
export async function tabTo(page: Page, target: Locator, maxPresses = 80): Promise<void> {
  for (let i = 0; i < maxPresses; i++) {
    if (await target.evaluate((el) => el === document.activeElement)) return;
    await page.keyboard.press("Tab");
  }
  throw new Error(`not reachable with Tab after ${maxPresses} presses: ${target.toString()}`);
}
