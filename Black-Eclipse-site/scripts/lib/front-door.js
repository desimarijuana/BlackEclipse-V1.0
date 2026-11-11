// Make sure the always-on front door is up.
//
// Used by the paths that find the APP already running (`black eclipse`,
// `npm run up`): the app may have been kept alive by its own task while the door
// was lost, and without this the user would be back to a refused connection.
//
// Starting is deliberately detached: the door outlives whoever asked for it.

const { spawn } = require("child_process");
const path = require("path");
const { liveProxy } = require("./proxy-state");

const ROOT = path.join(__dirname, "..", "..");

/**
 * @returns {{live: object|null, started: boolean}}
 */
function ensureFrontDoor() {
  const live = liveProxy();
  if (live) return { live, started: false };
  try {
    const child = spawn(process.execPath, [path.join(ROOT, "scripts", "local-proxy.js")], {
      cwd: ROOT,
      env: process.env,
      detached: true,
      stdio: "ignore",
      windowsHide: true,
    });
    child.unref();
    return { live: null, started: true };
  } catch {
    return { live: null, started: false };
  }
}

module.exports = { ensureFrontDoor };
