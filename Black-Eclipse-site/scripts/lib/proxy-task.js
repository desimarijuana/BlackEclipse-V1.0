// Per-user sign-in task for the front door ("BlackEclipse Front Door").
//
// Why: the branded offline page has to be served by SOMETHING. If the front door
// is also down (a reboot, a crash), the browser falls back to its own
// `ERR_CONNECTION_REFUSED` screen — the exact thing this work removes. So the
// proxy is registered to start at sign-in, per user, with no elevation, using
// the same `schtasks` mechanism the other operational tasks in `scripts/` use.
//
// There is no environment to pass through a scheduled task, so the wrapper is a
// tiny .cmd that cd's into the project and runs the proxy with its output in
// `.black-eclipse/proxy.log`. The proxy resolves its own defaults from
// `lib/profiles.js` + `lib/tls.js`, so it needs no variables.
//
// Everything here is best effort: a locked-down machine where schtasks is
// unavailable must not stop the app from starting.

const { execFile, execFileSync } = require("child_process");
const fs = require("fs");
const os = require("os");
const path = require("path");

const ROOT = path.join(__dirname, "..", "..");
const TASK_NAME = "BlackEclipse Front Door";
const WRAPPER = path.join(ROOT, ".black-eclipse", "proxy-task.cmd");
const LOG_FILE = path.join(ROOT, ".black-eclipse", "proxy.log");

/** `%APPDATA%\...\Startup` — used when Task Scheduler refuses (some policies). */
function startupDir() {
  const appData = process.env.APPDATA || path.join(os.homedir(), "AppData", "Roaming");
  return path.join(appData, "Microsoft", "Windows", "Start Menu", "Programs", "Startup");
}

function startupEntry() {
  return path.join(startupDir(), "BlackEclipse Front Door.vbs");
}

function supported() {
  return process.platform === "win32";
}

/** `BE_PROXY_TASK=0` opts out (servers, CI, anyone who manages processes). */
function enabled() {
  return String(process.env.BE_PROXY_TASK || "").trim() !== "0";
}

function writeWrapper() {
  const lines = [
    "@echo off",
    "rem Start the BlackEclipse front door. It answers even when the app is down.",
    `cd /d "${ROOT}"`,
    `"${process.execPath}" "${path.join(ROOT, "scripts", "local-proxy.js")}" >> "${LOG_FILE}" 2>&1`,
  ].join("\r\n");
  fs.mkdirSync(path.dirname(WRAPPER), { recursive: true });
  let current = "";
  try {
    current = fs.readFileSync(WRAPPER, "utf8");
  } catch {
    /* first time */
  }
  if (current !== lines) fs.writeFileSync(WRAPPER, lines);
  return WRAPPER;
}

function taskExists() {
  if (!supported()) return false;
  try {
    if (fs.existsSync(startupEntry())) return true;
  } catch {
    /* fall through to schtasks */
  }
  try {
    execFileSync("schtasks", ["/Query", "/TN", TASK_NAME], { stdio: "ignore", windowsHide: true });
    return true;
  } catch {
    return false;
  }
}

/**
 * A hidden sign-in launcher in the Startup folder. Task Scheduler can refuse
 * (`ERROR: Access is denied` on locked-down machines) — Startup always works
 * per user and needs no elevation.
 */
function writeStartupEntry() {
  const entry = startupEntry();
  const vbs = [
    "' Start the BlackEclipse front door hidden at sign-in.",
    "' It answers https://blackeclipse even when the app is stopped.",
    'Set sh = CreateObject("WScript.Shell")',
    `sh.CurrentDirectory = "${ROOT}"`,
    `sh.Run """${process.execPath}"" ""${path.join(ROOT, "scripts", "local-proxy.js")}""", 0, False`,
  ].join("\r\n");
  fs.mkdirSync(path.dirname(entry), { recursive: true });
  fs.writeFileSync(entry, vbs);
  return entry;
}

function removeStartupEntry() {
  try {
    fs.rmSync(startupEntry(), { force: true });
    return true;
  } catch {
    return false;
  }
}

function installProxyTask() {
  if (!supported()) return { ok: false, reason: "not Windows" };
  writeWrapper();
  try {
    execFileSync(
      "schtasks",
      // /TR needs the path itself quoted: Task Scheduler stores the string
      // verbatim and re-parses it when the trigger fires. Passing it unquoted
      // makes a path with spaces fail with "invalid argument".
      ["/Create", "/F", "/SC", "ONLOGON", "/TN", TASK_NAME, "/TR", `"${WRAPPER}"`, "/RL", "LIMITED"],
      { stdio: "ignore", windowsHide: true }
    );
    // A leftover Startup entry would start a second copy; the proxy ignores a
    // taken port, but one sign-in mechanism is enough.
    removeStartupEntry();
    return { ok: true, created: true, method: "task", task: TASK_NAME };
  } catch {
    try {
      writeStartupEntry();
      return { ok: true, created: true, method: "startup", task: TASK_NAME };
    } catch (err) {
      return { ok: false, reason: err.message };
    }
  }
}

function removeProxyTask() {
  if (!supported()) return { ok: false, reason: "not Windows" };
  let removed = false;
  try {
    execFileSync("schtasks", ["/Delete", "/F", "/TN", TASK_NAME], { stdio: "ignore", windowsHide: true });
    removed = true;
  } catch {
    /* not installed */
  }
  if (removeStartupEntry()) removed = true;
  return { ok: true, removed, task: TASK_NAME };
}

/**
 * Make sure the sign-in task exists. Async + silent: called on every production
 * launch, so a slow Task Scheduler must never delay the app.
 *
 * @param {(message: string) => void} [onLog]
 */
function ensureProxyTask(onLog) {
  if (!supported() || !enabled()) return;
  execFile("schtasks", ["/Query", "/TN", TASK_NAME], { windowsHide: true }, (queryErr) => {
    if (!queryErr) return;
    // A Startup-folder entry (the no-elevation fallback) counts as installed.
    if (taskExists()) return;
    const result = installProxyTask();
    if (onLog) {
      onLog(
        result.ok
          ? "front door: registered to start at sign-in (stays up when the app is stopped)"
          : `front door: could not register the sign-in task (${result.reason}) — the app still runs`
      );
    }
  });
}

module.exports = {
  TASK_NAME,
  TASK_WRAPPER: WRAPPER,
  TASK_LOG: LOG_FILE,
  startupEntry,
  supported,
  taskExists,
  installProxyTask,
  removeProxyTask,
  ensureProxyTask,
};
