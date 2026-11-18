#!/usr/bin/env node
// `npm run desktop:doctor` — one screen that answers "is the desktop healthy?".
//
//   node scripts/desktop-doctor.js              # Stable (3100)
//   node scripts/desktop-doctor.js --channel dev
//   node scripts/desktop-doctor.js --all        # both channels
//
// Checks the facts that actually explain the "it worked, then it broke" reports:
// the window, the port, the owner marker, the build the server is running vs the
// build that is available, harness liveness, provider config, a running build,
// and the data directory. Exit 1 when a core check fails.

const fs = require("fs");
const path = require("path");

const { STABLE, DEV, channelFor } = require("./lib/channels");
const { buildInProgress } = require("./lib/server");
const { readBuildId, buildLooksComplete, readPointer, ROOT } = require("./lib/desktop-release");
const { shellPathFor, readOwner } = require("./lib/desktop-process");

const argv = process.argv.slice(2);
const all = argv.includes("--all");
const channelArg = argv[argv.indexOf("--channel") + 1];
const channels = all ? [STABLE, DEV] : [channelFor(argv.includes("--channel") ? channelArg : "stable")];

const results = [];

function record(level, label, detail) {
  results.push({ level, label, detail });
  const mark = level === "ok" ? "PASS" : level === "warn" ? "WARN" : level === "fail" ? "FAIL" : "INFO";
  console.log(`  ${mark.padEnd(4)} ${label.padEnd(30)} ${detail}`);
}

async function json(url, timeoutMs = 4000) {
  try {
    const res = await fetch(url, { signal: AbortSignal.timeout(timeoutMs) });
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

function readJson(file) {
  try {
    return JSON.parse(fs.readFileSync(file, "utf8"));
  } catch {
    return null;
  }
}

async function checkChannel(channel) {
  console.log(`\n${channel.label}  (app ${channel.appPort} · harness ${channel.harnessPort})`);
  const exe = shellPathFor(channel);
  if (fs.existsSync(exe)) record("ok", "window binary", path.relative(ROOT, exe) || exe);
  else record("fail", "window binary", `missing: ${exe}`);

  const owner = readOwner(channel);
  if (owner) record("ok", "owned server", `pid ${owner.pid}, build ${owner.buildId}`);
  else record("warn", "owned server", "no live owner marker (server attached or down)");

  const current = readPointer(channel, "current");
  const pinFile = path.join(channel.pinDir, ".next");
  const pinId = buildLooksComplete(pinFile) ? readBuildId(pinFile) : null;
  const expected = current && current.valid ? current.buildId : pinId;
  if (expected) record("ok", "serving build (expected)", expected);
  else if (owner) record("warn", "serving build (expected)", `legacy pin · owner reports ${owner.buildId}`);
  else record("fail", "serving build (expected)", "no valid release or pin");

  if (owner && expected && owner.buildId !== expected) {
    record("fail", "server build mismatch", `server ${owner.buildId} ≠ expected ${expected}`);
  }

  const sourceId = buildLooksComplete(path.join(ROOT, channel.buildDir))
    ? readBuildId(path.join(ROOT, channel.buildDir))
    : null;
  if (!sourceId) record("info", "available build", `none in ${channel.buildDir}`);
  else if (sourceId === expected) record("ok", "available build", sourceId);
  else record("warn", "available build", `${sourceId} (newer than served; promote/refresh)`);

  const live = await json(`http://127.0.0.1:${channel.harnessPort}/health/live`);
  if (live && live.ok) {
    record("ok", "harness liveness", `${live.service}, ${live.activeRuns} active run(s)`);
  } else {
    record("fail", "harness liveness", `no answer on ${channel.harnessPort}`);
  }

  const agent = await json(`http://127.0.0.1:${channel.appPort}/api/agent/status`, 6000);
  if (agent && agent.configured) record("ok", "model provider", `${agent.provider} · ${agent.model}`);
  else record("fail", "model provider", "not configured (Settings → Models)");

  const app = await json(`http://127.0.0.1:${channel.appPort}/api/updates`, 6000);
  if (app) record("ok", "app server", `HTTP ok · v${app.currentVersion || "?"}`);
  else record("fail", "app server", `no answer on ${channel.appPort}`);

  try {
    const st = fs.statSync(channel.dataDir);
    record("ok", "data dir", `${path.relative(ROOT, channel.dataDir) || "."} (${st.isDirectory() ? "dir" : "file"})`);
  } catch {
    record("fail", "data dir", `missing: ${channel.dataDir}`);
  }

  const pin = readJson(path.join(channel.pinDir, "pin.json"));
  if (pin && pin.buildId) record("info", "pinned copy", pin.buildId);
}

/**
 * Optional feature packs of the INSTALLED app (not this checkout). Not a
 * failure: a slim install is supposed to start without them. The line exists so
 * "feature X does nothing" has an answer other than "look in Settings".
 */
function checkInstalledPacks() {
  const base =
    process.platform === "win32"
      ? path.join(process.env.LOCALAPPDATA || "", "Programs", "BlackEclipse", "app")
      : process.platform === "darwin"
        ? "/Applications/Black Eclipse.app/Contents/Resources/app"
        : "/usr/lib/blackeclipse/app";
  const manifest = readJson(path.join(base, "config", "packs.json"));
  if (!manifest || !Array.isArray(manifest.packs) || manifest.packs.length === 0) {
    record("info", "feature packs", "none published by this install (or no packaged app)");
    return;
  }
  const site = path.join(base, "scripts", "vendor", "python", "Lib", "site-packages");
  const missing = manifest.packs.filter(
    (pack) => !pack.packages.every((pkg) => fs.existsSync(path.join(site, pkg)))
  );
  if (missing.length === 0) {
    record("ok", "feature packs", `${manifest.packs.length}/${manifest.packs.length} installed`);
    return;
  }
  const names = missing.map((pack) => pack.name).join(", ");
  record(
    "info",
    "feature packs",
    `${manifest.packs.length - missing.length}/${manifest.packs.length} installed · missing ${names} (Settings → Data & Storage → Feature packs)`
  );
}

async function main() {
  console.log("Black Eclipse desktop doctor");
  const running = buildInProgress();
  if (running) record("warn", "build in progress", `pid ${running.pid} — expect CPU load`);
  else record("ok", "build in progress", "none");

  for (const channel of channels) {
    // eslint-disable-next-line no-await-in-loop - sequential, readable output
    await checkChannel(channel);
  }
  checkInstalledPacks();

  const failures = results.filter((r) => r.level === "fail");
  console.log("");
  if (failures.length) {
    console.log(`${failures.length} check(s) FAILED.`);
    process.exit(1);
  }
  console.log("All core checks passed.");
}

main().catch((err) => {
  console.error(`[desktop:doctor] ${err && err.message ? err.message : err}`);
  process.exit(1);
});
