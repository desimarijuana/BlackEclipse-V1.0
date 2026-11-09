/*
 * Reset scopes — one implementation for the Settings danger zone and the CLI.
 *
 *   onboarding  config-only: remove onboarding_v1 (re-ask the questions)
 *   setup       config-only: remove onboarding + source prefs + LLM + key vault
 *   factory     destructive: all personal databases + runtime state + backups
 *
 * Factory reset is NEVER executed from inside the running web process. The API
 * writes a marker; doctor.js consumes it before the DB guard opens jdds.db. The
 * CLI stops the servers, backs up (optional), then runs the existing
 * wipe-personal-data.js primitive.
 */
"use strict";

const fs = require("fs");
const path = require("path");
const { execFileSync } = require("child_process");

const SITE = path.join(__dirname, "..", "..");
const REPO = path.join(SITE, "..");
const WIPE_SCRIPT = path.join(SITE, "scripts", "wipe-personal-data.js");
const DB_NAMES = ["jdds.db", "agent-memory.db", "eclipse-memory.db"];

function readDotEnvValue(key) {
  try {
    const text = fs.readFileSync(path.join(SITE, ".env"), "utf8");
    for (const line of text.split(/\r?\n/)) {
      const m = /^\s*([A-Za-z0-9_]+)\s*=\s*(.*)\s*$/.exec(line);
      if (m && m[1] === key) return m[2].replace(/^["']|["']$/g, "");
    }
  } catch {
    /* no .env */
  }
  return undefined;
}

function dataDir() {
  if (process.env.BE_DATA_DIR) return path.resolve(process.env.BE_DATA_DIR);
  const fromEnv = readDotEnvValue("BE_DATA_DIR");
  return fromEnv ? path.resolve(fromEnv) : SITE;
}

function dbPath() {
  return process.env.BE_DB_PATH
    ? path.resolve(process.env.BE_DB_PATH)
    : path.join(dataDir(), "jdds.db");
}

function openDb() {
  const Database = require("better-sqlite3");
  return new Database(dbPath());
}

function deleteConfigKeys(keys) {
  let removed = 0;
  let db;
  try {
    db = openDb();
    const stmt = db.prepare("DELETE FROM SystemConfig WHERE key = ?");
    const tx = db.transaction((list) => {
      for (const key of list) removed += stmt.run(key).changes;
    });
    tx(keys);
    return { removed, dbPath: dbPath() };
  } catch (err) {
    return { removed, dbPath: dbPath(), error: err.message };
  } finally {
    try { db && db.close(); } catch { /* ignore */ }
  }
}

/** Write the explicit "not completed" row. Deleting the row would make an
 *  existing install look like an upgrade and auto-migrate, hiding the gate. */
function setOnboardingPending() {
  let db;
  try {
    db = openDb();
    db.prepare(
      "INSERT INTO SystemConfig (key, value) VALUES (?, ?) " +
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
    ).run("onboarding_v1", JSON.stringify({ completed: false, mode: "personal", version: 1 }));
    return { updated: 1, dbPath: dbPath() };
  } catch (err) {
    return { updated: 0, dbPath: dbPath(), error: err.message };
  } finally {
    try { db && db.close(); } catch { /* ignore */ }
  }
}

function resetOnboarding() {
  return setOnboardingPending();
}

function resetSetup() {
  const cleared = deleteConfigKeys([
    "data_source_prefs_v1",
    "llm_config",
    "provider_keys_v1",
  ]);
  const pending = setOnboardingPending();
  return {
    removed: cleared.removed + pending.updated,
    dbPath: cleared.dbPath,
    error: cleared.error || pending.error,
  };
}

// The app writes the marker under the ACTIVE data dir (dev and prod have
// different ones). Doctor resolves the same value from BE_DATA_DIR before it
// consumes the marker.
function markerPath() {
  return path.join(dataDir(), ".black-eclipse", "reset-request.json");
}

function readMarker() {
  try {
    const raw = fs.readFileSync(markerPath(), "utf8");
    const parsed = JSON.parse(raw);
    if (!parsed || parsed.scope !== "factory") return null;
    return {
      scope: "factory",
      requestedAt: typeof parsed.requestedAt === "string" ? parsed.requestedAt : new Date().toISOString(),
      backup: parsed.backup !== false,
      includeEnv: parsed.includeEnv === true,
      requestedBy: typeof parsed.requestedBy === "string" ? parsed.requestedBy : "unknown",
    };
  } catch {
    return null;
  }
}

function requestFactoryReset({ backup = true, includeEnv = false, requestedBy = "cli" } = {}) {
  const marker = {
    scope: "factory",
    requestedAt: new Date().toISOString(),
    backup: backup !== false,
    includeEnv: includeEnv === true,
    requestedBy,
  };
  const markerFile = markerPath();
  fs.mkdirSync(path.dirname(markerFile), { recursive: true });
  fs.writeFileSync(markerFile, JSON.stringify(marker, null, 2), "utf8");
  return { marker, path: markerFile };
}

function clearMarker() {
  try { fs.rmSync(markerPath(), { force: true }); } catch { /* ignore */ }
}

function backupDatabases() {
  const stamp = new Date().toISOString().replace(/[:.]/g, "-");
  // Keep backups OUTSIDE every wipe target (SITE/backups and REPO/_backups are
  // removed by a factory reset). `reset-backups/` at the repo root is not.
  const dest = path.join(REPO, "reset-backups", stamp);
  fs.mkdirSync(dest, { recursive: true });
  const dir = dataDir();
  let copied = 0;
  for (const name of DB_NAMES) {
    for (const suffix of ["", "-wal", "-shm", "-journal"]) {
      const src = path.join(dir, `${name}${suffix}`);
      if (!fs.existsSync(src)) continue;
      fs.copyFileSync(src, path.join(dest, `${name}${suffix}`));
      copied++;
    }
  }
  // Config files that are not databases but are worth keeping.
  for (const name of ["mcp-servers.json", ".connector-key"]) {
    const src = path.join(SITE, name);
    if (fs.existsSync(src)) {
      fs.copyFileSync(src, path.join(dest, name));
      copied++;
    }
  }
  return { dest, copied };
}

function wipe({ includeEnv = false } = {}) {
  const args = [WIPE_SCRIPT, "--confirm=WIPE"];
  if (includeEnv) args.push("--include-env");
  execFileSync(process.execPath, args, { stdio: "inherit", cwd: SITE });
}

/** Boot-time consumer used by doctor.js. Returns a summary or null. */
function consumeFactoryReset({ log = console.log } = {}) {
  const marker = readMarker();
  if (!marker) return null;

  log(`[reset] factory reset requested at ${marker.requestedAt} by ${marker.requestedBy}`);
  let backup = null;
  if (marker.backup) {
    backup = backupDatabases();
    log(`[reset] backup: ${backup.dest} (${backup.copied} file(s))`);
  } else {
    log("[reset] backup skipped (requested)");
  }
  wipe({ includeEnv: marker.includeEnv });
  clearMarker();
  log("[reset] factory reset complete — the app will boot as a new install");
  return { ...marker, backup };
}

/** CLI path: intended to run with the servers stopped. */
function runFactoryReset({ backup = true, includeEnv = false, log = console.log } = {}) {
  let backupResult = null;
  if (backup) {
    backupResult = backupDatabases();
    log(`[reset] backup: ${backupResult.dest} (${backupResult.copied} file(s))`);
  } else {
    log("[reset] backup skipped");
  }
  wipe({ includeEnv });
  clearMarker();
  return { backup: backupResult };
}

function describeTargets() {
  const dir = dataDir();
  const targets = [];
  for (const name of DB_NAMES) {
    for (const suffix of ["", "-wal", "-shm", "-journal"]) {
      const p = path.join(dir, `${name}${suffix}`);
      if (fs.existsSync(p)) targets.push(p);
    }
  }
  for (const p of [
    path.join(SITE, ".black-eclipse"),
    path.join(SITE, "python", ".black-eclipse"),
    path.join(SITE, "backups"),
    path.join(REPO, "_backups"),
    path.join(SITE, "mcp-servers.json"),
    path.join(REPO, "mcp-servers.json"),
    path.join(SITE, ".connector-key"),
    path.join(SITE, ".env"),
  ]) {
    if (fs.existsSync(p)) targets.push(p);
  }
  return targets;
}

module.exports = {
  SITE,
  REPO,
  dataDir,
  dbPath,
  markerPath,
  readMarker,
  clearMarker,
  requestFactoryReset,
  consumeFactoryReset,
  runFactoryReset,
  backupDatabases,
  resetOnboarding,
  resetSetup,
  describeTargets,
  DB_NAMES,
};
