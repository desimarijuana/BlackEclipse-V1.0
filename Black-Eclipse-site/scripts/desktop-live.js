#!/usr/bin/env node
// `npm run desktop:live` — the channel window on `next dev`.
//
// Why: the desktop window serves an immutable pinned build, so editing `src/`
// changes nothing until the build runs, the result is promoted and the window
// reopens (`npm run desktop:refresh`). Live mode swaps `next start` for
// `next dev` behind the SAME native window, so saving a file hot-reloads the
// page. It is the iteration loop, never a release.
//
// What it does:
//   1. make the channel able to run THIS checkout (bridge the installed shell,
//      build the Dev shell once if it is missing),
//   2. note when the Rust shell is older than its source (UI-only hot reload),
//   3. stop THIS channel's window and the server tree it owns,
//   4. relaunch it with BE_DESKTOP_LIVE=1 (see scripts/desktop-server.js).
//
// Flags: --channel dev (default stable)

const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");

const { channelFor } = require("./lib/channels");
const {
  ROOT,
  INSTALL,
  installedShellPath,
  devShellPath,
  shellPathFor,
  stopShell,
  stopOwnedServer,
  launchShell,
  waitForShellExit,
} = require("./lib/desktop-process");

const argv = process.argv.slice(2);
const channel = channelFor(
  argv.indexOf("--channel") >= 0 ? argv[argv.indexOf("--channel") + 1] : "stable",
);

// Rust source whose age decides whether the window binary is stale. Build
// output (target*) and generated files are never inputs.
const TAURI_ROOT = path.join(ROOT, "desktop", "src-tauri");
const TAURI_SKIP = new Set(["target", "target-dev", "gen", "bin", "icons"]);

function log(message) {
  console.log(`[desktop:live] ${message}`);
}

function fail(message) {
  console.error(`[desktop:live] ${message}`);
  process.exit(1);
}

function runScript(name) {
  const result = spawnSync(process.execPath, [path.join(__dirname, name)], {
    cwd: ROOT,
    stdio: "inherit",
    windowsHide: true,
  });
  return result.status === 0;
}

// The installed shell prefers its own frozen payload under `<install>\app`, so
// BE_DESKTOP_LIVE would never reach this repository's bootstrap. The bridge is
// what points the installed shell at the checkout.
function isBridged() {
  try {
    return fs
      .readFileSync(path.join(INSTALL, "app", "scripts", "desktop-server.js"), "utf8")
      .includes("desktop-dev-bridge.js");
  } catch {
    return false;
  }
}

function newestMtime(dir, newest = 0) {
  let entries;
  try {
    entries = fs.readdirSync(dir, { withFileTypes: true });
  } catch {
    return newest;
  }
  for (const entry of entries) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      if (TAURI_SKIP.has(entry.name)) continue;
      newest = newestMtime(full, newest);
    } else {
      try {
        newest = Math.max(newest, fs.statSync(full).mtimeMs);
      } catch {}
    }
  }
  return newest;
}

/** Does the window binary predate Rust source you are actually editing? */
function shellIsStale() {
  try {
    const exe = fs.statSync(shellPathFor(channel)).mtimeMs;
    if (newestMtime(TAURI_ROOT) <= exe) return false;
    // A checkout is almost always newer than an installed release, so mtimes
    // alone would warn on every launch. Only warn when Rust is DIRTY here -
    // i.e. someone is editing the shell right now.
    const status = spawnSync("git", ["status", "--porcelain", "--", "desktop/src-tauri"], {
      cwd: ROOT,
      encoding: "utf8",
      windowsHide: true,
    });
    return Boolean(status.stdout && status.stdout.trim());
  } catch {
    return false;
  }
}

function main() {
  if (channel.id === "stable") {
    if (!fs.existsSync(installedShellPath())) {
      fail(
        `the Stable desktop app is not installed (${installedShellPath()}).\n` +
          '  Run "npm run desktop:installer", or use "npm run desktop:live -- --channel dev".',
      );
    }
    if (!isBridged()) {
      // Bridging is exactly what `npm run desktop:dev-bridge` is for, and it is
      // reversible (the bundled payload is renamed, never deleted), so do it
      // rather than making the user read a refusal.
      log("the installed app still serves its bundled payload - bridging it to this checkout once…");
      if (!runScript("desktop-dev-bridge.js") || !isBridged()) {
        fail(
          "could not bridge the installed app to this checkout.\n" +
            "  Resolve the message above, or run \"npm run desktop:dev-bridge\" by hand.",
        );
      }
    }
  } else if (!fs.existsSync(devShellPath())) {
    log("the Dev shell is not built yet - building it once (its own app identity)…");
    if (!runScript("desktop-build-shell.js") || !fs.existsSync(devShellPath())) {
      fail('the Dev shell build failed. Run "npm run desktop:build:dev-shell" and read its output.');
    }
  }

  if (shellIsStale()) {
    // Not fatal: live mode serves the Next.js UI, which is where almost all
    // iteration happens. A compiled binary cannot hot-reload, so name the fix.
    log("note: desktop/src-tauri is newer than the window binary - UI edits hot-reload, but Rust changes need a new shell:");
    log(
      channel.id === "dev"
        ? '  npm run desktop:build:dev-shell, then run this command again'
        : '  npm run desktop:installer (or iterate on Rust in the Dev channel)',
    );
  }

  // A live launch is an explicit "show me the code in the tree", so the old
  // window (serving the old code) must not be focused by single-instance.
  const stopped = stopShell(channel);
  if (stopped.length) {
    log(`stopped the previous ${channel.label} window (pid ${stopped.join(", ")})`);
    // Single-instance forwards a launch to the OLD process while it is still
    // exiting; waiting is what makes the relaunch run its own bootstrap.
    if (!waitForShellExit(channel)) log("the previous window is taking a while to exit - launching anyway");
  }
  if (stopOwnedServer(channel)) log(`stopped the ${channel.label} server it owned`);

  const launched = launchShell(channel, { BE_DESKTOP_LIVE: "1" });
  if (!launched.launched) {
    fail(`could not launch ${launched.exe}${launched.reason ? ` (${launched.reason})` : ""}`);
  }

  log(`${channel.label} window launching in LIVE mode - http://127.0.0.1:${channel.appPort}`);
  log(`root  : ${ROOT}`);
  log(`dist  : .next-live-${channel.id} (never .next, so a live session cannot break a promoted build)`);
  log("saving a file under src/ hot-reloads the open window - no build, no re-pin, no relaunch.");
  log('leave live mode with "npm run desktop:refresh" (Stable) or "npm run desktop:dev" (Dev).');
}

main();
