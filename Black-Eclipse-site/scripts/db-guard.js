#!/usr/bin/env node
// ─── Database integrity guard ─────────────────────────────────────────────
// Runs BEFORE every server start (via doctor.js) and on a daily schedule
// (via instrumentation.ts) to:
//
//   1. Harden the DB: persistent WAL mode + durable synchronous level so a
//      crash/kill mid-write can't silently corrupt the b-trees (this is what
//      took down NewsItem last time).
//   2. Detect corruption early with `PRAGMA quick_check`.
//   3. Keep a rolling local backup so a healthy snapshot always exists.
//   4. Auto-repair: if the live DB is corrupt, rebuild it from the freshest
//      healthy source (rolling backup → committed seed snapshot → prisma db
//      push). This guarantees the app boots with a working database instead
//      of failing every /api route at 502/500.
//
// Pure Node + better-sqlite3. Uses the nested better-sqlite3 bundled inside
// @prisma/adapter-better-sqlite3 (the top-level native module is AppLocker-
// blocked on some Windows setups; this one is loaded by the Prisma driver).

const path = require("path");
const fs = require("fs");
const { execSync } = require("child_process");

// Resolve the better-sqlite3 that Prisma actually uses (works on all setups).
let Database;
for (const base of [
  path.join(__dirname, "..", "node_modules", "@prisma", "adapter-better-sqlite3", "node_modules", "better-sqlite3"),
  path.join(__dirname, "..", "node_modules", "better-sqlite3"),
]) {
  try {
    Database = require(base);
    break;
  } catch {}
}
if (!Database) {
  console.error("[db-guard] better-sqlite3 not found — run `npm install` first.");
  process.exit(1);
}

const root = path.join(__dirname, "..");
// BE_DB_PATH override lets CI/tests point the guard at a throwaway DB file.
const dbPath = process.env.BE_DB_PATH
  ? path.resolve(process.env.BE_DB_PATH)
  : path.join(root, "jdds.db");
const backupsDir = process.env.BE_DB_BACKUPS_DIR
  ? path.resolve(process.env.BE_DB_BACKUPS_DIR)
  : path.join(root, "backups");

const ROLLING_BACKUPS = 5;

function log(msg) {
  console.log(`[db-guard] ${msg}`);
}

function ts() {
  const d = new Date();
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}-${pad(d.getHours())}${pad(d.getMinutes())}${pad(d.getSeconds())}`;
}

function open(readonly = false) {
  const db = new Database(dbPath, { readonly });
  db.defaultSafeIntegers(true);
  return db;
}

/** Run `PRAGMA quick_check` (fast corruption scan). Returns list of problem strings or []. */
function quickCheck(db) {
  try {
    const rows = db.pragma("quick_check(1)");
    const text = rows.map((r) => String(r.quick_check ?? r.integrity_check ?? "")).join(" | ");
    return text === "ok" ? [] : [text];
  } catch (e) {
    return [String(e.message || e)];
  }
}

/** Hardening PRAGMAs. Returns true when the DB was already healthy + durable. */
function harden(db) {
  const out = {};
  db.exec("PRAGMA journal_mode=WAL");
  db.exec("PRAGMA synchronous=NORMAL");
  // Recover from any leftover hot journal / WAL from a prior crash.
  try {
    db.exec("PRAGMA wal_checkpoint(TRUNCATE)");
  } catch {}
  out.journal_mode = db.pragma("journal_mode")[0].journal_mode;
  out.synchronous = db.pragma("synchronous")[0].synchronous;
  return out;
}

/** Copy the live DB to a versioned backup in backups/. */
function backup() {
  fs.mkdirSync(backupsDir, { recursive: true });
  const file = path.join(backupsDir, `jdds-${ts()}.db`);
  // `VACUUM INTO` produces a fully-consistent standalone copy (safe under WAL).
  const src = new Database(dbPath, { readonly: true });
  src.defaultSafeIntegers(true);
  try {
    src.exec(`VACUUM INTO '${file.replace(/'/g, "''")}'`);
  } finally {
    src.close();
  }
  // Prune old backups.
  let files = fs.readdirSync(backupsDir).filter((f) => /^jdds-.*\.db$/.test(f));
  files = files.map((f) => path.join(backupsDir, f)).sort((a, b) => fs.statSync(a).mtimeMs - fs.statSync(b).mtimeMs);
  while (files.length > ROLLING_BACKUPS) {
    const old = files.shift();
    try { fs.unlinkSync(old); } catch {}
  }
  log(`backed up → ${path.relative(root, file)} (rolling ${ROLLING_BACKUPS})`);
}

/** Is the live DB currently healthy (opens + quick_check ok)? */
function isHealthy() {
  let db;
  try {
    db = open(true);
    return quickCheck(db).length === 0;
  } catch {
    return false;
  } finally {
    if (db) db.close();
  }
}

/**
 * Repair the live DB by rebuilding it from the freshest healthy source:
 *  1. newest rolling backup in backups/ that passes quick_check
 *  2. committed seed snapshot (git) — falls back to current file if not a repo
 *  3. brand-new empty schema via `prisma db push`
 * Returns true on success.
 */
function repair() {
  log("corruption detected — attempting auto-repair...");

  // Candidate sources: rolling backups, then git seed snapshot.
  const candidates = [];
  if (fs.existsSync(backupsDir)) {
    const files = fs.readdirSync(backupsDir)
      .filter((f) => /^jdds-.*\.db$/.test(f))
      .map((f) => path.join(backupsDir, f))
      .sort((a, b) => fs.statSync(b).mtimeMs - fs.statSync(a).mtimeMs); // newest first
    candidates.push(...files);
  }

  // Committed seed snapshot via git (the known-good baseline). The git repo
  // root is one level above the site folder (repo/ contains Black-Eclipse-site/),
  // so resolve it dynamically rather than assuming the DB path.
  try {
    const repoRoot = execSync("git rev-parse --show-toplevel", { cwd: root, encoding: "utf8", stdio: ["ignore", "pipe", "ignore"] }).trim();
    const relDb = path.relative(repoRoot, dbPath).split(path.sep).join("/");
    const tmp = path.join(require("os").tmpdir(), `jdds-snapshot-${ts()}.db`);
    execSync(`git show HEAD:${relDb} > "${tmp}"`, { cwd: repoRoot, stdio: "ignore", shell: true });
    candidates.push(tmp);
  } catch {}

  for (const cand of candidates) {
    // Verify the candidate is a valid, healthy DB before trusting it.
    let check;
    try {
      const c = new Database(cand, { readonly: true });
      c.defaultSafeIntegers(true);
      const ok = c.pragma("quick_check(1)").map((r) => String(r.quick_check ?? "")).join() === "ok";
      check = ok;
      c.close();
    } catch {
      check = false;
    }
    if (!check) {
      log(`  skipping unhealthy source: ${path.basename(cand)}`);
      continue;
    }
    try {
      // Backup the corrupt DB for forensics before overwriting.
      try {
        const forensic = path.join(backupsDir, `jdds-corrupt-${ts()}.db`);
        fs.mkdirSync(backupsDir, { recursive: true });
        fs.copyFileSync(dbPath, forensic);
        log(`  saved corrupt DB → ${path.relative(root, forensic)}`);
      } catch {}
      // Move the corrupt file aside, then bring in the healthy candidate.
      const corrupt = path.join(backupsDir, `jdds-corrupt-${ts()}.db-main`);
      fs.copyFileSync(cand, dbPath);
      log(`  restored from ${path.basename(cand)}`);
      return true;
    } catch (e) {
      log(`  restore from ${path.basename(cand)} failed: ${e.message}`);
    }
  }

  // Last resort: recreate empty schema.
  log("  no healthy source found — recreating empty schema via prisma db push");
  try {
    execSync("npx prisma db push", { cwd: root, stdio: "ignore", shell: true });
    return true;
  } catch (e) {
    log(`  prisma db push failed: ${e.message}`);
    return false;
  }
}

function main() {
  const mode = process.argv[2] || "check";

  if (mode === "check") {
    if (!fs.existsSync(dbPath)) {
      log("no database yet — will be created on first start");
      process.exit(0);
    }
    let db;
    try {
      db = open();
      // Hardening PRAGMAs are idempotent.
      const h = harden(db);
      log(`journal_mode=${h.journal_mode} synchronous=${h.synchronous}`);
      const problems = quickCheck(db);
      db.close();
      if (problems.length > 0) {
        log(`quick_check FAILED: ${problems[0]}`);
        if (repair()) {
          // Re-verify after repair.
          log("repaired — re-verifying...");
          const d2 = open(true);
          const ok = quickCheck(d2).length === 0;
          d2.close();
          log(ok ? "database healthy after repair ✓" : "repair did not yield a healthy database");
          process.exit(ok ? 0 : 1);
        }
        process.exit(1);
      }
      log("database healthy ✓");
      return;
    } catch (e) {
      log(`open failed: ${e.message}`);
      if (repair()) {
        log("database repaired ✓");
        process.exit(0);
      }
      process.exit(1);
    }
  }

  if (mode === "backup") {
    if (!fs.existsSync(dbPath)) {
      log("no database to back up");
      process.exit(0);
    }
    if (isHealthy()) {
      backup();
    } else {
      log("database unhealthy — backing up anyway for forensics");
      backup();
      process.exit(1);
    }
    process.exit(0);
  }

  if (mode === "repair") {
    // Runtime self-heal: invoked by API routes when they hit a corrupt DB.
    // Repairs in place (from rolling backup → git snapshot → prisma db push)
    // so the app recovers WITHOUT a restart. Returns 0 on success.
    if (!fs.existsSync(dbPath)) {
      log("no database to repair");
      process.exit(1);
    }
    if (isHealthy()) {
      log("database already healthy — nothing to repair");
      process.exit(0);
    }
    log("corruption detected at runtime — repairing...");
    if (repair()) {
      log("database repaired ✓");
      process.exit(0);
    }
    log("repair failed");
    process.exit(1);
  }

  if (mode === "status") {
    if (!fs.existsSync(dbPath)) {
      console.log("db-guard: no database yet");
      process.exit(0);
    }
    const healthy = isHealthy();
    console.log(`db-guard: ${healthy ? "healthy" : "CORRUPT"}`);
    if (fs.existsSync(backupsDir)) {
      const files = fs.readdirSync(backupsDir).filter((f) => /^jdds-.*\.db$/.test(f));
      console.log(`db-guard: ${files.length} local backup(s)`);
    }
    process.exit(healthy ? 0 : 1);
  }

  log(`unknown mode "${mode}"`);
  process.exit(1);
}

main();
