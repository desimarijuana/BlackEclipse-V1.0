// Native addons that the Next standalone tracer cannot install for us.
//
// `npm ci --ignore-scripts` (the release/CI default) skips better-sqlite3's
// install step. The top-level better-sqlite3@13 ships a prebuilt binary in its
// package, but @prisma/adapter-better-sqlite3 depends on better-sqlite3@12 and
// resolves its own nested copy. That copy only has a binary after its install
// script runs. Without it, every Prisma query throws "Could not locate the
// bindings file"; setup falls back to `isNewInstall`, so onboarding reappears
// on every launch and can never be saved.
//
// Repair that exact copy and prove it can open a database before a payload is
// assembled. A missing binding must fail the build, never reach a download.

const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");

const BETTER_SQLITE_REL = path.join(
  "node_modules",
  "@prisma",
  "adapter-better-sqlite3",
  "node_modules",
  "better-sqlite3"
);

function betterSqliteDir(rootDir) {
  return path.join(rootDir, BETTER_SQLITE_REL);
}

function canLoadBetterSqlite(nodeBin, dir) {
  if (!fs.existsSync(dir)) return false;
  const probe = spawnSync(
    nodeBin,
    [
      "-e",
      "const Database=require(process.argv[1]);const db=new Database(':memory:');db.prepare('select 1 as ok').get();db.close();",
      dir,
    ],
    { stdio: "ignore", windowsHide: true }
  );
  return probe.status === 0;
}

/**
 * Ensure the nested better-sqlite3 copy used by Prisma has a loadable native
 * binding, running its own install script when `--ignore-scripts` skipped it.
 * Returns `{ ok, dir, repaired, reason }`; callers decide whether to fail.
 */
function ensureBetterSqliteBinding(rootDir, { nodeBin = process.execPath, log = console.log } = {}) {
  const dir = betterSqliteDir(rootDir);
  if (!fs.existsSync(dir)) {
    return {
      ok: false,
      dir,
      repaired: false,
      reason: "nested better-sqlite3 is missing (run npm ci first)",
    };
  }
  if (canLoadBetterSqlite(nodeBin, dir)) {
    return { ok: true, dir, repaired: false };
  }

  log(`[native] ${path.relative(rootDir, dir)} has no loadable binding; running its install step`);
  const result = spawnSync("npm", ["run", "install"], {
    cwd: dir,
    stdio: "inherit",
    shell: process.platform === "win32",
    windowsHide: true,
  });
  if (result.status === 0 && canLoadBetterSqlite(nodeBin, dir)) {
    return { ok: true, dir, repaired: true };
  }

  return {
    ok: false,
    dir,
    repaired: false,
    reason: `better-sqlite3 install failed (exit ${result.status ?? "unknown"}) or produced no loadable binary`,
  };
}

module.exports = {
  BETTER_SQLITE_REL,
  betterSqliteDir,
  canLoadBetterSqlite,
  ensureBetterSqliteBinding,
};
