#!/usr/bin/env node
// Reads `pnpm licenses list --json [--prod]` from stdin and fails when any package's license is
// outside the allowlist (spec part1 2.6). SPDX expressions are evaluated: an OR expression passes
// when at least one branch is allowed, an AND expression only when every operand is allowed.
//
// Usage: pnpm licenses list --json --prod | node tools/license_check.mjs

import { resolve } from "node:path";
import { fileURLToPath } from "node:url";

export const ALLOWED = new Set([
  "MIT",
  "Apache-2.0",
  "BSD-2-Clause",
  "BSD-3-Clause",
  "ISC",
  "0BSD",
  "MPL-2.0",
  "CC-BY-4.0",
  "CC0-1.0",
  "BlueOak-1.0.0",
  "Python-2.0",
  "Unlicense",
]);

function tokenize(expr) {
  return expr.replace(/\(/g, " ( ").replace(/\)/g, " ) ").trim().split(/\s+/).filter(Boolean);
}

/** Returns true when the SPDX expression is satisfiable with allowlisted licenses. Throws on malformed input. */
export function isAllowed(expr) {
  if (typeof expr !== "string" || !expr.trim()) return false;
  const tokens = tokenize(expr);
  let pos = 0;
  const peek = () => tokens[pos]?.toUpperCase();

  const parseAtom = () => {
    const tok = tokens[pos++];
    if (tok === undefined) throw new Error("unexpected end of expression");
    if (tok === "(") {
      const value = parseOr();
      if (tokens[pos++] !== ")") throw new Error("missing )");
      return value;
    }
    if (tok === ")" || ["AND", "OR", "WITH"].includes(tok.toUpperCase())) throw new Error(`unexpected ${tok}`);
    let allowed = ALLOWED.has(tok.replace(/\+$/, ""));
    if (peek() === "WITH") {
      pos += 1;
      if (tokens[pos++] === undefined) throw new Error("missing exception after WITH");
      // An exception only grants extra permissions, so the base license decides.
    }
    return allowed;
  };
  const parseAnd = () => {
    let value = parseAtom();
    while (peek() === "AND") {
      pos += 1;
      const rhs = parseAtom();
      value = value && rhs;
    }
    return value;
  };
  function parseOr() {
    let value = parseAnd();
    while (peek() === "OR") {
      pos += 1;
      const rhs = parseAnd();
      value = value || rhs;
    }
    return value;
  }

  const result = parseOr();
  if (pos !== tokens.length) throw new Error(`trailing tokens in "${expr}"`);
  return result;
}

/** Returns offending `{license, name, versions}` entries from pnpm's JSON (keyed by license). */
export function findOffenders(report) {
  const offenders = [];
  for (const [license, packages] of Object.entries(report ?? {})) {
    let ok;
    try {
      ok = isAllowed(license);
    } catch {
      ok = false;
    }
    if (ok) continue;
    for (const pkg of Array.isArray(packages) ? packages : []) {
      offenders.push({ license, name: pkg.name, versions: pkg.versions ?? [pkg.version].filter(Boolean) });
    }
  }
  return offenders;
}

async function readStdin() {
  const chunks = [];
  for await (const chunk of process.stdin) chunks.push(chunk);
  return Buffer.concat(chunks).toString("utf8");
}

async function main() {
  const raw = (await readStdin()).trim();
  if (!raw) {
    console.error("license_check: no input on stdin. Pipe `pnpm licenses list --json --prod` into this script.");
    process.exit(2);
  }
  let report;
  try {
    // pnpm prints {} (or nothing) when there are no dependencies.
    report = JSON.parse(raw);
  } catch (err) {
    console.error(`license_check: stdin is not valid JSON: ${err.message}`);
    process.exit(2);
  }
  const offenders = findOffenders(report);
  const total = Object.values(report).reduce((n, list) => n + (Array.isArray(list) ? list.length : 0), 0);
  if (offenders.length) {
    console.error(`license_check: ${offenders.length} package(s) with licenses outside the allowlist:`);
    for (const o of offenders) console.error(`  ${o.name}@${o.versions.join(",")}: ${o.license}`);
    console.error(`Allowed: ${[...ALLOWED].join(", ")}`);
    process.exit(1);
  }
  console.log(`license_check: ${total} package(s) OK.`);
}

const isMain = Boolean(process.argv[1]) && resolve(process.argv[1]) === fileURLToPath(import.meta.url);
if (isMain) await main();
