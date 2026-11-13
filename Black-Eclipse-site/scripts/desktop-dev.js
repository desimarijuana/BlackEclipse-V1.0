#!/usr/bin/env node
// `npm run desktop:dev` — the Dev channel.
//
// Dev is a SECOND desktop app (its own identifier, port 3101, harness 8768,
// build `.next-desktop-dev`, isolated data) so you can test a build while
// Stable keeps running on 3100.
//
// Sequence:
//   1. build the dev shell if it does not exist (separate Tauri identifier),
//   2. build the dev payload only when the source changed,
//   3. prepare isolated dev data (a one-time JDdS snapshot),
//   4. stop only THIS channel's window/server, then relaunch it.
//
// Flags: --no-build (use the existing payload) · --no-shell (use the existing
// shell binary)

const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");

const { DEV } = require("./lib/channels");
const { prepareChannelData } = require("./lib/desktop-data");
const {
  ROOT,
  devShellPath,
  stopShell,
  stopOwnedServer,
  launchShell,
} = require("./lib/desktop-process");

const noBuild = process.argv.includes("--no-build");
const noShell = process.argv.includes("--no-shell");

function log(message) {
  console.log(`[desktop:dev] ${message}`);
}

function run(script, args) {
  const result = spawnSync(process.execPath, [path.join(ROOT, "scripts", script), ...args], {
    cwd: ROOT,
    stdio: "inherit",
    windowsHide: true,
  });
  return result.status === 0;
}

function main() {
  if (!noShell && !fs.existsSync(devShellPath())) {
    log("Dev shell not built yet — building it once (separate app identity)…");
    if (!run("desktop-build-shell.js", [])) process.exit(1);
  }
  if (!fs.existsSync(devShellPath())) {
    console.error(`[desktop:dev] Dev shell not found: ${devShellPath()}`);
    console.error('[desktop:dev] run "npm run desktop:build:dev-shell" first');
    process.exit(1);
  }

  if (!noBuild) {
    log("checking the Dev payload…");
    if (!run("desktop-build.js", ["--channel", "dev", "--if-needed"])) process.exit(1);
  }

  try {
    const prepared = prepareChannelData(DEV, ROOT);
    if (prepared.prepared) log(`isolated dev data seeded (${prepared.path})`);
  } catch (err) {
    log(`dev data preparation failed: ${err && err.message ? err.message : err}`);
  }

  // Single-instance would only focus the old window, which is still serving the
  // old payload. A dev launch is an explicit "show me the new build", so rotate.
  const stopped = stopShell(DEV);
  if (stopped.length) log(`stopped the previous Dev window (pid ${stopped.join(", ")})`);
  stopOwnedServer(DEV);

  const launched = launchShell(DEV);
  if (!launched.launched) {
    console.error(`[desktop:dev] could not launch ${launched.exe}`);
    process.exit(1);
  }
  log(`Dev window launched on http://127.0.0.1:${DEV.appPort} (harness ${DEV.harnessPort})`);
  log(`data: ${DEV.dataDir}`);
}

main();
