/// <reference types="vitest/config" />
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const pkg = JSON.parse(readFileSync(new URL("./package.json", import.meta.url), "utf8")) as { version: string };
const API_TARGET = process.env.EZMD_API_PROXY ?? "http://127.0.0.1:8000";
const proxy = Object.fromEntries(["/v1", "/healthz", "/readyz"].map((p) => [p, { target: API_TARGET, changeOrigin: false }]));

export default defineConfig({
  plugins: [react()],
  define: { __APP_VERSION__: JSON.stringify(pkg.version) },
  resolve: {
    // Consume the SDK from source so the web app never depends on a prebuilt dist.
    alias: { "@ezmd/sdk": fileURLToPath(new URL("../../packages/sdk-ts/src/index.ts", import.meta.url)) },
  },
  server: { proxy },
  preview: { proxy },
  build: { outDir: "dist", sourcemap: false, target: "es2022" },
  test: {
    environment: "jsdom",
    include: ["src/**/*.test.{ts,tsx}"],
    setupFiles: ["src/test-setup.ts"],
  },
});
