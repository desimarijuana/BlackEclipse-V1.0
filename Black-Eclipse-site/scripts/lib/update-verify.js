// ── Signed update manifests ──────────────────────────────────────────────────
// One place that decides whether an "update available" message can be trusted.
// Shared by the CLI (`black update`, scripts/update.js), the release signer
// (scripts/update-sign.js) and mirrored by the server route's TypeScript core
// (src/lib/updates/core.ts). Keep the wire format identical in both:
//
//   { "schema": 1, "payload": "<base64url JSON>", "signature": "<base64url>" }
//
// The signature is Ed25519 over the EXACT bytes of `payload`. Signing the bytes
// (not re-canonicalised JSON) removes every key-ordering/whitespace ambiguity:
// if a byte changes, the signature fails.
//
// SECURITY INVARIANTS — do not relax without a doc update in docs/UPDATES.md:
//   * The public key is baked into the repo. The private key never is, and
//     never lives in CI or on a machine that also runs the app publicly.
//   * Manifest + every URL inside it must be https on an allowlisted host.
//   * A manifest is only "usable" after its signature verifies. Any parse or
//     verify failure is a hard failure — never a partial result.
//   * Nothing fetched here is executed. The CLI separately verifies the git
//     commit SHA before checking anything out.

"use strict";

const crypto = require("crypto");
const fs = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "..", "..");
const CONFIG_PATH = path.join(ROOT, "config", "updates.json");
const PUBLIC_KEY_PATH = path.join(ROOT, "config", "update-signing-key.pub");

const ENVELOPE_SCHEMA = 1;
const CHANNELS = ["stable", "beta"];

class UpdateVerifyError extends Error {
  constructor(code, message) {
    super(message);
    this.name = "UpdateVerifyError";
    this.code = code;
  }
}

function readConfig() {
  let raw;
  try {
    raw = JSON.parse(fs.readFileSync(CONFIG_PATH, "utf8"));
  } catch (err) {
    throw new UpdateVerifyError("config", `Update config missing or unreadable: ${CONFIG_PATH}`);
  }
  if (!raw || typeof raw !== "object") {
    throw new UpdateVerifyError("config", "Update config must be a JSON object.");
  }
  if (typeof raw.repository !== "string" || !/^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(raw.repository)) {
    throw new UpdateVerifyError("config", "updates.json `repository` must be `owner/name`.");
  }
  if (!Array.isArray(raw.allowedHosts) || raw.allowedHosts.length === 0) {
    throw new UpdateVerifyError("config", "updates.json `allowedHosts` must be a non-empty array.");
  }
  const manifestUrls = raw.manifestUrls && typeof raw.manifestUrls === "object" ? raw.manifestUrls : {};
  return {
    schema: Number(raw.schema) || 1,
    repository: raw.repository,
    manifestUrls,
    allowedHosts: raw.allowedHosts.map((h) => String(h).toLowerCase()),
    enabled: raw.enabled !== false,
    published: raw.published !== false,
  };
}

function loadPublicKey(pemOrPath) {
  // Accept an already-loaded KeyObject (scripts/update-sign.js self-check).
  if (pemOrPath && typeof pemOrPath === "object" && pemOrPath.asymmetricKeyType) {
    if (pemOrPath.type !== "public" || pemOrPath.asymmetricKeyType !== "ed25519") {
      throw new UpdateVerifyError("pubkey", "Update signing key must be an Ed25519 public key.");
    }
    return pemOrPath;
  }
  let pem = pemOrPath;
  if (!pem) {
    try {
      pem = fs.readFileSync(PUBLIC_KEY_PATH, "utf8");
    } catch {
      throw new UpdateVerifyError("pubkey", "No update signing public key found.");
    }
  }
  if (typeof pem !== "string" || !pem.includes("BEGIN PUBLIC KEY")) {
    throw new UpdateVerifyError("pubkey", "Update signing public key is malformed.");
  }
  const key = crypto.createPublicKey(pem);
  if (key.asymmetricKeyType !== "ed25519") {
    throw new UpdateVerifyError("pubkey", "Update signing key must be Ed25519.");
  }
  return key;
}

function keyFingerprint(pem) {
  const key = loadPublicKey(pem);
  const der = key.export({ type: "spki", format: "der" });
  return crypto.createHash("sha256").update(der).digest("hex");
}

function parseVersion(value) {
  const m = /^v?(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?(?:\+[0-9A-Za-z.-]+)?$/.exec(
    String(value || "").trim(),
  );
  if (!m) return null;
  return {
    core: [Number(m[1]), Number(m[2]), Number(m[3])],
    pre: m[4] ? m[4].split(".") : null,
  };
}

function comparePrerelease(a, b) {
  if (a === null && b === null) return 0;
  // A release outranks any prerelease of the same core version.
  if (a === null) return 1;
  if (b === null) return -1;
  for (let i = 0; i < Math.max(a.length, b.length); i++) {
    const x = a[i];
    const y = b[i];
    if (x === undefined) return -1;
    if (y === undefined) return 1;
    const xn = /^\d+$/.test(x);
    const yn = /^\d+$/.test(y);
    if (xn && yn) {
      const diff = Number(x) - Number(y);
      if (diff !== 0) return diff < 0 ? -1 : 1;
    } else if (xn !== yn) {
      return xn ? -1 : 1; // numeric identifiers sort before alphanumeric
    } else if (x !== y) {
      return x < y ? -1 : 1;
    }
  }
  return 0;
}

/** -1 | 0 | 1. Throws on an unparseable version — callers must not guess. */
function compareVersions(a, b) {
  const pa = parseVersion(a);
  const pb = parseVersion(b);
  if (!pa) throw new UpdateVerifyError("version", `Invalid version: ${a}`);
  if (!pb) throw new UpdateVerifyError("version", `Invalid version: ${b}`);
  for (let i = 0; i < 3; i++) {
    if (pa.core[i] !== pb.core[i]) return pa.core[i] < pb.core[i] ? -1 : 1;
  }
  return comparePrerelease(pa.pre, pb.pre);
}

function isNewerVersion(candidate, current) {
  return compareVersions(candidate, current) > 0;
}

function assertSafeUrl(value, cfg) {
  let url;
  try {
    url = new URL(String(value));
  } catch {
    throw new UpdateVerifyError("url", `Update URL is malformed: ${value}`);
  }
  if (url.protocol !== "https:") {
    throw new UpdateVerifyError("url", `Update URL must use https: ${url.href}`);
  }
  if (!cfg.allowedHosts.includes(url.hostname.toLowerCase())) {
    throw new UpdateVerifyError("url", `Update URL host is not allowlisted: ${url.hostname}`);
  }
  return url.href;
}

function resolveManifestUrl(channel, cfg) {
  if (!CHANNELS.includes(channel)) {
    throw new UpdateVerifyError("channel", `Unknown update channel: ${channel}`);
  }
  const override = process.env.ECLIPSE_UPDATE_MANIFEST;
  if (override) return assertSafeUrl(override, cfg);
  const repo = process.env.ECLIPSE_UPDATE_REPO || cfg.repository;
  const template = cfg.manifestUrls[channel];
  if (!template) {
    throw new UpdateVerifyError("config", `No manifest URL configured for "${channel}".`);
  }
  return assertSafeUrl(template.replace("{repository}", repo), cfg);
}

const PAYLOAD_STRING_FIELDS = [
  "version",
  "commit",
  "notesUrl",
  "downloadUrl",
  "minSupported",
  "publishedAt",
];

/** Verify an envelope and return its payload. Throws on ANY doubt. */
function verifyEnvelope(envelopeJson, publicKeyPem, expectedChannel) {
  let envelope;
  try {
    envelope = typeof envelopeJson === "string" ? JSON.parse(envelopeJson) : envelopeJson;
  } catch {
    throw new UpdateVerifyError("parse", "Update manifest is not valid JSON.");
  }
  if (!envelope || typeof envelope !== "object") {
    throw new UpdateVerifyError("parse", "Update manifest is not an object.");
  }
  if (Number(envelope.schema) !== ENVELOPE_SCHEMA) {
    throw new UpdateVerifyError("schema", "Unsupported update manifest schema.");
  }
  if (typeof envelope.payload !== "string" || typeof envelope.signature !== "string") {
    throw new UpdateVerifyError("parse", "Update manifest is missing payload or signature.");
  }

  const payloadBytes = Buffer.from(envelope.payload, "base64url");
  const signature = Buffer.from(envelope.signature, "base64url");
  const key = loadPublicKey(publicKeyPem);

  let valid = false;
  try {
    valid = crypto.verify(null, payloadBytes, key, signature);
  } catch {
    valid = false;
  }
  if (!valid) {
    throw new UpdateVerifyError(
      "signature",
      "Update manifest signature is invalid — refusing to offer this update.",
    );
  }

  let payload;
  try {
    payload = JSON.parse(payloadBytes.toString("utf8"));
  } catch {
    throw new UpdateVerifyError("parse", "Signed update payload is not valid JSON.");
  }
  if (!payload || typeof payload !== "object") {
    throw new UpdateVerifyError("parse", "Signed update payload is not an object.");
  }
  if (expectedChannel && payload.channel !== expectedChannel) {
    throw new UpdateVerifyError("channel", "Update manifest channel does not match the request.");
  }
  if (!parseVersion(payload.version)) {
    throw new UpdateVerifyError("version", "Signed update payload has an invalid version.");
  }
  for (const field of PAYLOAD_STRING_FIELDS) {
    if (payload[field] !== undefined && typeof payload[field] !== "string") {
      throw new UpdateVerifyError("parse", `Signed update payload field "${field}" is invalid.`);
    }
  }
  if (typeof payload.commit !== "string" || !/^[0-9a-f]{40}$/.test(payload.commit)) {
    throw new UpdateVerifyError("commit", "Signed update payload has no valid commit SHA.");
  }
  return payload;
}

async function fetchManifest(channel, cfg) {
  const url = resolveManifestUrl(channel, cfg);
  let res;
  try {
    res = await fetch(url, {
      headers: { accept: "application/json", "cache-control": "no-cache" },
      redirect: "follow",
      signal: AbortSignal.timeout(8000),
    });
  } catch {
    throw new UpdateVerifyError("network", "Could not reach the update service.");
  }
  if (!res.ok) {
    throw new UpdateVerifyError("network", `Update service returned HTTP ${res.status}.`);
  }
  const text = await res.text();
  const payload = verifyEnvelope(text, null, channel);
  // Every URL the UI might open or the CLI might use is re-checked against the
  // allowlist, because the signed payload is still remote input.
  const safe = { ...payload };
  for (const field of ["notesUrl", "downloadUrl"]) {
    if (payload[field]) {
      safe[field] = assertSafeUrl(payload[field], cfg);
    }
  }
  return safe;
}

module.exports = {
  ENVELOPE_SCHEMA,
  CHANNELS,
  UpdateVerifyError,
  ROOT,
  CONFIG_PATH,
  PUBLIC_KEY_PATH,
  readConfig,
  loadPublicKey,
  keyFingerprint,
  parseVersion,
  compareVersions,
  isNewerVersion,
  assertSafeUrl,
  resolveManifestUrl,
  verifyEnvelope,
  fetchManifest,
};
