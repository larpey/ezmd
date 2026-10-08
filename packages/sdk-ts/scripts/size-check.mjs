// Size gate for @intomd/sdk (spec part4 4.5.3): the main ESM bundle must stay under 8 KB gzipped.
import { readFileSync } from "node:fs";
import { gzipSync } from "node:zlib";
import { fileURLToPath } from "node:url";

const LIMIT_BYTES = 8 * 1024;
const targets = ["../dist/index.js", "../dist/index.cjs"];
let failed = false;
for (const rel of targets) {
  const path = fileURLToPath(new URL(rel, import.meta.url));
  let raw;
  try {
    raw = readFileSync(path);
  } catch {
    console.error(`size-check: ${rel} not found; run the build first.`);
    process.exit(1);
  }
  const gz = gzipSync(raw, { level: 9 }).length;
  const ok = gz <= LIMIT_BYTES;
  failed ||= !ok;
  console.log(`size-check: ${rel.replace("../", "")} ${gz} B gzipped (limit ${LIMIT_BYTES} B) ${ok ? "OK" : "FAIL"}`);
}
process.exit(failed ? 1 : 0);
