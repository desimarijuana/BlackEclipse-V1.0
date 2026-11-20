// Launch/stop helpers for the desktop channels.
//
// The shell owns exactly one child (the bootstrap). Restarting a channel means:
//   1. stop the shell process (by exact executable path — never by name, so the
//      Dev binary can never stop the Stable one),
//   2. stop the server tree this install started (owner marker in the channel's
//      runtime dir; never a process we do not own),
//   3. relaunch the same executable with the channel's environment.
//
// Windows-first, matching the packaged shell.

const fs = require("fs");
const os = require("os");
const path = require("path");
const { spawn, spawnSync } = require("child_process");

const ROOT = path.join(__dirname, "..", "..");
const INSTALL = path.join(
  process.env.LOCALAPPDATA || path.join(os.homedir(), "AppData", "Local"),
  "Programs",
  "BlackEclipse",
);

function installedShellPath() {
  return path.join(INSTALL, "Black Eclipse.exe");
}

function devShellPath() {
  return path.join(
    ROOT,
    "desktop",
    "src-tauri",
    "target-dev",
    "debug",
    process.platform === "win32" ? "black-eclipse-desktop.exe" : "black-eclipse-desktop",
  );
}

function shellPathFor(channel) {
  return channel.id === "dev" ? devShellPath() : installedShellPath();
}

/**
 * The data dir the channel's window ACTUALLY uses.
 *
 * A packaged Stable install defaults to `%LOCALAPPDATA%\BlackEclipse\data`
 * (scripts/desktop-server.js `resolveDataDir`), so its owner marker is written
 * there. Reading it from the checkout root instead left `black stop` unable to
 * stop the app's server — every next launch hit "port 3100 is in use".
 */
function channelDataDir(channel) {
  if (channel.id !== "stable") return channel.dataDir;
  if (process.env.BE_DATA_DIR) return path.resolve(process.env.BE_DATA_DIR);
  const packaged = fs.existsSync(path.join(INSTALL, "app", "server.js"));
  const local = process.env.LOCALAPPDATA || path.join(os.homedir(), "AppData", "Local");
  return packaged ? path.join(local, "BlackEclipse", "data") : channel.dataDir;
}

function ownerFile(channel) {
  return path.join(channelDataDir(channel), ".runtime", "desktop-owned.json");
}

function pidAlive(pid) {
  try {
    process.kill(pid, 0);
    return true;
  } catch (err) {
    return Boolean(err && err.code === "EPERM");
  }
}

/** True when `pid` is a `desktop-server.js` bootstrap, not a reused PID. */
function isDesktopBootstrap(pid) {
  if (process.platform !== "win32") return pidAlive(pid);
  if (!pidAlive(pid)) return false;
  const script =
    "(Get-CimInstance Win32_Process -Filter " +
    JSON.stringify(`ProcessId=${pid}`) +
    ").CommandLine";
  const out = spawnSync("powershell", ["-NoProfile", "-Command", script], {
    encoding: "utf8",
    windowsHide: true,
  });
  return Boolean(out.stdout && out.stdout.includes("desktop-server.js"));
}

function readOwner(channel) {
  try {
    const info = JSON.parse(fs.readFileSync(ownerFile(channel), "utf8"));
    if (!info || !Number.isFinite(info.pid) || !pidAlive(info.pid)) return null;
    // A reused PID must never let us kill an unrelated process.
    if (!isDesktopBootstrap(info.pid)) return null;
    return info;
  } catch {
    return null;
  }
}

function clearOwner(channel) {
  try {
    fs.rmSync(ownerFile(channel), { force: true });
  } catch {}
}

/** Stop only the server tree this channel's install started. */
function stopOwnedServer(channel) {
  const owner = readOwner(channel);
  clearOwner(channel);
  if (!owner) return false;
  if (process.platform === "win32") {
    spawnSync("taskkill", ["/F", "/T", "/PID", String(owner.pid)], { stdio: "ignore" });
  } else {
    try {
      process.kill(owner.pid);
    } catch {}
  }
  return true;
}

function shellPids(exePath) {
  if (process.platform !== "win32") return [];
  // PowerShell single-quoted strings preserve a Windows path verbatim.
  // JSON.stringify here was the bug: it doubled every backslash, so the
  // comparison never matched and the channel window was never stopped
  // (single-instance then silently focused the stale window).
  const psPath = String(exePath).replace(/'/g, "''");
  const script =
    "Get-CimInstance Win32_Process | Where-Object { $_.ExecutablePath -eq '" +
    psPath +
    "' } | Select-Object -ExpandProperty ProcessId";
  const out = spawnSync("powershell", ["-NoProfile", "-Command", script], {
    encoding: "utf8",
    windowsHide: true,
  });
  if (out.status !== 0 || !out.stdout) return [];
  return out.stdout
    .split(/\s+/)
    .map((s) => Number(s.trim()))
    .filter((n) => Number.isFinite(n) && n > 0);
}

/** Stop the window process for this channel (never the other channel). */
function stopShell(channel) {
  const exe = shellPathFor(channel);
  const pids = shellPids(exe);
  for (const pid of pids) {
    if (process.platform === "win32") {
      spawnSync("taskkill", ["/F", "/PID", String(pid)], { stdio: "ignore" });
    } else {
      try {
        process.kill(pid);
      } catch {}
    }
  }
  return pids;
}

function channelLaunchEnv(channel) {
  const env = {
    ...process.env,
    BE_DESKTOP_CHANNEL: channel.id,
    BE_DESKTOP_PORT: String(channel.appPort),
  };
  // Only Dev is pointed at a checkout data dir (it is isolated by design). A
  // packaged Stable install owns `%LOCALAPPDATA%\BlackEclipse\data`; forcing the
  // checkout root made `black app` / `desktop:refresh` open the real window
  // against a checkout `jdds.db` that has no schema, so every screen failed with
  // "table does not exist" (and the server later died of OOM).
  if (channel.id === "dev") env.BE_DATA_DIR = channel.dataDir;
  return env;
}

/** Block the CLI briefly without spinning the CPU. */
function sleepSync(ms) {
  Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, ms);
}

/**
 * Wait until the channel's window process is actually gone.
 *
 * `stopShell` returns as soon as taskkill was issued, but Tauri's
 * single-instance plugin hands a launch to the OLD process while it is still
 * exiting — the new window then never runs its bootstrap, and the app sits on
 * the splash with a dead server. Waiting here makes the relaunch reliable.
 */
function waitForShellExit(channel, timeoutMs = 15000) {
  const exe = shellPathFor(channel);
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (shellPids(exe).length === 0) return true;
    sleepSync(300);
  }
  return shellPids(exe).length === 0;
}

/**
 * Wait for the channel port to be released before relaunching.
 *
 * A stopped window can outlive its own server by a moment: the new shell then
 * starts, finds port 3100 still held by the old process, and parks on the
 * "leftover server" conflict screen with a Retry button. Waiting here turns
 * that race into a slow launch instead of a stuck app.
 */
function waitForPortFree(port, timeoutMs = 15000) {
  if (process.platform !== "win32") return true;
  const deadline = Date.now() + timeoutMs;
  const script =
    "(Get-NetTCPConnection -State Listen -LocalPort " + Number(port) +
    " -ErrorAction SilentlyContinue | Measure-Object).Count";
  while (Date.now() < deadline) {
    const out = spawnSync("powershell", ["-NoProfile", "-Command", script], {
      encoding: "utf8",
      windowsHide: true,
    });
    if (out.status === 0 && String(out.stdout).trim() === "0") return true;
    sleepSync(400);
  }
  return false;
}

/**
 * Launch the channel window; returns the child pid or null when absent.
 *
 * `extraEnv` layers on the channel env (e.g. `BE_DESKTOP_LIVE=1`). The Tauri
 * shell inherits its environment and the bootstrap it spawns inherits it in
 * turn, so one variable here is enough to switch the whole tree to live mode.
 */
function launchShell(channel, extraEnv = {}) {
  const exe = shellPathFor(channel);
  if (!fs.existsSync(exe)) return { launched: false, exe, reason: "missing" };
  waitForPortFree(channel.appPort);
  const child = spawn(exe, [], {
    cwd: ROOT,
    detached: true,
    stdio: "ignore",
    env: { ...channelLaunchEnv(channel), ...extraEnv },
    windowsHide: false,
  });
  child.unref();
  return { launched: true, exe, pid: child.pid };
}

module.exports = {
  ROOT,
  INSTALL,
  installedShellPath,
  devShellPath,
  shellPathFor,
  ownerFile,
  readOwner,
  stopOwnedServer,
  stopShell,
  shellPids,
  launchShell,
  channelLaunchEnv,
  waitForShellExit,
  pidAlive,
};
