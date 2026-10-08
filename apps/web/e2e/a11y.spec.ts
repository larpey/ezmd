import { convertAndWait, expect, openApp, seriousViolations, tabTo, test, uniqueText, waitForNewestDone } from "./helpers";

test.use({ permissions: ["clipboard-read", "clipboard-write"] });

const bodyBackground = (page: import("@playwright/test").Page) => page.evaluate(() => getComputedStyle(document.body).backgroundColor);

test("dark mode toggle applies, persists across reloads, and returns to the system theme", async ({ page }) => {
  await page.emulateMedia({ colorScheme: "light" });
  await openApp(page);
  const light = await bodyBackground(page);
  const theme = page.getByLabel("Theme");

  await theme.selectOption("dark");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  const dark = await bodyBackground(page);
  expect(dark).not.toBe(light);

  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await expect(theme).toHaveValue("dark");
  expect(await bodyBackground(page)).toBe(dark);

  await theme.selectOption("system");
  await expect(page.locator("html")).not.toHaveAttribute("data-theme", /.+/);
  expect(await bodyBackground(page)).toBe(light);
  await page.emulateMedia({ colorScheme: "dark" });
  expect(await bodyBackground(page)).toBe(dark);
});

test("keyboard only: paste, convert, switch tabs, copy, download", async ({ page }) => {
  await openApp(page);
  const input = page.getByTestId("input-text");
  await tabTo(page, input);
  const text = uniqueText("Keyboard flow");
  await page.keyboard.insertText(text);
  await page.keyboard.press("Control+Enter");
  const card = await waitForNewestDone(page);

  // Tabs: roving tabindex with arrow keys.
  const rendered = card.getByTestId("tab-rendered");
  await tabTo(page, rendered);
  await page.keyboard.press("ArrowRight");
  await expect(card.getByTestId("tab-raw")).toBeFocused();
  await expect(card.getByTestId("tab-raw")).toHaveAttribute("aria-selected", "true");
  await expect(card.getByTestId("result-raw")).toContainText("Keyboard flow");
  await page.keyboard.press("End");
  await expect(card.getByTestId("tab-warnings")).toBeFocused();
  await page.keyboard.press("Home");
  await expect(rendered).toBeFocused();

  // Copy with Shift+Tab back to the copy button, then Enter.
  const copy = card.getByTestId("result-copy");
  await copy.focus();
  await page.keyboard.press("Enter");
  await expect(copy).toHaveText("Copied");
  expect(await page.evaluate(() => navigator.clipboard.readText())).toContain("Keyboard flow");

  await tabTo(page, card.getByTestId("download-md"));
  const [dl] = await Promise.all([page.waitForEvent("download"), page.keyboard.press("Enter")]);
  expect(dl.suggestedFilename()).toMatch(/\.md$/);
});

test("profile radios and the convert button are reachable and operable by keyboard", async ({ page }) => {
  await openApp(page);
  await tabTo(page, page.getByTestId("input-text"));
  await page.keyboard.insertText(uniqueText("Radio keys"));
  await tabTo(page, page.getByTestId("profile-compact"));
  await page.keyboard.press("ArrowRight");
  await expect(page.getByTestId("profile-rag")).toBeChecked();
  await tabTo(page, page.getByTestId("convert-button"));
  await page.keyboard.press("Enter");
  const card = await waitForNewestDone(page);
  await expect(card.getByTestId("result-profile")).toHaveValue("rag");
});

test("axe-core: no serious or critical violations on the empty page, with a result, and in dark mode", async ({ page }) => {
  await openApp(page);
  expect(await seriousViolations(page)).toEqual([]);

  await page.getByTestId("input-text").fill(uniqueText("Accessibility scan"));
  const card = await convertAndWait(page);
  await page.getByTestId("history").locator("summary").click();
  expect(await seriousViolations(page)).toEqual([]);

  await card.getByTestId("tab-raw").click();
  await page.getByLabel("Theme").selectOption("dark");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  expect(await seriousViolations(page)).toEqual([]);
});
