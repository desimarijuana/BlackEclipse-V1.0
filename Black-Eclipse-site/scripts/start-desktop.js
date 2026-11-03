#!/usr/bin/env node
// Desktop launcher: start the production site behind the local hostname proxy,
// wait until it answers, open http(s)://blackeclipse, and stop the server again
// when that tab closes.
//
// Started by ../start-eclipse.vbs with a HIDDEN console: no terminal window is
// shown, and the boot/stop log is appended to .black-eclipse/desktop-launch.log.
// The process exits on its own once the app is stopped.
//
// A double-click must always show SOMETHING within a fraction of a second. The
// hidden console used to mean a cold build (minutes) or a failed boot (silent
// exit) looked exactly like a dead icon. So the launcher now opens a loopback
// progress page FIRST (./lib/desktop-splash.js), keeps it updated with the real
// phase, and the page redirects to the app when it is ready. A second click
// attaches to the running launcher's page instead of starting a second boot.
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
const dns = require("dns");
const fs = require("fs");
const http = require("http");
const https = require("https");
const path = require("path");
const { tlsAvailable } = require("./lib/tls");
const { killPort, needsBuild, buildInProgress } = require("./lib/server");
const { createSplash, findSplash, BUILD_HINTS } = require("./lib/desktop-splash");
const { readTheme } = require("./lib/app-theme");

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
// The progress page lives on loopback only. Ports are tried in order so a
// second click can find the first launcher's page.
const SPLASH_PORT = Number(process.env.BE_SPLASH_PORT) || 3197;
const SPLASH_TRIES = 8;
// A warm start answers in seconds; a cold one may have to compile. Both get a
// deadline so a wedged boot reports an honest error instead of hanging forever.
const BOOT_DEADLINE_MS = 5 * 60 * 1000;
const BUILD_DEADLINE_MS = 30 * 60 * 1000;
// Keep the failure page (and this process) available long enough to read it.
const ERROR_HOLD_MS = 10 * 60 * 1000;
// A ready page only exists to hand the browser off to the app.
const READY_SPLASH_TTL_MS = 90_000;

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
  const fallback =
    process.platform === "win32"
      ? { exe: "cmd.exe", args: ["/c", "start", "", url] }
      : null;
  try {
    const child = spawn(cmd.exe, cmd.args, { detached: true, stdio: "ignore", windowsHide: true });
    child.on("error", (err) => {
      log(`browser error: ${err.message}`);
      // rundll32 is the most reliable shell-free opener on Windows, but if it
      // is unavailable an unopened window looks exactly like a dead icon.
      if (fallback) {
        try {
          spawn(fallback.exe, fallback.args, { detached: true, stdio: "ignore", windowsHide: true }).unref();
          log("browser launch retried via `start`");
        } catch (e2) {
          log(`browser fallback failed: ${e2.message}`);
        }
      }
    });
    child.unref();
    log(`browser launch requested: ${url}`);
  } catch (err) {
    log(`browser spawn failed: ${err.message}`);
  }
}

// The progress page the current launcher owns (null when this launcher did not
// start one, e.g. it attached to an existing app).
let splash = null;

function setPhase(phase, detail) {
  if (!splash) return;
  splash.update({ phase, detail });
}

function setHints(list) {
  if (!splash || !Array.isArray(list)) return;
  splash.update({ hints: list });
}

function setTail(chunk) {
  if (!splash) return;
  // Keep only the last meaningful line: the page shows it as "latest output".
  const text = String(chunk);
  const lines = text
    .split(/\r?\n/)
    .map((l) => l.replace(/\x1b\[[0-9;]*m/g, "").trim())
    .filter(Boolean);
  if (lines.length === 0) return;
  splash.update({ tail: lines[lines.length - 1].slice(0, 400) });
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
    // `built` is the state BEFORE this launch: false means the very first
    // build, true means a rebuild after a source change. The progress copy can
    // say which one it is instead of hedging.
    log(built ? "rebuilding (BE_DESKTOP_BUILD=1) — can take several minutes" : "no built app yet — building once (the only slow launch)");
    setPhase("building", built ? "Rebuilding after a source change…" : "Building the app for the first time…");
    setHints(built ? BUILD_HINTS.rebuild : BUILD_HINTS.first);
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
    setTail(chunk);
    const text = String(chunk);
    if (/Creating an optimized production build|building \(first run/i.test(text)) {
      setPhase("building", "Building the production bundle…");
    } else if (/build done in|build is up to date/i.test(text)) {
      setPhase("starting", "Build finished — starting the server…");
    } else if (/starting Black Eclipse|\[startup\] instrumentation/i.test(text)) {
      setPhase("starting", "Starting the server…");
    }
  };
  child.stdout.on("data", forward);
  child.stderr.on("data", forward);
  child.on("error", (err) => log(`spawn error: ${err.message}`));
  log(`server launcher pid=${child.pid}`);
  log(`server output → ${path.relative(ROOT, SERVER_LOG_FILE)}`);
  return { child, willBuild: forceBuild };
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

// Poll the app port for a short window. Used when a dying launcher is about to
// release the app, so this click boots a fresh instance instead of opening a
// tab that is about to 404.
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

  // ── A click must always show something ───────────────────────────────────
  // If another launcher is alive, its progress page (or the app it already
  // started) is the right thing to show. Attaching happens BEFORE the lock so a
  // duplicate click never competes with an in-flight build.
  const running = await findLiveSplash();
  if (running) {
    if (running.state && running.state.ready) {
      log("app is already running — opening it");
      openBrowser(desktopUrl(HOME_URL));
    } else {
      log("another launcher is booting the app — opening its progress page");
      openBrowser(running.url);
    }
    return;
  }

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
    // The owner may still be starting its progress page. Give it a moment to
    // appear; a silent no-op is what made a second click look broken.
    const deadline = Date.now() + 20_000;
    while (Date.now() < deadline) {
      const owner = await findLiveSplash();
      if (owner) {
        log("attaching to the launcher that is already booting the app");
        openBrowser(owner.url);
        return;
      }
      if (await probeOnce(PROBE_URL)) {
        log("app is already running under another launcher; opening it");
        openBrowser(desktopUrl(HOME_URL));
        return;
      }
      await sleep(500);
    }
    log("another launcher owns the boot but did not answer — leaving it to finish");
    return;
  }
  process.on("exit", releaseLock);

  // ── FAST PATH: never restart a server that is already answering ───────────
  // This was the lag: every icon click called stopExisting() first, so a warm
  // app paid a full kill + boot cycle (and lost whatever the open tab was
  // doing). If the app is up, opening the browser is all a click should do.
  // The running server keeps its own lifecycle (a launcher-started one is
  // already being watched by its owner). The PUBLIC url is checked too: an app
  // whose proxy died would otherwise open a connection-error tab.
  if ((await probeOnce(PROBE_URL)) && (await publicReady())) {
    log("app is already running — opening it without restarting");
    openBrowser(desktopUrl(HOME_URL));
    return;
  }

  // From here on the user is waiting, so give them a live status window first.
  let userClosedSplash = false;

  // The progress page renders in the user's saved app-wide theme (JDDS
  // SystemConfig.eclipse_theme): brand color, scheme, glass, radius, fonts and
  // logo. A read failure falls back to the shipped theme; it never blocks boot.
  const appTheme = readTheme();
  log(`progress page theme: ${appTheme.scheme}, brand ${appTheme.colors.primary} (${appTheme.source})`);

  splash = await createSplash({
    port: SPLASH_PORT,
    tries: SPLASH_TRIES,
    url: desktopUrl(HOME_URL),
    logPath: LOG_FILE,
    serverLogPath: SERVER_LOG_FILE,
    theme: appTheme,
    onClosed: () => {
      userClosedSplash = true;
    },
  });
  if (splash) {
    log(`progress page: ${splash.url}`);
    openBrowser(splash.url);
  } else {
    log("progress page unavailable — continuing without it");
  }

  setPhase("preparing", "Checking the build and freeing the old port…");

  // `next build` rewrites `.next` in place, so a launcher must never start a
  // second build while one is running (a terminal `npm run build` and an icon
  // click used to race, corrupt the output, and leave the app unable to start).
  // Wait for the running build to finish instead, then use its output.
  if (!hasBuild() && buildInProgress()) {
    log("a production build is already running — waiting for it instead of starting a second");
    setPhase("building", "A production build is already running — waiting for it to finish…");
    setHints(BUILD_HINTS.waiting);
    const until = Date.now() + BUILD_DEADLINE_MS;
    while (Date.now() < until && buildInProgress()) await sleep(1_000);
    if (hasBuild()) {
      log("the running build finished — starting the app from it");
      setPhase("starting", "Build finished — starting the server…");
    } else {
      log("the running build did not produce an app — continuing");
    }
  }

  stopExisting();

  const { child, willBuild } = startServer();
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
  // run for many minutes and must not be mistaken for a failure. The progress
  // page shows the phase; the deadline only catches a genuinely wedged boot.
  const bootedAt = Date.now();
  const deadline = bootedAt + (willBuild ? BUILD_DEADLINE_MS : BOOT_DEADLINE_MS);
  let lastProgress = bootedAt;
  let up = false;
  let timedOut = false;
  let proxyWarned = false;
  while (!exited) {
    await sleep(BOOT_POLL_MS);
    const appUp = await probeOnce(PROBE_URL);
    // Wait for the PUBLIC url, not just the app port: the proxy must be
    // listening too, or the tab opens on a 502/connection-error page that never
    // sends a beacon.
    if (appUp && (await publicReady())) {
      up = true;
      log("server answered");
      break;
    }
    if (appUp && !proxyWarned) {
      proxyWarned = true;
      setPhase("proxy", "The app is up; waiting for the local hostname proxy…");
      log("app port answers; waiting for the local proxy");
      // The proxy can be healthy while the browser still cannot resolve the
      // hostname (a Windows update can drop the hosts entry). Say so instead of
      // waiting out the deadline on a page that can never load.
      const name = (process.env.BE_LOCAL_HOSTNAME || "blackeclipse").trim();
      dns.lookup(name, { all: true }, (err, addrs) => {
        const loopback =
          !err &&
          Array.isArray(addrs) &&
          addrs.some((a) => a.address === "127.0.0.1" || a.address === "::1");
        if (!loopback) {
          log(`warning: "${name}" does not resolve to this computer — run npm run setup:hostname`);
          if (splash) {
            splash.update({
              detail: `The app is up, but "${name}" does not resolve to this computer.`,
              hint: 'Run "npm run setup:hostname" once (it needs Administrator), then double-click the icon again.',
            });
          }
        }
      });
    }
    if (Date.now() >= deadline) {
      timedOut = true;
      break;
    }
    if (Date.now() - lastProgress >= PROGRESS_EVERY_MS) {
      lastProgress = Date.now();
      log(`still starting (${Math.round((Date.now() - bootedAt) / 1000)}s)`);
    }
  }

  if (!up) {
    const reason = timedOut
      ? willBuild
        ? `The build did not finish within ${Math.round(BUILD_DEADLINE_MS / 60_000)} minutes.`
        : `The app did not answer within ${Math.round(BOOT_DEADLINE_MS / 60_000)} minutes.`
      : `The server stopped while starting (exit code ${exitCode ?? "unknown"}).`;
    log(`${reason} — see ${path.relative(ROOT, SERVER_LOG_FILE)}`);
    if (!up && timedOut) {
      // Nothing will finish this boot; do not leave a half-built app running.
      stopAll(child);
    }
    if (splash) {
      splash.fail(reason, readLogTail(8));
      log("leaving the report page open so the error is readable");
      // Free the lock now: the next double-click must be able to retry while
      // this page is still open for reading.
      releaseLock();
      const until = Date.now() + ERROR_HOLD_MS;
      while (Date.now() < until && !splash.closed) await sleep(1_000);
      splash.close();
    } else {
      // Hidden console: a dialog is the only way the user learns why.
      showFatal(reason);
      await sleep(15_000);
    }
    return;
  }

  const dest = desktopUrl(HOME_URL);
  if (splash) {
    splash.ready(dest);
    log("ready — redirecting the progress page");
    // If the user closed the page, still bring the app up.
    if (userClosedSplash) openBrowser(dest);
    const t = setTimeout(() => splash && splash.close(), READY_SPLASH_TTL_MS);
    if (typeof t.unref === "function") t.unref();
  } else {
    openBrowser(dest);
  }
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

    // The page never beaconed (JS failed, wrong browser, or the user closed the
    // progress page): retry the open once before giving up, then leave the
    // server up rather than killing something the user may still be using.
    if (!lastEvent && Date.now() - startedAt > 20_000 && !reopened) {
      reopened = true;
      log("no beacon yet; reopening browser");
      openBrowser(dest);
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

// The tail of the server log, shown on the failure page.
function readLogTail(lines = 8) {
  try {
    const text = fs.readFileSync(SERVER_LOG_FILE, "utf8");
    return text.split(/\r?\n/).filter(Boolean).slice(-lines).join("\n").slice(-1500);
  } catch {
    return "";
  }
}

// Splash pages that belong to a launcher whose process is still alive. A page
// showing a startup ERROR is deliberately excluded: a new double-click must
// retry the boot instead of re-displaying the failure.
async function findLiveSplash() {
  try {
    const found = await findSplash({ port: SPLASH_PORT, tries: SPLASH_TRIES, pidAlive });
    if (found && found.state && found.state.error) return null;
    return found;
  } catch {
    return null;
  }
}

// Last-resort visibility when the progress page could not be started.
function showFatal(message) {
  log(`fatal: ${message}`);
  if (process.platform !== "win32") return;
  try {
    spawnSync(
      "powershell",
      [
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        `Add-Type -AssemblyName PresentationFramework; [System.Windows.MessageBox]::Show(${JSON.stringify(
          `Black Eclipse could not start.\n\n${message}\n\nSee: ${LOG_FILE}`
        )}, "Black Eclipse")`,
      ],
      { stdio: "ignore", windowsHide: true }
    );
  } catch {
    /* best effort */
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
