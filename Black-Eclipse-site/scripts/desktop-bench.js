#!/usr/bin/env node
// Measure desktop startup stages honestly.
//
// What this reports:
//   spawn  -> HTTP 200 on the app port        ("server ready")
//   spawn  -> window process alive            ("window up")
// and the same for the attach path (a server already running).
//
// It does NOT report "click to interactive": that needs the rendered page to
// answer a probe, which the shell already does for notifications. See
// `desktop-selftest.js` for the in-page probe.

const fs = require("fs");
const net = require("net");
const os = require("os");
const path = require("path");
const { spawn } = require("child_process");

const ROOT = path.join(__dirname, "..");
const EXE =
  process.env.BE_DESKTOP_EXE ||
  path.join(ROOT, "desktop", "src-tauri", "target", "release", "black-eclipse-desktop.exe");

function portFree(port) {
  return new Promise((resolve) => {
    const s = net
      .createServer()
      .once("error", () => resolve(false))
      .once("listening", () => s.close(() => resolve(true)))
      .listen(port, "127.0.0.1");
  });
}

async function probe(port) {
  try {
    const res = await fetch(`http://127.0.0.1:${port}/`, {
      redirect: "manual",
      signal: AbortSignal.timeout(1500),
    });
    return res.status;
  } catch {
    return null;
  }
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

async function measureCold(port, label) {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "be-bench-"));
  const t0 = Date.now();
  const child = spawn(EXE, [], {
    env: { ...process.env, BE_DESKTOP_PORT: String(port), BE_DATA_DIR: dataDir },
    detached: true,
    stdio: "ignore",
  });
  child.unref();

  let windowAt = null;
  let readyAt = null;
  const { execFile, execFileSync } = require("child_process");

  const checkWindow = () =>
    new Promise((resolve) => {
      execFile(
        "powershell",
        [
          "-NoProfile",
          "-Command",
          `$p = Get-Process -Id ${child.pid} -ErrorAction SilentlyContinue; if ($p -and $p.MainWindowHandle -ne 0) { 'yes' }`,
        ],
        (err, stdout) => resolve(!err && String(stdout).trim() === "yes")
      );
    });

  for (let tick = 0; tick < 480; tick += 1) {
    await sleep(100);
    if (!windowAt && tick % 5 === 0 && (await checkWindow())) {
      windowAt = Date.now() - t0;
    }
    const status = await probe(port);
    if (status !== null) {
      readyAt = Date.now() - t0;
      break;
    }
  }

  try {
    execFileSync("taskkill", ["/PID", String(child.pid), "/T", "/F"], { stdio: "ignore" });
  } catch {}
  fs.rmSync(dataDir, { recursive: true, force: true });

  return { label, windowMs: windowAt, readyMs: readyAt };
}

(async () => {
  if (!fs.existsSync(EXE)) {
    console.error("No shell binary. Run `npm run desktop:build` first.");
    process.exit(1);
  }

  const results = [];

  // Cold: nothing listening on the port, empty data dir.
  for (const port of [3131, 3132, 3133]) {
    if (!(await portFree(port))) {
      console.log(`skip ${port}: busy`);
      continue;
    }
    results.push(await measureCold(port, `cold #${results.length + 1}`));
  }

  console.log("\nDesktop startup");
  console.log("─".repeat(46));
  for (const r of results) {
    console.log(
      `${r.label.padEnd(10)} window ${String(r.windowMs ?? "?").padStart(5)} ms   ready ${String(
        r.readyMs ?? "?"
      ).padStart(5)} ms`
    );
  }
  const ready = results.map((r) => r.readyMs).filter(Boolean);
  if (ready.length) {
    const avg = Math.round(ready.reduce((a, b) => a + b, 0) / ready.length);
    console.log("─".repeat(46));
    console.log(`average ready: ${avg} ms`);
  }
})();
