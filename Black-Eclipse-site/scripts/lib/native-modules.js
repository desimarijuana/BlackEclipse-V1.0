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

/** `process.versions.node` of an arbitrary node binary, or null. */
function nodeVersionOf(nodeBin) {
  const r = spawnSync(nodeBin, ["-p", "process.versions.node"], { encoding: "utf8", windowsHide: true });
  return r.status === 0 ? String(r.stdout).trim() : null;
}

/**
 * Make the packaged binding load under the *bundled* runtime rather than the
 * build machine's Node.
 *
 * A better-sqlite3@12 binary is ABI-specific, and the two versions routinely
 * differ — CI pins Node 22 while a dev box runs 24 — so a payload built only
 * for the build machine ships a binary the app can never load. The window then
 * opens, the guard fails, and the first relaunch dies before serving. Fetch the
 * prebuilt for the runtime's own version and prove it loads *there*.
 */
function ensureRuntimeSqlite(dir, runtimeNode, { log = console.log } = {}) {
  if (canLoadBetterSqlite(runtimeNode, dir)) return { ok: true, reason: null };

  const version = nodeVersionOf(runtimeNode);
  const prebuild = path.join(__dirname, "..", "..", "node_modules", "prebuild-install", "bin.js");
  if (!version || !fs.existsSync(prebuild)) {
    return { ok: false, reason: "cannot read the bundled Node version, or prebuild-install is missing" };
  }

  log(`[native] binding does not load under the bundled Node ${version}; fetching a matching prebuild`);
  spawnSync(
    process.execPath,
    [
      prebuild,
      "--force",
      "--runtime=node",
      `--target=${version}`,
      `--arch=${process.arch}`,
      `--platform=${process.platform}`,
    ],
    { cwd: dir, stdio: "pipe", encoding: "utf8", windowsHide: true }
  );
  return canLoadBetterSqlite(runtimeNode, dir)
    ? { ok: true, reason: null }
    : { ok: false, reason: `no prebuilt binding for Node ${version}` };
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
  ensureRuntimeSqlite,
  nodeVersionOf,
};
