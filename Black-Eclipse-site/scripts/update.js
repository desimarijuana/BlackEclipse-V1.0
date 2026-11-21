#!/usr/bin/env node
// ── `black update` ───────────────────────────────────────────────────────────
// Checks for a newer SIGNED release and, with consent, applies it safely.
//
//   black update              check, then ask before applying
//   black update --check      check only (no changes)
//   black update --yes        apply without prompting
//   black update --restart    restart the desktop app after applying
//   black update --no-desktop stage only (the in-app runner promotes)
//   black update --git        force checkout + build (contributor path)
//   black update --channel beta
//
// Desktop first: after a successful build the native app is re-pinned and
// restarted (scripts/desktop-refresh.js). There is no browser server to
// consider — the product is the desktop app. The refresh is a safe no-op when
// the desktop is not installed or is a packaged (non-bridged) install.
//
// TWO APPLICATION PATHS, one verification chain:
//
//   1. Prebuilt (normal). The signed manifest advertises `builds`, the release's
//      COMPILED `.next`. `scripts/lib/build-artifact.js` downloads it, verifies
//      the signed size + sha256, extracts it into `.runtime/updates`, and
//      `desktop-promote.js --from` swaps it in atomically. git is never read,
//      nothing is compiled, and a dirty working tree is irrelevant — every
//      release touches the changelog, so that used to block every update.
//   2. Git fallback (manifests through v0.4.21, or `--git`). The old path:
//      verify the tag, require a clean tree, checkout, `npm ci`, build.
//
// Shared safety order (do not reorder):
//   1. Manifest signature verifies against config/update-signing-key.pub.
//   2. Every artifact byte matches the signed size + sha256.
//   3. For the git path: working tree clean, tag commit == signed commit,
//      jdds.db backed up BEFORE checkout, build failure rolls back.
//
// This never downloads an executable and never runs remote code. The packaged
// installer path lives in scripts/update-apply.js.

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
  parseVersion,
} = require("./lib/update-verify");
const { assetForPlatform, downloadVerified, unpackBuild, lockHash } = require("./lib/build-artifact");

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
// Escape hatch: restore the old "check out the tag and build it here" path even
// when the release advertises a prebuilt build. Needed by a contributor who
// wants the signed tag in their own tree (detached HEAD).
const forceGit = hasFlag("git");

// The version the RUNNING app is serving, when the caller knows it (the in-app
// updater does). It is not always `package.json` on disk: a checkout can be
// ahead of the build the window is pinned to (or the other way round), and a
// self-update is defined by what the user is actually running. Falling back to
// the on-disk version keeps `black update` unchanged.
const runningVersionArg = argValue("running-version", process.env.BE_UPDATE_RUNNING_VERSION);
const runningVersion =
  runningVersionArg && parseVersion(runningVersionArg) ? runningVersionArg : pkg.version;

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

/** The uncommitted paths (`git status --porcelain`), or ["<git failed>"] . */
function dirtyPaths() {
  try {
    const out = git(["status", "--porcelain"]);
    return out ? out.split(/\r?\n/).filter(Boolean) : [];
  } catch {
    return ["<git status failed>"];
  }
}

/**
 * The refusal has to be actionable, because a dirty tree is the most common
 * reason an update "does nothing". Two states look identical to the user but
 * need different answers:
 *   * A developer tree already AT/PAST the signed release. There is nothing to
 *     fetch, and `git checkout <tag>` would move it backwards — the running app
 *     is just a stale pinned build, so `npm run desktop:refresh` is the fix.
 *   * An ordinary install behind the release: commit/stash, then retry.
 */
function dirtyTreeMessage(paths, manifest) {
  const sample = paths
    .slice(0, 3)
    .map((line) => line.replace(/^..\s+/, ""))
    .join(", ");
  const more = paths.length > 3 ? ` and ${paths.length - 3} more` : "";
  const ahead = compareVersions(pkg.version, manifest.version) >= 0;
  const hint = ahead
    ? `This checkout is already on v${pkg.version} (the signed release is v${manifest.version}), so ` +
      "the window is just serving an older pinned build. Commit or stash, then run " +
      "`npm run desktop:refresh` to rebuild and re-pin it — no git checkout is involved."
    : "Commit or stash them, then run `black update` again.";
  return (
    `the working tree has ${paths.length} uncommitted change(s) (${sample}${more}), so updating would ` +
    `mix your edits into the release build. ${hint}`
  );
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

// ── Dependency safety ───────────────────────────────────────────────────────
// `npm ci` deletes node_modules before it installs. If the running app holds a
// native module, that delete fails halfway and the install is destroyed. Check
// first, wait or close the app we own, and only then let npm touch the tree.
function releaseDependencies() {
  const { lockedNativeModules, waitForNativeUnlock, isAncestorOf } = require("./lib/update-locks");
  const locked = lockedNativeModules(ROOT);
  if (!locked.length) return;

  log(`${locked.length} native module(s) are in use by a running process`);
  if (!noDesktop) {
    const { channelFor } = require("./lib/channels");
    const { readOwner, stopOwnedServer } = require("./lib/desktop-process");
    const target = channelFor(channel);
    const owner = readOwner(target);
    // Only stop a server we did not launch ourselves: kill-tree follows parent
    // links, so an updater spawned by that server would die with it.
    if (owner && !isAncestorOf(owner.pid, process.pid)) {
      log("closing the running app so its dependencies can be replaced (it reopens after the build)");
      stopOwnedServer(target);
    }
  }

  log("waiting for the native modules to be released…");
  if (!waitForNativeUnlock(ROOT, 30000)) {
    throw new Error(
      "Eclipse is still holding its native dependencies. Quit Eclipse and run `black update` " +
        "again — nothing was installed or deleted, and your current build is intact.",
    );
  }
}

function installDependencies() {
  try {
    runShell("npm ci --no-audit --no-fund");
  } catch (err) {
    // A lock can appear between the probe and the write (an antivirus scan, a
    // just-started build). npm ci has already emptied node_modules by then, so
    // a retry is the difference between a recovered update and a broken app.
    log("dependency install failed — waiting for file locks, then retrying once…");
    releaseDependencies();
    runShell("npm ci --no-audit --no-fund");
  }
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

// The updater builds the new tag FIRST and refreshes the desktop afterwards, so
// the app being up is expected. `build-prod.js` refuses a plain `npm run build`
// while a channel is live; this is the managed path and owns the restart.
process.env.BE_ALLOW_BUILD_WHILE_RUNNING = "1";

// ── Prebuilt build mode ─────────────────────────────────────────────────────
// The normal path. The release publishes the COMPILED `.next` as a signed
// artifact, so an update is: verify the manifest, download, verify the bytes,
// extract, validate, promote. No git checkout, no `npm ci`, no local build —
// which is why an uncommitted changelog can no longer block an update.
//
// This mirrors how shipped desktop apps update (Tauri updater, VS Code,
// electron-updater, OpenCode): the vendor ships an artifact, the client swaps
// it atomically and restarts. Building the release on the user's machine was
// the design flaw.
function updatesDir() {
  return path.join(ROOT, ".runtime", "updates");
}

function promotePrebuilt(buildDir) {
  log("promoting the verified build…");
  run(process.execPath, [
    path.join(ROOT, "scripts", "desktop-promote.js"),
    "--channel",
    channel,
    "--from",
    buildDir,
  ]);
}

async function applyPrebuilt(manifest, { key, asset }, current) {
  log(`mode: signed prebuilt build (${key}) — no checkout, no local compile`);
  log("downloading the verified build…");

  const dest = path.join(updatesDir(), `BlackEclipse-Build-${manifest.version}-${key}.zip`);
  // A long download must keep talking, or the in-app job reads as dead after
  // five minutes without a heartbeat.
  let lastBeat = 0;
  const onBeat = () => {
    if (Date.now() - lastBeat < 20000) return;
    lastBeat = Date.now();
    log("still downloading…");
  };

  let downloaded;
  try {
    downloaded = await downloadVerified(asset.url, dest, {
      sha256: asset.sha256,
      size: asset.size,
      onBeat,
    });
  } catch (err) {
    fail(err && err.message ? err.message : "The build download failed.");
  }
  log(`checksum verified (${downloaded.bytes} bytes, sha256 ${asset.sha256.slice(0, 12)}…)`);

  log("extracting the verified build…");
  const stage = path.join(updatesDir(), `stage-${manifest.version}-${key}`);
  let build;
  try {
    build = unpackBuild(dest, stage, { buildId: asset.buildId });
  } catch (err) {
    fail(err && err.message ? err.message : "The downloaded build could not be unpacked.");
  }
  log(`build validated: ${build.buildId}`);

  // The artifact was compiled against the release's lockfile. If dependencies
  // moved, install them first — otherwise `next start` runs a build whose
  // modules are absent. Rare, and the only time this path touches node_modules.
  if (asset.lockHash) {
    const local = lockHash(ROOT);
    if (local && local !== asset.lockHash) {
      log("this release changed dependencies — installing them first…");
      releaseDependencies();
      installDependencies();
    }
  }

  if (noDesktop) {
    // In-app staging: the runner promotes (and owns the restart), exactly like
    // the git path. The CLI without --no-desktop promotes right here.
    log(`staged release: v${manifest.version}`);
    log(`build staged: ${build.buildDir}`);
    return;
  }

  promotePrebuilt(build.buildDir);
  log(`updated v${current} -> v${manifest.version}`);
}

async function main() {
  if (!CHANNELS.includes(channel)) fail(`unknown channel "${channel}" (use ${CHANNELS.join(" | ")})`);
  if (process.env.ECLIPSE_UPDATES_DISABLED === "1") fail("update checks are disabled by ECLIPSE_UPDATES_DISABLED=1");

  const current = runningVersion;
  log(
    `installed: v${current} (channel: ${channel})${
      current !== pkg.version ? ` · checkout on v${pkg.version}` : ""
    }`,
  );

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

  // Prefer the signed prebuilt build. Only fall back to checkout+build when the
  // release advertises none (every manifest through v0.4.21) or `--git` is set.
  const platform = `${process.platform}-${process.arch}`;
  const prebuilt = forceGit ? null : assetForPlatform(manifest.builds, platform);
  if (prebuilt) {
    await applyPrebuilt(manifest, prebuilt, current);
    return;
  }
  if (forceGit) {
    log("--git: using the checkout + build path");
  } else {
    log("this release advertises no prebuilt build — falling back to checkout + build");
  }

  const dirty = dirtyPaths();
  if (dirty.length) {
    fail(dirtyTreeMessage(dirty, manifest));
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
  // True once node_modules has actually been replaced. Rollback uses it: if the
  // install never ran, the old dependencies and the old build are still intact
  // and re-running `npm ci` could only do damage.
  let reinstalled = false;
  try {
    log(`checking out ${tag}…`);
    run("git", ["-c", "advice.detachedHead=false", "checkout", "--detach", tag]);
    applied = true;

    releaseDependencies();

    log("installing dependencies (npm ci)…");
    installDependencies();
    reinstalled = true;

    log("building production bundle…");
    runShell("npm run build");

    log(`updated v${current} -> v${manifest.version}`);
    if (backupDir) log(`database backup: ${backupDir}`);
    const desktopReady = refreshDesktop();
    if (restart && !desktopReady) {
      log('run "npm run desktop:refresh" to reopen the app on the new build');
    } else if (!desktopReady) {
      log('start it with "black" (opens the desktop app)');
    }
  } catch (err) {
    console.error("");
    console.error(`[update] FAILED: ${err && err.message ? err.message : err}`);
    if (applied) {
      console.error(`[update] rolling back to ${previousHead.slice(0, 12)}…`);
      try {
        run("git", ["-c", "advice.detachedHead=false", "checkout", "--detach", previousHead]);
        if (!reinstalled) {
          console.error("[update] dependencies were never replaced; the previous build is still intact");
        } else {
          runShell("npm ci --no-audit --no-fund");
          runShell("npm run build");
          console.error("[update] rollback complete — you are back on the previous build");
        }
      } catch {
        console.error("[update] rollback build failed. Your old source is checked out; run");
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
