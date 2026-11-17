// ── Scrub local state out of an assembled app directory ────────────────────
//
// WHY: `desktop-package.js` copies whole source trees (`python/`, `config/`,
// `skills/`) into the installer payload with `fs.cpSync`. Those trees also hold
// state that belongs to the BUILD MACHINE, not to the release:
//
//   python/.black-eclipse/channels/secret.key  channel-encryption key material
//   python/csess_*/trajectory.json             the author's own agent sessions
//   python/__pycache__ / .pytest_cache         compiled caches
//   any *.db, .env, mcp-servers.json, *.log    runtime vault, secrets, local paths
//
// Shipping them leaks the author's data and (worse) gives every install the same
// channel key. The standalone payload already prunes its own tree
// (`desktop-payload.js`), but the app-root copies happen afterwards, so this is
// the second, independent gate. `assertNoLocalState()` runs after the seed is
// created and fails the build rather than producing a leaking installer.
//
// The single allowed database is the freshly generated `seed/jdds.db`.

const fs = require("fs");
const path = require("path");

/** Directories (by name, at any depth) that are build-machine state. */
const PURGE_DIRS = [
  ".black-eclipse",
  "__pycache__",
  ".pytest_cache",
  ".ipynb_checkpoints",
  ".mypy_cache",
  ".ruff_cache",
  ".venv",
];

/** Directory-name prefixes that are per-run session output. */
const PURGE_DIR_PREFIXES = ["csess_"];

/** File names / suffixes that are local state, never source. */
const PURGE_FILE_PATTERNS = [
  /^\.env($|\.)/i, // .env, .env.local, .env.production — NOT .env.example
  /^mcp-servers\.json/i,
  /^\.connector-key$/i,
  /^agent-memory\.db/i,
  /^eclipse-memory\.db/i,
  /^jdds\.db/i,
  /\.db$/i,
  /\.db-(wal|shm|journal)$/i,
  /\.sqlite3?$/i,
  /\.(db|sqlite3)-(wal|shm)$/i,
  /\.sql$/i,
  /\.log$/i,
  /^first-run-notice-shown$/i,
];

/** `*` dirs such as `black_eclipse_harness.egg-info`. */
const PURGE_DIR_SUFFIXES = [".egg-info"];

/** The only database a packaged install may contain. */
const ALLOWED_DB = path.join("seed", "jdds.db");

function isEnvExample(name) {
  return /^\.env\.example$/i.test(name);
}

function shouldPurgeDir(name) {
  if (PURGE_DIRS.includes(name)) return true;
  if (PURGE_DIR_PREFIXES.some((p) => name.startsWith(p))) return true;
  return PURGE_DIR_SUFFIXES.some((s) => name.endsWith(s));
}

function shouldPurgeFile(name, relPosix) {
  if (isEnvExample(name)) return false;
  if (relPosix === ALLOWED_DB.split(path.sep).join("/")) return false;
  return PURGE_FILE_PATTERNS.some((re) => re.test(name));
}

function sizeOf(target) {
  try {
    const st = fs.lstatSync(target);
    if (st.isFile()) return st.size;
    if (!st.isDirectory()) return 0;
  } catch {
    return 0;
  }
  let total = 0;
  for (const entry of fs.readdirSync(target)) total += sizeOf(path.join(target, entry));
  return total;
}

/**
 * Delete local state below `root`. Returns `{ removed, bytes }` where `removed`
 * is the names of the top-most paths deleted (useful for a log line).
 */
function scrubAppState(root) {
  const removed = [];
  let bytes = 0;

  const walk = (dir) => {
    let entries;
    try {
      entries = fs.readdirSync(dir, { withFileTypes: true });
    } catch {
      return;
    }
    for (const entry of entries) {
      const full = path.join(dir, entry.name);
      const rel = path.relative(root, full).split(path.sep).join("/");
      if (entry.isDirectory()) {
        if (shouldPurgeDir(entry.name)) {
          bytes += sizeOf(full);
          removed.push(rel);
          try {
            fs.rmSync(full, { recursive: true, force: true });
          } catch {
            /* locked file: assertNoLocalState() reports it */
          }
          continue;
        }
        walk(full);
        continue;
      }
      if (shouldPurgeFile(entry.name, rel)) {
        bytes += sizeOf(full);
        removed.push(rel);
        try {
          fs.rmSync(full, { force: true });
        } catch {
          /* reported by the assert */
        }
      }
    }
  };

  walk(root);
  return { removed, bytes };
}

/**
 * Every local-state path still present below `root`. An empty array means the
 * payload is safe to hand to a user.
 */
function findLocalState(root) {
  const found = [];
  const walk = (dir) => {
    let entries;
    try {
      entries = fs.readdirSync(dir, { withFileTypes: true });
    } catch {
      return;
    }
    for (const entry of entries) {
      const full = path.join(dir, entry.name);
      const rel = path.relative(root, full).split(path.sep).join("/");
      if (entry.isDirectory()) {
        if (shouldPurgeDir(entry.name)) found.push(rel + "/");
        else walk(full);
        continue;
      }
      if (shouldPurgeFile(entry.name, rel)) found.push(rel);
    }
  };
  walk(root);
  return found;
}

/**
 * Fail the build when local state survived the scrub. `fail(message)` is the
 * caller's reporter so the CLI keeps one error style.
 */
function assertNoLocalState(root, fail) {
  const found = findLocalState(root);
  if (found.length === 0) return;
  const shown = found.slice(0, 12).join(", ");
  const more = found.length > 12 ? ` (+${found.length - 12} more)` : "";
  fail(
    `Refusing to package local state from this machine: ${shown}${more}. ` +
      `These are runtime files (keys, sessions, caches, databases) and must never ship.`
  );
}

module.exports = {
  scrubAppState,
  findLocalState,
  assertNoLocalState,
  PURGE_DIRS,
  PURGE_DIR_PREFIXES,
  PURGE_FILE_PATTERNS,
  ALLOWED_DB,
  shouldPurgeFile,
  shouldPurgeDir,
};
