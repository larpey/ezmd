import { chooseFiles, convertAndWait, download, expect, fixture, openApp, test, uniqueText, waitForNewestDone } from "./helpers";

const KITCHEN_SINK = fixture("text/markdown-kitchen-sink/input.md");
const TSV = fixture("data/tsv-basic/input.tsv");

test("converts an uploaded Markdown file and shows the rendered result", async ({ page }) => {
  await openApp(page);
  await chooseFiles(page, KITCHEN_SINK);
  await expect(page.getByTestId("input-chip")).toContainText("1 file");
  await page.getByTestId("profile-full").check();
  const card = await convertAndWait(page);

  const result = card.getByTestId("result");
  await expect(result.getByRole("heading", { name: "Kitchen Sink", level: 1 })).toBeVisible();
  await expect(result.getByRole("heading", { name: "Lists" })).toBeVisible();

  await card.getByTestId("tab-raw").click();
  await expect(card.getByTestId("result-raw")).toContainText("# Kitchen Sink");
  await card.getByTestId("tab-sidecar").click();
  await expect(card.getByRole("tabpanel")).toContainText('"blocks"');
});

// Regression (docs/decisions/P1-T15.md finding 2): files picked right after a profile click were dropped.
test("files chosen right after a profile change are kept", async ({ page }) => {
  await openApp(page);
  await page.getByTestId("profile-full").check();
  await chooseFiles(page, KITCHEN_SINK);
  await expect(page.getByTestId("input-chip")).toContainText("1 file", { timeout: 3_000 });
});

// Regression (docs/decisions/P1-T15.md finding 3): frontmatter `tokens` is an object per tokenizer.
test("result shows the o200k token count badge", async ({ page }) => {
  await openApp(page);
  await page.getByTestId("input-text").fill(uniqueText("Token badge"));
  const card = await convertAndWait(page);
  await expect(card.getByTestId("result-tokens")).toContainText(/\d tokens/, { timeout: 3_000 });
  await expect(card.getByTestId("result-tokens")).toHaveAttribute("title", "o200k_base count");
});

test("converts pasted text and reports progress", async ({ page }) => {
  await openApp(page);
  const text = uniqueText("Harbor notes");
  await page.getByTestId("input-text").fill(text);
  await expect(page.getByTestId("input-chip")).toContainText(/Text, \d+ words/);
  await page.getByTestId("convert-button").click();

  const card = page.getByTestId("job-card").first();
  await expect(card.getByRole("heading", { name: /Pasted text \(\d+ words\)/ })).toBeVisible();
  // Progress is shown until the result arrives (it may finish before the first paint on a fast box).
  await expect(card.getByTestId("job-progress").or(card.getByTestId("result"))).toBeVisible();
  const done = await waitForNewestDone(page);
  await expect(done.getByTestId("result-rendered")).toContainText("pasted by the Playwright suite");
  await expect(page.getByTestId("input-text")).toHaveValue("");
});

test("profile chosen before converting, then switched on the result without a new job", async ({ page, convertCalls }) => {
  await openApp(page);
  await page.getByTestId("profile-full").check();
  await expect(page.getByTestId("profile-full")).toBeChecked();
  await page.getByTestId("input-text").fill(uniqueText("Profile switch"));
  const card = await convertAndWait(page);
  expect(convertCalls).toHaveLength(1);

  const select = card.getByTestId("result-profile");
  await expect(select).toHaveValue("full");
  await card.getByTestId("tab-raw").click();
  const raw = card.getByTestId("result-raw");
  const fullText = await raw.innerText();

  const rerender = page.waitForResponse((r) => r.url().includes("/result") && r.url().includes("profile=agent") && r.ok());
  await select.selectOption("agent");
  await rerender;
  await expect(select).toHaveValue("agent");
  await expect(raw).not.toHaveText(fullText);
  await expect(raw).toContainText("Profile switch");
  expect(convertCalls, "switching the profile must not create a job").toHaveLength(1);
  await expect(page.getByTestId("job-card")).toHaveCount(1);
});

test("two files become two jobs and download together as a zip", async ({ page }) => {
  await openApp(page);
  await chooseFiles(page, KITCHEN_SINK, TSV);
  await expect(page.getByTestId("input-chip")).toContainText("2 files");
  await page.getByTestId("convert-button").click();
  const cards = page.getByTestId("job-card");
  await expect(cards).toHaveCount(2);
  for (const card of await cards.all()) await expect(card).toHaveAttribute("data-state", "done", { timeout: 60_000 });

  const all = page.getByTestId("download-all-zip");
  await expect(all).toContainText("(2)");
  const zip = await download(page, all);
  expect(zip.name).toBe("intomd-results.zip");
  expect(zip.body.subarray(0, 2).toString("latin1")).toBe("PK");
});

test("closing a job card removes it", async ({ page }) => {
  await openApp(page);
  await page.getByTestId("input-text").fill(uniqueText("Close me"));
  const card = await convertAndWait(page);
  await card.getByTestId("job-close").click();
  await expect(page.getByTestId("job-card")).toHaveCount(0);
});

// Needs the stack's phase 2 (tests/integration/stack.sh private): the fixture server is on a private network.
test("pastes a URL and converts the fetched page", async ({ page }) => {
  const origin = process.env.INTOMD_FIXTURE_ORIGIN;
  test.skip(!origin || process.env.INTOMD_PRIVATE_FETCH !== "1", "needs INTOMD_FIXTURE_ORIGIN and INTOMD_PRIVATE_FETCH=1");
  await openApp(page);
  const url = `${origin}/article-standard/input.html?run=${Date.now()}`;
  await page.getByTestId("input-text").fill(url);
  await expect(page.getByTestId("input-chip")).toContainText("URL");
  await page.getByTestId("input-text").press("Enter");
  const card = await waitForNewestDone(page);
  await expect(card.getByTestId("result-rendered").getByRole("heading", { name: "Tide Tables for Small Harbors" })).toBeVisible();
});
