#!/usr/bin/env node
/*
 * Runtime-junk sweep. `.black-eclipse/` accumulates scratch that nothing ever
 * prunes: corrupt index snapshots (CodeIndex.recover renames a bad DB and
 * rebuilds), per-workspace index DBs created by test runs, dev/prod logs, and
 * stderr/pid litter. None of it is user data and none of it is read again.
 *
 * SAFE BY DEFAULT: this only touches proved-dead scratch. It never removes a
 * DB vault (`jdds.db`, `agent-memory.db`, `eclipse-memory.db`), a pinned build
 * (`.black-eclipse/desktop-dist-*`, `.next-desktop*`, `.next-live-*`,
 * `releases/`), credentials, sessions/artifacts, or a code index that is still
 * being written (younger than the age guard, or holding a `-wal`/`-shm`).
 *
 * Run:
 *   npm run clean:junk            # dead scratch only
 *   npm run clean:junk -- --build # also wipe regenerable build output
 *   npm run clean:junk -- --dry-run
 */

const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..");
const DATA = path.join(ROOT, ".black-eclipse");
const CODE_INDEX = path.join(DATA, "code-index");
const WORKSPACE_INDEX = path.join(DATA, "workspace-index");
const SEARCH = path.join(DATA, "search");

// A code index older than this with no live WAL is a stale cache.
const STALE_INDEX_DAYS = 7;
const DAY_MS = 24 * 60 * 60 * 1000;

const args = new Set(process.argv.slice(2));
const dryRun = args.has("--dry-run");
const withBuild = args.has("--build");

let files = 0;
let bytes = 0;

function statSafe(p) {
  try {
    return fs.lstatSync(p);
  } catch {
    return null;
  }
}

function remove(p, label) {
  const st = statSafe(p);
  if (!st) return;
  // Count before deleting so the report includes directory contents.
  if (st.isDirectory()) files += countFiles(p);
  else {
    files += 1;
    bytes += st.size;
  }
  if (dryRun) {
    console.log(`  would remove ${label || p}`);
    return;
  }
  try {
    fs.rmSync(p, { recursive: true, force: true });
    console.log(`  removed ${label || p}`);
  } catch (err) {
    console.log(`  skipped ${label || p} (${err.code || "busy"})`);
  }
}

function countFiles(dir) {
  let n = 0;
  let walk = () => {};
  walk = (d) => {
    let entries;
    try {
      entries = fs.readdirSync(d, { withFileTypes: true });
    } catch {
      return;
    }
    for (const e of entries) {
      const p = path.join(d, e.name);
      if (e.isDirectory()) walk(p);
      else {
        n += 1;
        try {
          bytes += fs.statSync(p).size;
        } catch {
          /* vanished */
        }
      }
    }
  };
  if (fs.existsSync(dir)) walk(dir);
  return n;
}

function removeTree(p, label) {
  remove(p, label);
}

function sweepDir(dir, match) {
  let entries;
  try {
    entries = fs.readdirSync(dir, { withFileTypes: true });
  } catch {
    return;
  }
  for (const e of entries) {
    if (!e.isFile() || !match(e.name)) continue;
    remove(path.join(dir, e.name), path.join(path.basename(dir), e.name));
  }
}

function hasLiveSidecar(dbPath) {
  return fs.existsSync(`${dbPath}-wal`) || fs.existsSync(`${dbPath}-shm`);
}

function sweepStaleIndexes(dir, prefix) {
  let entries;
  try {
    entries = fs.readdirSync(dir, { withFileTypes: true });
  } catch {
    return;
  }
  const cutoff = Date.now() - STALE_INDEX_DAYS * DAY_MS;
  for (const e of entries) {
    if (!e.isFile() || !e.name.startsWith(prefix) || !e.name.endsWith(".db")) continue;
    const db = path.join(dir, e.name);
    const st = statSafe(db);
    if (!st) continue;
    if (st.mtimeMs > cutoff || hasLiveSidecar(db)) continue;
    remove(db, path.join(path.basename(dir), e.name));
    remove(`${db}-wal`);
    remove(`${db}-shm`);
  }
}

function sweepLogs(dir) {
  if (!fs.existsSync(dir)) return;
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    if (!e.isFile()) continue;
    if (/\.log(\.err)?$/i.test(e.name)) remove(path.join(dir, e.name), path.relative(ROOT, path.join(dir, e.name)));
  }
}

function report(label, fn) {
  const before = { files, bytes };
  fn();
  const df = files - before.files;
  const db = bytes - before.bytes;
  console.log(`${label}: ${df} file(s), ${(db / 1024 / 1024).toFixed(1)} MB`);
}

console.log(dryRun ? "clean-junk (dry run)" : "clean-junk");

report("dead code-index snapshots", () => {
  sweepDir(CODE_INDEX, (n) => n.includes(".corrupt-") && n.endsWith(".db"));
  sweepDir(SEARCH, (n) => n.includes(".corrupt-"));
});

report("test-created index DBs", () => {
  sweepDir(CODE_INDEX, (n) => n.startsWith("ws_tools_") && /\.db(-wal|-shm)?$/.test(n));
});

report("stale workspace index caches", () => {
  sweepStaleIndexes(CODE_INDEX, "ws_");
  sweepStaleIndexes(WORKSPACE_INDEX, "ws_");
});

report("logs + scratch", () => {
  sweepLogs(ROOT);
  sweepLogs(path.join(ROOT, "Black-Eclipse-site"));
  sweepLogs(DATA);
  removeTree(path.join(ROOT, "Black-Eclipse-site", "%SystemDrive%"), "%SystemDrive%");
  removeTree(path.join(ROOT, "Black-Eclipse-site", ".tmp-tests"), ".tmp-tests");
  removeTree(path.join(ROOT, "Black-Eclipse-site", ".pytest_cache"), ".pytest_cache");
  removeTree(path.join(ROOT, "Black-Eclipse-site", "python", ".pytest_cache"), "python/.pytest_cache");
});

if (withBuild) {
  report("build output", () => {
    for (const rel of [
      ".next",
      ".next-dev",
      "build",
      "dist",
      "desktop/src-tauri/target",
      "desktop/src-tauri/target-dev",
      "rust/fframes-worker/target",
    ]) {
      removeTree(path.join(ROOT, rel), rel);
    }
    for (const n of fs.readdirSync(ROOT)) {
      if (n.endsWith(".tsbuildinfo")) remove(path.join(ROOT, n), n);
    }
  });
}

console.log(
  `\n${dryRun ? "would free" : "freed"} ${files} file(s), ${(bytes / 1024 / 1024 / 1024).toFixed(2)} GB` +
    (withBuild ? "" : " (pass --build to also wipe .next/dist/target)"),
);
