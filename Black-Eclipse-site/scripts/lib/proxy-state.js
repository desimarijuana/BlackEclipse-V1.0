// State of the ALWAYS-ON front door (`scripts/local-proxy.js`).
//
// The proxy used to be a child of whichever launcher started it, so closing the
// app also closed the front door — and the next bookmark click hit a refused
// connection. The door is now a long-lived process that outlives the app, and
// this file is how every other script discovers it:
//
//   * launchers ATTACH to a live door instead of starting a second one,
//   * the door is re-used across boots via a per-user sign-in task,
//   * `proxy:stop` / `black proxy off` is the one explicit way to end it.
//
// The file lives beside the other runtime state under `.black-eclipse/` and is
// advisory: a dead PID or an unreadable file is treated as "no door".

const fs = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "..", "..");
const STATE_FILE = path.join(ROOT, ".black-eclipse", "proxy-state.json");

function readProxyState() {
  try {
    const raw = JSON.parse(fs.readFileSync(STATE_FILE, "utf8"));
    if (!raw || typeof raw !== "object" || !Number.isFinite(Number(raw.pid))) return null;
    return raw;
  } catch {
    return null;
  }
}

function pidAlive(pid) {
  const n = Number(pid);
  if (!Number.isInteger(n) || n <= 0) return false;
  try {
    process.kill(n, 0);
    return true;
  } catch (err) {
    // EPERM means the process exists but belongs to someone else.
    return err && err.code === "EPERM";
  }
}

function writeProxyState(state) {
  try {
    fs.mkdirSync(path.dirname(STATE_FILE), { recursive: true });
    fs.writeFileSync(STATE_FILE, JSON.stringify(state, null, 2));
  } catch {
    /* advisory only */
  }
}

/** Remove the state file, but never on behalf of a different live process. */
function clearProxyState(pid) {
  const current = readProxyState();
  if (pid !== undefined && pid !== null && current && Number(current.pid) !== Number(pid)) return;
  try {
    fs.rmSync(STATE_FILE, { force: true });
  } catch {
    /* advisory only */
  }
}

/** The live door, or null. A stale state file is cleaned up here. */
function liveProxy() {
  const state = readProxyState();
  if (!state) return null;
  if (!pidAlive(state.pid)) {
    clearProxyState(state.pid);
    return null;
  }
  return state;
}

module.exports = {
  ROOT,
  STATE_FILE,
  readProxyState,
  writeProxyState,
  clearProxyState,
  pidAlive,
  liveProxy,
};
