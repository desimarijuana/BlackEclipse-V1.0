#!/usr/bin/env node
// ── Stage a signed release for the desktop app ──────────────────────────────
//
// Spawned detached by `POST /api/updates/apply`. It runs the SAME verified
// updater the CLI uses (`scripts/update.js`), but with `--no-desktop`: verify the
// signed manifest, back up jdds.db, check out the tag, `npm ci`, `npm run
// build` — and then STOP.
//
// Why stop before promoting: promotion restarts the desktop window and kills the
// server tree (`taskkill /T`). A runner spawned by that server would be killed
// halfway through the promote, possibly after the copy but before the pointer
// moved. Staging touches nothing the running app serves, so it is safe to do
// in-app; the restart is requested separately and executed by the shell, which
// is not in the killed tree.
//
// Progress is written to a job file (`.runtime/update-job.json`) that the UI
// polls, because the runner outlives the server process that started it.
//
// Usage: node scripts/update-apply.js [--channel stable|beta] [--job <file>]

"use strict";

const fs = require("fs");
const os = require("os");
const path = require("path");
const crypto = require("crypto");
const { Readable, Transform } = require("stream");
const { pipeline } = require("stream/promises");
const { spawn, spawnSync } = require("child_process");

const ROOT = path.resolve(__dirname, "..");
const args = process.argv.slice(2);
const argValue = (name, fallback) => {
  const i = args.indexOf(`--${name}`);
  return i !== -1 && args[i + 1] ? args[i + 1] : fallback;
};

const channel = argValue("channel", "stable");
// The version the window is actually serving. `readVersion()` is the checkout on
// disk, which can differ (a pinned build, or a developer tree ahead/behind the
// running app). The caller passes the running version; the disk is only a
// fallback so a manual `node scripts/update-apply.js` still behaves sensibly.
const runningVersion = argValue("running-version", process.env.BE_UPDATE_RUNNING_VERSION);
// The build always lands in `.next`, which is the Stable channel's build dir.
// The in-app path refuses the Dev channel rather than promoting the wrong app.
const desktopChannel = process.env.BE_DESKTOP_CHANNEL === "dev" ? "dev" : "stable";
const jobFile =
  argValue("job") || process.env.BE_UPDATE_JOB_FILE || path.join(ROOT, ".runtime", "update-job.json");

const LOG_TAIL = 80;
const JOB_ID = crypto.randomBytes(8).toString("hex");
const fromVersion = runningVersion || readVersion();

const job = {
  id: JOB_ID,
  status: "running",
  phase: "starting",
  message: "Checking the signed release…",
  fromVersion,
  toVersion: null,
  // Set to "build" once the prebuilt path reports a staged build directory.
  mode: "git",
  stagedDir: null,
  artifact: null,
  startedAt: new Date().toISOString(),
  updatedAt: new Date().toISOString(),
  finishedAt: null,
  pid: process.pid,
  log: [],
  error: null,
};

let flushTimer = null;
// True once the updater has actually moved to the signed tag. Distinguishes a
// real stage from "nothing to do" exits (already current, not published).
let applied = false;
// True when this runner closed the app to free its native modules. The app must
// then be reopened, whether the update succeeded or failed.
let stoppedServer = false;

function readVersion() {
  try {
    return JSON.parse(fs.readFileSync(path.join(ROOT, "package.json"), "utf8")).version || "unknown";
  } catch {
    return "unknown";
  }
}

/** Write atomically: a poll must never read a half-written job. */
function flush() {
  flushTimer = null;
  job.updatedAt = new Date().toISOString();
  try {
    fs.mkdirSync(path.dirname(jobFile), { recursive: true });
    const tmp = `${jobFile}.${process.pid}.tmp`;
    fs.writeFileSync(tmp, JSON.stringify(job, null, 2), "utf8");
    fs.renameSync(tmp, jobFile);
  } catch {
    /* a failed write must never abort an update that is already in progress */
  }
}

function scheduleFlush() {
  if (flushTimer) return;
  flushTimer = setTimeout(flush, 200);
}

function setPhase(phase, message) {
  job.phase = phase;
  job.message = message;
  flush();
}

function pushLog(line) {
  const text = line.replace(/\u001b\[[0-9;]*m/g, "").replace(/\s+$/, "");
  if (!text) return;
  job.log.push(text.length > 400 ? `${text.slice(0, 400)}…` : text);
  if (job.log.length > LOG_TAIL) job.log.splice(0, job.log.length - LOG_TAIL);
  scheduleFlush();
}

// The updater's own output is the phase signal: it logs one line before each
// irreversible step. Matching text is preferable to guessing from timing.
const PHASES = [
  [/^\[update\] installed: v/, "verifying", "Checking the signed release…"],
  [/^\[update\] backing up jdds\.db/, "backing-up", "Backing up your database…"],
  [/^\[update\] mode: signed prebuilt build/, "verifying", "Checking the signed release…"],
  [/^\[update\] downloading the verified build/, "downloading", "Downloading the signed build…"],
  [/^\[update\] still downloading/, "downloading", "Downloading the signed build…"],
  [/^\[update\] extracting the verified build/, "unpacking", "Verifying and unpacking the build…"],
  [/^\[update\] build validated/, "unpacking", "Verifying and unpacking the build…"],
  [/^\[update\] this release changed dependencies/, "installing", "Installing dependencies…"],
  [/^\[update\] promoting the verified build/, "promoting", "Publishing the new build…"],
  [/^\[update\] checking out /, "checkout", "Checking out the signed release…"],
  [/^\[update\] waiting for the native modules/, "installing", "Waiting for Eclipse to release its files…"],
  [/^\[update\] installing dependencies/, "installing", "Installing dependencies (slow)…"],
  [/^\[update\] building production bundle/, "building", "Building the new version (slow)…"],
  [/^\[update\] rolling back/, "building", "Update failed — rolling back…"],
  [/^\[desktop:refresh\]/, "building", "Preparing the new build…"],
];

// Where the phases sit on the timeline. `downloading`/`unpacking` belong to the
// prebuilt path; `checkout`/`building` to the git fallback. A phase may only
// move forward, so a late "installed: v" line cannot undo "building".
const PHASE_ORDER = [
  "starting",
  "stopping",
  "verifying",
  "backing-up",
  "downloading",
  "unpacking",
  "checkout",
  "installing",
  "building",
  "promoting",
];

function onLine(line) {
  pushLog(line);
  if (
    /^\[update\] (checking out|installing dependencies|building production bundle|build staged:)/.test(line)
  ) {
    applied = true;
  }
  // The prebuilt path reports where it staged the verified build; the runner
  // promotes from exactly that directory (never from `.next`, which the user's
  // tree may have rebuilt since).
  const staged = /^\[update\] build staged: (.+)$/.exec(line);
  if (staged) {
    job.mode = "build";
    job.stagedDir = staged[1].trim();
  }
  // The staged directory is the checkout-independent truth about WHICH version
  // was staged; the checkout on disk may be on another version entirely.
  const stagedRelease = /^\[update\] staged release: v([\d.]+)/.exec(line);
  if (stagedRelease) job.toVersion = stagedRelease[1];
  for (const [pattern, phase, message] of PHASES) {
    if (pattern.test(line)) {
      if (PHASE_ORDER.indexOf(phase) > PHASE_ORDER.indexOf(job.phase)) setPhase(phase, message);
      return;
    }
  }
  const updated = /^\[update\] updated v[\d.]+ -> v?([\d.]+)/.exec(line);
  if (updated) job.toVersion = updated[1];
}

function finish(status, phase, message, error) {
  job.status = status;
  job.phase = phase;
  job.message = message;
  job.error = error || null;
  job.finishedAt = new Date().toISOString();
  if (!job.toVersion) job.toVersion = status === "ready" ? readVersion() : null;
  if (flushTimer) clearTimeout(flushTimer);
  flush();
}

function fail(message) {
  finish("failed", "failed", message, message);
  reviveIfStopped();
  process.exit(1);
}

/**
 * Reopen the window this runner closed. Without this a failed update would
 * leave the user with a window whose server is gone and no way back.
 */
function reviveIfStopped() {
  if (!stoppedServer) return;
  stoppedServer = false;
  try {
    const { channelFor } = require("./lib/channels");
    const { launchShell } = require("./lib/desktop-process");
    const launched = launchShell(channelFor(desktopChannel));
    if (launched && launched.launched) pushLog("[apply] reopened Eclipse on the current build");
  } catch (err) {
    pushLog(`[apply] could not reopen Eclipse: ${err && err.message ? err.message : err}`);
  }
}

/**
 * The running server holds `next-swc`/`skia`, so npm cannot replace them. Stop
 * the server this install owns, but only when it is not our own ancestor: the
 * HTTP fallback is spawned FROM that server, and killing it would kill us.
 */
function closeRunningApp() {
  try {
    const { channelFor } = require("./lib/channels");
    const { readOwner, stopOwnedServer } = require("./lib/desktop-process");
    const { lockedNativeModules, waitForNativeUnlock, isAncestorOf } = require("./lib/update-locks");
    if (!lockedNativeModules(ROOT).length) return false;

    const target = channelFor(desktopChannel);
    const owner = readOwner(target);
    if (!owner) {
      pushLog("[apply] dependencies are held by a process this install does not own");
      return false;
    }
    if (isAncestorOf(owner.pid, process.pid)) {
      pushLog("[apply] the running server started this updater; it must be closed by hand");
      return false;
    }

    setPhase("stopping", "Closing Eclipse so its files can be replaced…");
    pushLog("[apply] closing the running server so npm can replace its native modules");
    stopOwnedServer(target);
    if (!waitForNativeUnlock(ROOT, 60000)) {
      pushLog("[apply] the native modules are still locked");
      return false;
    }
    return true;
  } catch (err) {
    pushLog(`[apply] could not close the running server: ${err && err.message ? err.message : err}`);
    return false;
  }
}

/** Promote the staged build, restarting the window when this runner closed it. */
function promote(restart, from) {
  setPhase("promoting", "Publishing the new build…");
  const args = ["--no-build", "--channel", desktopChannel];
  // `--from` promotes the build the updater just verified, not `.next` (which
  // belongs to the user's working tree and may be anything).
  if (from) args.push("--from", from);
  if (!restart) args.push("--no-restart");
  const result = spawnSync(
    process.execPath,
    [path.join(ROOT, "scripts", "desktop-refresh.js"), ...args],
    { cwd: ROOT, encoding: "utf8", windowsHide: true, env: process.env },
  );
  for (const line of `${result.stdout || ""}\n${result.stderr || ""}`.split(/\r?\n/)) {
    if (line.trim()) onLine(line.trim());
  }
  if (result.status !== 0) {
    fail(
      "The new build could not be promoted. Your current build is untouched — " +
        "run `npm run desktop:refresh` in a terminal.",
    );
    return false;
  }
  return true;
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

// ── Packaged installs ────────────────────────────────────────────────────────
// A release installer has no git tree, so the checkout+build path cannot run.
// The signed manifest carries a per-platform installer URL and SHA-256; we
// download those exact bytes, verify them, and hand the verified file to the
// Windows installer. Nothing runs before the digest matches.

/**
 * Is this checkout a git work tree, or a packaged `<install>\app` payload?
 * The repo root can be above ROOT (this app lives in `Black-Eclipse-site/`
 * inside its repo), so look for the enclosing work tree, not `ROOT/.git`.
 */
function isGitCheckout() {
  try {
    return require("./lib/git-root").isSourceCheckout(ROOT);
  } catch {
    return false;
  }
}

function installerPlatform() {
  return `${process.platform}-${process.arch}`;
}

/**
 * Where user data lives, mirroring `resolveDataDir()` in
 * scripts/desktop-server.js. A packaged install keeps it outside `$INSTDIR`
 * (`%LOCALAPPDATA%\BlackEclipse\data`), which is also the only safe place to
 * download the installer that is about to replace `$INSTDIR\app`.
 */
function resolveDataDir() {
  if (process.env.BE_DATA_DIR) return path.resolve(process.env.BE_DATA_DIR);
  // `server.js` next to the payload marks a packaged install (STANDALONE).
  if (fs.existsSync(path.join(ROOT, "server.js"))) {
    const base = process.env.LOCALAPPDATA || path.join(os.homedir(), "AppData", "Local");
    const dir = path.join(base, "BlackEclipse", "data");
    process.env.BE_DATA_DIR = dir;
    return dir;
  }
  return path.resolve(path.dirname(ROOT));
}

const DATA_DIR = resolveDataDir();

/** Where the downloaded installer and its handoff helper live (outside $INSTDIR). */
function downloadsDir() {
  return path.join(DATA_DIR, ".runtime", "updates");
}

function quotePowerShell(value) {
  return `'${String(value).replace(/'/g, "''")}'`;
}

async function downloadVerified(url, dest, sha256, expectedSize) {
  fs.mkdirSync(path.dirname(dest), { recursive: true });
  const tmp = `${dest}.part`;
  fs.rmSync(tmp, { force: true });

  let response;
  try {
    response = await fetch(url, {
      headers: { accept: "application/octet-stream", "cache-control": "no-cache" },
      redirect: "follow",
      // An installer is large and a slow link is not a failure. The job
      // heartbeat keeps moving while bytes arrive.
      signal: AbortSignal.timeout(30 * 60 * 1000),
    });
  } catch {
    throw new Error("Could not reach the installer download.");
  }
  if (!response.ok || !response.body) {
    throw new Error(`The installer download returned HTTP ${response.status}.`);
  }

  const hash = crypto.createHash("sha256");
  let total = 0;
  const meter = new Transform({
    transform(chunk, _encoding, callback) {
      total += chunk.length;
      if (expectedSize && total > expectedSize) {
        callback(new Error("The installer is larger than the signed size."));
        return;
      }
      hash.update(chunk);
      // A long download must still write heartbeats, or the job reads as dead
      // after five minutes (`src/lib/updates/job.ts`).
      if (total % (8 * 1024 * 1024) < chunk.length) scheduleFlush();
      callback(null, chunk);
    },
  });

  // A long download must still write heartbeats, or the job reads as dead after
  // five minutes (`src/lib/updates/job.ts`). The byte-count flush below covers a
  // moving download; this timer covers a slow/blocked one.
  const beat = setInterval(scheduleFlush, 30_000);
  try {
    await pipeline(Readable.fromWeb(response.body), meter, fs.createWriteStream(tmp));
  } catch (err) {
    fs.rmSync(tmp, { force: true });
    throw err;
  } finally {
    clearInterval(beat);
  }

  const digest = hash.digest("hex");
  if (digest !== String(sha256).toLowerCase()) {
    fs.rmSync(tmp, { force: true });
    throw new Error(
      "The downloaded installer failed its signed checksum and was deleted. Nothing was installed.",
    );
  }
  if (expectedSize && total !== expectedSize) {
    fs.rmSync(tmp, { force: true });
    throw new Error(
      `The downloaded installer is ${total} bytes but the signed release says ${expectedSize}. Nothing was installed.`,
    );
  }
  fs.renameSync(tmp, dest);
  return total;
}

/**
 * Close this install's window and server, then open the verified installer.
 *
 * The shutdown is delegated to a detached PowerShell helper because an
 * HTTP-started runner lives inside the server tree (`taskkill /T` would kill it
 * before the installer starts). The helper waits for this process to exit,
 * stops only this install's processes, then opens the installer. The helper
 * lives in the data directory, so replacing `<install>\app` does not remove it.
 */
function launchInstaller(installerPath) {
  if (process.platform !== "win32") {
    throw new Error(
      "Automatic installation is Windows-only today. Open the release page to download the update.",
    );
  }
  const { channelFor } = require("./lib/channels");
  const { readOwner } = require("./lib/desktop-process");
  const target = channelFor(desktopChannel);
  const owner = readOwner(target);

  const lines = [
    "$ErrorActionPreference = 'SilentlyContinue'",
    "Start-Sleep -Milliseconds 1200",
    // Window first (exact image name; never the Dev channel's binary).
    "Get-Process -Name 'Black Eclipse' | Stop-Process -Force",
  ];
  if (owner && Number.isFinite(owner.pid)) {
    // The server tree. Safe now: this runner has already exited.
    lines.push(`& taskkill /F /T /PID ${Number(owner.pid)} | Out-Null`);
  }
  lines.push("Start-Sleep -Milliseconds 600");
  lines.push(`Start-Process -FilePath ${quotePowerShell(installerPath)}`);

  const dir = downloadsDir();
  fs.mkdirSync(dir, { recursive: true });
  const helper = path.join(dir, `apply-${JOB_ID}.ps1`);
  fs.writeFileSync(helper, `${lines.join("\n")}\n`, "utf8");
  pushLog(`[apply] handing off to ${path.basename(helper)}`);
  const child = spawn(
    "powershell",
    ["-NoProfile", "-ExecutionPolicy", "Bypass", "-File", helper],
    { cwd: dir, detached: true, stdio: "ignore", windowsHide: true },
  );
  child.unref();
}

/** Download+verify a signed installer and hand it to the OS installer. */
async function installFromInstaller() {
  const {
    readConfig,
    fetchManifest,
    isNewerVersion,
  } = require("./lib/update-verify");

  job.mode = "installer";
  setPhase("verifying", "Checking the signed release…");

  let config;
  try {
    config = readConfig();
  } catch (err) {
    fail(err && err.message ? err.message : "Update config is unavailable.");
    return;
  }

  let manifest;
  try {
    manifest = await fetchManifest(channel, config);
  } catch (err) {
    fail(err && err.message ? err.message : "Could not fetch the signed release.");
    return;
  }
  job.toVersion = manifest.version;

  if (!isNewerVersion(manifest.version, fromVersion)) {
    job.toVersion = fromVersion;
    finish("ready", "ready", `Nothing to install — this window is already on v${fromVersion}.`, null);
    return;
  }

  const platform = installerPlatform();
  const asset = manifest.installers && manifest.installers[platform];
  if (!asset) {
    fail(
      `v${manifest.version} has no signed ${platform} installer. ` +
        `Open the release page to update: ${manifest.notesUrl || "the GitHub releases page"}`,
    );
    return;
  }

  const extension = platform.startsWith("win32") ? ".exe" : "";
  const name = `BlackEclipse-Setup-${manifest.version}${extension}`;
  const dest = path.join(downloadsDir(), name);

  setPhase("downloading", `Downloading v${manifest.version}…`);
  pushLog(`[apply] downloading ${asset.url}`);
  let bytes;
  try {
    bytes = await downloadVerified(asset.url, dest, asset.sha256, asset.size);
  } catch (err) {
    fail(err && err.message ? err.message : "The installer download failed.");
    return;
  }
  pushLog(`[apply] verified sha256 ${asset.sha256} (${bytes} bytes)`);
  job.artifact = { path: dest, name, sha256: asset.sha256.toLowerCase(), bytes };

  setPhase("installing", "Opening the installer…");
  try {
    launchInstaller(dest);
  } catch (err) {
    fail(err && err.message ? err.message : "Could not open the installer.");
    return;
  }

  finish(
    "ready",
    "ready",
    `v${manifest.version} downloaded and verified. The installer is opening — follow its steps.`,
    null,
  );
}

async function main() {
  flush();
  pushLog(`[apply] staging ${channel} update (job ${JOB_ID})`);

  // A packaged install has no git tree. Use the signed installer it advertises
  // instead of pretending the checkout path can work.
  if (!isGitCheckout()) {
    job.mode = "installer";
    await installFromInstaller();
    return;
  }

  // If the app is holding its own native modules, it has to close before npm
  // can replace them. Give the window a moment to pick up this job first, so
  // the UI can say what is happening instead of silently losing its server.
  const { lockedNativeModules } = require("./lib/update-locks");
  if (lockedNativeModules(ROOT).length) {
    await sleep(2500);
    stoppedServer = closeRunningApp();
    if (!stoppedServer && lockedNativeModules(ROOT).length) {
      fail(
        "Eclipse is running and is using its own dependencies, so they cannot be replaced. " +
          "Quit Eclipse, then run `black update` in a terminal. Nothing was changed.",
      );
      return;
    }
  }

  const child = spawn(
    process.execPath,
    [
      path.join(ROOT, "scripts", "update.js"),
      "--yes",
      "--no-desktop",
      "--channel",
      channel,
      ...(runningVersion ? ["--running-version", runningVersion] : []),
    ],
    {
      cwd: ROOT,
      windowsHide: true,
      stdio: ["ignore", "pipe", "pipe"],
      env: { ...process.env, ECLIPSE_UPDATE_JOB: jobFile },
    },
  );

  let buffered = "";
  const consume = (chunk) => {
    buffered += chunk.toString("utf8");
    const lines = buffered.split(/\r?\n/);
    buffered = lines.pop() || "";
    for (const line of lines) onLine(line);
  };
  child.stdout.on("data", consume);
  child.stderr.on("data", consume);

  child.on("error", (err) => fail(`Could not start the updater: ${err.message}`));

  child.on("exit", (code) => {
    if (buffered) onLine(buffered);
    if (code === 0) {
      const version = job.toVersion || readVersion();
      if (!applied) {
        // The updater had nothing to do (already current, or not published).
        // Report it honestly instead of offering a restart that changes nothing.
        // `toVersion` is the RUNNING build, not the checkout on disk: a finished
        // job must never render as "v<newer disk version> is ready" for a window
        // that was not rebuilt.
        job.toVersion = fromVersion;
        finish(
          "ready",
          "ready",
          `Nothing to install — this window is already on v${fromVersion}.`,
          null,
        );
        reviveIfStopped();
        return;
      }
      if (!promote(stoppedServer, job.stagedDir || undefined)) return;
      // The promote relaunched the window on the new build.
      stoppedServer = false;
      finish(
        "ready",
        "ready",
        `v${version} is ready. Restart Eclipse to switch to it.`,
        null,
      );
      return;
    }
    const lastLine =
      [...job.log].reverse().find((line) => line.startsWith("[update]")) || "The updater failed.";
    fail(lastLine.replace(/^\[update\]\s*/, ""));
  });
}

main().catch((err) => {
  fail(err && err.message ? err.message : String(err));
});
