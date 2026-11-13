// Desktop channels — the ONE place the two desktop runtimes are defined.
//
// The product is the native desktop app. There is no website runtime: both
// channels are Tauri windows around the same Next.js UI, with SEPARATE app
// ports, harness ports, build artifacts and runtime state.
//
//   stable   installed `Black Eclipse.exe` · port 3100 · harness 8767
//   dev      `Black Eclipse Dev.exe`        · port 3101 · harness 8768
//
// Why the split: a build/test in the dev channel used to compete with the app
// the user was working in — shared `.next`, shared 3100, shared 8766. Every
// "I built it, then it broke" episode came from that. Channels make the dev
// lane incapable of touching the stable one.
//
// Ports are fixed (not dynamic): Tauri's IPC capability allowlist cannot
// wildcard a port, so notifications only work on the ports listed there.

const os = require("os");
const path = require("path");

const ROOT = path.join(__dirname, "..", "..");

function port(value, fallback) {
  const n = Number(value);
  return Number.isFinite(n) && n > 0 ? n : fallback;
}

function isTruthy(value) {
  return ["1", "true", "yes", "on"].includes(String(value || "").trim().toLowerCase());
}

// Stable keeps the historical checkout data directory (the repo root) so an
// existing install's journals, memory and JDdS snapshot are untouched. The
// packaged build overrides this with `%LOCALAPPDATA%\BlackEclipse\data`.
// Dev is ALWAYS isolated: a dev experiment can never write the real journals.
const STABLE = Object.freeze({
  id: "stable",
  label: "Stable",
  appPort: port(process.env.BE_STABLE_PORT || process.env.BE_DESKTOP_PORT, 3100),
  harnessPort: port(process.env.BE_STABLE_HARNESS_PORT, 8767),
  // Where the channel's build is produced. Stable builds the normal `.next`.
  buildDir: ".next",
  // Immutable pinned copy served by the desktop server.
  pinDir: path.join(ROOT, ".black-eclipse", "desktop-dist-stable"),
  // Versioned release artifacts + promotion pointers.
  releasesDir: path.join(ROOT, "releases", "stable"),
  dataDir: process.env.BE_DATA_DIR || ROOT,
  shellName: "Black Eclipse.exe",
});

const DEV = Object.freeze({
  id: "dev",
  label: "Dev",
  appPort: port(process.env.BE_DEV_DESKTOP_PORT, 3101),
  harnessPort: port(process.env.BE_DEV_DESKTOP_HARNESS_PORT, 8768),
  buildDir: ".next-desktop-dev",
  pinDir: path.join(ROOT, ".black-eclipse", "desktop-dist-dev"),
  releasesDir: path.join(ROOT, "releases", "dev"),
  dataDir: path.join(ROOT, ".black-eclipse", "desktop-dev"),
  shellName: "Black Eclipse Dev.exe",
});

const CHANNELS = Object.freeze({ stable: STABLE, dev: DEV });

/** Normalize any caller value to a channel. Unknown values are stable. */
function channelFor(raw) {
  return String(raw || "").trim().toLowerCase() === "dev" ? DEV : STABLE;
}

/** The channel this process is running as (`BE_DESKTOP_CHANNEL`). */
function channelFromEnv() {
  return channelFor(process.env.BE_DESKTOP_CHANNEL);
}

function samePath(a, b) {
  return path.resolve(a).toLowerCase() === path.resolve(b).toLowerCase();
}

/**
 * The environment for the channel's Next server + Python harness.
 *
 * Every value that used to come from the website `PROD` profile comes from the
 * channel now: app port, harness port, callback URL, build directory. The
 * harness child reads the SAME `HARNESS_PY_*` variables the supervisor uses,
 * so two channels cannot converge on one harness by accident.
 */
function channelEnv(channel, { dataDir, buildDir } = {}) {
  const ch = channel || STABLE;
  const dir = dataDir || ch.dataDir;
  const dist = buildDir || ch.buildDir;
  return {
    BE_DESKTOP_CHANNEL: ch.id,
    BE_PROFILE: ch.id,
    PORT: String(ch.appPort),
    HARNESS_PY_URL: `http://127.0.0.1:${ch.harnessPort}`,
    HARNESS_PY_HOST: "127.0.0.1",
    HARNESS_PY_PORT: String(ch.harnessPort),
    HARNESS_CALLBACK_URL: `http://127.0.0.1:${ch.appPort}`,
    NEXT_DIST_DIR: dist,
    BE_DATA_DIR: dir,
  };
}

/** Is the website/browser lane allowed to start? Desktop-only by default. */
function webLaneAllowed() {
  return isTruthy(process.env.BE_ALLOW_WEB);
}

/** Print the one message every retired website command shows. */
function refuseWebLane(command) {
  if (webLaneAllowed()) return false;
  console.log("");
  console.log(`[black-eclipse] "${command}" is disabled — the product is desktop-only.`);
  console.log("  Use:  npm run desktop:dev      (Dev window, port 3101)");
  console.log("        npm run desktop:refresh  (re-pin + reopen Stable)");
  console.log("        npm run desktop:doctor   (health check)");
  console.log("  The web code is kept for a future browser release; set BE_ALLOW_WEB=1");
  console.log("  only if you are deliberately working on that lane.");
  console.log("");
  return true;
}

module.exports = {
  ROOT,
  STABLE,
  DEV,
  CHANNELS,
  channelFor,
  channelFromEnv,
  channelEnv,
  samePath,
  webLaneAllowed,
  refuseWebLane,
};
