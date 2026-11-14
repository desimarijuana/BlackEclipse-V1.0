// First-run seed database for a packaged install.
//
// WHY: without a seed file a first run creates an empty database with no tables
// and every query fails. The seed is therefore generated from `prisma/schema.prisma`
// at package time — no binary database is committed to git.
//
// A schema-only seed still boots into an EMPTY journal, which reads as a broken
// app. So the seed is populated with the same deterministic demo journal the
// server seeds on boot (`src/lib/journal/demo.ts`, invoked through
// `scripts/seed-journal.ts`). One generator, two entry points.
//
// Safety contract (mirrors the seeder): every row is tagged `source:'demo'` and
// is removable from the Journal UI, so a release ships sample data that looks
// real without ever shipping a real trading journal.

const fs = require("fs");
const os = require("os");
const path = require("path");
const { spawnSync } = require("child_process");

const DEMO_TRADE_QUERY = "select count(*) as n from Trade where source = 'demo'";

/** Demo trades in a database file, or 0 when it cannot be read (schema-only). */
function countDemoTrades(file) {
  try {
    const Database = require("better-sqlite3");
    const db = new Database(file, { readonly: true });
    try {
      return db.prepare(DEMO_TRADE_QUERY).get().n || 0;
    } finally {
      db.close();
    }
  } catch {
    return 0;
  }
}

/**
 * Seed demo content into `file`. Returns the number of demo trades written.
 * Non-fatal on failure: a schema-only seed still boots, and the server-side
 * boot hook seeds the journal on first run.
 */
function populateDemoSeed(file, env, rootDir) {
  const tsx = path.join(rootDir, "node_modules", "tsx", "dist", "cli.mjs");
  if (!fs.existsSync(tsx)) {
    console.warn("  seed database: tsx unavailable — boot hook will seed on first run");
    return 0;
  }
  const seeded = spawnSync(
    process.execPath,
    [tsx, path.join(rootDir, "scripts", "seed-journal.ts")],
    { cwd: rootDir, env, stdio: "inherit" }
  );
  if (seeded.status !== 0) {
    console.warn("  seed database: demo seeding failed — boot hook will seed on first run");
    return 0;
  }
  // WAL mode: make sure the seeded rows are inside the file we are about to copy.
  try {
    const Database = require("better-sqlite3");
    const db = new Database(file);
    db.pragma("wal_checkpoint(TRUNCATE)");
    db.close();
  } catch {
    // Best-effort; the row check below is the real gate.
  }
  const demo = countDemoTrades(file);
  if (demo === 0) console.warn("  seed database: no demo rows written — shipping schema-only");
  return demo;
}

/**
 * Ensure `<appDir>/seed/jdds.db` exists AND carries demo rows.
 * Regenerates a stale schema-only seed left by an earlier build, otherwise every
 * install packaged from it would open empty.
 */
function ensureSeedDatabase({ appDir, rootDir, fail }) {
  const seedDir = path.join(appDir, "seed");
  const seedDb = path.join(seedDir, "jdds.db");

  if (fs.existsSync(seedDb)) {
    const existing = countDemoTrades(seedDb);
    if (existing > 0) {
      console.log(`  seed database: already present (${existing} demo trades)`);
      return;
    }
    console.log("  seed database: present but has no demo rows — regenerating");
  }

  fs.mkdirSync(seedDir, { recursive: true });
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "be-seed-"));
  // `db.ts` prefers BE_DB_PATH over BE_DATA_DIR; an inherited one would point the
  // seeder at the developer's own vault instead of the file being assembled.
  const env = { ...process.env, BE_DATA_DIR: tmp };
  delete env.BE_DB_PATH;

  const pushed = spawnSync(
    process.execPath,
    [
      path.join(rootDir, "node_modules", "prisma", "build", "index.js"),
      "db",
      "push",
      "--schema=prisma/schema.prisma",
    ],
    { cwd: rootDir, env, stdio: "inherit" }
  );
  const generated = path.join(tmp, "jdds.db");
  if (pushed.status !== 0 || !fs.existsSync(generated)) {
    fail("Could not generate the seed database (prisma db push failed).");
  }

  const demo = populateDemoSeed(generated, env, rootDir);
  fs.copyFileSync(generated, seedDb);
  fs.rmSync(tmp, { recursive: true, force: true });
  const mb = (fs.statSync(seedDb).size / 1024 / 1024).toFixed(1);
  console.log(`  seed database: ${mb} MB${demo ? `, ${demo} demo trades` : ""}`);
}

module.exports = { countDemoTrades, populateDemoSeed, ensureSeedDatabase };
