const { execSync } = require('child_process');
const fs = require('fs');
const path = require('path');

// 1. First check and kill any process running on port 3000 (releasing locks on .next directory)
let killedProcess = false;
try {
  console.log('Checking if port 3000 is in use...');
  if (process.platform === 'win32') {
    // Windows: Find PID using netstat
    const output = execSync('netstat -ano', { encoding: 'utf8' });
    const lines = output.split('\n');
    const pids = new Set();
    
    for (const line of lines) {
      if (line.includes(':3000') && line.includes('LISTENING')) {
        const parts = line.trim().split(/\s+/);
        const pid = parts[parts.length - 1];
        if (pid && pid !== '0') {
          pids.add(pid);
        }
      }
    }
    
    for (const pid of pids) {
      console.log(`Killing process on port 3000 (PID: ${pid})...`);
      try {
        execSync(`taskkill /F /PID ${pid}`);
        killedProcess = true;
      } catch (e) {
        // Ignore error if process already terminated
      }
    }
  } else {
    // Unix (macOS/Linux)
    try {
      const pid = execSync('lsof -t -i:3000', { encoding: 'utf8' }).trim();
      if (pid) {
        console.log(`Killing process on port 3000 (PID: ${pid})...`);
        execSync(`kill -9 ${pid}`);
        killedProcess = true;
      }
    } catch (e) {
      // lsof returns non-zero code if port is not in use
    }
  }
} catch (error) {
  // Keep silent so it doesn't block Next.js if no port conflicts exist
}
console.log('Port 3000 check completed.');

// If a process was terminated, wait 800ms to allow OS to release file handles
if (killedProcess) {
  console.log('Waiting for OS to release file locks on .next directory...');
  const start = Date.now();
  while (Date.now() - start < 800) {
    // Synchronous sleep block
  }
}

// 2. Clean .next cache ONLY when explicitly requested (BE_CLEAR_CACHE=1).
//    Wiping .next on every dev start forced every route to recompile from
//    scratch (40s+ per API route), making the whole site feel broken. The
//    persistent webpack cache makes restarts near-instant instead.
if (process.env.BE_CLEAR_CACHE === '1') {
  try {
    const nextCacheDir = path.join(__dirname, '../.next');
    if (fs.existsSync(nextCacheDir)) {
      console.log('Clearing Next.js build cache directory (.next)...');
      fs.rmSync(nextCacheDir, { recursive: true, force: true });
      console.log('Next.js build cache cleared.');
    }
  } catch (cacheErr) {
    console.warn('Warning: Could not clear .next directory:', cacheErr.message);
  }
}

