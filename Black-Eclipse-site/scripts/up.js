#!/usr/bin/env node
// `npm run up` — one command to start the site fast.
//
// Production mode is the most optimized way to run locally — zero
// per-request compilation. This script makes it one step:
//
//   1. Leave an already-running server alone (another shell/tab opening the app
//      must not trigger a kill + cold boot); `--restart` opts into replacing it.
//   2. Otherwise free PORT (stale server / .next file locks)
//   3. Rebuild ONLY if source changed since the last successful build
//   4. `next start` — instant serving
//
// Use `npm run dev` when actively editing code (hot reload).
// Use `black eclipse` for the same thing from anywhere (after `npm link`).

const {
  isUp,
  killPort,
  needsBuild,
  build,
} = require("./lib/server");
const { runLocalHost } = require("./local-host");
const { PROD } = require("./lib/profiles");

const PORT = String(PROD.appPort);

function log(msg) {
  console.log(`[up] ${msg}`);
}

const restart = process.argv.includes("--restart");
isUp(PORT, 10_000).then((running) => {
  if (running && !restart) {
    log(`already running (HTTP ${running}) — leaving it up: http://blackeclipse`);
    log(`use "npm run up -- --restart" to force a rebuild/restart`);
    return;
  }
  start();
});

function start() {
  killPort(PORT);
  // Free this profile's harness port too: an orphaned uvicorn from a previous
  // production run would otherwise hold 8766 and fight the fresh spawn.
  killPort(PROD.harnessPort);
  if (needsBuild()) {
    log("building (this runs once; next starts are instant)...");
    const t0 = Date.now();
    build();
    log(`build done in ${((Date.now() - t0) / 1000).toFixed(0)}s`);
  } else {
    log("build is up to date — skipping");
  }
  log(`starting production server → blackeclipse (bound to 127.0.0.1)`);
  runLocalHost({ mode: "start", port: PORT });
}