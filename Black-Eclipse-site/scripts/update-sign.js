#!/usr/bin/env node
// ── Sign a release manifest ──────────────────────────────────────────────────
// Run this locally, on the machine that holds the OFFLINE private key, after the
// release tag exists:
//
//   node scripts/update-sign.js --version 0.4.0 --channel stable --commit <sha>
//
// It writes `release/stable.json` (gitignored). Upload that file as an asset on
// the GitHub Release. The app reads it from
// `.../releases/latest/download/stable.json`.
//
// Optional flags:
//   --notes-url <url>       "What's new" link (defaults to the release page)
//   --download-url <url>    archive / source zip link
//   --min-supported <ver>   oldest version you will keep supporting
//   --installer-url <url>   the packaged installer for one platform
//   --installer-file <path> hash + size this local file (sets --installer-sha256)
//   --installer-sha256 <h>  hex SHA-256 of the exact installer bytes
//   --installer-size <n>    byte size (optional; enables an extra check)
//   --installer-platform    key for the asset map (default: this host/arch,
//                          e.g. win32-x64; use it for cross-platform signing)
//   --build-url <url>       the release's prebuilt build archive (zip of .next)
//   --build-file <path>     hash + size this local archive (sets --build-sha256)
//   --build-sha256 <h>      hex SHA-256 of the exact archive bytes
//   --build-size <n>        byte size (optional; enables an extra check)
//   --build-id <id>         BUILD_ID inside the archive (checked before promoting)
//   --build-lock-hash <h>   sha256 of the release's package-lock.json
//   --build-platform        `any` (default) or `<platform>-<arch>`
//   --key <path>            private key (default .black-eclipse/update-keys/...)
//   --out <path>            output file (default release/<channel>.json)
//   --force                 allow re-signing an existing output file

"use strict";

const crypto = require("crypto");
const fs = require("fs");
const path = require("path");
const {
  ENVELOPE_SCHEMA,
  ROOT,
  readConfig,
  loadPublicKey,
  verifyEnvelope,
} = require("./lib/update-verify");

function arg(name, fallback) {
  const i = process.argv.indexOf(`--${name}`);
  if (i !== -1 && process.argv[i + 1]) return process.argv[i + 1];
  return fallback;
}

function fail(message) {
  console.error(`[update-sign] ${message}`);
  process.exit(1);
}

const channel = arg("channel", "stable");
if (!["stable", "beta"].includes(channel)) fail(`unknown channel "${channel}"`);

const cfg = readConfig();
const pkg = JSON.parse(fs.readFileSync(path.join(ROOT, "package.json"), "utf8"));
const version = arg("version", pkg.version);
if (!/^v?\d+\.\d+\.\d+([-+][0-9A-Za-z.-]+)?$/.test(version)) {
  fail(`invalid version "${version}"`);
}
const normalizedVersion = version.replace(/^v/, "");

const commit = arg("commit", "");
if (!/^[0-9a-f]{40}$/.test(commit)) {
  fail("--commit must be the full 40-character git commit SHA of the release tag");
}

const notesUrl =
  arg("notes-url", "") || `https://github.com/${cfg.repository}/releases/tag/v${normalizedVersion}`;
const downloadUrl =
  arg("download-url", "") ||
  `https://github.com/${cfg.repository}/archive/refs/tags/v${normalizedVersion}.zip`;

const payload = {
  schema: 1,
  channel,
  version: normalizedVersion,
  publishedAt: new Date().toISOString(),
  commit,
  notesUrl,
  downloadUrl,
};
const minSupported = arg("min-supported", "");
if (minSupported) payload.minSupported = minSupported.replace(/^v/, "");

// A packaged install has no git tree, so it updates by running a signed
// installer. The signature covers the asset URL and its SHA-256: the runner
// downloads those bytes and refuses to start anything that does not match.
function fileDigest(file) {
  if (!fs.existsSync(file)) fail(`file not found: ${file}`);
  // Hash in bounded chunks: these assets are hundreds of MB and this runs on the
  // same memory-constrained machine that builds them.
  const hash = crypto.createHash("sha256");
  const fd = fs.openSync(file, "r");
  const chunk = Buffer.allocUnsafe(4 * 1024 * 1024);
  try {
    for (;;) {
      const read = fs.readSync(fd, chunk, 0, chunk.length, null);
      if (read <= 0) break;
      hash.update(chunk.subarray(0, read));
    }
  } finally {
    fs.closeSync(fd);
  }
  return { sha256: hash.digest("hex"), size: fs.statSync(file).size };
}

const installerFile = arg("installer-file", "");
let installerSha = arg("installer-sha256", "");
let installerSize = Number(arg("installer-size", "")) || 0;
if (installerFile) {
  const digest = fileDigest(installerFile);
  installerSha = digest.sha256;
  installerSize = digest.size;
}
const installerUrl = arg("installer-url", "");
if (installerUrl || installerSha) {
  if (!installerUrl) fail("--installer-url is required with --installer-sha256/--installer-file");
  if (!/^[0-9a-f]{64}$/i.test(installerSha)) {
    fail("--installer-sha256 must be a 64-character hex SHA-256");
  }
  if (installerSize && (!Number.isInteger(installerSize) || installerSize <= 0)) {
    fail("--installer-size must be a positive byte count");
  }
  const platform = arg("installer-platform", `${process.platform}-${process.arch}`);
  payload.installers = {
    [platform]: {
      url: installerUrl,
      sha256: installerSha.toLowerCase(),
      ...(installerSize ? { size: installerSize } : {}),
    },
  };
}

// The prebuilt build. This is the normal update path for a checkout: the runner
// downloads these bytes, verifies the signed size + sha256, and promotes the
// compiled `.next` — no git checkout, no `npm ci`, no local compile. Signing the
// digest is what makes "the release is the artifact" trustworthy.
const buildFile = arg("build-file", "");
let buildSha = arg("build-sha256", "");
let buildSize = Number(arg("build-size", "")) || 0;
if (buildFile) {
  const digest = fileDigest(buildFile);
  buildSha = digest.sha256;
  buildSize = digest.size;
}
const buildUrl = arg("build-url", "");
if (buildUrl || buildSha) {
  if (!buildUrl) fail("--build-url is required with --build-sha256/--build-file");
  if (!/^[0-9a-f]{64}$/i.test(buildSha)) {
    fail("--build-sha256 must be a 64-character hex SHA-256");
  }
  if (buildSize && (!Number.isInteger(buildSize) || buildSize <= 0)) {
    fail("--build-size must be a positive byte count");
  }
  const platform = arg("build-platform", "any");
  if (platform !== "any" && !/^[a-z0-9]+-[a-z0-9_]+$/i.test(platform)) {
    fail(`--build-platform must be "any" or "<platform>-<arch>" (got "${platform}")`);
  }
  const buildId = arg("build-id", "");
  const buildLockHash = arg("build-lock-hash", "");
  if (buildLockHash && !/^[0-9a-f]{64}$/i.test(buildLockHash)) {
    fail("--build-lock-hash must be a 64-character hex SHA-256");
  }
  payload.builds = {
    [platform]: {
      url: buildUrl,
      sha256: buildSha.toLowerCase(),
      ...(buildSize ? { size: buildSize } : {}),
      ...(buildId ? { buildId } : {}),
      ...(buildLockHash ? { lockHash: buildLockHash.toLowerCase() } : {}),
    },
  };
}

const keyPath = arg("key", path.join(ROOT, ".black-eclipse", "update-keys", "update-signing-key.pem"));
if (!fs.existsSync(keyPath)) fail(`private key not found: ${keyPath}`);

const privateKey = crypto.createPrivateKey(fs.readFileSync(keyPath, "utf8"));
if (privateKey.asymmetricKeyType !== "ed25519") fail("signing key must be Ed25519");

const payloadBytes = Buffer.from(JSON.stringify(payload), "utf8");
const envelope = {
  schema: ENVELOPE_SCHEMA,
  payload: payloadBytes.toString("base64url"),
  signature: crypto.sign(null, payloadBytes, privateKey).toString("base64url"),
};
const envelopeJson = JSON.stringify(envelope, null, 2) + "\n";

// Self-check with the committed public key BEFORE writing anything: a manifest
// the releases page cannot verify is worse than no manifest at all.
try {
  verifyEnvelope(envelopeJson, loadPublicKey(), channel);
} catch (err) {
  fail(`self-verification failed (public key does not match this private key?): ${err.message}`);
}

const outPath = arg("out", path.join(ROOT, "release", `${channel}.json`));
if (fs.existsSync(outPath) && !process.argv.includes("--force")) {
  fail(`${outPath} already exists; pass --force to overwrite`);
}
fs.mkdirSync(path.dirname(outPath), { recursive: true });
fs.writeFileSync(outPath, envelopeJson, "utf8");

console.log(`[update-sign] signed ${channel} v${normalizedVersion} -> ${outPath}`);
console.log(`[update-sign] commit ${commit}`);
if (payload.installers) {
  for (const [platform, asset] of Object.entries(payload.installers)) {
    console.log(`[update-sign] installer ${platform} sha256 ${asset.sha256}`);
  }
}
if (payload.builds) {
  for (const [platform, asset] of Object.entries(payload.builds)) {
    console.log(
      `[update-sign] build ${platform} sha256 ${asset.sha256}` +
        `${asset.buildId ? ` buildId ${asset.buildId}` : ""}`,
    );
  }
}
console.log("[update-sign] next: upload this file as a GitHub Release asset");
