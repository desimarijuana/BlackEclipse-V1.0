#!/usr/bin/env node
// `npm run build` — serialized production build.
//
// `next build` deletes and rewrites `.next` in place. Two builds started at the
// same time (a terminal `npm run build` plus the desktop icon, or a Stable and a
// Dev build) corrupt each other's output, and the app then fails to start
// with no useful error — the "sometimes the icon just hangs" report. Every
// supported entry point now takes `.next-build.lock` first; this wrapper means
// the plain npm script does too.
//
// While waiting it prints who it is waiting for, once every 15s, so a slow
// machine does not look frozen.

const { build, buildInProgress } = require("./lib/server");

const t0 = Date.now();
const pending = buildInProgress();
if (pending && pending.pid !== process.pid) {
  console.log(`[build] a production build is already running (pid ${pending.pid}) — waiting for it…`);
}

try {
  const built = build();
  if (built) {
    console.log(`[build] done in ${((Date.now() - t0) / 1000).toFixed(0)}s`);
  } else {
    console.log("[build] the current source is already built — nothing to do");
  }
} catch (err) {
  console.error(`[build] failed: ${err && err.message ? err.message : err}`);
  process.exit(1);
}
