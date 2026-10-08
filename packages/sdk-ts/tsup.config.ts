import { defineConfig } from "tsup";

export default defineConfig({
  entry: { index: "src/index.ts", node: "src/node.ts" },
  format: ["esm", "cjs"],
  dts: true,
  clean: true,
  minify: true,
  sourcemap: false,
  target: "es2022",
  platform: "neutral",
  external: ["node:fs", "node:path"],
});
