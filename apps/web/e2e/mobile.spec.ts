import { chooseFiles, convertAndWait, download, expect, fixture, openApp, seriousViolations, test, uniqueText } from "./helpers";

// Runs in the `mobile` project only (iPhone 13 viewport, touch; playwright.config.ts).

const noHorizontalScroll = (page: import("@playwright/test").Page) =>
  page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth);

test("@mobile core flow: paste text, convert, read, download", async ({ page }) => {
  await openApp(page);
  expect(await noHorizontalScroll(page)).toBe(true);
  await page.getByTestId("input-text").fill(uniqueText("Mobile notes"));
  await page.getByTestId("convert-button").tap();
  const card = page.getByTestId("job-card").first();
  await expect(card).toHaveAttribute("data-state", "done", { timeout: 60_000 });
  await expect(card.getByTestId("result-rendered")).toContainText("Mobile notes");
  expect(await seriousViolations(page)).toEqual([]);
  await card.getByTestId("tab-raw").tap();
  await expect(card.getByTestId("result-raw")).toContainText("Mobile notes");
  expect(await noHorizontalScroll(page)).toBe(true);

  const md = await download(page, card.getByTestId("download-md"));
  expect(md.name).toMatch(/\.md$/);
});

// Regression (docs/decisions/P1-T15.md finding 4): the Raw tab's scrolling <pre> must be focusable.
test("@mobile raw tab passes axe", async ({ page }) => {
  await openApp(page);
  await page.getByTestId("input-text").fill(uniqueText("Mobile raw axe"));
  const card = await convertAndWait(page);
  await card.getByTestId("tab-raw").tap();
  expect(await seriousViolations(page)).toEqual([]);
});

test("@mobile file upload with a wide table stays within the viewport", async ({ page }) => {
  await openApp(page);
  await chooseFiles(page, fixture("data/tsv-basic/input.tsv"));
  const card = await convertAndWait(page);
  await expect(card.getByTestId("result-rendered").locator("table")).toBeVisible();
  expect(await noHorizontalScroll(page)).toBe(true);
});
