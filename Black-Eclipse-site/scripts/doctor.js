// Self-healing environment check. Runs before dev/start: verifies Node,
// deps, Prisma client, DB, and Python bridge — auto-fixing what it can.
// Silent when everything is fine; prints [setup] lines when it fixes something.
const { execSync, spawnSync } = require("child_process");
const fs = require("fs");
const path = require("path");

const root = path.join(__dirname, "..");
let fixed = 0;

function run(cmd, opts = {}) {
  return spawnSync(cmd, { shell: true, stdio: "pipe", encoding: "utf8", ...opts });
}

function fix(label, cmd) {
  console.log(`[setup] ${label} missing — fixing (${cmd})...`);
  const r = run(cmd, { stdio: ["ignore", "ignore", "inherit"] });
  if (r.status !== 0) {
    console.error(`[setup] FAILED: ${label}. Run manually:\n  ${cmd}`);
    process.exit(1);
  }
  fixed++;
}

// 1. Node version (cannot auto-fix)
const major = Number(process.versions.node.split(".")[0]);
if (major < 20) {
  console.error(`[setup] Node.js v${process.versions.node} is too old — need v20+. Install from https://nodejs.org`);
  process.exit(1);
}

// 2. Dependencies
if (!fs.existsSync(path.join(root, "node_modules", ".package-lock.json"))) {
  fix("Dependencies", "npm install");
}

// 3. Prisma client
if (!fs.existsSync(path.join(root, "src", "generated", "prisma", "client.js")) &&
    fs.readdirSync(path.join(root, "src", "generated", "prisma")).length === 0) {
  fix("Prisma client", "npx prisma generate");
}

// 4. Database (committed seed should exist; create empty if clone was partial)
if (!fs.existsSync(path.join(root, "jdds.db"))) {
  fix("Database", "npx prisma db push");
}

// 4a. Schema drift — an existing jdds.db can predate models added since the
//     committed seed snapshot (e.g. the connector + Investor Eye tables). A
//     stale DB would boot but every query against a missing table would 500,
//     so detect the drift and apply the additive schema. Expected table names
//     are parsed from schema.prisma so this check never goes stale.
{
  const schemaPath = path.join(root, "prisma", "schema.prisma");
  const dbExists = fs.existsSync(path.join(root, "jdds.db"));
  if (dbExists && fs.existsSync(schemaPath)) {
    try {
      const Database = require(path.join(root, "node_modules", "better-sqlite3"));
      const schema = fs.readFileSync(schemaPath, "utf8");
      const expected = [...schema.matchAll(/^\s*model\s+(\w+)\s*\{/gm)].map((m) => m[1]);
      const db = new Database(path.join(root, "jdds.db"), { readonly: true });
      const present = new Set(
        db.prepare("select name from sqlite_master where type = 'table'").all().map((r) => r.name)
      );
      db.close();
      const missing = expected.filter((t) => !present.has(t));
      if (missing.length > 0) {
        console.log(`[setup] Database schema is stale — missing ${missing.length} table(s): ${missing.join(", ")}`);
        fix("Database schema", "npx prisma db push");
      }
    } catch (err) {
      // A locked/corrupt DB is handled by the integrity guard just below; a
      // drift check that cannot read the DB must never block boot.
      console.warn(`[setup] schema drift check skipped: ${err.message}`);
    }
  }
}

// 4b. Database integrity guard — hardens WAL/synchronous, detects corruption,
//     and auto-repairs from a healthy rolling backup or the committed seed
//     snapshot BEFORE the server starts (so no /api route can hit a corrupt DB).
{
  const dbGuard = path.join(__dirname, "db-guard.js");
  if (fs.existsSync(dbGuard)) {
    const r = spawnSync(process.execPath, [dbGuard, "check"], { stdio: "inherit" });
    if (r.status !== 0) {
      console.error("[setup] Database integrity check FAILED — see db-guard output above.");
      process.exit(1);
    }
  } else {
    console.warn("[setup] db-guard.js not found — skipping DB integrity check.");
  }
}

// 5. Python yfinance bridge (optional — live prices)
// 5a. On Windows, auto-provision the vendored embedded Python if the system
//     has no Python, so live prices work out of the box for new users.
const vendorScript = path.join(__dirname, "setup-embedded-python.js");
const vendorReady =
  process.platform === "win32" &&
  fs.existsSync(path.join(__dirname, "vendor", "python", "python.exe"));
if (process.platform === "win32" && !vendorReady && fs.existsSync(vendorScript)) {
  console.log("[setup] No Python found — provisioning embedded Python for live prices...");
  const v = spawnSync(process.execPath, [vendorScript], { stdio: "inherit" });
  if (v.status !== 0) {
    console.error("[setup] Could not provision embedded Python (offline?). Live prices disabled.");
  }
}

const pyCmds = process.platform === "win32" ? ["python", "python3", "py"] : ["python3", "python"];
const vendoredPy = path.join(__dirname, "vendor", "python", "python.exe");
const pyCandidates = fs.existsSync(vendoredPy) ? [vendoredPy, ...pyCmds] : pyCmds;
const py = pyCandidates.find((c) => run(`"${c}" --version`).status === 0);
if (py) {
  if (run(`"${py}" -c "import yfinance"`, { timeout: 15000 }).status !== 0) {
    fix("Python yfinance bridge", `"${py}" -m pip install yfinance`);
  }
} else {
  console.log("[setup] Python not found — live prices disabled. Install from https://python.org, then: pip install yfinance");
}

if (fixed > 0) console.log(`[setup] done — ${fixed} item(s) fixed.`);