// ── Connector secret storage ────────────────────────────────────────────────
// AES-256-GCM encryption for connector credentials at rest in JDDS.
//
// Key resolution (in order):
//   1. `CONNECTOR_SECRET_KEY` env var (base64, 32 bytes) — REQUIRED on hosted /
//      serverless deployments, where an instance-local file would give every
//      instance a different key.
//   2. A local key file, auto-generated on first use — keeps
//      `npm install && npm run dev` zero-config on single-node installs.
//
// The local key file path is committed to `.gitignore` (both repo root and
// `Black-Eclipse-site/`). Keys are never logged, never returned through an API,
// and never stored in the database.
//
// Zero-config note: this is intentionally NOT built on the `SystemConfig`
// plaintext storage used by `lib/settings.ts` — connector credentials must not
// be plaintext.

import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";

export const SECRET_ENV_VAR = "CONNECTOR_SECRET_KEY";
export const LOCAL_KEY_FILENAME = ".connector-key";

const ALGO = "aes-256-gcm";
const KEY_BYTES = 32;
const IV_BYTES = 12;
const PREFIX = "v1";

export class SecretError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "SecretError";
  }
}

/** True when running on infrastructure where an instance-local file is unsafe. */
export function isHostedDeployment(env: NodeJS.ProcessEnv = process.env): boolean {
  return Boolean(env.VERCEL || env.AWS_LAMBDA_FUNCTION_NAME || env.NETLIFY);
}

function decodeKey(raw: string): Buffer {
  const key = Buffer.from(raw.trim(), "base64");
  if (key.byteLength !== KEY_BYTES) {
    throw new SecretError(`${SECRET_ENV_VAR} must be ${KEY_BYTES} base64-encoded bytes`);
  }
  return key;
}

/** Absolute path of the local key file (project root, gitignored). */
export function localKeyPath(cwd: string = process.cwd()): string {
  return path.join(cwd, LOCAL_KEY_FILENAME);
}

let cachedKey: Buffer | null = null;

/**
 * Return the encryption key, generating a local one if allowed.
 * Throws on hosted deployments when `CONNECTOR_SECRET_KEY` is missing.
 */
export function loadKey(cwd: string = process.cwd()): Buffer {
  if (cachedKey) return cachedKey;

  const envKey = process.env[SECRET_ENV_VAR];
  if (envKey && envKey.trim() !== "") {
    cachedKey = decodeKey(envKey);
    return cachedKey;
  }

  if (isHostedDeployment()) {
    throw new SecretError(
      `Hosted deployments must set ${SECRET_ENV_VAR} (base64, 32 bytes) — instance-local keys are not stable`
    );
  }

  const file = localKeyPath(cwd);
  try {
    if (fs.existsSync(file)) {
      cachedKey = decodeKey(fs.readFileSync(file, "utf8"));
      return cachedKey;
    }
  } catch (err) {
    if (err instanceof SecretError) throw err;
    throw new SecretError(`Could not read local key file at ${file}`);
  }

  const key = crypto.randomBytes(KEY_BYTES);
  // `mode` only applies on POSIX; on Windows the file is ACL-protected by the
  // user profile. Either way it lives outside version control.
  fs.writeFileSync(file, key.toString("base64"), { mode: 0o600, flag: "w" });
  cachedKey = key;
  return cachedKey;
}

/** Test seam: forget the memoized key (used between test cases). */
export function resetKeyCache(): void {
  cachedKey = null;
}

function assertKey(key: Buffer): void {
  if (key.byteLength !== KEY_BYTES) throw new SecretError(`Key must be ${KEY_BYTES} bytes`);
}

/** Encrypt a plaintext secret. Returns a self-describing `v1.iv.tag.ct` payload. */
export function encryptSecret(plaintext: string, key: Buffer = loadKey()): string {
  assertKey(key);
  const iv = crypto.randomBytes(IV_BYTES);
  const cipher = crypto.createCipheriv(ALGO, key, iv);
  const ct = Buffer.concat([cipher.update(plaintext, "utf8"), cipher.final()]);
  const tag = cipher.getAuthTag();
  return [PREFIX, iv.toString("base64"), tag.toString("base64"), ct.toString("base64")].join(".");
}

/** Decrypt a payload produced by {@link encryptSecret}. Throws on tampering. */
export function decryptSecret(payload: string, key: Buffer = loadKey()): string {
  assertKey(key);
  const parts = payload.split(".");
  if (parts.length !== 4 || parts[0] !== PREFIX) throw new SecretError("Malformed secret payload");
  const iv = Buffer.from(parts[1], "base64");
  const tag = Buffer.from(parts[2], "base64");
  const ct = Buffer.from(parts[3], "base64");
  if (iv.byteLength !== IV_BYTES || tag.byteLength !== 16) throw new SecretError("Malformed secret payload");
  try {
    const decipher = crypto.createDecipheriv(ALGO, key, iv);
    decipher.setAuthTag(tag);
    return Buffer.concat([decipher.update(ct), decipher.final()]).toString("utf8");
  } catch {
    throw new SecretError("Could not decrypt secret (wrong key or tampered payload)");
  }
}

/** True when a stored value looks like an encrypted payload. */
export function isEncryptedPayload(value: string): boolean {
  return value.startsWith(`${PREFIX}.`) && value.split(".").length === 4;
}
