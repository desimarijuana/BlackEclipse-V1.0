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

function ownerFile(channel) {
  return path.join(channel.dataDir, ".runtime", "desktop-owned.json");
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
  return {
    ...process.env,
    BE_DESKTOP_CHANNEL: channel.id,
    BE_DESKTOP_PORT: String(channel.appPort),
    BE_DATA_DIR: channel.dataDir,
  };
}

/** Launch the channel window; returns the child pid or null when absent. */
function launchShell(channel) {
  const exe = shellPathFor(channel);
  if (!fs.existsSync(exe)) return { launched: false, exe, reason: "missing" };
  const child = spawn(exe, [], {
    cwd: ROOT,
    detached: true,
    stdio: "ignore",
    env: channelLaunchEnv(channel),
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
  launchShell,
  channelLaunchEnv,
  pidAlive,
};
