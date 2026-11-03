#!/usr/bin/env node
// Desktop launcher: start the production site behind the local hostname proxy,
// wait until it answers, open http(s)://blackeclipse, and stop the server again
// when that tab closes.
//
// Started by ../start-eclipse.vbs with a HIDDEN console: no terminal window is
// shown, and the boot/stop log is appended to .black-eclipse/desktop-launch.log.
// The process exits on its own once the app is stopped.
//
// Tab lifecycle: the app's <DesktopSession /> beacon writes this file while the
// desktop-opened tab is alive and writes `leave` on pagehide. The file is a
// REFCOUNT of live tabs (each tab has its own id), so closing one of several
// open tabs cannot stop the server under the others. We grant a short grace
// window so a reload (which immediately sends `alive` again) doesn't stop the
// server; otherwise the process tree is killed. If every tab disappears without
// a `pagehide` (crash, force-quit), a long stale-heartbeat watchdog stops the
// server once the beacon has been silent long enough to rule out background-tab
// freezing and the machine being asleep.

const { spawn, spawnSync } = require("child_process");
const fs = require("fs");
const http = require("http");
const https = require("https");
const path = require("path");
const { tlsAvailable } = require("./lib/tls");
const { killPort, needsBuild } = require("./lib/server");

const ROOT = path.join(__dirname, "..");
const APP_PORT = Number(process.env.BE_PROD_PORT) || 3100;
const PROBE_URL = `http://127.0.0.1:${APP_PORT}/`;
// Match local-host.js: a certificate alone does not mean the proxy serves TLS;
// BE_PROXY_TLS=0 switches it back to plain http, so the probe/open URL must
// follow the profile rather than the certificate.
const TLS_DISABLED = ["0", "false", "no", "off"].includes(
  String(process.env.BE_PROXY_TLS || "").trim().toLowerCase()
);
const HOME_URL =
  process.env.BE_DESKTOP_URL ||
  (!TLS_DISABLED && tlsAvailable() ? "https://blackeclipse" : "http://blackeclipse");
const PROXY_STOP = path.join(__dirname, "local-proxy-stop.js");
const SESSION_FILE = path.join(ROOT, ".black-eclipse", "desktop-session.json");
const LOG_FILE = path.join(ROOT, ".black-eclipse", "desktop-launch.log");
// Next's own stdout/stderr used to go to the hidden console, so a server crash
// after boot was invisible. Capture it next to the launcher log.
const SERVER_LOG_FILE = path.join(ROOT, ".black-eclipse", "desktop-server.log");
// One launcher at a time. Double-clicking the icon while a cold build is still
// running used to start a second (and third, and fourth...) launcher, and every
// one of them killed the port and started its own `next build`. Concurrent
// builds delete and rewrite the same `.next` folder, so they corrupt each
// other's output and the app never comes up. This lock makes extra clicks
// no-ops while the first launcher owns the boot.
const LOCK_FILE = path.join(ROOT, ".black-eclipse", "desktop-launcher.lock");
const MAX_LOCK_MS = 2 * 60 * 60 * 1000;
const POLL_MS = 1_000;
const LEAVE_GRACE_MS = 8_000;
// Chrome/Edge throttle timers in a background tab to ~1/min, and can FREEZE a
// hidden tab entirely; Windows also suspends timers while the machine sleeps.
// A 10s heartbeat therefore legitimately goes quiet for a long time. The old
// 2.5-minute watchdog killed the server under a tab the user still had open;
// the crash fallback now waits 30 minutes, by which point the page would have
// re-beaconed on wake/focus if it still existed.
const STALE_ALIVE_MS = 30 * 60 * 1000;
// A tab entry older than this is treated as gone (crash without `pagehide`).
const TAB_STALE_MS = STALE_ALIVE_MS;
const FIRST_BEACON_MS = 60_000;
const PROGRESS_EVERY_MS = 60_000;
const PROBE_TIMEOUT_MS = 5_000;
const BOOT_POLL_MS = 300;
// If a poll iteration slept far longer than requested, the machine was asleep;
// do not run crash/stale decisions on the first tick after resume.
const SLEEP_GAP_MS = 2 * 60 * 1000;

function log(msg) {
  const line = `${new Date().toISOString()} ${msg}`;
  try {
    console.log(`[blackeclipse] ${msg}`);
  } catch {
    /* console may be gone */
  }
  try {
    fs.mkdirSync(path.dirname(LOG_FILE), { recursive: true });
    fs.appendFileSync(LOG_FILE, `${line}\n`);
  } catch {
    /* diagnostics are best-effort */
  }
}

function probeStatus(url) {
  return new Promise((resolve) => {
    let parsed;
    try {
      parsed = new URL(url);
    } catch {
      resolve(null);
      return;
    }
    const client = parsed.protocol === "https:" ? https : http;
    const req = client.get(
      url,
      {
        timeout: PROBE_TIMEOUT_MS,
        // The local certificate is self-signed but trusted by this user's
        // store; a probe must still work on a machine where that store lookup
        // fails (or before it refreshes).
        ...(parsed.protocol === "https:" ? { rejectUnauthorized: false } : {}),
      },
      (res) => {
        res.resume();
        resolve(res.statusCode ?? null);
      },
    );
    req.on("timeout", () => {
      req.destroy();
      resolve(null);
    });
    req.on("error", () => resolve(null));
  });
}

async function probeOnce(url) {
  return (await probeStatus(url)) !== null;
}

// The launcher opens the PUBLIC url (https://blackeclipse behind the proxy), so
// "the app port answers" is not enough: the proxy must be up too or the browser
// lands on an error page that never beacons. The proxy returns 502 while Next
// is still starting; only a < 400 answer means the front door is usable.
async function publicReady() {
  const code = await probeStatus(HOME_URL);
  return typeof code === "number" && code > 0 && code < 400;
}

function openBrowser(url) {
  const cmd =
    process.platform === "win32"
      ? { exe: "rundll32.exe", args: ["url.dll,FileProtocolHandler", url] }
      : process.platform === "darwin"
        ? { exe: "open", args: [url] }
        : { exe: "xdg-open", args: [url] };
  try {
    const child = spawn(cmd.exe, cmd.args, { detached: true, stdio: "ignore", windowsHide: true });
    child.on("error", (err) => log(`browser error: ${err.message}`));
    child.unref();
    log(`browser launch requested: ${url}`);
  } catch (err) {
    log(`browser spawn failed: ${err.message}`);
  }
}

function desktopUrl(url) {
  try {
    const u = new URL(url);
    u.searchParams.set("desktop", "1");
    return u.toString();
  } catch {
    return url;
  }
}

let lockHeld = false;

function pidAlive(pid) {
  try {
    process.kill(pid, 0);
    return true;
  } catch (err) {
    // EPERM means the process exists but belongs to someone else.
    return Boolean(err && err.code === "EPERM");
  }
}

function readLock() {
  try {
    const parsed = JSON.parse(fs.readFileSync(LOCK_FILE, "utf8"));
    if (parsed && Number.isFinite(parsed.pid) && Number.isFinite(parsed.at)) return parsed;
  } catch {
    /* no lock, or a half-written one */
  }
  return null;
}

function acquireLock(retried = false) {
  try {
    fs.mkdirSync(path.dirname(LOCK_FILE), { recursive: true });
    const fd = fs.openSync(LOCK_FILE, "wx");
    fs.writeSync(fd, JSON.stringify({ pid: process.pid, at: Date.now() }));
    fs.closeSync(fd);
    lockHeld = true;
    return true;
  } catch (err) {
    if (!err || err.code !== "EEXIST") {
      // The lock is a safety net, not a prerequisite: if the filesystem refuses
      // it, still boot rather than leaving the user with no app at all.
      log(`launcher lock unavailable (${err && err.message}); continuing`);
      lockHeld = false;
      return true;
    }
  }

  const held = readLock();
  const alive = held && held.pid !== process.pid && pidAlive(held.pid);
  const fresh = held && Date.now() - held.at < MAX_LOCK_MS;
  if (alive && fresh) return false;

  // The owner is gone (crash, force-quit, or a PID that has since been reused
  // by an unrelated process after the lock aged out). Take the lock over.
  try {
    fs.rmSync(LOCK_FILE, { force: true });
  } catch {
    /* best effort */
  }
  return retried ? false : acquireLock(true);
}

function releaseLock() {
  if (!lockHeld) return;
  lockHeld = false;
  try {
    const held = readLock();
    if (held && held.pid === process.pid) fs.rmSync(LOCK_FILE, { force: true });
  } catch {
    /* best effort */
  }
}

function readSession() {
  try {
    const parsed = JSON.parse(fs.readFileSync(SESSION_FILE, "utf8"));
    if (parsed && typeof parsed.at === "number" && (parsed.event === "alive" || parsed.event === "leave")) {
      return parsed;
    }
  } catch {
    /* no beacon yet */
  }
  return null;
}

// Tab ids with a heartbeat inside the freshness window. A single-tab payload
// from an older page (no `tabs` map) degrades to one implicit tab, so a cached
// app build and a freshly built one both keep working.
function liveTabs(session) {
  if (!session) return [];
  const now = Date.now();
  const tabs = session.tabs && typeof session.tabs === "object" ? session.tabs : null;
  if (!tabs) {
    return session.event === "alive" && now - session.at < TAB_STALE_MS ? ["legacy"] : [];
  }
  return Object.entries(tabs)
    .filter(([, ts]) => Number.isFinite(Number(ts)) && now - Number(ts) < TAB_STALE_MS)
    .map(([id]) => id);
}

function stopExisting() {
  log("stopping any existing production instance...");
  try {
    killPort(APP_PORT);
  } catch {
    /* best effort */
  }
  try {
    spawnSync(process.execPath, [PROXY_STOP], {
      cwd: ROOT,
      stdio: "ignore",
      windowsHide: true,
      env: process.env,
    });
  } catch {
    /* best effort */
  }
}

function hasBuild() {
  return fs.existsSync(path.join(ROOT, ".next", "BUILD_ID"));
}

function startServer() {
  try {
    fs.mkdirSync(path.dirname(SESSION_FILE), { recursive: true });
    fs.rmSync(SESSION_FILE, { force: true });
  } catch {
    /* best effort */
  }

  const built = hasBuild();
  const forceBuild = !built || process.env.BE_DESKTOP_BUILD === "1";
  const env = {
    ...process.env,
    BE_DESKTOP_HEARTBEAT_FILE: SESSION_FILE,
    NODE_ENV: "production",
  };

  let args;
  if (forceBuild) {
    log(built ? "rebuilding (BE_DESKTOP_BUILD=1) — can take several minutes" : "no built app yet — building once (the only slow launch)");
    args = [path.join(ROOT, "bin", "black.js"), "eclipse", "--restart"];
    env.BE_DESKTOP_FAST = "1";
  } else {
    // Never rebuild here. A launch must be instant; a production rebuild of this
    // app takes minutes, and doing it while the user waits was the whole delay.
    if (needsBuild()) {
      log("source is newer than the build — starting the existing build instantly");
      log("run `npm run build` with the app closed to update it");
    } else {
      log("build is current — starting instantly");
    }
    args = [path.join(ROOT, "scripts", "local-host.js"), "start", "-p", String(APP_PORT)];
  }

  const child = spawn(process.execPath, args, {
    cwd: ROOT,
    // Capture the server's output instead of inheriting the hidden console:
    // otherwise a post-boot crash leaves no trace at all.
    stdio: ["ignore", "pipe", "pipe"],
    windowsHide: false,
    env,
  });
  rotateServerLog();
  const forward = (chunk) => {
    try {
      process.stdout.write(chunk);
    } catch {
      /* console may be gone */
    }
    try {
      fs.appendFileSync(SERVER_LOG_FILE, chunk);
    } catch {
      /* diagnostics are best-effort */
    }
  };
  child.stdout.on("data", forward);
  child.stderr.on("data", forward);
  child.on("error", (err) => log(`spawn error: ${err.message}`));
  log(`server launcher pid=${child.pid}`);
  log(`server output → ${path.relative(ROOT, SERVER_LOG_FILE)}`);
  return child;
}

// Rotate the previous server log on every cold launch so it stays small; the
// last crash is what matters for diagnosis. Synchronous writes keep the log
// from holding the launcher process open after the server stops.
function rotateServerLog() {
  try {
    fs.mkdirSync(path.dirname(SERVER_LOG_FILE), { recursive: true });
    if (fs.statSync(SERVER_LOG_FILE).size > 2 * 1024 * 1024) {
      fs.renameSync(SERVER_LOG_FILE, `${SERVER_LOG_FILE}.1`);
    }
  } catch {
    /* no previous log */
  }
}

function stopServer(child) {
  if (!child || child.pid == null) return;
  try {
    if (process.platform === "win32") {
      spawnSync("taskkill", ["/F", "/T", "/PID", String(child.pid)], {
        stdio: "ignore",
        windowsHide: true,
      });
    } else {
      process.kill(-child.pid, "SIGTERM");
    }
  } catch {
    /* already gone */
  }
}

function stopAll(child) {
  // Nothing we started (e.g. a second click that found a managed app already
  // running): never tear down that app's proxy on the way out.
  if (!child) return;
  stopServer(child);
  try {
    spawnSync(process.execPath, [PROXY_STOP], {
      cwd: ROOT,
      stdio: "ignore",
      windowsHide: true,
      env: process.env,
    });
  } catch {
    /* best effort */
  }
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

let serverChild = null;

// Poll the app port for a short window. Used by a second click while the owning
// launcher is still booting, so it opens a WORKING tab instead of an error page.
async function waitForApp(ms) {
  const deadline = Date.now() + ms;
  while (Date.now() < deadline) {
    if (await probeOnce(PROBE_URL)) return true;
    await sleep(500);
  }
  return false;
}

async function waitForAppDown(ms) {
  const deadline = Date.now() + ms;
  while (Date.now() < deadline) {
    if (!(await probeOnce(PROBE_URL))) return true;
    await sleep(500);
  }
  return false;
}

// The LAST tab is gone and the owning launcher is in its 8s stop grace. A click
// in that window must not open a tab on a server that is about to be killed.
function sessionLeaving() {
  const session = readSession();
  return Boolean(session && session.event === "leave" && liveTabs(session).length === 0);
}

async function main(attempt = 0) {
  log(`launcher start (node ${process.version}, cwd ${process.cwd()})`);

  // The owning launcher both boots the app and opens the browser, so an extra
  // click has nothing left to do. Without this guard each click spawned its own
  // build against the same `.next` directory.
  if (!acquireLock()) {
    if (sessionLeaving() && attempt === 0) {
      log("previous session is closing; waiting for it to finish");
      await waitForAppDown(20_000);
      // The owner has stopped the app (and released its lock) by now; boot it
      // fresh for this click instead of opening a tab that is about to die.
      return main(1);
    }
    if (await waitForApp(15_000)) {
      // The owner is up already; just bring the tab back. While it is still
      // building this probe fails and we leave silently so the owner can open
      // the browser itself (no duplicate tabs, no second build).
      log("app is already running under another launcher; opening it");
      openBrowser(desktopUrl(HOME_URL));
    } else {
      log("another launcher is already booting the app — leaving it to finish");
    }
    return;
  }
  process.on("exit", releaseLock);

  // ── FAST PATH: never restart a server that is already answering ───────────
  // This was the lag: every icon click called stopExisting() first, so a warm
  // app paid a full kill + boot cycle (and lost whatever the open tab was
  // doing). If the app is up, opening the browser is all a click should do.
  // The running server keeps its own lifecycle (a launcher-started one is
  // already being watched by its owner).
  if (await probeOnce(PROBE_URL)) {
    log("app is already running — opening it without restarting");
    openBrowser(desktopUrl(HOME_URL));
    return;
  }

  stopExisting();

  const child = startServer();
  serverChild = child;
  let exited = false;
  let exitCode = null;
  child.on("exit", (code) => {
    exited = true;
    exitCode = code;
  });

  process.on("SIGINT", () => shutdown("interrupted"));
  process.on("SIGTERM", () => shutdown("terminated"));
  process.on("SIGBREAK", () => shutdown("console closing"));
  process.on("SIGHUP", () => shutdown("console closing"));
  process.on("exit", () => stopAll(serverChild));

  // Wait for the server for as long as it takes: a cold production rebuild can
  // run for many minutes and must not be mistaken for a failure. The launcher
  // log shows the build progress.
  const bootedAt = Date.now();
  let lastProgress = bootedAt;
  let up = false;
  while (!exited) {
    await sleep(BOOT_POLL_MS);
    // Wait for the PUBLIC url, not just the app port: the proxy must be
    // listening too, or the tab opens on a 502/connection-error page that never
    // sends a beacon.
    if ((await probeOnce(PROBE_URL)) && (await publicReady())) {
      up = true;
      log("server answered");
      break;
    }
    if (Date.now() - lastProgress >= PROGRESS_EVERY_MS) {
      lastProgress = Date.now();
      log(`still starting (${Math.round((Date.now() - bootedAt) / 1000)}s)`);
    }
  }

  if (!up) {
    log(`server stopped during boot (exit ${exitCode})`);
    // Keep the process briefly so the log flushes, then exit.
    await sleep(15_000);
    return;
  }

  // The probe above already fetched the page through the proxy, so there is
  // nothing left to settle; open immediately.
  openBrowser(desktopUrl(HOME_URL));
  log("browser opened; watching tab lifecycle");

  const startedAt = Date.now();
  let lastEvent = null;
  let lastAt = 0;
  let lastAliveAt = 0;
  let leaveSince = 0;
  let lastTick = Date.now();
  let reopened = false;
  let noBeaconLogged = false;

  while (!exited) {
    await sleep(POLL_MS);
    const now = Date.now();
    const slept = now - lastTick;
    lastTick = now;

    const session = readSession();
    const tabs = liveTabs(session);
    if (session && (session.at !== lastAt || session.event !== lastEvent)) {
      if (session.event !== lastEvent) log(`tab ${session.event} (${tabs.length} live)`);
      lastEvent = session.event;
      lastAt = session.at;
    }

    if (tabs.length > 0) {
      lastAliveAt = now;
      leaveSince = 0;
    } else if (session && session.event === "leave" && !leaveSince) {
      leaveSince = now;
    }

    // The machine was asleep. Timers on both sides were suspended, so a stale
    // heartbeat here means "we were not running", not "the tab is gone". Start
    // a fresh liveness window instead of killing the app on the next tick.
    if (slept >= SLEEP_GAP_MS && lastAliveAt) {
      lastAliveAt = now;
      log("machine resumed — resetting tab liveness window");
    }

    if (leaveSince && now - leaveSince >= LEAVE_GRACE_MS) {
      shutdown("all tabs closed");
      return;
    }

    // Crash/force-quit fallback: every tab is gone without a `pagehide`. The
    // window is deliberately long (30 min) because a hidden/frozen tab and a
    // sleeping machine both stop the heartbeat while the page is still open.
    // After resume, an alive page re-beacons on visibilitychange/pageshow; the
    // slept-gap guard skips the decision on that first tick.
    if (
      tabs.length === 0 &&
      lastAliveAt &&
      now - lastAliveAt >= STALE_ALIVE_MS &&
      slept < SLEEP_GAP_MS
    ) {
      shutdown("no tab heartbeat for 30 minutes");
      return;
    }

    // The page never beaconed (JS failed, wrong browser): retry the open once
    // before giving up, then leave the server up rather than killing something
    // the user may still be using.
    if (!lastEvent && Date.now() - startedAt > 20_000 && !reopened) {
      reopened = true;
      log("no beacon yet; reopening browser");
      openBrowser(desktopUrl(HOME_URL));
    }
    if (!lastEvent && Date.now() - startedAt > FIRST_BEACON_MS) {
      // No beacon at all (JS failed, unsupported browser): keep the server and
      // the console up rather than exiting into an orphaned process. Closing
      // the console still stops everything.
      if (!noBeaconLogged) {
        noBeaconLogged = true;
        log("no page beacon — leaving the server up; close this window to stop it");
      }
    }
  }

  // A post-boot exit used to end the launcher silently (the app just vanished).
  log(`server exited (code ${exitCode}) — stopping`);
  stopAll(child);
  process.exit(0);
}

let shuttingDown = false;
function shutdown(reason) {
  if (shuttingDown) return;
  shuttingDown = true;
  log(`${reason}; stopping server`);
  stopAll(serverChild);
  process.exit(0);
}

main().catch((err) => {
  log(`fatal: ${err && err.stack ? err.stack : err}`);
  process.exit(1);
});
