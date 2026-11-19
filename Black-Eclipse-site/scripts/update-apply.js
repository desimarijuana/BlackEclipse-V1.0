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
const path = require("path");
const crypto = require("crypto");
const { spawn, spawnSync } = require("child_process");

const ROOT = path.resolve(__dirname, "..");
const args = process.argv.slice(2);
const argValue = (name, fallback) => {
  const i = args.indexOf(`--${name}`);
  return i !== -1 && args[i + 1] ? args[i + 1] : fallback;
};

const channel = argValue("channel", "stable");
// The build always lands in `.next`, which is the Stable channel's build dir.
// The in-app path refuses the Dev channel rather than promoting the wrong app.
const desktopChannel = process.env.BE_DESKTOP_CHANNEL === "dev" ? "dev" : "stable";
const jobFile =
  argValue("job") || process.env.BE_UPDATE_JOB_FILE || path.join(ROOT, ".runtime", "update-job.json");

const LOG_TAIL = 80;
const JOB_ID = crypto.randomBytes(8).toString("hex");
const fromVersion = readVersion();

const job = {
  id: JOB_ID,
  status: "running",
  phase: "starting",
  message: "Checking the signed release…",
  fromVersion,
  toVersion: null,
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
  [/^\[update\] checking out /, "checkout", "Checking out the signed release…"],
  [/^\[update\] waiting for the native modules/, "installing", "Waiting for Eclipse to release its files…"],
  [/^\[update\] installing dependencies/, "installing", "Installing dependencies (slow)…"],
  [/^\[update\] building production bundle/, "building", "Building the new version (slow)…"],
  [/^\[update\] rolling back/, "building", "Update failed — rolling back…"],
  [/^\[desktop:refresh\]/, "building", "Preparing the new build…"],
];

function onLine(line) {
  pushLog(line);
  if (/^\[update\] (checking out|installing dependencies|building production bundle)/.test(line)) {
    applied = true;
  }
  for (const [pattern, phase, message] of PHASES) {
    if (pattern.test(line)) {
      // Never move backwards: a late "installed: v" line must not undo "building".
      const order = ["starting", "stopping", "verifying", "backing-up", "checkout", "installing", "building", "promoting"];
      if (order.indexOf(phase) > order.indexOf(job.phase)) setPhase(phase, message);
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
function promote(restart) {
  setPhase("promoting", "Publishing the new build…");
  const args = ["--no-build", "--channel", desktopChannel];
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

async function main() {
  flush();
  pushLog(`[apply] staging ${channel} update (job ${JOB_ID})`);

  // A packaged install has no repository for the verified updater to check out.
  // Say that plainly instead of letting it die inside `update.js`.
  if (!fs.existsSync(path.join(ROOT, ".git"))) {
    fail(
      "This installed build cannot update in place. Download the new release " +
        "from its release page and run the installer. Nothing was changed.",
    );
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
    [path.join(ROOT, "scripts", "update.js"), "--yes", "--no-desktop", "--channel", channel],
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
      const version = readVersion();
      if (!applied) {
        // The updater had nothing to do (already current, or not published).
        // Report it honestly instead of offering a restart that changes nothing.
        finish(
          "ready",
          "ready",
          `Nothing to install — Eclipse is already on v${version}.`,
          null,
        );
        reviveIfStopped();
        return;
      }
      if (!promote(stoppedServer)) return;
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
