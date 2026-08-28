// Shared cross-platform server helpers used by both `npm run up`
// (scripts/up.js) and the global `black` CLI (bin/black.js).
//
// Everything here must work on Windows, macOS, and Linux with zero
// native dependencies — pure Node.js + whatever ships with the OS.

const { execSync, spawn } = require("child_process");
const fs = require("fs");
const path = require("path");
const crypto = require("crypto");

const root = path.join(__dirname, "..", "..");
const nextDir = path.join(root, ".next");
const hashFile = path.join(nextDir, ".build-hash");

/**
 * Kill whatever process is LISTENING on `port`. Works on all three OSes.
 * Returns true when at least one process was terminated.
 */
function killPort(port) {
  let killed = false;
  const pids = new Set();
  try {
    if (process.platform === "win32") {
      const output = execSync("netstat -ano", { encoding: "utf8" });
      for (const line of output.split("\n")) {
        const cols = line.trim().split(/\s+/);
        // [proto, local, remote, state, pid] — local ends with ":port"
        if (cols.length >= 5 && cols[1] && cols[1].endsWith(`:${port}`) && cols[3] === "LISTENING") {
          const pid = cols[4];
          if (pid && pid !== "0") pids.add(pid);
        }
      }
    } else {
      // macOS + Linux: lsof (present by default on macOS; common on Linux).
      try {
        const out = execSync(`lsof -t -i tcp:${port} -s tcp:listen`, { encoding: "utf8" });
        for (const pid of out.split("\n")) {
          if (pid.trim()) pids.add(pid.trim());
        }
      } catch {
        // Linux fallback when lsof is missing.
        try {
          execSync(`fuser -k ${port}/tcp`, { stdio: "ignore" });
          killed = true;
        } catch {}
      }
    }
    for (const pid of pids) {
      try {
        if (process.platform === "win32") execSync(`taskkill /F /PID ${pid}`, { stdio: "ignore" });
        else process.kill(Number(pid), "SIGKILL");
        killed = true;
      } catch {}
    }
  } catch {}
  if (killed) {
    // Let the OS release file locks (Windows holds .next file handles).
    const start = Date.now();
    while (Date.now() - start < 800) {
      // brief synchronous pause — mirrors the original kill-port.js behavior
    }
  }
  return killed;
}

/** Hash of every source file that affects the production build. */
function sourceHash() {
  const targets = [
    "src",
    "prisma",
    "public",
    "next.config.ts",
    "package.json",
    "tsconfig.json",
    "postcss.config.mjs",
    "eslint.config.mjs",
  ];
  const hash = crypto.createHash("sha256");
  const skip = new Set(["node_modules", ".next", "generated", "__pycache__"]);
  const walk = (dir) => {
    let entries;
    try {
      entries = fs.readdirSync(dir, { withFileTypes: true });
    } catch {
      return;
    }
    for (const e of entries) {
      const full = path.join(dir, e.name);
      if (e.isDirectory()) {
        if (skip.has(e.name)) continue;
        walk(full);
      } else {
        try {
          const st = fs.statSync(full);
          hash.update(path.relative(root, full));
          hash.update(String(st.mtimeMs));
          hash.update(String(st.size));
        } catch {}
      }
    }
  };
  for (const t of targets) walk(path.join(root, t));
  return hash.digest("hex");
}

/** Whether a production build is needed (missing or source changed). */
function needsBuild() {
  if (process.env.BE_FORCE_BUILD === "1") return true;
  if (!fs.existsSync(path.join(nextDir, "BUILD_ID"))) return true;
  if (fs.existsSync(hashFile)) {
    const last = fs.readFileSync(hashFile, "utf8").trim();
    if (last === sourceHash()) return false;
  }
  return true;
}

/** Run `next build` and record the source hash on success. */
function build() {
  execSync("npx next build", { cwd: root, stdio: "inherit", env: process.env });
  fs.mkdirSync(nextDir, { recursive: true });
  fs.writeFileSync(hashFile, sourceHash());
}

/** Path to Next.js's JS entrypoint (spawnable without a shell). */
function nextBin() {
  const p = path.join(root, "node_modules", "next", "dist", "bin", "next");
  if (!fs.existsSync(p)) {
    console.error(`[black] Next.js not found in ${root} — run "npm install" there first.`);
    process.exit(1);
  }
  return p;
}

/** Start `next start` in the FOREGROUND (Ctrl+C stops it). */
function startServer(port) {
  const child = spawn(process.execPath, [nextBin(), "start", "-p", String(port)], {
    cwd: root,
    stdio: "inherit",
    env: process.env,
  });
  child.on("exit", (code) => process.exit(code ?? 0));
}

/** Start `next dev` in the FOREGROUND. */
function startDev(port) {
  const child = spawn(process.execPath, [nextBin(), "dev", "-p", String(port)], {
    cwd: root,
    stdio: "inherit",
    env: process.env,
  });
  child.on("exit", (code) => process.exit(code ?? 0));
}

/** Probe whether something answers HTTP on the port. */
async function isUp(port) {
  try {
    const res = await fetch(`http://127.0.0.1:${port}/`, { signal: AbortSignal.timeout(4000) });
    return res.status;
  } catch {
    return null;
  }
}

module.exports = {
  root,
  nextDir,
  killPort,
  sourceHash,
  needsBuild,
  build,
  nextBin,
  startServer,
  startDev,
  isUp,
};