#!/usr/bin/env node
// ── `black update` ───────────────────────────────────────────────────────────
// Checks for a newer SIGNED release and, with consent, applies it safely.
//
//   black update              check, then ask before applying
//   black update --check      check only (no changes)
//   black update --yes        apply without prompting
//   black update --restart    also restart the browser production server (3105)
//   black update --no-desktop skip the desktop refresh (web-only machines)
//   black update --channel beta
//
// Desktop first: after a successful build the native app is re-pinned and
// restarted (scripts/desktop-refresh.js) BEFORE anything web-facing is
// considered. The browser production server on 3105 is secondary and only
// restarts when --restart is passed. The refresh is a safe no-op when the
// desktop is not installed or is a packaged (non-bridged) install.
//
// Safety order (do not reorder):
//   1. Manifest signature verifies against config/update-signing-key.pub.
//   2. Working tree is clean, so nothing of the user's is overwritten.
//   3. The release tag's commit SHA equals the signed manifest's commit.
//   4. jdds.db is backed up BEFORE checkout.
//   5. Build runs; ANY failure rolls the checkout back and rebuilds the old one.
//
// This never downloads an executable and never runs remote code. It checks out
// a signed-off git tag from the repository the user already cloned.

"use strict";

const fs = require("fs");
const path = require("path");
const { execFileSync, execSync, spawn } = require("child_process");
const {
  ROOT,
  CHANNELS,
  readConfig,
  fetchManifest,
  compareVersions,
  isNewerVersion,
} = require("./lib/update-verify");

const pkg = JSON.parse(fs.readFileSync(path.join(ROOT, "package.json"), "utf8"));
const args = process.argv.slice(2);
const hasFlag = (name) => args.includes(`--${name}`);
const argValue = (name, fallback) => {
  const i = args.indexOf(`--${name}`);
  return i !== -1 && args[i + 1] ? args[i + 1] : fallback;
};

const channel = argValue("channel", "stable");
const checkOnly = hasFlag("check");
const assumeYes = hasFlag("yes") || hasFlag("y");
const restart = hasFlag("restart");
const noDesktop = hasFlag("no-desktop");
const skipBackup = hasFlag("no-backup");

function log(message) {
  console.log(`[update] ${message}`);
}

function fail(message) {
  console.error(`[update] ${message}`);
  process.exit(1);
}

function run(command, commandArgs, options = {}) {
  execFileSync(command, commandArgs, { cwd: ROOT, stdio: "inherit", ...options });
}

function runShell(command) {
  execSync(command, { cwd: ROOT, stdio: "inherit", env: process.env });
}

function git(commandArgs, options = {}) {
  return execFileSync("git", commandArgs, {
    cwd: ROOT,
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
    ...options,
  }).trim();
}

function workingTreeDirty() {
  try {
    return git(["status", "--porcelain"]) !== "";
  } catch {
    return true;
  }
}

function ask(question) {
  if (!process.stdin.isTTY) {
    fail("Not a terminal. Re-run with --yes to apply the update non-interactively.");
  }
  const readline = require("readline").createInterface({
    input: process.stdin,
    output: process.stdout,
  });
  return new Promise((resolve) => {
    readline.question(question, (answer) => {
      readline.close();
      resolve(/^y(es)?$/i.test(answer.trim()));
    });
  });
}

function backupDatabase() {
  const dbPath = path.join(ROOT, "jdds.db");
  if (!fs.existsSync(dbPath)) {
    log("no jdds.db yet — nothing to back up");
    return null;
  }
  if (skipBackup) {
    log("WARNING: --no-backup set; continuing without a database backup");
    return null;
  }
  log("backing up jdds.db before touching anything…");
  run(process.execPath, [path.join(ROOT, "scripts", "db-guard.js"), "backup"]);
  return path.join(ROOT, "backups");
}

// Desktop first: the native window is the primary front door, so it gets the
// new build before any web server is touched. `desktop-refresh.js` owns the
// safe sequence (build if needed, re-pin the immutable copy, restart only the
// server this install started, reopen the shell) and no-ops with an
// explanation when the desktop is absent or a packaged install.
function refreshDesktop() {
  if (noDesktop) {
    log("desktop refresh skipped (--no-desktop)");
    return false;
  }
  log("desktop-first: re-pinning and restarting the native app…");
  try {
    run(process.execPath, [path.join(ROOT, "scripts", "desktop-refresh.js")]);
    log("desktop is on the new build");
    return true;
  } catch {
    log('desktop refresh did not complete — the build is still applied; run "npm run desktop:refresh" to retry');
    return false;
  }
}

function restartProduction() {
  try {
    const { PROD } = require("./lib/profiles");
    const { killPort } = require("./lib/server");
    killPort(String(PROD.appPort));
  } catch (err) {
    log(`could not stop the running server automatically (${err.message}); stop it yourself`);
    return;
  }
  const child = spawn(process.execPath, [path.join(ROOT, "bin", "black.js")], {
    cwd: ROOT,
    detached: true,
    stdio: "ignore",
    env: process.env,
  });
  child.unref();
  log("production server restarting in the background");
}

async function main() {
  if (!CHANNELS.includes(channel)) fail(`unknown channel "${channel}" (use ${CHANNELS.join(" | ")})`);
  if (process.env.ECLIPSE_UPDATES_DISABLED === "1") fail("update checks are disabled by ECLIPSE_UPDATES_DISABLED=1");

  const current = pkg.version;
  log(`installed: v${current} (channel: ${channel})`);

  let config;
  try {
    config = readConfig();
  } catch (err) {
    fail(err.message);
  }

  if (!config.published) {
    log("updates are not published yet (config/updates.json → published: false)");
    log("nothing to check — this is the private-development state");
    return;
  }

  let manifest;
  try {
    manifest = await fetchManifest(channel, config);
  } catch (err) {
    fail(err.message);
  }

  log(`latest signed release: v${manifest.version}`);
  if (!isNewerVersion(manifest.version, current)) {
    log(`already up to date (v${current})`);
    return;
  }

  log(`commit: ${manifest.commit}`);
  if (manifest.notesUrl) log(`notes:  ${manifest.notesUrl}`);

  if (checkOnly) {
    log(`update available: v${current} -> v${manifest.version}`);
    return;
  }

  if (workingTreeDirty()) {
    fail(
      "the working tree has uncommitted changes. Commit or stash them first — updating would " +
        "otherwise overwrite local edits.",
    );
  }

  if (!assumeYes) {
    const ok = await ask(`\nUpdate v${current} -> v${manifest.version}? [y/N] `);
    if (!ok) {
      log("cancelled — nothing changed");
      return;
    }
  }

  // ── Integrity: the signed commit must be the tag's commit ──────────────────
  const tag = `v${manifest.version}`;
  log(`fetching release tag ${tag}…`);
  run("git", ["fetch", "--tags", "--force", "origin"]);
  let tagCommit;
  try {
    tagCommit = git(["rev-parse", `refs/tags/${tag}^{commit}`]);
  } catch {
    fail(`tag ${tag} does not exist in this clone. Check that the release was published.`);
  }
  if (tagCommit !== manifest.commit) {
    fail(
      `tag ${tag} points at ${tagCommit}, but the signed manifest names ${manifest.commit}. ` +
        "Refusing to update — the tag may have been moved.",
    );
  }
  log(`tag verified: ${tag} -> ${tagCommit.slice(0, 12)}`);

  const previousHead = git(["rev-parse", "HEAD"]);
  const backupDir = backupDatabase();

  let applied = false;
  try {
    log(`checking out ${tag}…`);
    run("git", ["-c", "advice.detachedHead=false", "checkout", "--detach", tag]);
    applied = true;

    log("installing dependencies (npm ci)…");
    runShell("npm ci --no-audit --no-fund");

    log("building production bundle…");
    runShell("npm run build");

    log(`updated v${current} -> v${manifest.version}`);
    if (backupDir) log(`database backup: ${backupDir}`);
    const desktopReady = refreshDesktop();
    if (restart) restartProduction();
    else if (desktopReady) {
      log('browser production server (3105) left alone — run "npm run up" only if you need it');
    } else {
      log('start it with "black" (or "npm run up") to load the new build');
    }
  } catch (err) {
    console.error("");
    console.error(`[update] FAILED: ${err && err.message ? err.message : err}`);
    if (applied) {
      console.error(`[update] rolling back to ${previousHead.slice(0, 12)}…`);
      try {
        run("git", ["-c", "advice.detachedHead=false", "checkout", "--detach", previousHead]);
        runShell("npm ci --no-audit --no-fund");
        runShell("npm run build");
        console.error("[update] rollback complete — you are back on the previous build");
      } catch {
        console.error("[update] rollback build also failed. Your old source is checked out; run");
        console.error('         "npm install && npm run build" manually before starting Eclipse.');
      }
      if (backupDir) {
        console.error(`[update] database backup was not touched: ${backupDir}`);
      }
    }
    process.exit(1);
  }
}

main().catch((err) => {
  console.error("[update] unexpected error:", err && err.message ? err.message : err);
  process.exit(1);
});
