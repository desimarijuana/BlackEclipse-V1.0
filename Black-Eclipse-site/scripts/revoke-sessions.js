#!/usr/bin/env node
// ── Revoke BlackEclipse auth sessions ───────────────────────────────────────
// The incident-response containment step "revoke sessions / disable the user"
// needs a runnable command. Sessions are opaque rows in AuthSession, so
// deleting them logs the user out everywhere immediately.
//
//   node scripts/revoke-sessions.js                     # every session
//   node scripts/revoke-sessions.js --user alice        # one user
//   node scripts/revoke-sessions.js --disable-user alice # revoke + disable
//   node scripts/revoke-sessions.js --list              # who/what exists
//   node scripts/revoke-sessions.js --db path/to/auth.db
//
// The DB path is --db, then HARNESS_AUTH_DB, then .black-eclipse/auth.db.
// Stop the app first only if you also rotate HARNESS_AUTH_SECRET; deleting rows
// takes effect on the next request. Exit 0 = done, 1 = error.
'use strict';

const fs = require('node:fs');
const path = require('node:path');

function parseArgs(argv) {
  const out = { user: null, disableUser: null, list: false, db: null };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--user') out.user = argv[++i];
    else if (a === '--disable-user') out.disableUser = argv[++i];
    else if (a === '--list') out.list = true;
    else if (a === '--db') out.db = argv[++i];
    else if (a === '--help' || a === '-h') out.help = true;
    else throw new Error(`unknown argument: ${a}`);
  }
  return out;
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  if (args.help) {
    console.log(fs.readFileSync(__filename, 'utf8').split('\n').slice(1, 16).join('\n'));
    return 0;
  }
  const dbPath =
    args.db || process.env.HARNESS_AUTH_DB || path.join(process.cwd(), '.black-eclipse', 'auth.db');
  if (!fs.existsSync(dbPath)) {
    console.error(`no auth database at ${dbPath}`);
    return 1;
  }

  const Database = require('better-sqlite3');
  const db = new Database(dbPath);
  try {
    db.pragma('journal_mode = WAL');
    const hasTable = db
      .prepare("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'AuthSession'")
      .get();
    if (!hasTable) {
      console.error(`${dbPath} is not an auth database (no AuthSession table)`);
      return 1;
    }

    if (args.list) {
      const users = db.prepare('SELECT id, username, scope, disabled FROM AuthUser ORDER BY username').all();
      const sessions = db.prepare('SELECT userId, COUNT(*) AS n FROM AuthSession GROUP BY userId').all();
      const byUser = new Map(sessions.map((s) => [s.userId, s.n]));
      for (const u of users) {
        console.log(`${u.username}\t${u.id}\tscope=${u.scope}\tdisabled=${u.disabled}\tsessions=${byUser.get(u.id) || 0}`);
      }
      console.log(`total sessions: ${sessions.reduce((n, s) => n + s.n, 0)}`);
      return 0;
    }

    const username = args.user || args.disableUser;
    if (username) {
      const user = db.prepare('SELECT id, username FROM AuthUser WHERE username = ?').get(username);
      if (!user) {
        console.error(`no such user: ${username}`);
        return 1;
      }
      const revoked = db.prepare('DELETE FROM AuthSession WHERE userId = ?').run(user.id).changes;
      if (args.disableUser) {
        db.prepare('UPDATE AuthUser SET disabled = 1 WHERE id = ?').run(user.id);
        console.log(`disabled user ${username}`);
      }
      console.log(`revoked ${revoked} session(s) for ${username}`);
      return 0;
    }

    const revoked = db.prepare('DELETE FROM AuthSession').run().changes;
    console.log(`revoked ${revoked} session(s) for every user`);
    return 0;
  } finally {
    db.close();
  }
}

try {
  process.exitCode = main();
} catch (err) {
  console.error(err instanceof Error ? err.message : String(err));
  process.exitCode = 1;
}
