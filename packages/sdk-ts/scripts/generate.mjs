// Regenerates src/openapi.d.ts from docs/api/openapi.json when the API has exported it.
import { existsSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const spec = fileURLToPath(new URL("../../../docs/api/openapi.json", import.meta.url));
const out = fileURLToPath(new URL("../src/openapi.d.ts", import.meta.url));
if (!existsSync(spec)) {
  console.log("generate: docs/api/openapi.json not found; keeping hand-written types in src/types.ts.");
  process.exit(0);
}
const result = spawnSync("openapi-typescript", [spec, "-o", out], { stdio: "inherit", shell: process.platform === "win32" });
process.exit(result.status ?? 1);
