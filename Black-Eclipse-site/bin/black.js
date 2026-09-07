#!/usr/bin/env node
// `black` — global CLI for the Black Eclipse site.
//
//   black            (or `black eclipse`)  → start the site (production, fast)
//   black dev        → start in dev mode (hot reload)
//   black stop       → kill whatever is running on the port
//   black status     → is the site up? what's running?
//   black build      → force a production rebuild
//   black doctor     → check the environment (Node, deps, DB, Python)
//
// Registered globally via `npm link` from the Black-Eclipse-site folder —
// works in cmd, PowerShell, and Git Bash on Windows/macOS/Linux.

const { execSync, spawn } = require("child_process");
const fs = require("fs");
const path = require("path");
const {
  root,
  killPort,
  needsBuild,
  build,
  nextBin,
  startServer,
  startDev,
  isUp,
} = require("../scripts/lib/server");

const PORT = process.env.PORT || "3000";

function log(msg) {
  console.log(`[black] ${msg}`);
}

function argValue(flag, fallback) {
  const i = process.argv.indexOf(flag);
  if (i !== -1 && process.argv[i + 1]) return process.argv[i + 1];
  return fallback;
}

function projectRoot() {
  return root;
}

// ─── black status ──────────────────────────────────────────────────────────
async function status() {
  const code = await isUp(PORT);
  if (code) {
    log(`site is UP on http://localhost:${PORT} (HTTP ${code})`);
  } else {
    log(`site is DOWN — run "black eclipse" to start it`);
  }
}

// ─── black stop ────────────────────────────────────────────────────────────
async function stop() {
  const wasUp = await isUp(PORT);
  if (killPort(PORT)) {
    log(`stopped (port ${PORT} freed)`);
  } else if (wasUp) {
    log(`could not stop — something still holds port ${PORT}`);
  } else {
    log(`nothing was running on port ${PORT}`);
  }
}

// ─── black eclipse ─────────────────────────────────────────────────────────
async function eclipse() {
  log(`starting Black Eclipse → http://localhost:${PORT}`);

  // 1. Free the port if a stale server holds it.
  if (killPort(PORT)) log(`freed port ${PORT}`);

  // 2. Production build only when needed — unchanged source skips it.
  if (needsBuild()) {
    log("building (first run or source changed — this can take a few minutes)...");
    const t0 = Date.now();
    build();
    log(`build done in ${((Date.now() - t0) / 1000).toFixed(0)}s`);
  } else {
    log("build is up to date — skipping");
  }

  // 3. Foreground start (Ctrl+C stops it).
  log("site starting — press Ctrl+C to stop");
  startServer(PORT);
}

// ─── black doctor ──────────────────────────────────────────────────────────
function findPython() {
  const candidates = process.platform === "win32" ? ["python", "python3", "py"] : ["python3", "python"];
  for (const cmd of candidates) {
    try {
      const v = execSync(`${cmd} --version`, { encoding: "utf8", stdio: ["pipe", "pipe", "pipe"] }).trim();
      return { cmd, version: v };
    } catch {}
  }
  return null;
}

function check(name, ok, failHint, okDetail) {
  const mark = ok ? "OK " : "!! ";
  const detail = ok ? okDetail : failHint;
  console.log(`  [${mark}] ${name}${detail ? ` — ${detail}` : ""}`);
  return ok;
}

async function doctor() {
  log("environment check:");
  let failures = 0;

  // Node version
  const major = Number(process.versions.node.split(".")[0]);
  if (!check("Node.js", major >= 20, `v${process.versions.node} (need >= 20)`)) failures++;

  // Project + dependencies
  const nm = path.join(projectRoot(), "node_modules");
  if (!check("project found", fs.existsSync(projectRoot()), "", projectRoot())) failures++;
  if (!check("dependencies", fs.existsSync(nm), 'run "npm install" in the project folder')) failures++;

  // Next.js binary
  let nextOk = false;
  try {
    nextBin();
    nextOk = true;
  } catch {}
  if (!check("Next.js", nextOk, 'run "npm install" in the project folder')) failures++;

  // Prisma client (generated)
  const genDir = path.join(projectRoot(), "src", "generated", "prisma");
  if (!check("Prisma client", fs.existsSync(genDir), 'run "npx prisma generate"')) failures++;

  // Database
  const db = path.join(projectRoot(), "jdds.db");
  if (!check("database", fs.existsSync(db), "auto-created on first run")) {
    log("  (the DB is created on first start — usually nothing to worry about)");
  }

  // Python + yfinance (price bridge)
  const py = findPython();
  if (!check("Python", !!py, "install python3 + pip", py ? py.version : "")) failures++;
  if (py) {
    let yf = false;
    try {
      execSync(`${py.cmd} -c "import yfinance"`, { stdio: "ignore", timeout: 15000 });
      yf = true;
    } catch {}
    if (!check("yfinance (price bridge)", yf, `run "${py.cmd} -m pip install yfinance scrapling"`)) failures++;
  }

  // Build cache
  const built = fs.existsSync(path.join(projectRoot(), ".next", "BUILD_ID"));
  check("production build", built, 'run "black eclipse" once to create it', "ready");

  if (failures > 0) {
    console.log(`\n[black] ${failures} issue(s) found — see the !! lines above.`);
    process.exit(1);
  }
  log("all good");
}

// ─── black build ───────────────────────────────────────────────────────────
function forceBuild() {
  process.env.BE_FORCE_BUILD = "1";
  log("forcing production rebuild...");
  const t0 = Date.now();
  killPort(PORT);
  build();
  log(`build done in ${((Date.now() - t0) / 1000).toFixed(0)}s — run "black eclipse" to start`);
}

// ─── routing ───────────────────────────────────────────────────────────────
async function main() {
  const [, , cmd, ...rest] = process.argv;
  const sub = (cmd || "eclipse").toLowerCase();
  switch (sub) {
    case "eclipse":
    case "start":
      await eclipse();
      break;
    case "dev":
      startDev(argValue("-p", PORT));
      break;
    case "stop":
      await stop();
      break;
    case "status":
      await status();
      break;
    case "build":
      forceBuild();
      break;
    case "doctor":
      if (argValue("--fix") !== undefined || rest.includes("--fix")) {
        // Reuse the self-healing script, then report.
        try {
          execSync(`node "${path.join(__dirname, "..", "scripts", "doctor.js")}"`, { stdio: "inherit" });
        } catch {}
      }
      await doctor();
      break;
    case "help":
    case "--help":
    case "-h":
      console.log(`Usage: black [command]

Commands:
  eclipse      start the site (production, fast) [default]
  dev          start in dev mode (hot reload)
  stop         stop the running site
  status       check if the site is up
  build        force a production rebuild
  doctor       check the environment (--fix to auto-repair)

Options:
  -p <port>    use a custom port (default 3000)`);
      break;
    default:
      log(`unknown command "${sub}${rest.length ? " " + rest.join(" ") : ""}" — try "black help"`);
      process.exit(1);
  }
}

main().catch((err) => {
  console.error("[black] error:", err.message || err);
  process.exit(1);
});