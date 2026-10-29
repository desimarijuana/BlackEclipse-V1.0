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
// desktop-opened tab is alive and writes `leave` on pagehide. We grant a short
// grace window so a reload (which immediately sends `alive` again) doesn't stop
// the server; otherwise the process tree is killed. If the tab dies without a
// `pagehide` (crash, force-quit), a stale-heartbeat watchdog stops the server
// once the beacon has been silent long enough to rule out normal background-tab
// timer throttling.

const { spawn, spawnSync } = require("child_process");
const fs = require("fs");
const http = require("http");
const path = require("path");
const { tlsAvailable } = require("./lib/tls");
const { killPort, needsBuild } = require("./lib/server");

const ROOT = path.join(__dirname, "..");
const APP_PORT = Number(process.env.BE_PROD_PORT) || 3100;
const PROBE_URL = `http://127.0.0.1:${APP_PORT}/`;
const HOME_URL =
  process.env.BE_DESKTOP_URL || (tlsAvailable() ? "https://blackeclipse" : "http://blackeclipse");
const PROXY_STOP = path.join(__dirname, "local-proxy-stop.js");
const SESSION_FILE = path.join(ROOT, ".black-eclipse", "desktop-session.json");
const LOG_FILE = path.join(ROOT, ".black-eclipse", "desktop-launch.log");
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
// Chrome/Edge throttle timers in a background tab to ~1/min after a few
// minutes, so the 10s heartbeat can legitimately go quiet. Stay well above that
// before treating silence as "the tab is gone".
const STALE_ALIVE_MS = 150_000;
const FIRST_BEACON_MS = 60_000;
const PROGRESS_EVERY_MS = 60_000;
// A hidden tab can have its 10s heartbeat throttled, so a second icon click
// must still recognise a healthy running app rather than restarting it.
const MANAGED_ALIVE_MS = 90_000;
const PROBE_TIMEOUT_MS = 5_000;

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

function probeOnce(url) {
  return new Promise((resolve) => {
    const req = http.get(url, { timeout: PROBE_TIMEOUT_MS }, (res) => {
      res.resume();
      resolve(true);
    });
    req.on("timeout", () => {
      req.destroy();
      resolve(false);
    });
    req.on("error", () => resolve(false));
  });
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
    stdio: "inherit",
    windowsHide: false,
    env,
  });
  child.on("error", (err) => log(`spawn error: ${err.message}`));
  log(`server launcher pid=${child.pid}`);
  return child;
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

async function main() {
  log(`launcher start (node ${process.version}, cwd ${process.cwd()})`);

  // The owning launcher both boots the app and opens the browser, so an extra
  // click has nothing left to do. Without this guard each click spawned its own
  // build against the same `.next` directory.
  if (!acquireLock()) {
    const existing = readSession();
    if (existing && existing.event === "alive" && (await probeOnce(PROBE_URL))) {
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

  // A second click while another launcher is watching should just bring the
  // browser back, not restart the app under it.
  const existing = readSession();
  if (existing && existing.event === "alive" && Date.now() - existing.at < MANAGED_ALIVE_MS) {
    if (await probeOnce(PROBE_URL)) {
      log("app is already running under a launcher; opening it");
      openBrowser(desktopUrl(HOME_URL));
      return;
    }
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
    await sleep(800);
    if (await probeOnce(PROBE_URL)) {
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

  // Let Next settle its first response before opening the browser.
  await sleep(3_000);
  openBrowser(desktopUrl(HOME_URL));
  log("browser opened; watching tab lifecycle");

  const startedAt = Date.now();
  let lastEvent = null;
  let lastAt = 0;
  let leaveSince = 0;
  let reopened = false;
  let noBeaconLogged = false;

  while (!exited) {
    await sleep(POLL_MS);
    const session = readSession();
    if (session && (session.at !== lastAt || session.event !== lastEvent)) {
      if (session.event !== lastEvent) log(`tab ${session.event}`);
      lastEvent = session.event;
      lastAt = session.at;
      if (session.event === "alive") leaveSince = 0;
      if (session.event === "leave") leaveSince = Date.now();
    }

    if (lastEvent === "leave" && leaveSince && Date.now() - leaveSince >= LEAVE_GRACE_MS) {
      log("tab closed; stopping server");
      stopAll(child);
      return;
    }

    // Crash/force-quit fallback: the tab never sent `leave`, but its heartbeat
    // stopped. Background-tab throttling is slower than this, so prolonged
    // silence means the page is really gone rather than merely hidden.
    if (lastEvent === "alive" && lastAt && Date.now() - lastAt >= STALE_ALIVE_MS) {
      log("tab heartbeat stopped; stopping server");
      stopAll(child);
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
