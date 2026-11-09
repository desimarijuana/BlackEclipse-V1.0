#!/usr/bin/env node
// `black` — global CLI for the Black Eclipse site.
//
//   black            (or `black eclipse`)  → start the site (production, fast)
//   black dev        → start in dev mode (hot reload)
//   black stop       → kill whatever is running on the port
//   black status     → is the site up? what's running?
//   black build      → force a production rebuild
//   black doctor     → check the environment (Node, deps, DB, Python)
//   black desktop    → (re)install the desktop shortcut + its app icon
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
  isUp,
} = require("../scripts/lib/server");
const { runLocalHost } = require("../scripts/local-host");
const { DEV, PROD } = require("../scripts/lib/profiles");

// `black` (no subcommand) controls the production server. `black dev` controls
// the development server, which runs on its own port and data directory.
const PORT = String(PROD.appPort);
const DEV_PORT = String(DEV.appPort);

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
  const prod = await isUp(PORT);
  const dev = await isUp(DEV_PORT);
  log(`production: ${prod ? `UP (HTTP ${prod}) -> http://blackeclipse` : "DOWN"} [port ${PORT}]`);
  log(`development: ${dev ? `UP (HTTP ${dev}) -> http://127.0.0.1:${DEV_PORT}` : "DOWN"} [port ${DEV_PORT}]`);
}

// ─── black stop ────────────────────────────────────────────────────────────
async function stop({ all = false } = {}) {
  let stopped = false;
  if (killPort(PORT)) {
    log(`production stopped (port ${PORT} freed)`);
    stopped = true;
  }
  if (all && killPort(DEV_PORT)) {
    log(`development stopped (port ${DEV_PORT} freed)`);
    stopped = true;
  }
  if (!stopped) log(`nothing was running on port ${all ? `${PORT}/${DEV_PORT}` : PORT}`);
}

// ─── black eclipse ─────────────────────────────────────────────────────────
async function eclipse({ restart = false } = {}) {
  // Opening Eclipse again (another terminal tab, a second shell, a pinned
  // command) must NOT tear down the healthy server that is already serving the
  // open browser tab. Restarting costs doctor + a possible multi-minute build +
  // a cold boot, which is exactly what made a second open feel like it hung.
  // A loaded machine can take several seconds to answer its first request
  // (dev server still booting, background warm-up); a short probe would read
  // that as "down" and trigger the very restart this guard exists to avoid.
  const running = await isUp(PORT, 10_000);
  if (running && !restart && process.env.BE_FORCE_BUILD !== "1") {
    log(`already running (HTTP ${running}) — leaving it up: http://blackeclipse`);
    log(`use "black eclipse --restart" (or "black build") to force a rebuild`);
    return;
  }

  log(`starting Black Eclipse → http://blackeclipse`);

  // 1. Self-heal the environment (deps, prisma client, DB, python bridge).
  try {
    execSync(`node "${path.join(__dirname, "..", "scripts", "doctor.js")}"`, { stdio: "inherit" });
  } catch {
    log("setup failed — see errors above");
    process.exit(1);
  }

  // 2. Free the port if a stale server holds it.
  if (killPort(PORT)) log(`freed port ${PORT}`);

  // 2. Production build only when needed — unchanged source skips it. The build
  //    lock makes this wait for a build that is already running instead of
  //    corrupting `.next` with a second one.
  if (needsBuild()) {
    log("building (first run or source changed — this can take a few minutes)...");
    const t0 = Date.now();
    const didBuild = build();
    log(
      didBuild
        ? `build done in ${((Date.now() - t0) / 1000).toFixed(0)}s`
        : "another process already built this source — using that build"
    );
  } else {
    log("build is up to date — skipping");
  }

  // 3. Foreground start of BOTH the app (loopback) and the local proxy; the
  //    only advertised address is http://blackeclipse. Ctrl+C stops both.
  runLocalHost({ mode: "start", port: PORT });
}

// ─── black doctor ──────────────────────────────────────────────────────────
function findPython() {
  // Vendored embedded Python (scripts/vendor/python) is the preferred runtime.
  const vendored =
    process.platform === "win32"
      ? path.join(__dirname, "..", "scripts", "vendor", "python", "python.exe")
      : null;
  if (vendored && fs.existsSync(vendored)) {
    try {
      const v = execSync(`"${vendored}" --version`, { encoding: "utf8", stdio: ["pipe", "pipe", "pipe"] }).trim();
      return { cmd: vendored, version: `${v} (vendored)` };
    } catch {}
  }
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
      execSync(`"${py.cmd}" -c "import yfinance"`, { stdio: "ignore", timeout: 15000 });
      yf = true;
    } catch {}
    if (!check("yfinance (price bridge)", yf, `run "${py.cmd}" -m pip install yfinance scrapling`)) failures++;
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
      await eclipse({ restart: rest.includes("--restart") });
      break;
    case "dev":
      runLocalHost({ mode: "dev", port: argValue("-p", DEV_PORT) });
      break;
    case "stop":
      await stop({ all: rest.includes("--all") });
      break;
    case "status":
      await status();
      break;
    case "build":
      forceBuild();
      break;
    case "desktop": {
      const { spawnSync } = require("child_process");
      const result = spawnSync(
        process.execPath,
        [path.join(__dirname, "..", "scripts", "desktop-shortcut.js")],
        { stdio: "inherit" }
      );
      if (result.status !== 0) process.exit(result.status || 1);
      break;
    }
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
  eclipse      start the production site (fast) [default]
  dev          start the development server (hot reload)
  stop         stop production (--all also stops development)
  status       check both servers
  build        force a production rebuild
  desktop      (re)install the desktop shortcut and its app icon
  doctor       check the environment (--fix to auto-repair)

Options:
  -p <port>    use a custom port (production ${PORT}, development ${DEV_PORT})`);
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