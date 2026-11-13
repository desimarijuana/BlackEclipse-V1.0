#!/usr/bin/env node
/**
 * Turn on the front-door login (single-operator auth), safely.
 *
 * BlackEclipse ships with `HARNESS_AUTH=off` because it is a local, single-user
 * app. The moment it is reachable by another machine that is the wrong default,
 * and flipping it by hand is easy to get wrong (a required mode with no secret
 * fails every request closed with 503). This script does the one correct edit:
 *
 *   HARNESS_AUTH=required
 *   HARNESS_AUTH_SECRET=<32 random bytes, hex>
 *
 * It NEVER rotates a secret that is already set, and it never prints the value.
 *
 *   npm run auth:setup              # edit .env in the app root
 *   npm run auth:setup -- --dry-run # show the change, write nothing
 *   npm run auth:setup -- --file path/to/.env
 */

"use strict";

const crypto = require("crypto");
const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..");
const PLACEHOLDER = "change-me-to-a-random-secret";

function parseArgs(argv) {
  const out = { file: path.join(ROOT, ".env"), dryRun: false };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === "--dry-run") out.dryRun = true;
    else if (arg === "--file") {
      const value = argv[i + 1];
      if (!value) throw new Error("--file needs a path");
      out.file = path.resolve(process.cwd(), value);
      i += 1;
    } else if (arg === "--help" || arg === "-h") out.help = true;
    else throw new Error(`unknown option: ${arg}`);
  }
  return out;
}

/** The value of `KEY` in a .env body, or undefined. Pure; testable. */
function readValue(text, key) {
  const match = text.match(new RegExp(`^\\s*${key}\\s*=\\s*(.*)$`, "m"));
  if (!match) return undefined;
  return match[1].trim().replace(/^["']|["']$/g, "");
}

/** Replace or append `KEY=value` without disturbing any other line. Pure. */
function setValue(text, key, value) {
  const line = `${key}=${value}`;
  const pattern = new RegExp(`^\\s*${key}\\s*=.*$`, "m");
  if (pattern.test(text)) return text.replace(pattern, line);
  const sep = text.length === 0 || text.endsWith("\n") ? "" : "\n";
  return `${text}${sep}${line}\n`;
}

function buildUpdate(text, secret) {
  const current = readValue(text, "HARNESS_AUTH_SECRET");
  if (current && current !== PLACEHOLDER && current.length >= 16) {
    return { ok: false, reason: "already-configured", secret: null };
  }
  let next = setValue(text, "HARNESS_AUTH", "required");
  next = setValue(next, "HARNESS_AUTH_SECRET", secret);
  return { ok: true, text: next, secret };
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  if (args.help) {
    console.log("Usage: node scripts/enable-auth.js [--dry-run] [--file <path>]");
    return 0;
  }
  const exists = fs.existsSync(args.file);
  const text = exists ? fs.readFileSync(args.file, "utf8") : "";
  const secret = crypto.randomBytes(32).toString("hex");
  const update = buildUpdate(text, secret);

  if (!update.ok) {
    console.error(
      `Refusing to touch ${args.file}: HARNESS_AUTH_SECRET is already set.\n` +
        "Rotating a live signing secret would sign every user out. Edit it by hand if that is what you want.",
    );
    return 1;
  }

  if (args.dryRun) {
    console.log(`[auth] would write ${args.file}`);
    console.log(`[auth] HARNESS_AUTH=required`);
    console.log(`[auth] HARNESS_AUTH_SECRET=<generated, ${secret.length} chars>`);
    return 0;
  }

  fs.writeFileSync(args.file, update.text, "utf8");
  console.log(`[auth] wrote ${args.file}`);
  console.log("[auth] HARNESS_AUTH=required, HARNESS_AUTH_SECRET generated (value not printed)");
  console.log("");
  console.log("Next:");
  console.log("  1. Restart the app (close the window and reopen it, or npm run desktop:refresh).");
  console.log("  2. Open the app: the first visit shows /login in SETUP mode.");
  console.log("  3. Create the operator account, then sign in.");
  console.log("");
  console.log("Keep CRON_SECRET set as well: the runtime uses it for non-loopback binds.");
  console.log("Docs: docs/harness/authentication.md");
  return 0;
}

if (require.main === module) {
  try {
    process.exitCode = main();
  } catch (err) {
    console.error(`[auth] ${err instanceof Error ? err.message : String(err)}`);
    process.exitCode = 1;
  }
}

module.exports = { buildUpdate, readValue, setValue };
