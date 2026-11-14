// Shared cross-platform server helpers used by the desktop server
// (scripts/desktop-server.js), the build wrappers and the global `black` CLI
// (bin/black.js). The browser lane that used to share them was deleted.
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
// One production build at a time, machine-wide. `next build` wipes and rewrites
// the SAME `.next` directory, so two concurrent builds corrupt each other's
// output (and the app then fails to start with no useful error). The file lives
// OUTSIDE `.next` because the build deletes that directory. It is advisory: a
// build invoked as raw `npx next build` cannot take it, but every supported
// entry point (`npm run build`, `desktop:build:dev`, `desktop:refresh`,
// `desktop:promote`, the desktop icon) goes through this lock.
const BUILD_LOCK = path.join(root, ".next-build.lock");
const BUILD_WAIT_MS = 45 * 60 * 1000;

function pidAlive(pid) {
  try {
    process.kill(pid, 0);
    return true;
  } catch (err) {
    // EPERM means the process exists but belongs to someone else.
    return Boolean(err && err.code === "EPERM");
  }
}

function sleepSync(ms) {
  try {
    Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, ms);
  } catch {
    const end = Date.now() + ms;
    while (Date.now() < end) {
      /* last-resort busy wait on platforms without SharedArrayBuffer */
    }
  }
}

function readBuildLock() {
  try {
    const parsed = JSON.parse(fs.readFileSync(BUILD_LOCK, "utf8"));
    if (parsed && Number.isFinite(parsed.pid) && Number.isFinite(parsed.at)) return parsed;
  } catch {
    /* no lock, or a half-written one */
  }
  return null;
}

/** The build currently running, or null. Cleans up a lock whose owner is gone. */
function buildInProgress() {
  const held = readBuildLock();
  if (!held) return null;
  if (!pidAlive(held.pid)) {
    try {
      fs.rmSync(BUILD_LOCK, { force: true });
    } catch {
      /* best effort */
    }
    return null;
  }
  return held;
}

/**
 * Take the build lock, waiting for any running build to finish first.
 * Returns a release function, or null when the wait timed out.
 */
function acquireBuildLock({ waitMs = BUILD_WAIT_MS, onWait } = {}) {
  const start = Date.now();
  let announced = -1;
  for (;;) {
    try {
      const fd = fs.openSync(BUILD_LOCK, "wx");
      fs.writeSync(fd, JSON.stringify({ pid: process.pid, at: Date.now() }));
      fs.closeSync(fd);
      return () => {
        try {
          const held = readBuildLock();
          if (held && held.pid === process.pid) fs.rmSync(BUILD_LOCK, { force: true });
        } catch {
          /* best effort */
        }
      };
    } catch (err) {
      if (!err || err.code !== "EEXIST") {
        // The lock is a safety net, not a prerequisite: never refuse to build
        // because the filesystem cannot create the file.
        return () => {};
      }
    }

    const held = readBuildLock();
    if (!held || !pidAlive(held.pid)) {
      try {
        fs.rmSync(BUILD_LOCK, { force: true });
      } catch {
        /* best effort */
      }
      continue;
    }

    const waited = Date.now() - start;
    if (waited > waitMs) return null;
    // Report about once per 15s, not once per poll.
    const bucket = Math.floor(waited / 15_000);
    if (onWait && bucket !== announced) {
      announced = bucket;
      onWait(held, waited);
    }
    sleepSync(750);
  }
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

/** Record the current source as built (after any successful `next build`). */
function markBuilt() {
  fs.mkdirSync(nextDir, { recursive: true });
  fs.writeFileSync(hashFile, sourceHash());
}

/**
 * Run `next build` (serialized) and record the source hash on success.
 *
 * Returns true when a build ran, false when another build finished this exact
 * source while we were waiting, so the work was already done.
 */
function build(options = {}) {
  const release = acquireBuildLock({
    waitMs: options.waitMs,
    onWait:
      options.onWait ||
      ((held, waited) => {
        console.log(
          `[build] another production build is running (pid ${held.pid}, ${Math.round(waited / 1000)}s) — waiting for it to finish…`
        );
      }),
  });
  if (!release) throw new Error("timed out waiting for another production build to finish");
  try {
    if (!needsBuild()) return false;
    // Hash the sources as they are WHEN THE BUILD STARTS. Writing the hash
    // computed at the end records edits that `next build` never compiled — a
    // file changed mid-build then looked "already built" on the next refresh,
    // and a stale chunk was promoted (the release whose Stop control was
    // missing). Recording the start hash means such a build is honestly stale.
    const startedHash = sourceHash();
    execSync("npx next build", { cwd: root, stdio: "inherit", env: process.env });
    fs.mkdirSync(nextDir, { recursive: true });
    fs.writeFileSync(hashFile, startedHash);
    return true;
  } finally {
    release();
  }
}

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
          // Content, not mtime: editors that rewrite a file without changing it
          // (save-all, formatters) must not invalidate an expensive production
          // build.
          hash.update(path.relative(root, full));
          hash.update(fs.readFileSync(full));
        } catch {}
      }
    }
  };
  for (const t of targets) walk(path.join(root, t));
  return hash.digest("hex");
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
    windowsHide: true,
  });
  child.on("exit", (code) => process.exit(code ?? 0));
}

/** Start `next dev` in the FOREGROUND. */
function startDev(port) {
  // `next.config.ts` routes dev output to `.next-dev` (via NODE_ENV) so a dev
  // run never deletes the cached production build in `.next`.
  const child = spawn(process.execPath, [nextBin(), "dev", "-p", String(port)], {
    cwd: root,
    stdio: "inherit",
    env: process.env,
    windowsHide: true,
  });
  child.on("exit", (code) => process.exit(code ?? 0));
}

/** Probe whether something answers HTTP on the port. */
async function isUp(port, timeoutMs = 4000) {
  try {
    // Do not follow redirects: a legacy browser-path server sets
    // BE_CANONICAL_HOST, so 127.0.0.1:port could answer with a 307 to a TLS
    // hostname. Following it makes Node reject the locally-trusted certificate
    // and report a live server as down (which then used to trigger an
    // unnecessary restart). The desktop channel never redirects.
    const res = await fetch(`http://127.0.0.1:${port}/`, {
      signal: AbortSignal.timeout(timeoutMs),
      redirect: "manual",
    });
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
  markBuilt,
  build,
  buildInProgress,
  acquireBuildLock,
  nextBin,
  startServer,
  startDev,
  isUp,
};