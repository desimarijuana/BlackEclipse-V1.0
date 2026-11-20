import { describe, expect, it } from "vitest";
import crypto from "node:crypto";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import {
  assertSafeUrl,
  compareVersions,
  installerForPlatform,
  isNewerVersion,
  isSourceCheckout,
  parseVersion,
  verifyEnvelope,
} from "./core";

function keypair() {
  const { publicKey, privateKey } = crypto.generateKeyPairSync("ed25519");
  return {
    publicPem: publicKey.export({ type: "spki", format: "pem" }).toString(),
    privateKey,
  };
}

function envelope(payload: Record<string, unknown>, privateKey: crypto.KeyObject) {
  const bytes = Buffer.from(JSON.stringify(payload), "utf8");
  return JSON.stringify({
    schema: 1,
    payload: bytes.toString("base64url"),
    signature: crypto.sign(null, bytes, privateKey).toString("base64url"),
  });
}

const basePayload = {
  schema: 1,
  channel: "stable",
  version: "0.4.0",
  publishedAt: "2026-11-09T00:00:00.000Z",
  commit: "a".repeat(40),
  notesUrl: "https://github.com/black-eclipse/black-eclipse/releases/tag/v0.4.0",
};

const config = { allowedHosts: ["github.com", "objects.githubusercontent.com"] };

describe("version comparison", () => {
  it("orders core versions", () => {
    expect(compareVersions("0.3.0", "0.4.0")).toBe(-1);
    expect(compareVersions("0.4.0", "0.4.0")).toBe(0);
    expect(compareVersions("1.0.0", "0.99.99")).toBe(1);
  });

  it("ranks a release above its prereleases", () => {
    expect(compareVersions("0.4.0", "0.4.0-beta.1")).toBe(1);
    expect(compareVersions("0.4.0-beta.2", "0.4.0-beta.1")).toBe(1);
    expect(compareVersions("0.4.0-beta.10", "0.4.0-beta.9")).toBe(1);
    expect(compareVersions("0.4.0-alpha", "0.4.0-beta")).toBe(-1);
  });

  it("tolerates a leading v and build metadata", () => {
    expect(compareVersions("v0.4.0", "0.4.0")).toBe(0);
    expect(compareVersions("0.4.0+build.7", "0.4.0")).toBe(0);
  });

  it("refuses to guess at garbage", () => {
    expect(parseVersion("latest")).toBeNull();
    expect(parseVersion("0.4")).toBeNull();
    expect(() => compareVersions("latest", "0.4.0")).toThrow();
  });

  it("only offers genuinely newer versions", () => {
    expect(isNewerVersion("0.4.0", "0.3.0")).toBe(true);
    expect(isNewerVersion("0.3.0", "0.4.0")).toBe(false);
    expect(isNewerVersion("0.4.0", "0.4.0")).toBe(false);
  });
});

describe("installer asset selection", () => {
  const asset = {
    url: "https://github.com/o/r/releases/download/v1/Setup.exe",
    sha256: "a".repeat(64),
    size: 10,
  };

  it("picks the exact platform's signed installer, never another platform's", () => {
    expect(installerForPlatform({ "win32-x64": asset }, "win32-x64")).toEqual(asset);
    expect(installerForPlatform({ "win32-x64": asset }, "darwin-arm64")).toBeNull();
    expect(installerForPlatform(undefined, "win32-x64")).toBeNull();
  });
});

describe("in-app update capability", () => {
  it("is true only for a git checkout", () => {
    const dir = fs.mkdtempSync(path.join(os.tmpdir(), "be-update-"));
    try {
      expect(isSourceCheckout(dir)).toBe(false);
      // Worktrees use a `.git` file, not a directory.
      fs.writeFileSync(path.join(dir, ".git"), "gitdir: elsewhere\n");
      expect(isSourceCheckout(dir)).toBe(true);
    } finally {
      fs.rmSync(dir, { recursive: true, force: true });
    }
  });
});

describe("signed manifest verification", () => {
  it("accepts a correctly signed manifest", () => {
    const { publicPem, privateKey } = keypair();
    const payload = verifyEnvelope(envelope(basePayload, privateKey), publicPem, "stable");
    expect(payload.version).toBe("0.4.0");
    expect(payload.commit).toBe(basePayload.commit);
  });

  it("rejects a manifest signed with another key", () => {
    const { privateKey } = keypair();
    const { publicPem } = keypair();
    expect(() => verifyEnvelope(envelope(basePayload, privateKey), publicPem)).toThrow(
      /signature/i,
    );
  });

  it("rejects a payload changed after signing", () => {
    const { publicPem, privateKey } = keypair();
    const signed = JSON.parse(envelope(basePayload, privateKey));
    const tampered = JSON.parse(
      Buffer.from(signed.payload, "base64url").toString("utf8"),
    );
    tampered.version = "9.9.9";
    signed.payload = Buffer.from(JSON.stringify(tampered), "utf8").toString("base64url");
    expect(() => verifyEnvelope(JSON.stringify(signed), publicPem)).toThrow(/signature/i);
  });

  it("rejects a signature moved to a different payload", () => {
    const { publicPem, privateKey } = keypair();
    const one = JSON.parse(envelope(basePayload, privateKey));
    const two = JSON.parse(envelope({ ...basePayload, version: "9.9.9" }, privateKey));
    two.signature = one.signature;
    expect(() => verifyEnvelope(JSON.stringify(two), publicPem)).toThrow(/signature/i);
  });

  it("rejects a cross-channel replay", () => {
    const { publicPem, privateKey } = keypair();
    expect(() => verifyEnvelope(envelope(basePayload, privateKey), publicPem, "beta")).toThrow(
      /channel/i,
    );
  });

  it("rejects a signed payload with no commit", () => {
    const { publicPem, privateKey } = keypair();
    const payload = { ...basePayload, commit: undefined };
    expect(() => verifyEnvelope(envelope(payload, privateKey), publicPem)).toThrow(/commit/i);
  });

  it("rejects malformed envelopes", () => {
    const { publicPem, privateKey } = keypair();
    expect(() => verifyEnvelope("not json", publicPem)).toThrow(/JSON/i);
    expect(() => verifyEnvelope(JSON.stringify({ schema: 99 }), publicPem)).toThrow(/schema/i);
    expect(() =>
      verifyEnvelope(JSON.stringify({ schema: 1, payload: "x", signature: "y" }), publicPem),
    ).toThrow(/signature/i);
    expect(() => verifyEnvelope(envelope(basePayload, privateKey), "not a key")).toThrow(
      /public key/i,
    );
  });
});

describe("signed installer assets", () => {
  const installer = {
    url: "https://github.com/o/r/releases/download/v0.4.0/BlackEclipse-Setup-0.4.0.exe",
    sha256: "b".repeat(64),
    size: 188_484_501,
  };

  it("accepts a manifest whose installer map is signed", () => {
    const { publicPem, privateKey } = keypair();
    const payload = verifyEnvelope(
      envelope({ ...basePayload, installers: { "win32-x64": installer } }, privateKey),
      publicPem,
    );
    expect(payload.installers?.["win32-x64"]).toEqual(installer);
  });

  it("rejects an installer with a malformed checksum", () => {
    const { publicPem, privateKey } = keypair();
    const installers = { "win32-x64": { ...installer, sha256: "not-a-hash" } };
    expect(() =>
      verifyEnvelope(envelope({ ...basePayload, installers }, privateKey), publicPem),
    ).toThrow(/sha256/i);
  });

  it("rejects an installer map that is not keyed by platform/arch", () => {
    const { publicPem, privateKey } = keypair();
    const installers = { windows: installer };
    expect(() =>
      verifyEnvelope(envelope({ ...basePayload, installers }, privateKey), publicPem),
    ).toThrow(/platform/i);
  });

  it("rejects a non-positive installer size", () => {
    const { publicPem, privateKey } = keypair();
    const installers = { "win32-x64": { ...installer, size: 0 } };
    expect(() =>
      verifyEnvelope(envelope({ ...basePayload, installers }, privateKey), publicPem),
    ).toThrow(/size/i);
  });
});

describe("update URL allowlist", () => {
  it("accepts https URLs on allowlisted hosts", () => {
    expect(assertSafeUrl("https://github.com/o/r/releases", config)).toContain("github.com");
    expect(
      assertSafeUrl("https://objects.githubusercontent.com/a/b", config),
    ).toContain("objects.githubusercontent.com");
  });

  it("rejects http, unknown hosts, and malformed URLs", () => {
    expect(() => assertSafeUrl("http://github.com/o/r", config)).toThrow(/https/i);
    expect(() => assertSafeUrl("https://evil.example/o/r", config)).toThrow(/allowlist/i);
    expect(() => assertSafeUrl("not a url", config)).toThrow(/malformed/i);
  });
});
