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
// The browser path (`local-host.js`, `up.js`, `start-desktop.js`, `bin/black.js`)
// is a separate front door and is untouched.

const fs = require("fs");
const os = require("os");
const path = require("path");
const crypto = require("crypto");
const { spawn } = require("child_process");

const { needsBuild, nextBin, root: SERVER_ROOT } = require("./lib/server");
const { PROD, childEnv } = require("./lib/profiles");

const ROOT = SERVER_ROOT || path.join(__dirname, "..");
const PORT = Number(process.env.BE_DESKTOP_PORT || PROD.appPort);
const HOST = "127.0.0.1";
const READY_TIMEOUT_MS = Number(process.env.BE_DESKTOP_READY_MS || 90_000);
const LOCK_TTL_MS = 90_000;

// Packaged installs run the prebuilt Next standalone server (`server.js`) with a
// bundled Node; the repository runs `next start` against `.next`. One bootstrap
// serves both so the attach/lock/identity logic is never duplicated.
const STANDALONE = fs.existsSync(path.join(ROOT, "server.js"));

const RUNTIME_DIR = path.join(ROOT, ".black-eclipse");
const LOCK_FILE = path.join(RUNTIME_DIR, "desktop-server.lock");
const GUARD_STAMP = path.join(RUNTIME_DIR, "db-guard.stamp");
const GUARD_FAILED = path.join(RUNTIME_DIR, "db-guard.failed");

function marker(kind, payload = "") {
  process.stdout.write(`@@BE:${kind}@@${payload}\n`);
}

function log(line) {
  process.stdout.write(`[desktop-server] ${line}\n`);
}

function buildExists() {
  if (STANDALONE) return true;
  return (
    fs.existsSync(path.join(ROOT, ".next", "BUILD_ID")) ||
    fs.existsSync(path.join(ROOT, ".next", "server", "app"))
  );
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

  // A browser-path server (`npm start`) answers `/` with a 307 to the TLS
  // hostname, so it has no body to shape-check. That is normal — the plan calls
  // it out explicitly. Identity still answers on `/api/updates` (the canonical
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

// Per-OS user data root. The equivalent of Local Storage on a desktop app:
//   Windows  %LOCALAPPDATA%\BlackEclipse\data
//   macOS    ~/Library/Application Support/BlackEclipse/data
//   Linux    $XDG_DATA_HOME/BlackEclipse/data  (default ~/.local/share)
function defaultDataDir() {
  if (process.platform === "win32") {
    const base = process.env.LOCALAPPDATA || path.join(os.homedir(), "AppData", "Local");
    return path.join(base, "BlackEclipse", "data");
  }
  if (process.platform === "darwin") {
    return path.join(os.homedir(), "Library", "Application Support", "BlackEclipse", "data");
  }
  const base = process.env.XDG_DATA_HOME || path.join(os.homedir(), ".local", "share");
  return path.join(base, "BlackEclipse", "data");
}

function resolveDataDir() {
  // A packaged install writes user data under the platform's data root so a
  // reinstall never touches the database and an uninstall can leave it behind.
  // Repository checkouts keep the historical behaviour (the project root).
  if (!process.env.BE_DATA_DIR && STANDALONE) {
    process.env.BE_DATA_DIR = defaultDataDir();
  }
  const raw = process.env.BE_DATA_DIR;
  const dir = raw ? path.resolve(raw) : path.resolve(ROOT);
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
        if (code === 0) {
          fs.mkdirSync(RUNTIME_DIR, { recursive: true });
          fs.writeFileSync(GUARD_STAMP, new Date().toISOString());
          if (fs.existsSync(GUARD_FAILED)) fs.unlinkSync(GUARD_FAILED);
        } else {
          fs.mkdirSync(RUNTIME_DIR, { recursive: true });
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

/* -------------------------------------------------------------- the server */

/// Environment for the server this shell spawns. The desktop window talks to
/// `http://127.0.0.1:3100`, which is the origin listed in the Tauri capability;
/// a canonical-host redirect (`BE_CANONICAL_HOST`, set by the browser launcher)
/// would navigate the WebView to `https://blackeclipse`, where `__TAURI__` is
/// absent and glass/window IPC silently stop working. Strip it for our child.
function desktopChildEnv(extra = {}) {
  const env = { ...process.env, ...extra };
  delete env.BE_CANONICAL_HOST;
  return env;
}

function startServerLoopback() {
  if (STANDALONE) {
    // Prebuilt payload: no CLI, no build step, no node_modules resolution.
    const child = spawn(process.execPath, [path.join(ROOT, "server.js")], {
      cwd: ROOT,
      stdio: "inherit",
      env: desktopChildEnv({ PORT: String(PORT), HOSTNAME: HOST }),
      windowsHide: true,
    });
    child.on("exit", (code) => {
      log(`server exited (code ${code ?? "signal"})`);
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
    env: desktopChildEnv(),
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
  log(`root=${ROOT} host=${HOST} port=${PORT}`);

  // 1. Is a server already there? If so, is it OURS? Identity is verified
  //    BEFORE attaching, because an existing process might be anything.
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
    // window that looks alive and does nothing, so refuse with an actionable
    // message. Never kill it: the ownership rule still holds, even for a corpse.
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

  // 2. Nothing identified. Do we know how to start one?
  if (!buildExists()) {
    marker(
      "ERROR",
      "No production build yet. Run `npm run build` once in the project folder, then reopen Black Eclipse."
    );
    process.exitCode = 3;
    return;
  }

  const failed = previousGuardFailed();
  if (failed) {
    marker(
      "ERROR",
      `The last database integrity check failed (${failed}). Your data has not been touched. ` +
        `Backups are in Black-Eclipse-site/backups/ — restore one, or re-run \`npm run doctor\`.`
    );
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

  const onExit = () => releaseLock();
  process.on("exit", onExit);
  for (const sig of ["SIGINT", "SIGTERM", "SIGBREAK"]) {
    process.on(sig, () => {
      releaseLock();
      process.exit(0);
    });
  }

  // 4. Canonical data directory, resolved before any service starts.
  const { dir: dataDir } = reportDataDir();
  applySingleUserDefaults(dataDir);
  seedFirstRunDatabase(dataDir);

  if (!STANDALONE && needsBuild()) {
    marker("WARN", "Starting the last build — your source is newer. Run `npm run build` to refresh it.");
  }

  Object.assign(process.env, childEnv(PROD));
  process.env.PORT = String(PORT);

  marker("WARN", "Starting the server…");
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
