#!/usr/bin/env node
// Runtime smoke test: launch the packaged app and prove it actually serves.
//
// A build that compiles is not an app that runs. This starts the real binary
// from the real layout, waits for the local server to answer, and reports the
// log tail if it does not. Runs on all three platforms.
//
//   node scripts/desktop-smoke.js --bin "<path to Black Eclipse binary>"
//
// Exit 0 only when the server answered. Anything else is a failure with the
// first useful lines of the log.

const fs = require("fs");
const os = require("os");
const path = require("path");
const { spawn, spawnSync } = require("child_process");

const ROOT = path.join(__dirname, "..");
const argBin = (() => {
  const i = process.argv.indexOf("--bin");
  return i !== -1 ? process.argv[i + 1] : null;
})();

const DEFAULT_BIN = path.join(
  ROOT,
  "dist",
  "BlackEclipse",
  process.platform === "win32" ? "Black Eclipse.exe" : "Black Eclipse"
);

const BIN = argBin || DEFAULT_BIN;
const PORT = Number(process.env.BE_SMOKE_PORT || 3199);
const TIMEOUT_MS = Number(process.env.BE_SMOKE_TIMEOUT_MS || 120_000);

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

async function probe() {
  try {
    const res = await fetch(`http://127.0.0.1:${PORT}/`, {
      redirect: "manual",
      signal: AbortSignal.timeout(4000),
    });
    return res.status;
  } catch {
    return null;
  }
}

function killTree(pid) {
  if (process.platform === "win32") {
    spawnSync("taskkill", ["/PID", String(pid), "/T", "/F"], { stdio: "ignore" });
  } else {
    try {
      process.kill(-pid, "SIGKILL");
    } catch {
      try {
        spawnSync("pkill", ["-P", String(pid)], { stdio: "ignore" });
        process.kill(pid, "SIGKILL");
      } catch {}
    }
  }
}

(async () => {
  if (!fs.existsSync(BIN)) {
    console.error(`[smoke] binary not found: ${BIN}`);
    process.exit(1);
  }

  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "be-smoke-"));
  const logPath = path.join(dataDir, "smoke.log");
  const log = fs.createWriteStream(logPath);

  console.log(`[smoke] ${BIN}`);
  console.log(`[smoke] data dir ${dataDir}, port ${PORT}`);

  const child = spawn(BIN, [], {
    env: {
      ...process.env,
      BE_DESKTOP_PORT: String(PORT),
      BE_DATA_DIR: dataDir,
      // Xvfb has no GPU; force software rendering for WebKitGTK.
      WEBKIT_DISABLE_COMPOSITING_MODE: "1",
      LIBGL_ALWAYS_SOFTWARE: "1",
    },
    detached: true,
    stdio: ["ignore", "pipe", "pipe"],
  });
  child.stdout.pipe(log);
  child.stderr.pipe(log);

  let answered = null;
  const started = Date.now();
  while (Date.now() - started < TIMEOUT_MS) {
    await sleep(1000);
    const status = await probe();
    // 503 is the app's honest "runtime still starting" gate: the server is up.
    if (status !== null) {
      answered = status;
      break;
    }
    if (child.exitCode !== null) break;
  }

  const elapsed = Math.round((Date.now() - started) / 1000);
  killTree(child.pid);
  await sleep(500);
  log.end();

  const text = fs.existsSync(logPath) ? fs.readFileSync(logPath, "utf8") : "";
  const interesting = text
    .split("\n")
    .filter((l) => /error|Error|Denied|EACCES|EPERM|failed|FATAL|server is up|conflict/i.test(l))
    .slice(-12);

  if (answered === null) {
    console.error(`[smoke] FAIL — no answer after ${elapsed}s`);
    if (interesting.length) {
      console.error("[smoke] log:");
      for (const line of interesting) console.error(`  ${line}`);
    } else {
      console.error("[smoke] log was empty — the binary probably exited immediately");
    }
    process.exit(1);
  }

  console.log(`[smoke] PASS — HTTP ${answered} after ${elapsed}s`);
  if (interesting.length) {
    for (const line of interesting.slice(-4)) console.log(`  ${line}`);
  }
  process.exit(0);
})();
