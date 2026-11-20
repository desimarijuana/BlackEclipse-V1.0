#!/usr/bin/env node
// Build ONE desktop channel's Next payload — never the other channel's.
//
//   node scripts/desktop-build.js --channel dev        # .next-desktop-dev
//   node scripts/desktop-build.js --channel stable     # .next (delegates to build-prod)
//   node scripts/desktop-build.js --channel dev --if-needed
//
// Why a channel build exists: the desktop serves an immutable pinned/released
// copy, but that copy has to come from a completed build. Building the Dev
// channel into its own directory means a dev build can never rewrite the
// artifact Stable is serving, and vice versa.
//
// The build lock (`.next-build.lock`) is SHARED with every other build entry
// point, so two builds can never run at once on one checkout.

const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");

const { channelFor } = require("./lib/channels");
const {
  acquireBuildLock,
  buildNodeOptions,
  nextBin,
  sourceHash,
} = require("./lib/server");

const ROOT = path.join(__dirname, "..");
const TSCONFIG = path.join(ROOT, "tsconfig.json");

function argValue(flag) {
  const i = process.argv.indexOf(flag);
  return i >= 0 ? process.argv[i + 1] : undefined;
}

function hasFlag(flag) {
  return process.argv.includes(flag);
}

const channel = channelFor(argValue("--channel") || process.env.BE_DESKTOP_CHANNEL || "dev");
const stampFile = path.join(ROOT, ".black-eclipse", `desktop-build-${channel.id}.hash`);

function log(message) {
  console.log(`[desktop:build:${channel.id}] ${message}`);
}

function stampMatches() {
  try {
    return fs.readFileSync(stampFile, "utf8").trim() === sourceHash();
  } catch {
    return false;
  }
}

function writeStamp() {
  try {
    fs.mkdirSync(path.dirname(stampFile), { recursive: true });
    fs.writeFileSync(stampFile, sourceHash());
  } catch {}
}

function buildStable() {
  log("stable uses the production build (.next)");
  const result = spawnSync(process.execPath, [path.join(__dirname, "build-prod.js")], {
    cwd: ROOT,
    stdio: "inherit",
    windowsHide: true,
    // This is the managed path: it promotes the build and restarts the window,
    // so building under a running app is expected (build-prod.js refuses only a
    // plain `npm run build`).
    env: { ...process.env, BE_ALLOW_BUILD_WHILE_RUNNING: "1" },
  });
  if (result.status !== 0) process.exit(result.status || 1);
}

function buildChannel() {
  const distDir = channel.buildDir;
  const distPath = path.join(ROOT, distDir);
  log(`building ${distDir}`);

  const release = acquireBuildLock({
    onWait: (held, waited) => {
      log(
        `another build is running (pid ${held.pid}, ${Math.round(waited / 1000)}s) — waiting for it`,
      );
    },
  });
  if (!release) {
    console.error("[desktop:build] timed out waiting for another build to finish");
    process.exit(1);
  }

  // Next rewrites tsconfig `include` to add the dist dir. It is a tracked file
  // shared with every other build, so snapshot and restore it.
  const before = fs.existsSync(TSCONFIG) ? fs.readFileSync(TSCONFIG) : null;
  try {
    // Turbopack for the same reason as the stable path (scripts/lib/server.js):
    // the webpack production compile exceeds the host's heap. Escape hatch:
    // BE_BUILD_WEBPACK=1.
    const bundler = process.env.BE_BUILD_WEBPACK === "1" ? [] : ["--turbopack"];
    const result = spawnSync(process.execPath, [nextBin(), "build", ...bundler], {
      cwd: ROOT,
      stdio: "inherit",
      windowsHide: true,
      env: {
        ...process.env,
        NODE_ENV: "production",
        NODE_OPTIONS: buildNodeOptions(process.env.NODE_OPTIONS),
        NEXT_DIST_DIR: distDir,
        NEXT_TELEMETRY_DISABLED: "1",
        // A dev-channel build is a normal (non-standalone) build so the desktop
        // bootstrap can `next start` it with NEXT_DIST_DIR pointing at the pin.
        BE_STANDALONE: "",
      },
    });
    if (result.status !== 0) {
      console.error(`[desktop:build] build failed with exit ${result.status}`);
      process.exit(result.status || 1);
    }
    if (!fs.existsSync(path.join(distPath, "BUILD_ID"))) {
      console.error(`[desktop:build] ${distDir}/BUILD_ID is missing after a successful build`);
      process.exit(2);
    }
    writeStamp();
    log(`built ${distDir} (build ${fs.readFileSync(path.join(distPath, "BUILD_ID"), "utf8").trim()})`);
  } finally {
    if (before) {
      try {
        if (!fs.readFileSync(TSCONFIG).equals(before)) fs.writeFileSync(TSCONFIG, before);
      } catch {}
    }
    release();
  }
}

if (channel.id === "stable") {
  buildStable();
} else if (hasFlag("--if-needed") && stampMatches()) {
  log("build is current — skipping");
} else {
  buildChannel();
}
