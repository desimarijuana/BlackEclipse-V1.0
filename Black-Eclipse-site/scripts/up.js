#!/usr/bin/env node
// `npm run up` — one command to start the site fast.
//
// Production mode is the most optimized way to run locally — zero
// per-request compilation. This script makes it one step:
//
//   1. Kill whatever is on PORT (frees .next file locks)
//   2. Rebuild ONLY if source changed since the last successful build
//   3. `next start` — instant serving
//
// Use `npm run dev` when actively editing code (hot reload).
// Use `black eclipse` for the same thing from anywhere (after `npm link`).

const {
  killPort,
  needsBuild,
  build,
  startServer,
} = require("./lib/server");

const PORT = process.env.PORT || "3000";

function log(msg) {
  console.log(`[up] ${msg}`);
}

killPort(PORT);
if (needsBuild()) {
  log("building (this runs once; next starts are instant)...");
  const t0 = Date.now();
  build();
  log(`build done in ${((Date.now() - t0) / 1000).toFixed(0)}s`);
} else {
  log("build is up to date — skipping");
}
log(`starting production server on http://localhost:${PORT}`);
startServer(PORT);