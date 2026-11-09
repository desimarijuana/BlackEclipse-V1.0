// Server-only update checking. Mirrors scripts/lib/update-verify.js exactly —
// that file is the canonical wire format; this one is what the Next.js route
// can import.
//
// Trust model (see docs/UPDATES.md):
//   * The manifest is remote input. It is only trusted after an Ed25519
//     signature verifies against the public key committed at
//     config/update-signing-key.pub.
//   * Manifest URL + every URL inside the payload must be https on an
//     allowlisted host.
//   * Nothing fetched is executed. The CLI verifies the release commit before
//     checking anything out.
//   * Failures are explicit (`ok: false`). A failed check never renders as
//     "up to date".

import crypto from "node:crypto";
import fs from "node:fs";
import path from "node:path";

import {
  isUpdateChannel,
  type UpdateChannel,
  type UpdateManifestPayload,
  type UpdateStatus,
} from "./types";

const ROOT = process.cwd();
const CONFIG_PATH = path.join(ROOT, "config", "updates.json");
const PUBLIC_KEY_PATH = path.join(ROOT, "config", "update-signing-key.pub");

const ENVELOPE_SCHEMA = 1;
const CACHE_TTL_MS = 6 * 60 * 60 * 1000;
const FETCH_TIMEOUT_MS = 8000;

interface UpdateConfig {
  schema: number;
  repository: string;
  manifestUrls: Record<string, string>;
  allowedHosts: string[];
  enabled: boolean;
  /** Maintainer switch: false while the release repo is still private. */
  published: boolean;
}

export class UpdateCheckError extends Error {
  constructor(
    readonly code: string,
    message: string,
  ) {
    super(message);
    this.name = "UpdateCheckError";
  }
}

// ── Pure primitives (exported for tests) ─────────────────────────────────────

export function parseVersion(value: string): { core: number[]; pre: string[] | null } | null {
  const match = /^v?(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?(?:\+[0-9A-Za-z.-]+)?$/.exec(
    String(value || "").trim(),
  );
  if (!match) return null;
  return {
    core: [Number(match[1]), Number(match[2]), Number(match[3])],
    pre: match[4] ? match[4].split(".") : null,
  };
}

function comparePrerelease(a: string[] | null, b: string[] | null): number {
  if (a === null && b === null) return 0;
  if (a === null) return 1;
  if (b === null) return -1;
  for (let i = 0; i < Math.max(a.length, b.length); i++) {
    const x = a[i];
    const y = b[i];
    if (x === undefined) return -1;
    if (y === undefined) return 1;
    const xNumeric = /^\d+$/.test(x);
    const yNumeric = /^\d+$/.test(y);
    if (xNumeric && yNumeric) {
      const diff = Number(x) - Number(y);
      if (diff !== 0) return diff < 0 ? -1 : 1;
    } else if (xNumeric !== yNumeric) {
      return xNumeric ? -1 : 1;
    } else if (x !== y) {
      return x < y ? -1 : 1;
    }
  }
  return 0;
}

/** -1 | 0 | 1. Throws on an unparseable version rather than guessing. */
export function compareVersions(a: string, b: string): number {
  const pa = parseVersion(a);
  const pb = parseVersion(b);
  if (!pa) throw new UpdateCheckError("version", `Invalid version: ${a}`);
  if (!pb) throw new UpdateCheckError("version", `Invalid version: ${b}`);
  for (let i = 0; i < 3; i++) {
    if (pa.core[i] !== pb.core[i]) return pa.core[i] < pb.core[i] ? -1 : 1;
  }
  return comparePrerelease(pa.pre, pb.pre);
}

export function isNewerVersion(candidate: string, current: string): boolean {
  return compareVersions(candidate, current) > 0;
}

export function assertSafeUrl(value: string, config: Pick<UpdateConfig, "allowedHosts">): string {
  let url: URL;
  try {
    url = new URL(String(value));
  } catch {
    throw new UpdateCheckError("url", `Update URL is malformed: ${value}`);
  }
  if (url.protocol !== "https:") {
    throw new UpdateCheckError("url", `Update URL must use https: ${url.href}`);
  }
  if (!config.allowedHosts.includes(url.hostname.toLowerCase())) {
    throw new UpdateCheckError("url", `Update URL host is not allowlisted: ${url.hostname}`);
  }
  return url.href;
}

export function loadPublicKey(input?: string | crypto.KeyObject): crypto.KeyObject {
  if (input && typeof input !== "string") {
    if (input.type !== "public" || input.asymmetricKeyType !== "ed25519") {
      throw new UpdateCheckError("pubkey", "Update signing key must be an Ed25519 public key.");
    }
    return input;
  }
  let material = input;
  if (!material) {
    try {
      material = fs.readFileSync(PUBLIC_KEY_PATH, "utf8");
    } catch {
      throw new UpdateCheckError("pubkey", "No update signing public key found.");
    }
  }
  if (!material.includes("BEGIN PUBLIC KEY")) {
    throw new UpdateCheckError("pubkey", "Update signing public key is malformed.");
  }
  const key = crypto.createPublicKey(material);
  if (key.asymmetricKeyType !== "ed25519") {
    throw new UpdateCheckError("pubkey", "Update signing key must be Ed25519.");
  }
  return key;
}

/** Verify an envelope and return its payload. Throws on ANY doubt. */
export function verifyEnvelope(
  envelopeJson: string,
  publicKeyPem?: string,
  expectedChannel?: UpdateChannel,
): UpdateManifestPayload {
  let envelope: unknown;
  try {
    envelope = JSON.parse(envelopeJson);
  } catch {
    throw new UpdateCheckError("parse", "Update manifest is not valid JSON.");
  }
  if (!envelope || typeof envelope !== "object") {
    throw new UpdateCheckError("parse", "Update manifest is not an object.");
  }
  const env = envelope as Record<string, unknown>;
  if (Number(env.schema) !== ENVELOPE_SCHEMA) {
    throw new UpdateCheckError("schema", "Unsupported update manifest schema.");
  }
  if (typeof env.payload !== "string" || typeof env.signature !== "string") {
    throw new UpdateCheckError("parse", "Update manifest is missing payload or signature.");
  }

  const payloadBytes = Buffer.from(env.payload, "base64url");
  const signature = Buffer.from(env.signature, "base64url");
  const key = loadPublicKey(publicKeyPem);

  let valid = false;
  try {
    valid = crypto.verify(null, payloadBytes, key, signature);
  } catch {
    valid = false;
  }
  if (!valid) {
    throw new UpdateCheckError(
      "signature",
      "Update manifest signature is invalid — refusing to offer this update.",
    );
  }

  let payload: Record<string, unknown>;
  try {
    payload = JSON.parse(payloadBytes.toString("utf8")) as Record<string, unknown>;
  } catch {
    throw new UpdateCheckError("parse", "Signed update payload is not valid JSON.");
  }
  if (!payload || typeof payload !== "object") {
    throw new UpdateCheckError("parse", "Signed update payload is not an object.");
  }
  if (expectedChannel && payload.channel !== expectedChannel) {
    throw new UpdateCheckError("channel", "Update manifest channel does not match the request.");
  }
  if (typeof payload.version !== "string" || !parseVersion(payload.version)) {
    throw new UpdateCheckError("version", "Signed update payload has an invalid version.");
  }
  if (typeof payload.commit !== "string" || !/^[0-9a-f]{40}$/.test(payload.commit)) {
    throw new UpdateCheckError("commit", "Signed update payload has no valid commit SHA.");
  }
  for (const field of ["version", "commit", "notesUrl", "downloadUrl", "minSupported", "publishedAt"]) {
    if (payload[field] !== undefined && typeof payload[field] !== "string") {
      throw new UpdateCheckError("parse", `Signed update payload field "${field}" is invalid.`);
    }
  }
  return payload as unknown as UpdateManifestPayload;
}

export function readUpdateConfig(): UpdateConfig {
  let raw: Record<string, unknown>;
  try {
    raw = JSON.parse(fs.readFileSync(CONFIG_PATH, "utf8")) as Record<string, unknown>;
  } catch {
    throw new UpdateCheckError("config", "Update config is missing or unreadable.");
  }
  const repository = String(raw.repository || "");
  if (!/^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(repository)) {
    throw new UpdateCheckError("config", "Update config repository must be `owner/name`.");
  }
  const allowedHosts = Array.isArray(raw.allowedHosts)
    ? raw.allowedHosts.map((host) => String(host).toLowerCase())
    : [];
  if (allowedHosts.length === 0) {
    throw new UpdateCheckError("config", "Update config allowedHosts must be non-empty.");
  }
  return {
    schema: Number(raw.schema) || 1,
    repository,
    manifestUrls:
      raw.manifestUrls && typeof raw.manifestUrls === "object"
        ? (raw.manifestUrls as Record<string, string>)
        : {},
    allowedHosts,
    enabled: raw.enabled !== false,
    published: raw.published !== false,
  };
}

export function resolveManifestUrl(channel: UpdateChannel, config: UpdateConfig): string {
  const override = process.env.ECLIPSE_UPDATE_MANIFEST;
  if (override) return assertSafeUrl(override, config);
  const repository = process.env.ECLIPSE_UPDATE_REPO || config.repository;
  const template = config.manifestUrls[channel];
  if (!template) throw new UpdateCheckError("config", `No manifest URL configured for "${channel}".`);
  return assertSafeUrl(template.replace("{repository}", repository), config);
}

// ── Fetch + cache ────────────────────────────────────────────────────────────

const cache = new Map<string, { at: number; status: UpdateStatus }>();

async function fetchManifest(channel: UpdateChannel, config: UpdateConfig): Promise<UpdateManifestPayload> {
  const url = resolveManifestUrl(channel, config);
  let response: Response;
  try {
    response = await fetch(url, {
      headers: { accept: "application/json", "cache-control": "no-cache" },
      redirect: "follow",
      signal: AbortSignal.timeout(FETCH_TIMEOUT_MS),
      cache: "no-store",
    });
  } catch {
    throw new UpdateCheckError("network", "Could not reach the update service.");
  }
  if (!response.ok) {
    throw new UpdateCheckError("network", `Update service returned HTTP ${response.status}.`);
  }
  const payload = verifyEnvelope(await response.text(), undefined, channel);

  // The signed payload is still remote input: re-check the URLs the UI will
  // render before returning them.
  const safe: UpdateManifestPayload = { ...payload };
  for (const field of ["notesUrl", "downloadUrl"] as const) {
    if (payload[field]) safe[field] = assertSafeUrl(payload[field], config);
  }
  return safe;
}

function baseStatus(currentVersion: string, channel: UpdateChannel, repository: string): UpdateStatus {
  return {
    ok: false,
    currentVersion,
    channel,
    repository,
    checkedAt: null,
    latestVersion: null,
    available: false,
    mandatory: false,
    notesUrl: null,
    downloadUrl: null,
    publishedAt: null,
    error: null,
  };
}

export async function getUpdateStatus(options: {
  currentVersion: string;
  channel?: string;
  refresh?: boolean;
}): Promise<UpdateStatus> {
  const channel: UpdateChannel = isUpdateChannel(options.channel) ? options.channel : "stable";
  const currentVersion = options.currentVersion;

  let config: UpdateConfig;
  try {
    config = readUpdateConfig();
  } catch (err) {
    return {
      ...baseStatus(currentVersion, channel, "unknown"),
      error: err instanceof Error ? err.message : "Update config is unavailable.",
    };
  }

  const base = baseStatus(currentVersion, channel, config.repository);
  if (!config.published) {
    // Private development. There is no public manifest yet, so do not make a
    // pointless request that can only 404. Honest, not a fake "up to date".
    return { ...base, error: "Updates are not published yet." };
  }
  if (!config.enabled || process.env.ECLIPSE_UPDATES_DISABLED === "1") {
    return { ...base, error: "Update checks are disabled." };
  }

  const key = `${config.repository}:${channel}`;
  const cached = cache.get(key);
  if (!options.refresh && cached && Date.now() - cached.at < CACHE_TTL_MS) {
    return cached.status;
  }

  try {
    const manifest = await fetchManifest(channel, config);
    const available = isNewerVersion(manifest.version, currentVersion);
    const mandatory =
      available &&
      Boolean(manifest.minSupported) &&
      isNewerVersion(manifest.minSupported as string, currentVersion);
    const status: UpdateStatus = {
      ok: true,
      currentVersion,
      channel,
      repository: config.repository,
      checkedAt: new Date().toISOString(),
      latestVersion: manifest.version,
      available,
      mandatory,
      notesUrl: manifest.notesUrl ?? null,
      downloadUrl: manifest.downloadUrl ?? null,
      publishedAt: manifest.publishedAt ?? null,
      error: null,
    };
    cache.set(key, { at: Date.now(), status });
    return status;
  } catch (err) {
    const message =
      err instanceof UpdateCheckError
        ? err.message
        : "Could not check for updates.";
    // Do not cache failures — the next check should really retry.
    return { ...base, error: message };
  }
}

/** Test hook: clears the in-process manifest cache. */
export function clearUpdateCache(): void {
  cache.clear();
}
