// Who is holding node_modules, and would replacing it destroy the install?
//
// Windows keeps a loaded `.node` binary locked for the lifetime of the process
// that loaded it. The running Eclipse server loads `next-swc` and `skia`, so
// `npm ci` cannot replace them. That matters because `npm ci` deletes
// node_modules FIRST: it empties the tree, then fails on the locked file, and
// the app is left with no dependencies at all.
//
// So the updater asks this module before it touches anything. A rename probe is
// the test — a loaded DLL cannot be renamed, an idle one can — and the probe
// always renames back. When something is locked, the caller waits, then either
// stops the app it owns or fails with the install still intact.

"use strict";

const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");

const PROBE_SUFFIX = ".be-lock-probe";
const MAX_NATIVE_FILES = 4000;

function collectNativeFiles(dir, out, depth) {
  if (out.length >= MAX_NATIVE_FILES || depth > 12) return;
  let entries;
  try {
    entries = fs.readdirSync(dir, { withFileTypes: true });
  } catch {
    return;
  }
  for (const entry of entries) {
    if (out.length >= MAX_NATIVE_FILES) return;
    if (entry.name.startsWith(".")) continue;
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      // Skip the nested caches that never contain loadable binaries.
      if (entry.name === "node_modules") continue;
      collectNativeFiles(full, out, depth + 1);
    } else if (entry.name.endsWith(".node")) {
      out.push(full);
    }
  }
}

/**
 * A file is locked when it cannot be renamed. Restoring the name is best-effort
 * but never optional: a failed restore would leave the install broken, so there
 * is a copy fallback behind the rename.
 */
function probeLocked(file) {
  const probe = `${file}${PROBE_SUFFIX}`;
  try {
    fs.renameSync(file, probe);
  } catch {
    return true;
  }
  try {
    fs.renameSync(probe, file);
  } catch {
    try {
      fs.copyFileSync(probe, file);
      fs.unlinkSync(probe);
    } catch {
      /* leave the probe beside it; a reinstall replaces both */
    }
  }
  return false;
}

/** Native modules under `root/node_modules` that a running process still holds. */
function lockedNativeModules(root) {
  const dir = path.join(root, "node_modules");
  if (!fs.existsSync(dir)) return [];
  const files = [];
  collectNativeFiles(dir, files, 0);
  return files.filter(probeLocked).map((file) => path.relative(root, file));
}

/** Poll until nothing is locked or the deadline passes. True when free. */
function waitForNativeUnlock(root, timeoutMs = 30000, intervalMs = 500) {
  const deadline = Date.now() + timeoutMs;
  for (;;) {
    if (lockedNativeModules(root).length === 0) return true;
    if (Date.now() >= deadline) return false;
    sleep(intervalMs);
  }
}

function sleep(ms) {
  Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, ms);
}

/**
 * Parent chain of `pid`, nearest first. null on any failure so callers can
 * choose the safe answer instead of guessing.
 */
function ancestorsOf(pid) {
  try {
    if (process.platform === "win32") {
      const script =
        "Get-CimInstance Win32_Process | Select-Object ProcessId,ParentProcessId | ConvertTo-Json -Compress";
      const out = spawnSync("powershell", ["-NoProfile", "-Command", script], {
        encoding: "utf8",
        windowsHide: true,
        maxBuffer: 16 * 1024 * 1024,
      });
      if (out.status !== 0 || !out.stdout) return null;
      const parsed = JSON.parse(out.stdout);
      const rows = Array.isArray(parsed) ? parsed : [parsed];
      const parents = new Map();
      for (const row of rows) {
        const id = Number(row && row.ProcessId);
        if (Number.isFinite(id)) parents.set(id, Number(row.ParentProcessId) || 0);
      }
      const chain = [];
      let cursor = Number(pid);
      for (let i = 0; i < 64 && cursor > 0; i++) {
        chain.push(cursor);
        cursor = parents.get(cursor) || 0;
      }
      return chain;
    }
    const chain = [];
    let cursor = Number(pid);
    for (let i = 0; i < 64 && cursor > 0; i++) {
      chain.push(cursor);
      const out = spawnSync("ps", ["-o", "ppid=", "-p", String(cursor)], { encoding: "utf8" });
      const parent = Number((out.stdout || "").trim());
      cursor = Number.isFinite(parent) ? parent : 0;
    }
    return chain;
  } catch {
    return null;
  }
}

/**
 * Is `pid` an ancestor of `childPid`? When the tree cannot be read the answer is
 * TRUE: kill-tree commands follow parent links, so assuming "related" is what
 * keeps a process from shooting its own parent.
 */
function isAncestorOf(pid, childPid = process.pid) {
  const target = Number(pid);
  if (!Number.isFinite(target) || target <= 0) return false;
  const chain = ancestorsOf(childPid);
  if (!chain) return true;
  return chain.includes(target);
}

module.exports = {
  lockedNativeModules,
  waitForNativeUnlock,
  isAncestorOf,
  ancestorsOf,
};
