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
const pyCmds = process.platform === "win32" ? ["python", "python3", "py"] : ["python3", "python"];
const py = pyCmds.find((c) => run(`${c} --version`).status === 0);
if (py) {
  if (run(`${py} -c "import yfinance"`, { timeout: 15000 }).status !== 0) {
    fix("Python yfinance bridge", `${py} -m pip install yfinance`);
  }
} else {
  console.log("[setup] Python not found — live prices disabled. Install from https://python.org, then: pip install yfinance");
}

if (fixed > 0) console.log(`[setup] done — ${fixed} item(s) fixed.`);