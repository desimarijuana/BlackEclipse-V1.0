#!/usr/bin/env node
// Desktop shell server bootstrap — the ONLY process the native window owns.
//
// The Tauri shell (desktop/src-tauri) spawns this file and reads its stdout for
// `@@BE:<KIND>@@<payload>` markers. Everything else in the stream is forwarded
// to `.black-eclipse/desktop-native.log` by the shell.
//
// Markers:
//   @@BE:ATTACH@@<detail>  an identified BlackEclipse server is already on the
//                          port. The shell navigates to it and does NOT own it,
//                          so quitting never kills the browser path.
//   @@BE:CONFLICT@@<detail> something else owns the port. Never killed, never
//                          bypassed with a different port.
//   @@BE:WARN@@<message>   recoverable problem, shown on the splash screen.
//   @@BE:ERROR@@<message>  nothing will load; the splash offers retry.
//   @@BE:READY@@<port>     this process owns a live server on <port>.
//
// Requirements implemented here (see docs/desktop-app-plan.md):
//   §3.2  identity + version verification before attaching
//   §3.4  never kill a server this shell did not start (no killPort, ever)
//   §3.7  cross-process start lock
//   §4    one canonical, absolute BE_DATA_DIR passed explicitly to the child
//   §5    bind 127.0.0.1 only — never 0.0.0.0
//
// The browser lane used to run a separate Next server on 3000/3105 behind a
// local reverse proxy. It was deleted on 2026-11-13; the desktop window is the
// only front door and loads the channel's loopback port directly.

const fs = require("fs");
const os = require("os");
const path = require("path");
const crypto = require("crypto");
const { spawn, spawnSync } = require("child_process");
const net = require("net");

const { nextBin, root: SERVER_ROOT } = require("./lib/server");
const { channelFromEnv, channelEnv } = require("./lib/channels");
const { prepareChannelData } = require("./lib/desktop-data");

const ROOT = SERVER_ROOT || path.join(__dirname, "..");
// The channel is fixed at launch (`BE_DESKTOP_CHANNEL`). Stable owns 3100,
// Dev owns 3101; each has its own harness port, build, pin and runtime state.
// Ports are literal (via the channel table) because Tauri's IPC allowlist
// cannot wildcard a port — moving a channel would silently disable toasts.
const CHANNEL = channelFromEnv();
const PORT = Number(process.env.BE_DESKTOP_PORT || CHANNEL.appPort);
const HOST = "127.0.0.1";
// Cold starts are slow on a loaded machine: Next measured 126 s while another
// build was running, against the old 90 s budget — the bootstrap declared a
// failure, left the (healthy) child running unowned, and the window showed a
// failure panel. Five minutes survives the measured worst case with margin.
const READY_TIMEOUT_MS = Number(process.env.BE_DESKTOP_READY_MS || 300_000);
const LOCK_TTL_MS = 90_000;

// ── immutable build pin ─────────────────────────────────────────────────────
//
// `.next` is a MUTABLE build directory: `next build` deletes and rewrites it in
// place while any `next start` is serving it. The desktop window used to load
// that live output, so an "update Eclipse" running in another tool (build,
// restart, dev bridge) broke the open window: stale client chunks, missing
// manifests, dead navigation.
//
// The desktop therefore serves a PINNED copy, taken only from a completed
// build. Agent builds keep rewriting `.next`; the window keeps reading the pin.
// It picks up a new build on the next launch/`npm run desktop:refresh`, never
// mid-session.
const PIN_ROOT = CHANNEL.pinDir;
const PIN_DIST = path.join(PIN_ROOT, ".next");
const PIN_MANIFEST = path.join(PIN_ROOT, "pin.json");
// The channel's own build output. Stable uses `.next`; Dev uses its own dir so
// a dev build can never rewrite the artifact stable pins from.
const SOURCE_DIST = path.join(ROOT, CHANNEL.buildDir);

// ── live (development) mode ─────────────────────────────────────────────────
//
// `npm run desktop:live` launches the window with BE_DESKTOP_LIVE=1. The
// bootstrap then runs `next dev` behind the window instead of pinning a
// production build: saving a file under `src/` hot-reloads the open window, so
// there is nothing to rebuild, re-pin or relaunch while iterating.
//
// It writes to its OWN dist dir, so live mode can never clobber `.next` (the
// artifact `desktop:refresh` builds and promotes). Leaving live mode is the
// ordinary `desktop:refresh` / `desktop:dev` command.
const LIVE = /^(1|true|yes|on)$/i.test(String(process.env.BE_DESKTOP_LIVE || ""));
const LIVE_DIST = `.next-live-${CHANNEL.id}`;
// Never copy Next's multi-GB cache or diagnostics into the pin.
const PIN_SKIP = new Set(["cache", "diagnostics", "standalone", "types", "trace", ".build-hash"]);

// Packaged installs run the prebuilt Next standalone server (`server.js`) with a
// bundled Node; the repository runs `next start` against `.next`. One bootstrap
// serves both so the attach/lock/identity logic is never duplicated.
const STANDALONE = fs.existsSync(path.join(ROOT, "server.js"));

// Runtime state (locks, stamps, logs) belongs beside the user's data, never in
// the install directory: a system-wide .deb installs under /usr/lib, which is
// root-owned, and a normal user cannot write there. The paths are resolved once
// the data directory is known (see `setRuntimeDir`).
let RUNTIME_DIR = null;
let LOCK_FILE = null;
let GUARD_STAMP = null;
let GUARD_FAILED = null;

function setRuntimeDir(dataDir) {
  RUNTIME_DIR = path.join(dataDir, ".runtime");
  LOCK_FILE = path.join(RUNTIME_DIR, "desktop-server.lock");
  GUARD_STAMP = path.join(RUNTIME_DIR, "db-guard.stamp");
  GUARD_FAILED = path.join(RUNTIME_DIR, "db-guard.failed");
}

function marker(kind, payload = "") {
  process.stdout.write(`@@BE:${kind}@@${payload}\n`);
}

function log(line) {
  process.stdout.write(`[desktop-server] ${line}\n`);
}

/* ------------------------------------------------- immutable build pin §6 */

function readBuildId(dir) {
  try {
    return fs.readFileSync(path.join(dir, "BUILD_ID"), "utf8").trim() || null;
  } catch {
    return null;
  }
}

/** A build `next start` can actually serve: id + manifests + server + static. */
function buildLooksComplete(dir) {
  if (!readBuildId(dir)) return false;
  try {
    const manifest = JSON.parse(fs.readFileSync(path.join(dir, "routes-manifest.json"), "utf8"));
    if (!manifest || typeof manifest !== "object") return false;
  } catch {
    return false;
  }
  return fs.existsSync(path.join(dir, "server")) && fs.existsSync(path.join(dir, "static"));
}

/** A build written seconds ago may still be mid-flight; wait before pinning. */
function buildLooksSettled(dir) {
  if (!buildLooksComplete(dir)) return false;
  const newest = ["BUILD_ID", "routes-manifest.json"]
    .map((name) => {
      try {
        return fs.statSync(path.join(dir, name)).mtimeMs;
      } catch {
        return 0;
      }
    })
    .reduce((a, b) => Math.max(a, b), 0);
  return newest > 0 && Date.now() - newest > 2_500;
}

function copyBuild(from, to) {
  fs.mkdirSync(to, { recursive: true });
  for (const entry of fs.readdirSync(from, { withFileTypes: true })) {
    if (PIN_SKIP.has(entry.name)) continue;
    fs.cpSync(path.join(from, entry.name), path.join(to, entry.name), {
      recursive: true,
      force: true,
    });
  }
}

/**
 * Use the newest completed `.next` build as the desktop payload. Returns
 * `{ dist, buildId, refreshed }` or null when there is no usable build and no
 * previous pin. Never throws: a missing/in-progress build falls back to the
 * last pinned one, which is what keeps the window alive during an update.
 *
 * A promoted, versioned release (written by `desktop:promote`) wins over the
 * ad-hoc pin. It is already a complete, health-checked copy; nothing rebuilds
 * or rewrites it, so it survives every dev build.
 */
function currentRelease() {
  const pointer = path.join(CHANNEL.releasesDir, "current.json");
  try {
    const info = JSON.parse(fs.readFileSync(pointer, "utf8"));
    const dist = path.resolve(ROOT, info && info.dir ? info.dir : "");
    if (!buildLooksComplete(dist)) {
      log(`release pointer ${info && info.dir} is not a complete build — ignoring it`);
      return null;
    }
    return { dist, buildId: readBuildId(dist), refreshed: false, release: true };
  } catch {
    return null;
  }
}

// Before channels existed, every install pinned into `.black-eclipse/desktop-dist`.
// Carry that build forward instead of forcing a rebuild: the first launch after
// this change would otherwise report "no completed build".
const LEGACY_PIN = path.join(ROOT, ".black-eclipse", "desktop-dist");

function migrateLegacyPin() {
  // The legacy pin belongs to Stable; Dev must never consume it.
  if (CHANNEL.id !== "stable") return;
  if (buildLooksComplete(PIN_DIST)) return;
  const legacyDist = path.join(LEGACY_PIN, ".next");
  if (!buildLooksComplete(legacyDist)) return;
  try {
    // A rename is atomic and free; the old server is gone by the time a new
    // bootstrap pins (the shell kills its owned tree on quit).
    fs.rmSync(PIN_ROOT, { recursive: true, force: true });
    fs.renameSync(LEGACY_PIN, PIN_ROOT);
    log(`migrated the previous pin into ${path.relative(ROOT, PIN_ROOT)}`);
  } catch (err) {
    try {
      copyBuild(legacyDist, PIN_DIST);
      log(`copied the previous pin into ${path.relative(ROOT, PIN_ROOT)} (${err && err.message})`);
    } catch (copyErr) {
      log(`could not migrate the previous pin: ${copyErr && copyErr.message}`);
    }
  }
}

async function ensurePinnedBuild() {
  migrateLegacyPin();
  const release = currentRelease();
  if (release) {
    log(`serving promoted ${CHANNEL.id} release ${release.buildId}`);
    return release;
  }
  const source = SOURCE_DIST;
  const sourceId = readBuildId(source);
  const pinnedId = readBuildId(PIN_DIST);
  const pinUsable = buildLooksComplete(PIN_DIST);

  if (sourceId && sourceId === pinnedId && pinUsable) {
    log(`pinned build is current (${sourceId})`);
    return { dist: PIN_DIST, buildId: pinnedId, refreshed: false };
  }

  if (sourceId && !buildLooksSettled(source)) {
    log("a production build is still writing .next — keeping the last pinned build");
    await new Promise((r) => setTimeout(r, 3_000));
  }

  if (buildLooksSettled(source)) {
    const nextId = readBuildId(source);
    const temp = path.join(PIN_ROOT, ".next-new");
    const previous = path.join(PIN_ROOT, ".next-old");
    try {
      fs.rmSync(temp, { recursive: true, force: true });
      fs.rmSync(previous, { recursive: true, force: true });
      log(`pinning completed build ${nextId} for the desktop…`);
      copyBuild(source, temp);
      if (!buildLooksComplete(temp)) throw new Error("pinned copy is incomplete");
      fs.mkdirSync(PIN_ROOT, { recursive: true });
      // Swap by rename so a half-written copy can never become the pin.
      if (fs.existsSync(PIN_DIST)) fs.renameSync(PIN_DIST, previous);
      fs.renameSync(temp, PIN_DIST);
      fs.rmSync(previous, { recursive: true, force: true });
      fs.writeFileSync(
        PIN_MANIFEST,
        JSON.stringify({ buildId: nextId, pinnedAt: new Date().toISOString(), source }, null, 2),
      );
      log(`desktop build pinned: ${nextId} (${path.relative(ROOT, PIN_DIST)})`);
      return { dist: PIN_DIST, buildId: nextId, refreshed: true };
    } catch (err) {
      log(`pin failed (${err && err.message}); using the previous pin`);
      try {
        fs.rmSync(temp, { recursive: true, force: true });
      } catch {}
      // Restore the previous pin if the swap failed between the two renames.
      if (!fs.existsSync(PIN_DIST) && fs.existsSync(previous)) {
        try {
          fs.renameSync(previous, PIN_DIST);
        } catch {}
      }
    }
  }

  if (pinUsable) {
    log(`serving the last pinned build (${pinnedId}) — run npm run desktop:refresh after a build`);
    return { dist: PIN_DIST, buildId: pinnedId, refreshed: false };
  }
  return null;
}

/* ---------------------------------------------------- desktop ownership */

// Written by a bootstrap that started a desktop server. It lets the NEXT shell
// attach to its own orphaned server after a crash, while refusing to attach to
// a checkout/website server that a rebuild could break mid-session.
function ownerFile() {
  return path.join(RUNTIME_DIR, "desktop-owned.json");
}

function readOwner() {
  try {
    const info = JSON.parse(fs.readFileSync(ownerFile(), "utf8"));
    if (!info || !Number.isFinite(info.pid) || !pidAlive(info.pid)) return null;
    return info;
  } catch {
    return null;
  }
}

function writeOwner(buildId) {
  try {
    fs.mkdirSync(RUNTIME_DIR, { recursive: true });
    fs.writeFileSync(
      ownerFile(),
      JSON.stringify({ pid: process.pid, port: PORT, buildId, startedAt: Date.now() }),
    );
  } catch {}
}

function clearOwner() {
  try {
    const info = JSON.parse(fs.readFileSync(ownerFile(), "utf8"));
    if (info && info.pid === process.pid) fs.rmSync(ownerFile(), { force: true });
  } catch {}
}

/** True when `pid` is verifiably a desktop-server bootstrap (never a reused PID). */
function isOwnedBootstrap(pid) {
  if (!pidAlive(pid)) return false;
  if (process.platform !== "win32") return true;
  const script =
    "(Get-CimInstance Win32_Process -Filter " +
    JSON.stringify(`ProcessId=${pid}`) +
    ").CommandLine";
  const out = spawnSync("powershell", ["-NoProfile", "-Command", script], {
    encoding: "utf8",
    windowsHide: true,
  });
  return Boolean(out.stdout && out.stdout.includes("desktop-server.js"));
}

/** Cheap async TCP probe: is anything accepting connections on this port? */
function portAccepts(port, timeoutMs = 400) {
  return new Promise((resolve) => {
    const socket = net.connect({ host: HOST, port });
    let settled = false;
    const finish = (value) => {
      if (settled) return;
      settled = true;
      socket.destroy();
      resolve(value);
    };
    socket.setTimeout(timeoutMs, () => finish(true));
    socket.once("connect", () => finish(true));
    socket.once("error", () => finish(false));
  });
}

/**
 * Reclaim the channel port from THIS install's orphaned desktop server.
 *
 * A window can crash or be closed before its owned server tree exits, leaving a
 * listener that the next launch refuses to attach to (different build, failed
 * build-health probe, or an unresponsive event loop). Because the owner marker
 * records the exact bootstrap pid and we re-verify its command line, stopping it
 * stays within the "never kill a server this shell did not start" rule: a
 * foreign listener has no matching owner marker and is still left alone.
 *
 * Returns true only when the port is actually free afterwards.
 */
async function reclaimOwnedPort() {
  const owner = readOwner();
  if (!owner || !Number.isFinite(owner.pid) || owner.pid === process.pid) return false;
  if (!isOwnedBootstrap(owner.pid)) return false;

  log(`reclaiming the channel port from this install's orphaned server (pid ${owner.pid})`);
  if (process.platform === "win32") {
    spawnSync("taskkill", ["/F", "/T", "/PID", String(owner.pid)], { stdio: "ignore" });
  } else {
    try {
      process.kill(owner.pid, "SIGTERM");
    } catch {}
  }

  const deadline = Date.now() + 8000;
  while (Date.now() < deadline) {
    if (!(await portAccepts(PORT))) {
      // The dead bootstrap's lock/owner files are now stale; clear the owner so
      // the fresh server writes its own identity.
      try {
        fs.rmSync(ownerFile(), { force: true });
      } catch {}
      return true;
    }
    await new Promise((resolve) => setTimeout(resolve, 200));
  }
  log(`orphaned server ${owner.pid} did not release port ${PORT}`);
  return false;
}

function expectedVersion() {
  try {
    return JSON.parse(fs.readFileSync(path.join(ROOT, "package.json"), "utf8")).version || null;
  } catch {
    return null;
  }
}

/* ------------------------------------------------------------------ identity */

// Liveness: cheap, polls in a loop. `/` is served by the app shell and costs
// nothing extra.
async function probeLiveness(port, timeoutMs = 2000) {
  try {
    const res = await fetch(`http://${HOST}:${port}/`, {
      redirect: "manual",
      signal: AbortSignal.timeout(timeoutMs),
    });
    const text = res.status === 200 ? await res.text().catch(() => "") : "";
    return {
      up: true,
      status: res.status,
      nextShaped: text.includes("__next_f") || text.includes("/_next/"),
      html: text,
    };
  } catch (err) {
    return { up: false, status: null, nextShaped: false, refused: /ECONNREFUSED|fetch failed/i.test(String(err && err.message)) };
  }
}

// Identity: who is this, and which version? `/api/updates` is anonymous,
// read-only and reports the installed version plus the repository slug, so it
// answers that without adding a route to the app.
//
// It can block up to ~8 s on a cold, offline manifest cache, so it is only ever
// called when a server ALREADY exists (the attach path) or once in the
// background after our own server is ready. Never on the hot boot path.
async function probeIdentity(port, timeoutMs = 9000) {
  try {
    const res = await fetch(`http://${HOST}:${port}/api/updates`, {
      redirect: "manual",
      signal: AbortSignal.timeout(timeoutMs),
    });
    if (res.status !== 200) {
      return { kind: "other", detail: `/api/updates answered HTTP ${res.status}` };
    }
    const body = await res.json().catch(() => null);
    if (body) {
      // `repository` is the strongest signal, but it degrades to "unknown" when
      // the update config cannot be read — a legitimate install must not look
      // foreign because of an unrelated config problem. Fall back to the
      // response shape, which is specific to this app.
      const namedRepo = body.repository === "black-eclipse/black-eclipse";
      const shaped =
        typeof body.currentVersion === "string" &&
        typeof body.channel === "string" &&
        typeof body.ok === "boolean";
      if (namedRepo || shaped) {
        return { kind: "ours", version: body.currentVersion || null };
      }
    }
    return { kind: "other", detail: "/api/updates answered without the Black Eclipse identity" };
  } catch (err) {
    return { kind: "unknown", detail: err && err.message ? err.message : "identity probe failed" };
  }
}

/* ---------------------------------------------------------- build health */

// Identity is necessary but not sufficient. A Next server whose build output
// was deleted while the process kept running still answers `/` with a full HTML
// document, and still passes the identity probe — but every asset the document
// references now fails. The window then shows an unstyled skeleton whose
// buttons and navigation silently do nothing (the reported "the rest of the
// pages do not work" state). Probe what the HTML actually asks the browser to
// load before trusting the server with the window.
//
// Only ever called on the attach path, so a cold start pays nothing for it.
async function probeBuildHealth(port, html, timeoutMs = 4000) {
  const assets = [...new Set(html.match(/\/_next\/static\/[^"'\s>]+/g) || [])];
  if (assets.length === 0) {
    return { ok: false, detail: "the page references no build assets" };
  }
  // A JS chunk is the load-bearing one: without it there is no hydration and no
  // client navigation, which is exactly the failure this check exists for.
  const scripts = assets.filter((a) => a.endsWith(".js"));
  const sample = (scripts.length ? scripts : assets).slice(0, 2);
  for (const asset of sample) {
    try {
      const res = await fetch(`http://${HOST}:${port}${asset}`, {
        redirect: "manual",
        signal: AbortSignal.timeout(timeoutMs),
      });
      const type = res.headers.get("content-type") || "";
      if (res.status === 200 && !type.includes("text/html")) return { ok: true };
      return {
        ok: false,
        detail: `${asset} answered HTTP ${res.status} (${type || "no content-type"})`,
      };
    } catch (err) {
      return {
        ok: false,
        detail: `${asset} could not be fetched: ${err && err.message ? err.message : String(err)}`,
      };
    }
  }
  return { ok: true };
}

// Verdict for an already-running listener.
async function classify(port) {
  const live = await probeLiveness(port);
  if (!live.up) return { kind: "none" };

  // A legacy browser-path server answers `/` with a redirect to a hostname and
  // so has no body to shape-check. That lane is deleted, but a listener left by
  // an old install can still hold the port, so tolerate the redirect rather than
  // misreporting it. Identity still answers on `/api/updates` (the canonical
  // redirect never applies to API routes), so let the probe decide instead of
  // misreporting a healthy listener as a foreign application.
  const redirected = live.status >= 300 && live.status < 400;
  if (!live.nextShaped && !redirected) {
    return { kind: "other", detail: `port ${port} answered HTTP ${live.status} but is not Black Eclipse` };
  }

  const id = await probeIdentity(port);
  if (id.kind === "ours") {
    // Build health needs the HTML the server would render. A redirect hands us
    // no document, and the browser path owns its own build, so only check when
    // there is HTML to inspect.
    if (live.html) {
      const health = await probeBuildHealth(port, live.html);
      if (!health.ok) return { kind: "stale", version: id.version, detail: health.detail };
    }
    return { kind: "ours", version: id.version };
  }
  return { kind: "tentative", detail: id.detail || "identity endpoint did not answer" };
}

/* --------------------------------------------------------------- data §4 */

function resolveDataDir() {
  // A packaged install writes user data to %LOCALAPPDATA%\BlackEclipse\data so a
  // reinstall never touches the database and an uninstall can leave it behind.
  // Repository checkouts keep the historical behaviour (the project root).
  if (!process.env.BE_DATA_DIR && STANDALONE) {
    const base = process.env.LOCALAPPDATA || path.join(os.homedir(), "AppData", "Local");
    process.env.BE_DATA_DIR = path.join(base, "BlackEclipse", "data");
  }
  const raw = process.env.BE_DATA_DIR;
  // Stable keeps the historical checkout root; Dev is always isolated.
  const dir = raw ? path.resolve(raw) : path.resolve(CHANNEL.dataDir);
  // Pass it to the child explicitly, always. This is what makes "one canonical
  // data directory" a construction guarantee instead of a coincidence: the
  // Python stores read the same variable, and its own default is derived from
  // its package location rather than the process cwd.
  process.env.BE_DATA_DIR = dir;
  return { dir, wasRaw: raw || null, wasRelative: Boolean(raw) && !path.isAbsolute(raw) };
}

/* ------------------------------------------- single-user local defaults §zero-config */

// A packaged install ships no `.env` (it held the developer's config), but two
// values there are not optional:
//
//   HARNESS_AUTH=off   Without it, `src/lib/auth/config.ts` treats a production
//                      build as public and shows "Create your operator account".
//                      The desktop app is single-user and loopback-only, so there
//                      is nothing to sign in to — it must open and be usable.
//   CRON_SECRET        Signs operator/cron actions. Generated per install.
//
// Repository checkouts keep `.env` authority; this is a packaged-install rule.
function applySingleUserDefaults(dataDir) {
  if (!STANDALONE) return;

  if (!process.env.HARNESS_AUTH) {
    process.env.HARNESS_AUTH = "off";
    log("local single-user mode: HARNESS_AUTH=off (no sign-in screen)");
  }

  if (!process.env.CRON_SECRET) {
    const file = path.join(dataDir, "operator-secret");
    let secret = null;
    try {
      secret = fs.readFileSync(file, "utf8").trim();
    } catch {}

    if (!secret || secret.length < 16) {
      secret = crypto.randomBytes(32).toString("hex");
      try {
        fs.mkdirSync(dataDir, { recursive: true });
        fs.writeFileSync(file, secret, { mode: 0o600 });
        log(`operator secret: generated for this install (${file})`);
      } catch (err) {
        log(`operator secret: could not be persisted (${err.message})`);
      }
    } else {
      log(`operator secret: loaded from ${file}`);
    }
    process.env.CRON_SECRET = secret;
  }
}

// A first run must not create an empty database file: Prisma would then fail every
// query with "table does not exist". The installer ships a schema-only seed.
function seedFirstRunDatabase(dataDir) {
  if (!STANDALONE || process.env.BE_DB_PATH) return;
  const target = path.join(dataDir, "jdds.db");
  if (fs.existsSync(target)) return;
  const seed = path.join(ROOT, "seed", "jdds.db");
  try {
    fs.mkdirSync(dataDir, { recursive: true });
    fs.copyFileSync(seed, target);
    log("first run: created the database from the bundled schema seed");
  } catch (err) {
    log(`first run: no usable seed (${err.message}) — the app may fail to query data`);
  }
}

function reportDataDir() {  const { dir, wasRaw, wasRelative } = resolveDataDir();
  const dbPath = process.env.BE_DB_PATH ? path.resolve(process.env.BE_DB_PATH) : path.join(dir, "jdds.db");

  log(`data dir (canonical) = ${dir}`);
  log(`  node   : BE_DATA_DIR explicitly set${wasRaw ? ` (from "${wasRaw}"${wasRelative ? ", was relative" : ""})` : " (defaulted to the repo root)"}`);
  log(`  python : BE_DATA_DIR (harness/persistence.py + eclipse_memory/config.py read the same variable)`);
  log(`  jdds.db: ${dbPath}`);

  if (process.env.BE_DB_PATH) {
    // A dev-profile override leaking into a desktop launch would point the
    // market database at a different file than the data directory.
    marker("WARN", "BE_DB_PATH is set — it overrides the market database path away from the data directory.");
  }

  try {
    const st = fs.statSync(dbPath);
    log(`  database present, ${(st.size / 1024 / 1024).toFixed(1)} MB`);
  } catch {
    log("  database will be created by the server on first use");
  }

  return { dir, dbPath };
}

/* ---------------------------------------------------------------- lock §3.7 */

function pidAlive(pid) {
  try {
    process.kill(pid, 0);
    return true;
  } catch (err) {
    return err && err.code === "EPERM";
  }
}

function readLock() {
  try {
    const info = JSON.parse(fs.readFileSync(LOCK_FILE, "utf8"));
    if (!info || !info.pid) return null;
    const age = Date.now() - Number(info.startedAt || 0);
    return { ...info, stale: !pidAlive(info.pid) || age > LOCK_TTL_MS };
  } catch {
    return null;
  }
}

function acquireLock() {
  fs.mkdirSync(RUNTIME_DIR, { recursive: true });
  const payload = JSON.stringify({ pid: process.pid, startedAt: Date.now(), port: PORT });

  for (let attempt = 0; attempt < 2; attempt += 1) {
    try {
      fs.writeFileSync(LOCK_FILE, payload, { flag: "wx" });
      return { ok: true };
    } catch (err) {
      if (!err || err.code !== "EEXIST") throw err;
      const held = readLock();
      if (held && !held.stale) return { ok: false, holder: held };
      // Stale (dead pid or older than the TTL): take it over.
      try {
        fs.unlinkSync(LOCK_FILE);
      } catch {}
    }
  }
  return { ok: false, holder: readLock() };
}

function releaseLock() {
  const held = readLock();
  if (held && held.pid === process.pid) {
    try {
      fs.unlinkSync(LOCK_FILE);
    } catch {}
  }
}

/* ------------------------------------------------------------ db guard §4 */

const GUARD_TTL_MS = 12 * 60 * 60 * 1000;

function guardIsFresh() {
  try {
    const age = Date.now() - fs.statSync(GUARD_STAMP).mtimeMs;
    return age >= 0 && age < GUARD_TTL_MS;
  } catch {
    return false;
  }
}

// Runs AFTER first paint so it can never delay the window. A non-zero exit
// leaves a marker that the next launch turns into recovery instructions
// instead of a silent serve of a suspect database.
function runDbGuardInBackground() {
  if (guardIsFresh()) {
    log("db-guard fresh — skipped");
    return;
  }
  try {
    const child = spawn(process.execPath, [path.join(__dirname, "db-guard.js")], {
      cwd: ROOT,
      env: process.env,
      stdio: "inherit",
      windowsHide: true,
    });
    child.on("close", (code) => {
      log(`db-guard finished (exit ${code})`);
      try {
        fs.mkdirSync(RUNTIME_DIR, { recursive: true });
        if (code === 0) {
          fs.writeFileSync(GUARD_STAMP, new Date().toISOString());
          clearGuardFailure();
        } else {
          // Recorded so the next launch re-checks before serving a suspect
          // database. `recheckGuard` keeps that from becoming a dead end.
          fs.writeFileSync(GUARD_FAILED, `exit ${code} at ${new Date().toISOString()}`);
        }
      } catch {}
    });
  } catch (err) {
    log(`db-guard skipped: ${err && err.message}`);
  }
}

function previousGuardFailed() {
  try {
    return fs.readFileSync(GUARD_FAILED, "utf8").trim();
  } catch {
    return null;
  }
}

function clearGuardFailure() {
  try {
    fs.unlinkSync(GUARD_FAILED);
  } catch {}
}

/**
 * Re-run the guard for a stored failure instead of trusting the marker forever.
 * The marker used to be a one-way door: written when the install could not load
 * its SQLite binding, it blocked every later launch, so retrying could never
 * succeed and only deleting a file by hand recovered the app.
 */
function recheckGuard() {
  log("a previous database check failed — re-checking before starting");
  try {
    const r = spawnSync(process.execPath, [path.join(__dirname, "db-guard.js")], {
      cwd: ROOT,
      env: process.env,
      encoding: "utf8",
      windowsHide: true,
      timeout: 60_000,
    });
    const out = `${r.stdout || ""}${r.stderr || ""}`.trim();
    if (out) log(out);
    if (r.status !== 0) return false;
    clearGuardFailure();
    log("database check passes now — continuing");
    return true;
  } catch (err) {
    log(`database check could not run: ${err && err.message}`);
    return false;
  }
}

function guardFailureMessage(failed) {
  const code = /exit\s+(\d+)/.exec(failed || "");
  // exit 2 is db-guard saying "I could not inspect the file" (missing native
  // binding, locked or unreadable), which is an install/environment problem —
  // not the corruption advice that only fits a failed quick_check.
  if (code && code[1] === "2") {
    return (
      `Black Eclipse could not open its database (${failed}). Your data has not been touched. ` +
      `Close any other Black Eclipse window and try again; if this keeps happening, reinstall — ` +
      `the app's SQLite component is missing from this installation.`
    );
  }
  const backups = path.join(path.dirname(RUNTIME_DIR), "backups");
  return (
    `The database integrity check failed (${failed}) and the database is still unreadable. ` +
    `Your data has not been touched. A backup may be in ${backups} — with Black Eclipse ` +
    `closed, copy one over jdds.db in that folder, or reinstall.`
  );
}

/* -------------------------------------------------------------- the server */

function startServerLoopback() {
  if (STANDALONE) {
    // Prebuilt payload: no CLI, no build step, no node_modules resolution.
    const child = spawn(process.execPath, [path.join(ROOT, "server.js")], {
      cwd: ROOT,
      stdio: "inherit",
      env: { ...process.env, PORT: String(PORT), HOSTNAME: HOST },
      windowsHide: true,
    });
    child.on("exit", (code) => {
      log(`server exited (code ${code ?? "signal"})`);
      process.exit(code ?? 0);
    });
    return child;
  }

  if (LIVE) {
    // Hot-reloading development server, behind the native window. It keeps its
    // own dist dir so a save can never overwrite the production `.next` that
    // `desktop:refresh` builds and promotes.
    const child = spawn(process.execPath, [nextBin(), "dev", "-p", String(PORT), "-H", HOST], {
      cwd: ROOT,
      stdio: "inherit",
      env: { ...process.env, NEXT_DIST_DIR: LIVE_DIST, NODE_ENV: "development" },
      windowsHide: true,
    });
    child.on("exit", (code) => {
      log(`live server exited (code ${code ?? "signal"})`);
      process.exit(code ?? 0);
    });
    return child;
  }

  // Repository: `startServer()` from lib/server.js would bind every interface
  // (§5 requires loopback only), and it is shared with the browser path, so the
  // desktop path spawns its own child with an explicit hostname.
  const child = spawn(process.execPath, [nextBin(), "start", "-p", String(PORT), "-H", HOST], {
    cwd: ROOT,
    stdio: "inherit",
    env: process.env,
    windowsHide: true,
  });
  child.on("exit", (code) => {
    log(`server exited (code ${code ?? "signal"})`);
    process.exit(code ?? 0);
  });
  return child;
}

async function waitForLive(timeoutMs) {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    const live = await probeLiveness(PORT);
    if (live.up) {
      // 503 is the app's own honest "runtime still starting" gate, and redirects
      // are normal. Only a genuine 5xx means the spawned server is broken.
      if (live.status < 500 || live.status === 503) {
        return { ok: true, status: live.status };
      }
      return { ok: false, kind: "other", detail: `HTTP ${live.status}` };
    }
    await new Promise((r) => setTimeout(r, 250));
  }
  return { ok: false, kind: "timeout" };
}

async function main() {
  log(`channel=${CHANNEL.id} root=${ROOT} host=${HOST} port=${PORT} harness=${CHANNEL.harnessPort}`);

  // Runtime state and the data directory are resolved first: the lock and the
  // guard markers live beside the user data, not in the (possibly read-only)
  // install directory.
  const { dir: dataDir } = reportDataDir();
  setRuntimeDir(dataDir);
  fs.mkdirSync(RUNTIME_DIR, { recursive: true });
  process.env.BE_DESKTOP_RUNTIME = RUNTIME_DIR;
  // Dev gets its own JDdS snapshot on first launch, so a dev experiment can
  // never write the journals or market rows the Stable channel is using.
  try {
    prepareChannelData(CHANNEL, ROOT);
  } catch (err) {
    log(`dev data preparation failed: ${err && err.message ? err.message : err}`);
  }
  applySingleUserDefaults(dataDir);
  seedFirstRunDatabase(dataDir);

  // 1. Is a server already there?
  //
  // STANDALONE (a packaged install) serves its own frozen payload, so the
  // historical identity attach is safe. A repository checkout is different: its
  // `.next` is rewritten by every build, so attaching to *any* website/agent
  // server would put the window back on mutable output — exactly the bug this
  // bootstrap exists to remove. In checkout mode we attach only to a server this
  // install started itself (owner marker) and that serves the same pinned build.
  let pin = null;

  if (LIVE) {
    // Live mode never serves a pin: an old server on the channel port would
    // keep showing the previous code while the developer edits new code.
    const existing = await probeLiveness(PORT);
    if (existing.up) {
      marker(
        "CONFLICT",
        `Port ${PORT} is already serving something. Close the running ${CHANNEL.label} window ` +
          "(or stop its server), then run `npm run desktop:live` again."
      );
      process.exitCode = 5;
      return;
    }
  } else if (STANDALONE) {
    const first = await classify(PORT);
    if (first.kind === "ours") {
      const want = expectedVersion();
      if (want && first.version && want !== first.version) {
        marker("WARN", `Attached to version ${first.version}, but this install is ${want}.`);
      }
      log(`attached to an identified server (version ${first.version || "unknown"})`);
      marker("ATTACH", `v${first.version || "?"}`);
      return;
    }
    if (first.kind === "tentative") {
      log(`attached tentatively: ${first.detail}`);
      marker("WARN", "Attached to a server that did not confirm its version.");
      marker("ATTACH", "unverified");
      return;
    }
    if (first.kind === "stale") {
      // Identified as ours, but its build files are gone. Attaching would open a
      // window that looks alive and does nothing. If the owner marker proves it
      // is THIS install's orphan, reclaim the port and start a fresh server;
      // otherwise refuse with an actionable message (never kill a foreign one).
      if (await reclaimOwnedPort()) {
        log("reclaimed the port from this install's orphaned server");
      } else {
        log(`identified but unusable server: ${first.detail}`);
        marker(
          "CONFLICT",
          `Port ${PORT} is held by a Black Eclipse server (version ${first.version || "unknown"}) whose build files ` +
            `are missing or unreadable: ${first.detail}. Pages would load without styles or scripts. ` +
            `Stop that leftover Node.js process in Task Manager (or restart the computer), then click Retry.`
        );
        process.exitCode = 5;
        return;
      }
    }
    if (first.kind === "other") {
      log(`conflict: ${first.detail}`);
      marker(
        "CONFLICT",
        `Port ${PORT} is used by another application (${first.detail}). ` +
          `Black Eclipse will not kill it or take a different port. Stop that program, then retry.`
      );
      process.exitCode = 5;
      return;
    }
  } else {
    const live = await probeLiveness(PORT);
    if (live.up) {
      const owner = readOwner();
      // The server this channel serves may be the promoted release, not the
      // ad-hoc pin; comparing only against PIN_DIST reported a live, healthy
      // own server as "older" and parked the app on the conflict screen after
      // every promotion.
      const currentId = currentRelease()?.buildId || readBuildId(PIN_DIST);
      if (owner && currentId && owner.buildId === currentId && live.html) {
        const health = await probeBuildHealth(PORT, live.html);
        if (health.ok) {
          log(`attached to this install's own desktop server (build ${currentId})`);
          marker("ATTACH", `desktop ${currentId}`);
          return;
        }
      }
      // It has our owner marker, so it is this install's own server (verified by
      // command line): an orphan whose build was replaced or whose event loop is
      // stuck. Stop it and start a fresh one instead of asking the user to open
      // Task Manager. A foreign listener has no marker and is never killed.
      if (owner && await reclaimOwnedPort()) {
        log("this install's orphaned server was stopped; starting a fresh one");
      } else {
        const id = await probeIdentity(PORT);
        const who =
          id.kind === "ours"
            ? "an older Black Eclipse server (a leftover desktop/website process)"
            : "another application";
        log(`port ${PORT} is held by ${who}`);
        marker(
          "CONFLICT",
          `Port ${PORT} is used by ${who}. The ${CHANNEL.label} desktop app needs that port for its own frozen build. ` +
            `The website lane is retired; this is a leftover process from before. ` +
            `Stop it (end the Node.js process in Task Manager), then click Retry.`
        );
        process.exitCode = 5;
        return;
      }
    }

    // 2. Pin the newest COMPLETED build. `.next` is left to the website/agent.
    pin = await ensurePinnedBuild();
    if (!pin) {
      marker(
        "ERROR",
        "No completed production build yet. Run `npm run desktop:refresh` in the project folder, then reopen Black Eclipse."
      );
      process.exitCode = 3;
      return;
    }
  }

  // 2b. Liveness can miss a listener that is bound but stuck (a 2 s probe
  // timeout while the orphan's event loop is blocked). Without this check the
  // bootstrap spawns `next start`, which dies with EADDRINUSE and leaves a bare
  // "server exited" panel. Detect the bound port and reclaim it when the owner
  // marker proves it is THIS install's orphan.
  if (!LIVE && (await portAccepts(PORT))) {
    const owner = readOwner();
    if (owner && (await reclaimOwnedPort())) {
      log("this install's orphaned server was stopped; starting a fresh one");
    } else {
      const id = await probeIdentity(PORT);
      const who =
        id.kind === "ours"
          ? "an older Black Eclipse server (a leftover desktop/website process)"
          : "another application";
      log(`port ${PORT} is bound but did not become ready (${who})`);
      marker(
        "CONFLICT",
        `Port ${PORT} is in use by ${who} and did not become ready. ` +
          `Stop that process in Task Manager, then click Retry.`
      );
      process.exitCode = 5;
      return;
    }
  }

  const failed = previousGuardFailed();
  if (failed && !recheckGuard()) {
    marker("ERROR", guardFailureMessage(failed));
    process.exitCode = 6;
    return;
  }

  // 3. One starter at a time.
  const lock = acquireLock();
  if (!lock.ok) {
    log(`another instance holds the lock (pid ${lock.holder && lock.holder.pid}) — waiting for it`);
    marker("WARN", "Another Black Eclipse instance is starting…");
    const live = await waitForLive(30_000);
    if (live.ok) {
      marker("ATTACH", "unverified");
      return;
    }
    marker("ERROR", "Another Black Eclipse instance is starting but did not become ready. Try again in a moment.");
    process.exitCode = 7;
    return;
  }

  const onExit = () => {
    releaseLock();
    clearOwner();
  };
  process.on("exit", onExit);
  for (const sig of ["SIGINT", "SIGTERM", "SIGBREAK"]) {
    process.on(sig, () => {
      releaseLock();
      clearOwner();
      process.exit(0);
    });
  }

  // 4. Canonical data directory, resolved before any service starts.
  //    (Done at the top of main: the lock and guard markers depend on it.)
  setRuntimeDir(dataDir);
  fs.mkdirSync(RUNTIME_DIR, { recursive: true });

  Object.assign(process.env, channelEnv(CHANNEL, { dataDir }));
  process.env.PORT = String(PORT);
  if (LIVE) {
    process.env.NEXT_DIST_DIR = LIVE_DIST;
    marker("WARN", "Live mode: the window hot-reloads from source on every save.");
  } else if (pin) {
    // Serve the pinned copy, never the live `.next`. A concurrent agent build
    // can now rewrite `.next` from first file to last without touching the
    // window. `pin.dist` is relative so `next start` resolves it from ROOT.
    process.env.NEXT_DIST_DIR = path.relative(ROOT, pin.dist).split(path.sep).join("/");
    if (pin.refreshed) {
      marker("WARN", `Picked up build ${pin.buildId}.`);
    } else if (!STANDALONE) {
      marker(
        "WARN",
        `Serving the last completed build (${pin.buildId}). Run \`npm run desktop:refresh\` to update it.`
      );
    }
  }

  marker(
    "WARN",
    LIVE
      ? "Live mode: compiling the UI for this window — the first start can take a minute."
      : "Starting the server…",
  );
  startServerLoopback();

  // We spawned it, so it is ours by construction: liveness is the bar for
  // READY. Identity is confirmed afterwards, off the critical path, purely to
  // report a version mismatch.
  const live = await waitForLive(READY_TIMEOUT_MS);

  // We spawned this server, so a 5xx is OUR failure, not another application.
  // Reporting it as a port conflict would be actively misleading.
  if (!live.ok) {
    marker(
      "ERROR",
      "The server answered with an error. See .black-eclipse/desktop-native.log for the first stack trace."
    );
    process.exitCode = 4;
    return;
  }

  log(`server is up (HTTP ${live.status})`);
  // Record ownership AFTER readiness: a later shell may attach to this server
  // (crash recovery), but only because it is this install's pinned build.
  if (LIVE) writeOwner("live");
  else if (pin) writeOwner(pin.buildId);
  marker("READY", String(PORT));

  // Only now, so it can never delay the first paint.
  runDbGuardInBackground();

  probeIdentity(PORT)
    .then((id) => {
      if (id.kind === "ours") {
        const want = expectedVersion();
        log(`identity confirmed: version ${id.version}`);
        if (want && id.version && want !== id.version) {
          marker("WARN", `Serving build ${id.version}, but this install is ${want}.`);
        }
      } else {
        log(`identity not confirmed: ${id.detail || id.kind}`);
      }
    })
    .catch(() => {});
}

main().catch((err) => {
  releaseLock();
  marker("ERROR", `Startup failed: ${err && err.message ? err.message : String(err)}`);
  process.exitCode = 1;
});
