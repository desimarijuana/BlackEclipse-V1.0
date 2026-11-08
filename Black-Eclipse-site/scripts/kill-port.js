const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');
const { profileFor } = require('./lib/profiles');

const root = path.join(__dirname, '..');

// The profile this launch belongs to: `node scripts/kill-port.js dev|prod`.
// `predev` and `prestart` pass it explicitly; a manual run defaults to prod.
const profile = profileFor(process.argv[2]);

// ── kill listeners on a port ─────────────────────────────────────────────────
function pidsListeningOn(port) {
  const pids = new Set();
  try {
    if (process.platform === 'win32') {
      const output = execSync('netstat -ano', { encoding: 'utf8', windowsHide: true });
      for (const line of output.split('\n')) {
        if (line.includes(`:${port}`) && line.includes('LISTENING')) {
          const parts = line.trim().split(/\s+/);
          const pid = parts[parts.length - 1];
          if (pid && pid !== '0') pids.add(pid);
        }
      }
    } else {
      const out = execSync(`lsof -t -i:${port}`, { encoding: 'utf8' }).trim();
      if (out) out.split('\n').forEach((pid) => pid && pids.add(pid));
    }
  } catch {
    // No listener (netstat/lsof unavailable or port free) — nothing to do.
  }
  return [...pids];
}

function killPort(port, label) {
  let killed = false;
  for (const pid of pidsListeningOn(port)) {
    console.log(`Killing process on port ${port} (${label}, PID: ${pid})...`);
    try {
      execSync(process.platform === 'win32' ? `taskkill /F /PID ${pid}` : `kill -9 ${pid}`, { windowsHide: true });
      killed = true;
    } catch {
      // Already gone.
    }
  }
  return killed;
}

// 1. Clear this profile's Next.js port. Only the port of the profile being
//    launched is touched — the other environment keeps running untouched.
console.log(`Checking if ${profile.label} port ${profile.appPort} is in use...`);
let killedProcess = killPort(profile.appPort, 'Next.js');

// 2. Clear this profile's Python runtime port. A runtime spawned as a child of
//    a previous launch survives the parent on Windows and keeps holding the
//    port; a fresh runtime then fails to bind (`WinError 10048`) and its boot
//    reconciliation would orphan the runs the survivor is executing. Dev and
//    production use different harness ports, so neither clears the other's.
const pyPort = (() => {
  // The URL is what the server binds (python-runtime derives host/port from it),
  // so it wins over the discrete port variable.
  const raw = process.env.HARNESS_PY_URL;
  if (raw) {
    try {
      const url = new URL(raw);
      const fromUrl = Number(url.port);
      if (fromUrl > 0) return fromUrl;
    } catch {
      /* fall through to the explicit port / profile default */
    }
  }
  const explicit = Number(process.env.HARNESS_PY_PORT);
  return explicit > 0 ? explicit : profile.harnessPort;
})();
if (pyPort !== profile.appPort) {
  console.log(`Checking if Python runtime port ${pyPort} is in use...`);
  killedProcess = killPort(pyPort, 'Python runtime') || killedProcess;
}

console.log('Port check completed.');

// If a process was terminated, wait 800ms to allow the OS to release file handles.
if (killedProcess) {
  console.log('Waiting for OS to release port/file locks...');
  const start = Date.now();
  while (Date.now() - start < 800) {
    // Synchronous sleep block.
  }
}

// 3. Clean the .next cache ONLY when explicitly requested (BE_CLEAR_CACHE=1).
//    Wiping .next on every dev start forced every route to recompile from
//    scratch (40s+ per API route), making the whole site feel broken. The
//    persistent webpack cache makes restarts near-instant instead.
if (process.env.BE_CLEAR_CACHE === '1') {
  try {
    const nextCacheDir = path.join(root, profile.distDir);
    if (fs.existsSync(nextCacheDir)) {
      console.log(`Clearing Next.js build cache directory (${profile.distDir})...`);
      fs.rmSync(nextCacheDir, { recursive: true, force: true });
      console.log('Next.js build cache cleared.');
    }
  } catch (cacheErr) {
    console.warn(`Warning: Could not clear ${profile.distDir} directory:`, cacheErr.message);
  }
}
