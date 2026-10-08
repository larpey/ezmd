import { chooseFiles, convertAndWait, download, expect, fixture, openApp, test, uniqueText } from "./helpers";

test("downloads every offered format", async ({ page }) => {
  await openApp(page);
  await page.getByTestId("input-text").fill(uniqueText("Download formats"));
  const card = await convertAndWait(page);

  const md = await download(page, card.getByTestId("download-md"));
  expect(md.name).toMatch(/\.md$/);
  expect(md.body.toString("utf8")).toMatch(/^---\n/);
  expect(md.body.toString("utf8")).toContain("Download formats");

  const txt = await download(page, card.getByTestId("download-txt"));
  expect(txt.name).toMatch(/\.txt$/);
  expect(txt.body.toString("utf8")).toContain("Download formats");
  expect(txt.body.toString("utf8")).not.toMatch(/^---\n/);

  const json = await download(page, card.getByTestId("download-json"));
  expect(json.name).toMatch(/\.json$/);
  // The compact profile has no sidecar, so the .json download is the whole JSON result.
  const body = JSON.parse(json.body.toString("utf8")) as { markdown?: string; frontmatter?: { profile?: string } };
  expect(body.markdown).toContain("Download formats");
  expect(body.frontmatter?.profile).toBe("compact");

  const zip = await download(page, card.getByTestId("download-zip"));
  expect(zip.name).toMatch(/\.zip$/);
  expect(zip.body.subarray(0, 2).toString("latin1")).toBe("PK");

  await expect(card.getByTestId("download-docx")).toHaveCount(0);
});

test("warnings panel shows each warning with its code and a suggested action", async ({ page }) => {
  await openApp(page);
  await chooseFiles(page, fixture("code/source-planted-secret/input.py"));
  const card = await convertAndWait(page);

  const panel = card.getByTestId("warnings-panel");
  await expect(panel).toBeVisible();
  await expect(card.getByTestId("warnings-summary")).toContainText(/\d+ warnings?/);
  await card.getByTestId("warnings-summary").click();
  const item = panel.locator('[data-testid="warning-item"][data-code="secret_redacted"]');
  await expect(item).toBeVisible();
  await expect(item.getByTestId("warning-action")).not.toBeEmpty();

  await card.getByTestId("tab-warnings").click();
  await expect(card.getByTestId("tab-warnings")).toHaveText(/Warnings \([1-9]\d*\)/);
  await expect(card.getByRole("tabpanel").locator('[data-code="secret_redacted"]')).toBeVisible();

  await card.getByTestId("tab-raw").click();
  await expect(card.getByTestId("result-raw")).not.toContainText("a4e3770643c072829845a0b6c58a00aa6f78e8b5");
});

test("a clean conversion says nothing was dropped", async ({ page }) => {
  await openApp(page);
  await page.getByTestId("input-text").fill(uniqueText("No warnings here"));
  const card = await convertAndWait(page);
  await expect(card.getByTestId("warnings-panel")).toHaveCount(0);
  await card.getByTestId("tab-warnings").click();
  await expect(card.getByRole("tabpanel")).toContainText("Nothing was dropped");
});
