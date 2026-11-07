// Two run profiles: development and production.
//
// They are deliberately separate PROCESS TREES, not just a NODE_ENV flag:
//
//   development  `npm run dev`   Next dev (Turbopack) on 3000, no proxy,
//                               harness on 8765, isolated runtime databases
//                               under `.black-eclipse/dev/`.
//   production   `npm run up`    built Next server on 3100 behind the local
//                               proxy (http://blackeclipse), harness on 8766,
//                               the real runtime databases.
//
// Why distinct ports: both can run at the same time. Before this split the
// pre-hooks killed port 3000 and the harness port unconditionally, so starting
// dev tore down the running production server (and vice versa).
//
// Every value is overridable from the environment. The profile-specific names
// win over a generic PORT so a `.env` written for one environment can never
// silently move the other one onto the same port.

const path = require("path");
const fs = require("fs");

const ROOT = path.join(__dirname, "..", "..");

function port(value, fallback) {
  const n = Number(value);
  return Number.isFinite(n) && n > 0 ? n : fallback;
}

function withoutEmpty(env) {
  const out = {};
  for (const [key, value] of Object.entries(env)) {
    if (value !== undefined && value !== null && value !== "") out[key] = String(value);
  }
  return out;
}

const DEV = {
  id: "dev",
  label: "development",
  appPort: port(process.env.BE_DEV_PORT, 3000),
  harnessPort: port(process.env.BE_DEV_HARNESS_PORT, 8765),
  distDir: ".next-dev",
  // Dev is addressed directly (http://localhost:3000). No reverse proxy and no
  // canonical-host redirect, so it never forwards the browser to production.
  proxy: false,
  canonical: false,
  command: "dev",
};

const PROD = {
  id: "prod",
  label: "production",
  // BE_PROD_PORT wins; PORT is honored for a caller that explicitly exports it
  // (containers), but the default stays off the dev port so both can coexist.
  appPort: port(process.env.BE_PROD_PORT, port(process.env.PORT, 3100)),
  harnessPort: port(process.env.BE_PROD_HARNESS_PORT, 8766),
  distDir: ".next",
  proxy: true,
  canonical: true,
  command: "start",
};

function profileFor(mode) {
  return String(mode || "").toLowerCase() === "dev" ? DEV : PROD;
}

/**
 * Child-process environment for a profile. These override anything Next would
 * read from `.env`, which is what keeps the two servers from converging on the
 * same ports or the same agent-memory databases.
 */
function childEnv(profile) {
  const base = { ...process.env };
  delete base.BE_CANONICAL_HOST;
  // An operator who sets a harness address in the environment means it: that is
  // the documented override, and it is the only way to move the runtime off a
  // port something else already owns. `.env` is read by Next, not by this
  // launcher, so this cannot leak a profile's default into the other profile.
  return {
    ...base,
    ...withoutEmpty({
      PORT: profile.appPort,
      HARNESS_PY_URL: process.env.HARNESS_PY_URL || `http://127.0.0.1:${profile.harnessPort}`,
      HARNESS_PY_HOST: process.env.HARNESS_PY_HOST || "127.0.0.1",
      HARNESS_PY_PORT: process.env.HARNESS_PY_PORT || profile.harnessPort,
      HARNESS_CALLBACK_URL: `http://127.0.0.1:${profile.appPort}`,
      NEXT_DIST_DIR: profile.distDir,
      BE_PROFILE: profile.id,
    }),
    ...(profile.id === "dev" ? devDataEnv() : {}),
  };
}

/**
 * Development runtime state lives under `.black-eclipse/dev/` so feature work
 * cannot pollute the production agent memory, evolution history, or recovery
 * ledger. Market data (`jdds.db`) and the workspace tree are shared on purpose:
 * dev should read the same JDdS snapshot instead of copying a 60 MB vault.
 */
function devDataEnv() {
  const dir = path.join(ROOT, ".black-eclipse", "dev");
  // sqlite3.connect does not create missing parent directories.
  try {
    fs.mkdirSync(dir, { recursive: true });
  } catch {}
  return withoutEmpty({
    AGENT_MEMORY_DB_PATH: path.join(dir, "agent-memory.db"),
    ECLIPSE_MEMORY_DB_PATH: path.join(dir, "eclipse-memory.db"),
    BE_DATA_DIR: dir,
    // Market + journal data stays shared with the real snapshot: BE_DATA_DIR
    // above would otherwise make `src/lib/db.ts` open an empty
    // `.black-eclipse/dev/jdds.db` with no schema. `BE_DB_PATH` is the
    // established single-file override (doctor.js / db-guard.js honour it).
    BE_DB_PATH: path.join(ROOT, "jdds.db"),
  });
}

module.exports = {
  ROOT,
  DEV,
  PROD,
  profileFor,
  childEnv,
  devDataEnv,
};
