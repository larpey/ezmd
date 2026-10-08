// Fails the build when the main JS chunk exceeds 180 KB gzipped (spec part4 4.1.3).
import { readdirSync, readFileSync } from "node:fs";
import { gzipSync } from "node:zlib";
import { fileURLToPath } from "node:url";

const LIMIT = 180 * 1024;
const dir = fileURLToPath(new URL("../dist/assets/", import.meta.url));
const files = readdirSync(dir).filter((f) => f.endsWith(".js"));
let total = 0;
for (const f of files) {
  const gz = gzipSync(readFileSync(dir + f), { level: 9 }).length;
  total += gz;
  console.log(`bundle-size: ${f} ${(gz / 1024).toFixed(1)} KB gzipped`);
}
console.log(`bundle-size: total ${(total / 1024).toFixed(1)} KB (limit ${LIMIT / 1024} KB)`);
process.exit(total > LIMIT ? 1 : 0);
