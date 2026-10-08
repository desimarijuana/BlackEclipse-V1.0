// SERVER-ONLY: the auth store — users and sessions on the app's own SQLite.
//
// It reuses `better-sqlite3` (already a dependency, and already how the app
// persists runtime state) and Node's built-in `crypto` for password hashing, so
// this feature adds NO new dependency. The database lives under the gitignored
// `.black-eclipse/` runtime tree, never in JDdS and never committed.
//
// Security properties:
//   * Passwords are stored as `scrypt` hashes with a per-user random salt, and
//     verified with a constant-time compare. A plaintext password is never
//     stored, logged, or returned.
//   * Sessions are opaque random ids stored server-side; the cookie carries only
//     the id (signed). A session can be revoked by deleting the row.
//   * No table holds a secret that is echoed back to a client.

import crypto from "node:crypto";
import path from "node:path";
import { mkdirSync } from "node:fs";
import Database from "better-sqlite3";

type DB = InstanceType<typeof Database>;

export interface AuthUser {
  id: string;
  username: string;
  scope: string;
  createdAt: string;
  disabled: boolean;
}

export interface AuthSession {
  id: string;
  userId: string;
  createdAt: string;
  expiresAt: string;
  lastSeenAt: string;
}

const SCRYPT_N = 16384;
const SCRYPT_KEYLEN = 64;

// A constant dummy hash so an unknown username still spends one real scrypt
// (constant-time login: no username oracle). Built once, never a real credential.
const DUMMY_HASH = `scrypt$${SCRYPT_N}$${"0".repeat(32)}$${"0".repeat(SCRYPT_KEYLEN * 2)}`;

function nowIso(): string {
  return new Date().toISOString();
}

function newId(prefix: string): string {
  return `${prefix}_${crypto.randomBytes(16).toString("hex")}`;
}

/** `scrypt` hash as `scrypt$N$salt$hash` — self-describing, versionable. */
export function hashPassword(password: string): string {
  const salt = crypto.randomBytes(16);
  const derived = crypto.scryptSync(password, salt, SCRYPT_KEYLEN, { N: SCRYPT_N });
  return `scrypt$${SCRYPT_N}$${salt.toString("hex")}$${derived.toString("hex")}`;
}

/** Constant-time password verification. Never throws on malformed input. */
export function verifyPassword(password: string, stored: string): boolean {
  try {
    const [scheme, nStr, saltHex, hashHex] = stored.split("$");
    if (scheme !== "scrypt") return false;
    const n = Number(nStr);
    const salt = Buffer.from(saltHex, "hex");
    const expected = Buffer.from(hashHex, "hex");
    const derived = crypto.scryptSync(password, salt, expected.length, { N: n });
    return crypto.timingSafeEqual(derived, expected);
  } catch {
    return false;
  }
}

export class AuthStore {
  private readonly db: DB;

  constructor(dbPath?: string) {
    const file =
      dbPath ??
      process.env.HARNESS_AUTH_DB ??
      path.join(process.cwd(), ".black-eclipse", "auth.db");
    if (file !== ":memory:") {
      mkdirSync(path.dirname(file), { recursive: true });
    }
    this.db = new Database(file);
    this.db.pragma("journal_mode = WAL");
    this._ensureSchema();
  }

  private _ensureSchema(): void {
    this.db.exec(`
      CREATE TABLE IF NOT EXISTS AuthUser (
        id         TEXT PRIMARY KEY,
        username   TEXT NOT NULL UNIQUE,
        password   TEXT NOT NULL,
        scope      TEXT NOT NULL,
        role       TEXT NOT NULL DEFAULT 'operator',
        createdAt  TEXT NOT NULL,
        disabled   INTEGER NOT NULL DEFAULT 0
      );
      CREATE TABLE IF NOT EXISTS AuthSession (
        id          TEXT PRIMARY KEY,
        userId      TEXT NOT NULL,
        tokenHash   TEXT NOT NULL,
        createdAt   TEXT NOT NULL,
        expiresAt   TEXT NOT NULL,
        lastSeenAt  TEXT,
        FOREIGN KEY (userId) REFERENCES AuthUser(id) ON DELETE CASCADE
      );
      CREATE INDEX IF NOT EXISTS idx_auth_session_user ON AuthSession(userId);
    `);
  }

  /** How many users exist (used to decide whether first-run setup is allowed). */
  userCount(): number {
    const row = this.db.prepare("SELECT COUNT(*) AS n FROM AuthUser").get() as { n: number };
    return row.n;
  }

  createUser(username: string, password: string, scope = "local"): AuthUser {
    const id = newId("user");
    this.db
      .prepare(
        "INSERT INTO AuthUser (id, username, password, scope, role, createdAt, disabled) VALUES (?, ?, ?, ?, 'operator', ?, 0)"
      )
      .run(id, username, hashPassword(password), scope, nowIso());
    const user = this.getUserByUsername(username);
    if (!user) throw new Error("user creation failed");
    return user;
  }

  getUserByUsername(username: string): AuthUser | null {
    const row = this.db
      .prepare("SELECT * FROM AuthUser WHERE username = ?")
      .get(username) as Record<string, unknown> | undefined;
    return row ? mapUser(row) : null;
  }

  getUserById(id: string): AuthUser | null {
    const row = this.db
      .prepare("SELECT * FROM AuthUser WHERE id = ?")
      .get(id) as Record<string, unknown> | undefined;
    return row ? mapUser(row) : null;
  }

  /** Verify a username/password pair. Returns the user, or null (never which field failed). */
  authenticate(username: string, password: string): AuthUser | null {
    const row = this.db
      .prepare("SELECT * FROM AuthUser WHERE username = ?")
      .get(username) as Record<string, unknown> | undefined;
    if (!row) {
      // Still spend one scrypt on a fixed dummy hash so a missing user and a
      // wrong password take the same time (no username oracle). The dummy is
      // constant, so the work is real and the comparison is discarded.
      verifyPassword(password, DUMMY_HASH);
      return null;
    }
    if (Number(row.disabled) === 1) return null;
    if (!verifyPassword(password, String(row.password))) return null;
    return mapUser(row);
  }

  /** Create a session; `tokenHash` is the hash of the signed cookie token. */
  createSession(userId: string, tokenHash: string, ttlSeconds: number, id?: string): AuthSession {
    const sessionId = id ?? newId("sess");
    const created = nowIso();
    const expires = new Date(Date.now() + ttlSeconds * 1000).toISOString();
    this.db
      .prepare(
        "INSERT INTO AuthSession (id, userId, tokenHash, createdAt, expiresAt, lastSeenAt) VALUES (?, ?, ?, ?, ?, ?)"
      )
      .run(sessionId, userId, tokenHash, created, expires, created);
    return { id: sessionId, userId, createdAt: created, expiresAt: expires, lastSeenAt: created };
  }

  /** Resolve a non-expired session by id, refreshing `lastSeenAt`. */
  resolveSession(id: string): AuthSession | null {
    const row = this.db
      .prepare("SELECT * FROM AuthSession WHERE id = ?")
      .get(id) as Record<string, unknown> | undefined;
    if (!row) return null;
    if (new Date(String(row.expiresAt)).getTime() < Date.now()) {
      this.deleteSession(id);
      return null;
    }
    const lastSeenAt = nowIso();
    this.db.prepare("UPDATE AuthSession SET lastSeenAt = ? WHERE id = ?").run(lastSeenAt, id);
    return {
      id: String(row.id),
      userId: String(row.userId),
      createdAt: String(row.createdAt),
      expiresAt: String(row.expiresAt),
      lastSeenAt,
    };
  }

  deleteSession(id: string): void {
    this.db.prepare("DELETE FROM AuthSession WHERE id = ?").run(id);
  }

  /** Delete every session for a user (used on password change / disable). */
  deleteUserSessions(userId: string): void {
    this.db.prepare("DELETE FROM AuthSession WHERE userId = ?").run(userId);
  }

  close(): void {
    this.db.close();
  }
}

function mapUser(row: Record<string, unknown>): AuthUser {
  return {
    id: String(row.id),
    username: String(row.username),
    scope: String(row.scope),
    createdAt: String(row.createdAt),
    disabled: Number(row.disabled) === 1,
  };
}

// A process-wide store (the app is single-process). Tests construct their own.
let store: AuthStore | null = null;
export function getAuthStore(): AuthStore {
  if (!store) store = new AuthStore();
  return store;
}
export function setAuthStore(next: AuthStore | null): void {
  store = next;
}
