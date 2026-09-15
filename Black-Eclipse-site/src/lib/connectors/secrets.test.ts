import { describe, it, expect, beforeEach, afterAll } from "vitest";
import crypto from "node:crypto";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import {
  encryptSecret,
  decryptSecret,
  isEncryptedPayload,
  resetKeyCache,
  SecretError,
  SECRET_ENV_VAR,
  localKeyPath,
} from "./secrets";

const KEY = crypto.randomBytes(32);

describe("connector secrets", () => {
  it("round-trips a secret", () => {
    const payload = encryptSecret("sk-live-123", KEY);
    expect(isEncryptedPayload(payload)).toBe(true);
    expect(decryptSecret(payload, KEY)).toBe("sk-live-123");
  });

  it("produces different ciphertext each time (random IV)", () => {
    const a = encryptSecret("same", KEY);
    const b = encryptSecret("same", KEY);
    expect(a).not.toBe(b);
    expect(decryptSecret(a, KEY)).toBe(decryptSecret(b, KEY));
  });

  it("stores no plaintext", () => {
    const payload = encryptSecret("super-secret-token", KEY);
    expect(payload).not.toContain("super-secret-token");
  });

  it("fails with the wrong key", () => {
    const payload = encryptSecret("value", KEY);
    expect(() => decryptSecret(payload, crypto.randomBytes(32))).toThrow(SecretError);
  });

  it("fails on tampered payloads", () => {
    const payload = encryptSecret("value", KEY);
    const parts = payload.split(".");
    parts[3] = Buffer.from("tampered").toString("base64");
    expect(() => decryptSecret(parts.join("."), KEY)).toThrow(SecretError);
  });

  it("rejects malformed payloads", () => {
    expect(() => decryptSecret("nope", KEY)).toThrow(SecretError);
    expect(() => decryptSecret("v1.a.b", KEY)).toThrow(SecretError);
  });
});

describe("connector secret key resolution", () => {
  const originalEnv = process.env[SECRET_ENV_VAR];
  const originalVercel = process.env.VERCEL;
  let tmpDir: string;

  beforeEach(() => {
    resetKeyCache();
    tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "be-connector-key-"));
  });

  afterAll(() => {
    if (originalEnv === undefined) delete process.env[SECRET_ENV_VAR];
    else process.env[SECRET_ENV_VAR] = originalEnv;
    if (originalVercel === undefined) delete process.env.VERCEL;
    else process.env.VERCEL = originalVercel;
    resetKeyCache();
  });

  it("uses CONNECTOR_SECRET_KEY when set", async () => {
    delete process.env.VERCEL;
    process.env[SECRET_ENV_VAR] = KEY.toString("base64");
    const { loadKey } = await import("./secrets");
    expect(loadKey(tmpDir).equals(KEY)).toBe(true);
  });

  it("auto-generates a local key file when env is unset", async () => {
    delete process.env.VERCEL;
    delete process.env[SECRET_ENV_VAR];
    const { loadKey } = await import("./secrets");
    const key = loadKey(tmpDir);
    expect(key.byteLength).toBe(32);
    expect(fs.existsSync(localKeyPath(tmpDir))).toBe(true);
    // The file must never be inside version control by default.
    expect(path.basename(localKeyPath(tmpDir))).toBe(".connector-key");
  });

  it("refuses to auto-generate on hosted deployments", async () => {
    process.env.VERCEL = "1";
    delete process.env[SECRET_ENV_VAR];
    const { loadKey } = await import("./secrets");
    expect(() => loadKey(tmpDir)).toThrow(SecretError);
  });
});
