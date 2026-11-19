#!/usr/bin/env node
// Runtime smoke test: launch the packaged app and prove it actually serves.
//
// A build that compiles is not an app that runs. This starts the real binary
// from the real layout, waits for the local server to answer, and reports the
// log tail if it does not. Runs on all three platforms.
//
//   node scripts/desktop-smoke.js --bin "<path to Black Eclipse binary>"
//
// Exit 0 only when the server answered, a database-backed request succeeded AND
// the Python runtime became healthy. Anything else is a failure with the first
// useful lines of the log.

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
// The Python runtime's own cold-start budget is 300s, and after a fresh install
// the payload is cold on disk (often still being scanned): a first import
// measured over 3 minutes. Waiting less than the runtime is allowed makes a
// healthy runtime fail the gate. Override for a deliberately slow machine.
const HARNESS_WAIT_MS = Number(process.env.BE_SMOKE_HARNESS_MS || 300_000);

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

/**
 * Prove the payload can actually read its database. A release whose native
 * binding is missing still answers `/`, so only a DB-backed route catches it —
 * which is how a build shipped an installer that could never finish onboarding.
 *
 * `/api/alerts` is a plain table read: 200 with an empty list on a fresh
 * install, 500 when the binding is gone. `/api/setup` is NOT usable here: with
 * no database yet it answers 200 from defaults without ever touching SQLite.
 */
async function probeDb() {
  try {
    const res = await fetch(`http://127.0.0.1:${PORT}/api/alerts`, {
      signal: AbortSignal.timeout(8000),
    });
    return res.status === 200
      ? { ok: true }
      : { ok: false, why: `HTTP ${res.status} from /api/alerts` };
  } catch (err) {
    return { ok: false, why: String((err && err.message) || err) };
  }
}

/**
 * Prove the Python runtime becomes healthy. Nothing used to check this: a build
 * whose runtime never answers still serves `/` and still passes the DB probe, so
 * every agent/chat/research page hangs behind an endless "runtime still
 * starting" while the window looks fine.
 *
 * This is the same route the UI uses to decide the runtime is available, so a
 * healthy answer here means the pages have something to talk to. Verified
 * against a live install: 200 while uvicorn answers, 500 once it is killed.
 */
/**
 * The packaged app's own log, filtered to the lines that explain a runtime
 * failure. A plain tail is mostly Next route stack traces; the spawn command,
 * the interpreter path and the Python traceback are what identify the cause.
 */
function nativeLogTail(dataDir, lines = 60) {
  const candidates = [
    path.join(path.dirname(BIN), "app", ".black-eclipse", "desktop-native.log"),
    path.join(path.dirname(BIN), ".black-eclipse", "desktop-native.log"),
    path.join(dataDir, ".runtime", "desktop-native.log"),
  ];
  const found = candidates.find((p) => fs.existsSync(p));
  if (!found) return [`[smoke] no shell log found in: ${candidates.join(", ")}`];
  const all = fs.readFileSync(found, "utf8").split("\n");
  const relevant = all.filter((line) => /harness|uvicorn|traceback|error|spawn|python/i.test(line));
  // Both ends matter: the FIRST lines carry the resolved interpreter and the
  // spawn command; the LAST lines carry what it was doing when time ran out.
  const head = relevant.slice(0, 15);
  const tail = relevant.slice(-45);
  return [
    `[smoke] shell log ${found} (${relevant.length} relevant lines)`,
    "[smoke] first:",
    ...head.map((l) => `  ${l}`),
    "[smoke] last:",
    ...tail.map((l) => `  ${l}`),
  ];
}

async function probeHarness() {
  const deadline = Date.now() + HARNESS_WAIT_MS;
  let last = { ok: false, why: "the runtime never answered" };
  while (Date.now() < deadline) {
    try {
      const res = await fetch(`http://127.0.0.1:${PORT}/api/harness/model-runtime/health`, {
        signal: AbortSignal.timeout(10_000),
      });
      if (res.ok) return { ok: true };
      last = { ok: false, why: `HTTP ${res.status} from /api/harness/model-runtime/health` };
    } catch (err) {
      last = { ok: false, why: String((err && err.message) || err) };
    }
    await sleep(2500);
  }
  return last;
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

  // Once the page serves, prove the database behind it is readable. 30s covers
  // first-run schema creation on a cold runner.
  let db = null;
  if (answered !== null) {
    const dbStart = Date.now();
    while (Date.now() - dbStart < 30_000) {
      db = await probeDb();
      if (db.ok) break;
      await sleep(1000);
    }
  }

  // …then prove the Python runtime behind the pages is actually healthy.
  const harness = db && db.ok ? await probeHarness() : null;

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
    console.error(`[smoke] FAIL — no answer after ${elapsed}s (exit ${child.exitCode})`);

    // The shell writes its own log, not to stdout. Try the install tree first,
    // then the data directory (used when the install dir is read-only).
    const candidates = [
      path.join(path.dirname(BIN), "app", ".black-eclipse", "desktop-native.log"),
      path.join(path.dirname(BIN), ".black-eclipse", "desktop-native.log"),
      path.join(dataDir, ".runtime", "desktop-native.log"),
    ];
    const internalLog = candidates.find((p) => fs.existsSync(p));
    if (internalLog) {
      console.error(`[smoke] shell log ${internalLog}:`);
      for (const line of fs.readFileSync(internalLog, "utf8").split("\n").slice(-15)) {
        console.error(`  ${line}`);
      }
    } else {
      console.error(`[smoke] no shell log found in: ${candidates.join(", ")}`);
    }

    if (interesting.length) {
      console.error("[smoke] captured output:");
      for (const line of interesting) console.error(`  ${line}`);
    }
    process.exit(1);
  }

  if (!db || !db.ok) {
    console.error(`[smoke] FAIL — the app served but could not read its database (${db && db.why})`);
    console.error("[smoke] the payload is missing a loadable SQLite binding for its bundled Node runtime.");
    if (interesting.length) {
      console.error("[smoke] captured output:");
      for (const line of interesting) console.error(`  ${line}`);
    }
    process.exit(1);
  }

  if (!harness || !harness.ok) {
    console.error(
      `[smoke] FAIL — the app served but its Python runtime never became healthy ` +
        `(${harness ? harness.why : "not probed"}) within ${Math.round(HARNESS_WAIT_MS / 1000)}s.`
    );
    console.error("[smoke] every agent/chat/research page would hang behind a runtime that never answers.");
    // The runtime's own log is the only useful evidence (the smoke pipes the
    // shell's stdout, which does not carry it). Without this the gate reports
    // "never healthy" with no cause at all.
    for (const line of nativeLogTail(dataDir)) console.error(line);
    if (interesting.length) {
      console.error("[smoke] captured output:");
      for (const line of interesting) console.error(`  ${line}`);
    }
    process.exit(1);
  }

  console.log(`[smoke] PASS — HTTP ${answered} after ${elapsed}s`);
  console.log("[smoke] PASS — database readable via /api/alerts");
  console.log(`[smoke] PASS — Python runtime healthy via /api/harness/model-runtime/health`);
  if (interesting.length) {
    for (const line of interesting.slice(-4)) console.log(`  ${line}`);
  }
  process.exit(0);
})();
