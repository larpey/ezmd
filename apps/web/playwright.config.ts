import { defineConfig, devices } from "@playwright/test";

// Browser tier (docs/spec/part4.md 4.14.6). Runs against a served web UI: the compose stack
// (tests/integration/stack.sh, PLAYWRIGHT_BASE_URL=http://localhost:8080) or `uv run uvicorn` serving
// apps/web/dist. Every test skips when PLAYWRIGHT_BASE_URL/healthz does not answer.
// One worker: the anonymous per-IP limits (concurrency, creations per minute) are shared by all tests.
export default defineConfig({
  testDir: "e2e",
  timeout: 90_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  workers: 1,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["github"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL ?? "http://127.0.0.1:8000",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    acceptDownloads: true,
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] }, grepInvert: /@mobile/ },
    // iPhone 13 viewport, touch and user agent, rendered by Chromium so CI installs one browser.
    { name: "mobile", use: { ...devices["iPhone 13"], browserName: "chromium" }, grep: /@mobile/ },
  ],
});
