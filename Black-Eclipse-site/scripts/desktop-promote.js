#!/usr/bin/env node
// `npm run desktop:promote` — atomically make a completed build the channel's
// current release, with a rollback target.
//
//   node scripts/desktop-promote.js                     # promote Stable (.next)
//   node scripts/desktop-promote.js --channel dev       # promote Dev payload
//   node scripts/desktop-promote.js --rollback          # flip to the previous release
//
// Safety contract:
//   * never promotes while another build is running;
//   * copies into a temporary directory and renames, so a partial copy can
//     never become current;
//   * validates the copied build (BUILD_ID, routes manifest, server + static,
//     per-build static manifest) BEFORE moving the pointer;
//   * keeps the previous release and never deletes user data;
//   * restarts only the target channel's own window/server.

const fs = require("fs");
const path = require("path");

const { channelFor } = require("./lib/channels");
const { buildInProgress } = require("./lib/server");
const {
  ROOT,
  readBuildId,
  buildLooksComplete,
  copyRuntime,
  readPointer,
  writePointer,
} = require("./lib/desktop-release");
const {
  shellPathFor,
  stopShell,
  stopOwnedServer,
  launchShell,
} = require("./lib/desktop-process");

function argValue(flag) {
  const i = process.argv.indexOf(flag);
  return i >= 0 ? process.argv[i + 1] : undefined;
}

const rollback = process.argv.includes("--rollback");
const channel = channelFor(argValue("--channel") || "stable");
// An explicit source build. `--from .next-desktop-dev` lets a verified Dev
// build serve Stable without a second identical compile. Omitted: the channel's
// own build dir.
const fromArg = argValue("--from");

function log(message) {
  console.log(`[desktop:promote:${channel.id}] ${message}`);
}

function fail(message) {
  console.error(`[desktop:promote:${channel.id}] ${message}`);
  process.exit(1);
}

function relative(from) {
  return path.relative(ROOT, from).split(path.sep).join("/");
}

function pointerInfo(dist) {
  return {
    dir: relative(dist),
    buildId: readBuildId(dist),
    channel: channel.id,
    promotedAt: new Date().toISOString(),
  };
}

async function waitPortFree(port, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      await fetch(`http://127.0.0.1:${port}/`, {
        redirect: "manual",
        signal: AbortSignal.timeout(1200),
      });
    } catch {
      return true;
    }
    await new Promise((r) => setTimeout(r, 300));
  }
  return false;
}

async function restart() {
  const exe = shellPathFor(channel);
  if (!fs.existsSync(exe)) {
    log(`window binary not found: ${exe}`);
    log("the release pointer is updated; launch the channel when the binary is available");
    return;
  }
  log("stopping this channel's window and server…");
  const pids = stopShell(channel);
  if (pids.length) log(`stopped window pid ${pids.join(", ")}`);
  stopOwnedServer(channel);
  const free = await waitPortFree(channel.appPort, 15_000);
  if (!free) log(`port ${channel.appPort} is still busy — the next launch will report it`);
  const launched = launchShell(channel);
  if (launched.launched) log(`window relaunched (pid ${launched.pid})`);
}

function rollbackRelease() {
  const current = readPointer(channel, "current");
  const previous = readPointer(channel, "previous");
  if (!previous) fail("no previous release to roll back to");
  if (!previous.valid) fail(`previous release is missing/incomplete: ${previous.dir}`);

  log(`rolling back ${current && current.buildId ? current.buildId : "current"} → ${previous.buildId}`);
  if (current && current.valid) {
    writePointer(channel, "previous", { ...current, demotedAt: new Date().toISOString() });
  }
  writePointer(channel, "current", {
    dir: previous.dir,
    buildId: previous.buildId,
    channel: channel.id,
    promotedAt: previous.promotedAt || new Date().toISOString(),
    rolledBackFrom: current ? current.buildId : null,
  });
  log(`current is now ${previous.buildId}`);
}

function promoteRelease() {
  const running = buildInProgress();
  if (running) {
    fail(
      `a production build is running (pid ${running.pid}). Finish it, then promote. ` +
        "Promotion never races a build.",
    );
  }

  const source = fromArg ? path.resolve(ROOT, fromArg) : path.join(ROOT, channel.buildDir);
  if (!buildLooksComplete(source)) {
    fail(
      `no completed build in ${fromArg || channel.buildDir}. Run ` +
        `${channel.id === "dev" ? '"npm run desktop:build:dev"' : '"npm run build"'} first.`,
    );
  }
  const buildId = readBuildId(source);
  const releaseDir = path.join(channel.releasesDir, buildId);
  const distDir = path.join(releaseDir, ".next");

  if (!buildLooksComplete(distDir)) {
    const temp = `${releaseDir}.tmp`;
    log(`staging ${buildId} into ${relative(releaseDir)}…`);
    fs.rmSync(temp, { recursive: true, force: true });
    try {
      copyRuntime(source, path.join(temp, ".next"));
      if (!buildLooksComplete(path.join(temp, ".next"))) {
        throw new Error("copied build failed validation");
      }
      fs.writeFileSync(
        path.join(temp, "manifest.json"),
        JSON.stringify(
          {
            channel: channel.id,
            buildId,
            version: readVersion(),
            createdAt: new Date().toISOString(),
            source: relative(source),
          },
          null,
          2,
        ),
      );
      fs.mkdirSync(channel.releasesDir, { recursive: true });
      fs.rmSync(releaseDir, { recursive: true, force: true });
      fs.renameSync(temp, releaseDir);
    } catch (err) {
      fs.rmSync(temp, { recursive: true, force: true });
      fail(`staging failed: ${err && err.message ? err.message : err}`);
    }
  } else {
    log(`release ${buildId} already staged`);
  }

  // Validation happens BEFORE the pointer moves.
  if (!buildLooksComplete(distDir)) fail("staged release is not serviceable; current left untouched");

  const current = readPointer(channel, "current");
  if (current && current.valid) {
    writePointer(channel, "previous", {
      dir: current.dir,
      buildId: current.buildId,
      channel: channel.id,
      promotedAt: current.promotedAt || null,
    });
    log(`previous release kept: ${current.buildId}`);
  }
  writePointer(channel, "current", pointerInfo(distDir));
  log(`current is now ${buildId}`);
}

/** Keep only the current + previous release directories (each ~260 MB). */
function pruneReleases() {
  const current = readPointer(channel, "current");
  const previous = readPointer(channel, "previous");
  const keep = new Set();
  for (const p of [current, previous]) {
    if (!p || !p.dir) continue;
    // dir is `releases/<channel>/<buildId>/.next`
    const dir = path.resolve(ROOT, p.dir);
    keep.add(path.basename(path.dirname(dir)));
  }
  let removed = 0;
  try {
    for (const entry of fs.readdirSync(channel.releasesDir, { withFileTypes: true })) {
      if (!entry.isDirectory()) continue;
      if (keep.has(entry.name)) continue;
      fs.rmSync(path.join(channel.releasesDir, entry.name), { recursive: true, force: true });
      removed += 1;
    }
  } catch {}
  if (removed) log(`pruned ${removed} old release folder(s)`);
}

function readVersion() {
  try {
    return JSON.parse(fs.readFileSync(path.join(ROOT, "package.json"), "utf8")).version || null;
  } catch {
    return null;
  }
}

async function main() {
  if (rollback) rollbackRelease();
  else promoteRelease();
  pruneReleases();
  await restart();
  log("done");
}

main().catch((err) => fail(err && err.message ? err.message : String(err)));
