import { fileURLToPath } from "node:url";
import { expect, test } from "@playwright/test";

const BASE_URL = process.env.PLAYWRIGHT_BASE_URL ?? "http://127.0.0.1:8000";
const FIXTURE = fileURLToPath(new URL("../../../fixtures/text/markdown-kitchen-sink/input.md", import.meta.url));

let reachable = false;

test.beforeAll(async () => {
  try {
    const res = await fetch(new URL("/healthz", BASE_URL), { signal: AbortSignal.timeout(3000) });
    reachable = res.ok;
  } catch {
    reachable = false;
  }
});

// Evaluated before the page fixture is created, so an unreachable server skips without launching a browser.
test.skip(() => !reachable, `intomd API not reachable at ${BASE_URL}/healthz; start it or set PLAYWRIGHT_BASE_URL`);

test("uploads a Markdown file and shows the rendered result", async ({ page }) => {

  const offOrigin: string[] = [];
  page.on("request", (req) => {
    const url = new URL(req.url());
    if (url.origin !== new URL(BASE_URL).origin && url.hostname !== "challenges.cloudflare.com") offOrigin.push(req.url());
  });

  await page.goto("/");
  await page.getByLabel("Files to convert").setInputFiles(FIXTURE);
  await expect(page.getByText(/1 file/)).toBeVisible();
  await page.getByRole("button", { name: "Convert" }).click();

  const result = page.getByRole("region", { name: "Result" });
  await expect(result.getByRole("heading", { name: "Kitchen Sink", level: 1 })).toBeVisible({ timeout: 45_000 });
  await expect(result.getByRole("heading", { name: "Lists" })).toBeVisible();

  await result.getByRole("tab", { name: "Raw" }).click();
  await expect(result.getByRole("tabpanel")).toContainText("# Kitchen Sink");
  expect(offOrigin).toEqual([]);
});
