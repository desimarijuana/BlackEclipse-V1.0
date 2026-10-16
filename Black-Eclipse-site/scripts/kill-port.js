const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const root = path.join(__dirname, '..');

// ── port resolution ──────────────────────────────────────────────────────────
// Resolve an env var from the process env OR `.env`. Next.js loads `.env` for
// the app, but this pre-hook is a bare node process, so read the file as well.
function envValue(key) {
  if (process.env[key]) return process.env[key];
  try {
    const text = fs.readFileSync(path.join(root, '.env'), 'utf8');
    for (const line of text.split(/\r?\n/)) {
      const m = line.match(/^\s*([A-Za-z0-9_]+)\s*=\s*(.*?)\s*$/);
      if (m && m[1] === key) return m[2].replace(/^["']|["']$/g, '').trim();
    }
  } catch {
    // No .env — fall through to the default.
  }
  return undefined;
}

// The Python runtime port, resolved the SAME way as
// `src/lib/harness/python-runtime.ts` so the pre-hook clears the port the front
// door will actually spawn uvicorn on.
function runtimePort() {
  const url = envValue('HARNESS_PY_URL');
  if (url) {
    try {
      const parsed = new URL(url);
      if (parsed.port) return Number(parsed.port);
    } catch {
      // Malformed URL — fall through.
    }
  }
  const explicit = Number(envValue('HARNESS_PY_PORT'));
  return Number.isFinite(explicit) && explicit > 0 ? explicit : 8765;
}

// ── kill listeners on a port ─────────────────────────────────────────────────
function pidsListeningOn(port) {
  const pids = new Set();
  try {
    if (process.platform === 'win32') {
      const output = execSync('netstat -ano', { encoding: 'utf8' });
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
      execSync(process.platform === 'win32' ? `taskkill /F /PID ${pid}` : `kill -9 ${pid}`);
      killed = true;
    } catch {
      // Already gone.
    }
  }
  return killed;
}

// 1. Clear the Next.js port (releases locks on the .next directory).
console.log('Checking if port 3000 is in use...');
let killedProcess = killPort(3000, 'Next.js');

// 2. Clear the Python runtime port. A runtime spawned as a child of a previous
//    `npm run dev`/`npm start` survives the parent on Windows and keeps holding
//    this port; a fresh runtime then fails to bind (`WinError 10048`) and its
//    boot reconciliation would orphan the runs the survivor is executing.
//    Clearing it here means every launch starts from a clean runtime.
const pyPort = runtimePort();
if (pyPort !== 3000) {
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
    const nextCacheDir = path.join(root, '.next');
    if (fs.existsSync(nextCacheDir)) {
      console.log('Clearing Next.js build cache directory (.next)...');
      fs.rmSync(nextCacheDir, { recursive: true, force: true });
      console.log('Next.js build cache cleared.');
    }
  } catch (cacheErr) {
    console.warn('Warning: Could not clear .next directory:', cacheErr.message);
  }
}
