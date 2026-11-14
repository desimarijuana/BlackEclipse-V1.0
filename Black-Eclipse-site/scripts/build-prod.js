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
// It also refuses to run while a desktop channel is live. The window is safe
// (it serves a pinned copy), but a build started under a running app starves the
// Python runtime's cold start and leaves `.next` without a BUILD_ID until it
// finishes. The managed paths — `npm run desktop:refresh` (via
// scripts/desktop-build.js) and `black update` — set
// BE_ALLOW_BUILD_WHILE_RUNNING=1, because they own the pin and the restart.
//
// While waiting for the lock it prints who it is waiting for, once every 15s, so
// a slow machine does not look frozen.

const { build, buildInProgress, isUp } = require("./lib/server");
const { STABLE, DEV } = require("./lib/channels");
const { readOwner, pidAlive, shellPids, shellPathFor } = require("./lib/desktop-process");
const {
  allowBuildWhileRunning,
  shouldRefuseBuild,
  refusalMessage,
} = require("./lib/build-guard");

/**
 * Channels with a live app: an owner marker we wrote, an HTTP answer, or a
 * running window process.
 *
 * The window check matters because the app can be alive while its server is
 * briefly down (a Tauri-initiated restart): a build started in that gap still
 * saturates the CPU when the app comes back, so "port is free" is not proof that
 * nothing is running.
 */
async function detectLiveChannels() {
  const live = [];
  for (const channel of [STABLE, DEV]) {
    const owner = readOwner(channel);
    const owned = Boolean(owner && pidAlive(owner.pid));
    let answers = false;
    try {
      answers = Boolean(await isUp(String(channel.appPort), 2_500));
    } catch {
      /* a probe failure is not evidence of a live app */
    }
    const windows = shellPids(shellPathFor(channel));
    if (owned || answers || windows.length > 0) {
      live.push({
        id: channel.id,
        label: channel.label,
        appPort: channel.appPort,
        pid: owned ? owner.pid : undefined,
        windowPids: windows,
      });
    }
  }
  return live;
}

async function main() {
  const allow = allowBuildWhileRunning(process.env.BE_ALLOW_BUILD_WHILE_RUNNING);
  const live = await detectLiveChannels();
  if (shouldRefuseBuild({ live, allow })) {
    console.log(refusalMessage(live));
    process.exit(1);
  }

  const t0 = Date.now();
  const pending = buildInProgress();
  if (pending && pending.pid !== process.pid) {
    console.log(`[build] a production build is already running (pid ${pending.pid}) — waiting for it…`);
  }

  const built = build();
  if (built) {
    console.log(`[build] done in ${((Date.now() - t0) / 1000).toFixed(0)}s`);
  } else {
    console.log("[build] the current source is already built — nothing to do");
  }
}

main().catch((err) => {
  console.error(`[build] failed: ${err && err.message ? err.message : err}`);
  process.exit(1);
});
