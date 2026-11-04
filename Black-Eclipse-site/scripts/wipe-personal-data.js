#!/usr/bin/env node
/*
 * Wipe personal data — the "leave no trace" control.
 *
 * WHY: "your data stays with you" also means you can destroy it on demand. This
 * removes the databases, the runtime state, the artifacts, the recordings, the
 * backups and the credential files the app created. It never touches source code.
 *
 * Usage:
 *   node scripts/wipe-personal-data.js                 show what would be removed
 *   node scripts/wipe-personal-data.js --confirm=WIPE  actually remove
 *   node scripts/wipe-personal-data.js --confirm=WIPE --include-env
 *
 * IMPORTANT: this is a delete, not a secure erase. On SSDs/Windows the old bytes
 * may survive in free space or in shadow copies. The real guarantee is that the
 * data lived on an encrypted volume (scripts/setup-data-vault.ps1): once the
 * files are gone and the volume is re-encrypted, the ciphertext is all that
 * remains. If you have no vault, wipe the free space too (cipher /w:).
 */
"use strict";

const fs = require("fs");
const path = require("path");

const SITE = path.join(__dirname, "..");
const REPO = path.join(SITE, "..");
const CONFIRM = process.argv.find((a) => a.startsWith("--confirm="));
const CONFIRMED = CONFIRM === "--confirm=WIPE";
const INCLUDE_ENV = process.argv.includes("--include-env");

function readDotEnvValue(key) {
  try {
    const text = fs.readFileSync(path.join(SITE, ".env"), "utf8");
    for (const line of text.split(/\r?\n/)) {
      const m = /^\s*([A-Za-z0-9_]+)\s*=\s*(.*)\s*$/.exec(line);
      if (m && m[1] === key) return m[2].replace(/^["']|["']$/g, "");
    }
  } catch {
    /* no .env */
  }
  return undefined;
}

const dataDir = process.env.BE_DATA_DIR
  ? path.resolve(process.env.BE_DATA_DIR)
  : readDotEnvValue("BE_DATA_DIR")
    ? path.resolve(readDotEnvValue("BE_DATA_DIR"))
    : SITE;

// The three personal databases and their SQLite sidecars.
const dbNames = ["jdds.db", "agent-memory.db", "eclipse-memory.db"];
const dbFiles = [];
for (const name of dbNames) {
  for (const suffix of ["", "-wal", "-shm", "-journal"]) {
    dbFiles.push(path.join(dataDir, `${name}${suffix}`));
  }
}

const targets = [
  ...dbFiles,
  path.join(SITE, ".black-eclipse"),
  path.join(SITE, "python", ".black-eclipse"),
  path.join(dataDir, "backups"),
  path.join(SITE, "backups"),
  path.join(REPO, "_backups"),
  path.join(SITE, "mcp-servers.json"),
  path.join(REPO, "mcp-servers.json"),
  path.join(SITE, ".connector-key"),
];
if (INCLUDE_ENV) targets.push(path.join(SITE, ".env"));

// When the data lives on the encrypted vault, most of the paths above are
// links/junctions. Deleting a link removes only the link, so add the REAL
// targets too (the same names setup-data-vault.ps1 uses).
if (path.resolve(dataDir) !== path.resolve(SITE)) {
  targets.push(
    path.join(dataDir, ".black-eclipse"),
    path.join(dataDir, "python-black-eclipse"),
    path.join(dataDir, "backups"),
    path.join(dataDir, "_backups"),
    path.join(dataDir, "site-mcp-servers.json"),
    path.join(dataDir, "mcp-servers.json"),
    path.join(dataDir, "connector-key"),
  );
}

// Refuse to delete anything outside the three roots we own. A wrong BE_DATA_DIR
// must never turn into "rm -rf /".
const allowedRoots = [SITE, REPO, dataDir].map((p) => path.resolve(p) + path.sep);
function insideAllowed(target) {
  const resolved = path.resolve(target);
  return allowedRoots.some((root) => resolved.startsWith(root));
}

const existing = [...new Set(targets.filter((t) => fs.existsSync(t) && insideAllowed(t)))];
const skipped = [...new Set(targets.filter((t) => fs.existsSync(t) && !insideAllowed(t)))];

console.log("BlackEclipse personal-data wipe");
console.log(`  data dir: ${dataDir}`);
console.log(`  targets with data: ${existing.length}`);
for (const t of existing) console.log(`    - ${t}`);
if (skipped.length) {
  console.log("\n  REFUSED (outside the repo/vault roots):");
  for (const t of skipped) console.log(`    - ${t}`);
}

if (!CONFIRMED) {
  console.log(
    "\nNothing was deleted. Re-run with:\n  node scripts/wipe-personal-data.js --confirm=WIPE" +
      (INCLUDE_ENV ? "" : "\n(add --include-env to also delete .env, which holds your secrets)"),
  );
  process.exit(0);
}

for (const t of existing) {
  fs.rmSync(t, { recursive: true, force: true });
  console.log(`  removed ${t}`);
}

console.log(
  "\nDone. Conversations, memory, portfolio/journal, skills, artifacts, recordings," +
    "\nbackups and credential files are gone. On an unencrypted disk the bytes may" +
    "\nstill exist in free space; encrypt the volume or run `cipher /w:<drive>`." +
    "\nRestart the app to create fresh, empty stores.",
);
