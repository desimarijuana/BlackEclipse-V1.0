#!/usr/bin/env node
/*
 * Reset Black Eclipse from the terminal.
 *
 *   node scripts/reset.js --list
 *   node scripts/reset.js --onboarding
 *   node scripts/reset.js --setup
 *   node scripts/reset.js --factory [--confirm=WIPE] [--no-backup] [--include-env] [--start]
 *
 * `--factory` stops the production and development servers first, then backs
 * up (default), then runs the existing wipe-personal-data.js primitive.
 */
"use strict";

const readline = require("readline");
const { execFileSync } = require("child_process");
const path = require("path");
const reset = require("./lib/reset");
const { killPort } = require("./lib/server");
const { DEV, PROD } = require("./lib/profiles");

const args = process.argv.slice(2);
const flag = (name) => args.includes(name);
const value = (prefix, fallback) => {
  const hit = args.find((a) => a.startsWith(prefix));
  return hit ? hit.slice(prefix.length) : fallback;
};

function log(msg) {
  console.log(`[reset] ${msg}`);
}

function usage() {
  console.log(`Usage: node scripts/reset.js <scope>

Scopes:
  --list             show every path each scope touches (dry run)
  --onboarding       re-ask the setup questions; keys and data are kept
  --setup            clear setup + API keys; chats, portfolio and research are kept
  --factory          wipe all personal data and runtime state

Factory options:
  --confirm=WIPE     required in a non-interactive shell
  --no-backup        skip the automatic backup
  --include-env      also delete .env (host secrets)
  --start            start production after the reset

Examples:
  node scripts/reset.js --list
  node scripts/reset.js --factory --confirm=WIPE
`);
}

async function confirmFactory() {
  if (value("--confirm=", "") === "WIPE") return true;
  if (!process.stdin.isTTY) {
    log('refusing non-interactive factory reset without --confirm=WIPE');
    return false;
  }
  const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
  const answer = await new Promise((resolve) =>
    rl.question('Type WIPE to permanently remove all local Eclipse data: ', resolve),
  );
  rl.close();
  return answer.trim() === "WIPE";
}

function stopServers() {
  const prod = killPort(String(PROD.appPort));
  const dev = killPort(String(DEV.appPort));
  log(`servers stopped: production=${prod ? "yes" : "no"}, development=${dev ? "yes" : "no"}`);
}

async function main() {
  if (flag("--help") || flag("-h") || args.length === 0) {
    usage();
    return;
  }

  if (flag("--list")) {
    const targets = reset.describeTargets();
    log(`data dir: ${reset.dataDir()}`);
    log(`database: ${reset.dbPath()}`);
    log(`factory reset would touch ${targets.length} existing path(s):`);
    for (const t of targets) console.log(`  - ${t}`);
    log(`onboarding/setup reset would clear SystemConfig rows only (no user data).`);
    return;
  }

  if (flag("--onboarding")) {
    const result = reset.resetOnboarding();
    if (result.error) {
      log(`failed: ${result.error}`);
      process.exitCode = 1;
      return;
    }
    log(`onboarding set to pending (${result.updated ?? result.removed} row). The next start shows setup.`);
    log("run `black eclipse` (or `npm run dev`) to open it.");
    return;
  }

  if (flag("--setup")) {
    const result = reset.resetSetup();
    if (result.error) {
      log(`failed: ${result.error}`);
      process.exitCode = 1;
      return;
    }
    log(`setup config removed (${result.removed} row(s)). Chats, portfolio and research are untouched.`);
    log("run `black eclipse` (or `npm run dev`) to open setup.");
    return;
  }

  if (flag("--factory")) {
    if (!(await confirmFactory())) {
      log("nothing was deleted.");
      process.exitCode = 1;
      return;
    }
    stopServers();
    const backup = !flag("--no-backup");
    const includeEnv = flag("--include-env");
    log(`factory reset starting (backup=${backup ? "yes" : "no"}, include-env=${includeEnv ? "yes" : "no"})`);
    reset.runFactoryReset({ backup, includeEnv, log });
    log("done. The next start boots as a new install.");

    if (flag("--start")) {
      const bin = path.join(reset.SITE, "bin", "black.js");
      execFileSync(process.execPath, [bin, "eclipse"], { stdio: "inherit" });
    } else {
      log("run `black eclipse` to start and show onboarding.");
    }
    return;
  }

  usage();
  process.exitCode = 2;
}

main().catch((err) => {
  console.error("[reset] error:", err && err.message ? err.message : err);
  process.exitCode = 1;
});
