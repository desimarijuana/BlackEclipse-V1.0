// Per-channel data preparation for the desktop app.
//
// Stable keeps the historical checkout data directory (repo root in a checkout,
// %LOCALAPPDATA%\BlackEclipse\data in an install). Dev is always isolated under
// `.black-eclipse/desktop-dev/`, so testing a feature can never write the real
// journals, memory or market rows.
//
// Dev still needs a usable JDdS snapshot (otherwise every screen is empty and
// the agent has no data). The first dev launch takes a CONSISTENT SQLite
// snapshot of the real `jdds.db` with `VACUUM INTO` — copying the `.db` alone
// while the app is live loses the newest WAL transactions. It is a one-time
// copy; Dev never writes back to the source.

const fs = require("fs");
const path = require("path");

/** True when the path exists and is a non-empty regular file. */
function hasFile(file) {
  try {
    return fs.statSync(file).size > 0;
  } catch {
    return false;
  }
}

/**
 * Create the Dev channel's data directory and seed its market snapshot.
 * No-op for Stable. Best-effort: a missing source or unavailable SQLite binding
 * must not stop the app from opening (it will simply have no market data).
 */
function prepareChannelData(channel, root) {
  if (!channel || channel.id !== "dev") return { prepared: false, reason: "not-dev" };

  const dataDir = channel.dataDir;
  fs.mkdirSync(dataDir, { recursive: true });

  const target = path.join(dataDir, "jdds.db");
  if (hasFile(target)) return { prepared: false, reason: "exists", path: target };

  const source = path.join(root, "jdds.db");
  if (!hasFile(source)) return { prepared: false, reason: "no-source", path: target };

  let Database;
  try {
    // The same native binding the app already uses; no new dependency.
    Database = require("better-sqlite3");
  } catch (err) {
    return { prepared: false, reason: `no-sqlite (${err && err.message})`, path: target };
  }

  fs.rmSync(target, { force: true });
  const db = new Database(source, { readonly: true, fileMustExist: true });
  try {
    const escaped = target.replace(/'/g, "''");
    db.exec(`VACUUM INTO '${escaped}'`);
    return { prepared: true, reason: "snapshot", path: target, bytes: fs.statSync(target).size };
  } finally {
    db.close();
  }
}

module.exports = { prepareChannelData };
