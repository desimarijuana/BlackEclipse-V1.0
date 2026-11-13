#!/usr/bin/env node
// `black` — global CLI for Black Eclipse.
//
// The product is the NATIVE DESKTOP APP. There is no browser/website runtime:
// the one UI is served to the Tauri window over loopback on the channel's port
// (Stable 3100, Dev 3101). Every command here drives that app or the shells
// around it.
//
//   black            → open the desktop app (Stable)
//   black dev        → build + open the Dev channel (port 3101)
//   black refresh    → re-pin the current build and reopen Stable
//   black stop       → stop the channel window and the server it owns
//   black status     → is the app up? which channel, which port?
//   black build      → force a production rebuild
//   black doctor     → check the environment (Node, deps, DB, Python)
//   black desktop    → (re)install the desktop shortcut + its app icon
//   black update     → check for a signed release and apply it safely
//   black reset      → reset setup or wipe data
//
// `eclipse`, `start` and `proxy` were the retired browser front door. They no
// longer run anything; they explain where that functionality went.
//
// Registered globally via `npm link` from the Black-Eclipse-site folder —
// works in cmd, PowerShell, and Git Bash on Windows/macOS/Linux.

const { execSync, spawnSync } = require("child_process");
const fs = require("fs");
const path = require("path");
const { root, build, nextBin, isUp } = require("../scripts/lib/server");
const { STABLE, DEV } = require("../scripts/lib/channels");
const {
  launchShell,
  shellPathFor,
  stopShell,
  stopOwnedServer,
  readOwner,
} = require("../scripts/lib/desktop-process");

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

function runScript(name, args = []) {
  const result = spawnSync(process.execPath, [path.join(__dirname, "..", "scripts", name), ...args], {
    stdio: "inherit",
    cwd: projectRoot(),
  });
  process.exit(result.status ?? 1);
}

// ─── black (default) ───────────────────────────────────────────────────────
// Opens the channel window. The shell boots its own loopback server and owns
// the lifecycle, so this never starts a Next server itself and never builds.
// A second invocation focuses the existing window (Tauri single-instance).
function openApp(channel = STABLE) {
  const res = launchShell(channel);
  if (res.launched) {
    log(`${channel.label} desktop app launched (pid ${res.pid}) — ${channel.appPort}`);
    log(`if a window was already open, it was focused instead`);
    return;
  }
  log(`the ${channel.label} desktop app is not installed at:`);
  log(`  ${res.exe}`);
  log("");
  log("Desktop-only product — there is no browser site to fall back to.");
  log("  npm run desktop:installer   build the Windows installer");
  log("  npm run desktop:refresh     re-pin this checkout and reopen Stable");
  process.exit(1);
}

// ─── black status ──────────────────────────────────────────────────────────
async function status() {
  for (const channel of [STABLE, DEV]) {
    const up = await isUp(String(channel.appPort));
    const owner = readOwner(channel);
    const state = up ? `UP (HTTP ${up})` : "DOWN";
    log(`${channel.label.padEnd(6)} ${state} — http://127.0.0.1:${channel.appPort}`);
    log(`        harness ${channel.harnessPort}${owner ? ` · server pid ${owner.pid}` : ""}`);
  }
}

// ─── black stop ────────────────────────────────────────────────────────────
function stop({ all = false } = {}) {
  const channels = all ? [STABLE, DEV] : [STABLE];
  let stopped = false;
  for (const channel of channels) {
    const pids = stopShell(channel);
    if (pids.length) {
      log(`${channel.label} window stopped (pid ${pids.join(", ")})`);
      stopped = true;
    }
    // Only the server tree this install started — never another process that
    // happens to hold the port.
    if (stopOwnedServer(channel)) {
      log(`${channel.label} server stopped (port ${channel.appPort})`);
      stopped = true;
    }
  }
  if (!stopped) log("nothing was running");
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

  // Desktop shell (the product)
  const shell = shellPathFor(STABLE);
  check("desktop app", fs.existsSync(shell), 'run "npm run desktop:installer" to install it', shell);

  // Build cache
  const built = fs.existsSync(path.join(projectRoot(), STABLE.buildDir, "BUILD_ID"));
  check("production build", built, 'run "npm run desktop:refresh" to create it', "ready");

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
  build();
  log(`build done in ${((Date.now() - t0) / 1000).toFixed(0)}s — run "black refresh" to pin and reopen`);
}

// ─── reset / onboarding ────────────────────────────────────────────────────
// One implementation lives in scripts/reset.js; the CLI only forwards flags so
// Settings, `black`, and `npm run reset:*` cannot drift.
function runReset(args) {
  const result = spawnSync(
    process.execPath,
    [path.join(__dirname, "..", "scripts", "reset.js"), ...args],
    { stdio: "inherit", cwd: path.join(__dirname, "..") },
  );
  process.exit(result.status ?? 1);
}

// ─── retired browser front door ────────────────────────────────────────────
// These commands used to boot a Next server on 3105 behind the local proxy.
// That lane is deleted, not merely gated: keeping a callable browser start is
// how "the web app" kept reappearing. Say where everything went, then exit.
function retired(command) {
  log(`"${command}" was the browser front door — it no longer exists.`);
  log("");
  log("The product is the native desktop app. Use:");
  log("  black            open the desktop app (Stable, port 3100)");
  log("  black dev        build + open the Dev channel (port 3101)");
  log("  black refresh    re-pin the current build and reopen Stable");
  log("  black status     is the app up?");
  process.exit(1);
}

// ─── routing ───────────────────────────────────────────────────────────────
async function main() {
  const [, , cmd, ...rest] = process.argv;
  const sub = (cmd || "app").toLowerCase();
  switch (sub) {
    case "app":
    case "open":
      openApp(STABLE);
      break;
    case "eclipse":
    case "start":
    case "proxy":
      retired(sub);
      break;
    case "dev":
      runScript("desktop-dev.js");
      break;
    case "refresh":
      runScript("desktop-refresh.js", rest);
      break;
    case "stop":
      stop({ all: rest.includes("--all") });
      break;
    case "status":
      await status();
      break;
    case "build":
      forceBuild();
      break;
    case "desktop": {
      const result = spawnSync(
        process.execPath,
        [path.join(__dirname, "..", "scripts", "desktop-shortcut.js")],
        { stdio: "inherit" }
      );
      if (result.status !== 0) process.exit(result.status || 1);
      break;
    }
    case "update": {
      // One implementation lives in scripts/update.js so the CLI, docs and the
      // in-app notice cannot drift. It verifies the signed tag before applying.
      const result = spawnSync(
        process.execPath,
        [path.join(__dirname, "..", "scripts", "update.js"), ...rest],
        { stdio: "inherit", cwd: path.join(__dirname, "..") },
      );
      process.exit(result.status ?? 1);
    }
    case "onboarding":
    case "onboard":
      runReset(["--onboarding"]);
      break;
    case "reset":
      runReset(rest);
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
  (none)       open the desktop app (Stable, port ${STABLE.appPort}) [default]
  app          same as above
  dev          build + open the Dev channel (port ${DEV.appPort})
  refresh      re-pin the current build and reopen Stable
  stop         stop the channel window and the server it owns
               (--all also stops Dev)
  status       is the app up? which channel, which port?
  build        force a production rebuild
  desktop      (re)install the desktop shortcut and its app icon
  update       check for a signed release and apply it safely
                 black update --check
                 black update --yes [--restart]
                 black update --channel beta
  doctor       check the environment (--fix to auto-repair)
  onboarding   re-run the setup questions (keeps keys and data)
  reset        reset setup or wipe data:
                 black reset --list
                 black reset --onboarding
                 black reset --setup
                 black reset --factory [--confirm=WIPE] [--no-backup]

Retired (no longer runs anything): eclipse, start, proxy

The product is desktop-only. There is no browser/website runtime to start.`);
      break;
    default:
      log(`unknown command "${sub}${rest.length ? " " + rest.join(" ") : ""}" — try "black help"`);
      process.exit(1);
  }
}

main().catch((err) => {
  log(err && err.message ? err.message : String(err));
  process.exit(1);
});
